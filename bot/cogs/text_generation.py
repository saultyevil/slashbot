"""AI chat and text-to-image features.

The purpose of this cog is to enable AI features in the Discord chat. This
currently implements AI chat/vision using ChatGPT and Claude, as well as
text-to-image generation using Monster API.
"""

from __future__ import annotations

import copy
import datetime
import json
import logging
import random
from collections import defaultdict
from typing import TYPE_CHECKING

import aiofiles
import disnake
from disnake.ext import commands
from disnake.utils import escape_markdown
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from bot.custom_cog import SlashbotCog
from bot.custom_command import cooldown_and_slash_command
from bot.messages import get_attached_images_from_message, send_message_to_channel
from bot.responses import is_reply_to_slash_command_response
from slashbot.config import App
from slashbot.markov import generate_markov_sentence
from slashbot.models import ChannelHistory, Conversation
from slashbot.text_generation import (
    check_if_user_rate_limited,
    generate_text,
    get_prompts_at_launch,
    get_token_count,
)
from slashbot.util import create_prompt_dict, read_in_prompt_json

if TYPE_CHECKING:
    from bot.custom_bot import SlashbotInterationBot
    from bot.types import ApplicationCommandInteraction, Message

LOGGER = logging.getLogger(App.get_config("LOGGER_NAME"))
MAX_MESSAGE_LENGTH = App.get_config("MAX_CHARS")
DEFAULT_PROMPT, AVAILABLE_PROMPTS, DEFAULT_PROMPT_TOKEN_COUNT = get_prompts_at_launch()


def get_history_id(obj: Message | ApplicationCommandInteraction) -> str | int:
    """Determine the history ID to use given the origin of the message.

    Historically, this used to return different values for text channels and
    direct messages.

    Parameters
    ----------
    obj
        The Disnake object to get the history ID from.

    Returns
    -------
    int
        The ID to use for history purposes.

    """
    return obj.channel.id


class TextGeneration(SlashbotCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: SlashbotInterationBot) -> None:
        """Initialize the AIChatbot class.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The instance of the SlashbotInterationBot class.

        """
        super().__init__(bot)
        self.conversations: dict[Conversation] = defaultdict(
            lambda: Conversation(DEFAULT_PROMPT, DEFAULT_PROMPT_TOKEN_COUNT),
        )
        self.channel_histories: dict[ChannelHistory] = defaultdict(lambda: ChannelHistory())
        self.cooldowns = defaultdict(
            lambda: {"count": 0, "last_interaction": datetime.datetime.now(tz=datetime.UTC)},
        )

    def clear_conversation_history(self, history_id: str | int) -> None:
        """Clear chat history and reset the token counter.

        Parameters
        ----------
        history_id : str | int
            The index to reset in chat history.

        """
        self.conversations[history_id].clear_messages()

    async def get_conversation(
        self, discord_message: disnake.Message, conversation: Conversation
    ) -> tuple[list[dict[str, str]], disnake.Message]:
        """Retrieve a list of messages up to a reference point.

        Parameters
        ----------
        discord_message : disnake.Message
            The message containing the reference
        conversation : Conversation
            The conversation to retrieve messages from

        Returns
        -------
        list
            List of messages up to the reference point.

        """
        # we need the message first, to find it in the messages list
        message_reference = discord_message.reference
        previous_message = message_reference.cached_message
        if not previous_message:
            try:
                channel = await self.bot.fetch_channel(message_reference.channel_id)
                previous_message = await channel.fetch_message(message_reference.message_id)
            except disnake.NotFound:
                return conversation.get_conversation(), discord_message

        # the bot will only ever respond to one person, so we can do something
        # vile to remove the first word which is always a mention to the user
        # it is responding to. This is not included in the prompt history.
        message_to_find = " ".join(previous_message.content.split()[1:])
        messages = conversation.get_conversation(last_message=message_to_find, role="assistant")

        return messages, previous_message

    async def update_channel_message_history(self, history_id: int, user: str, message: str) -> None:
        """Record the history of messages in a channel.

        Parameters
        ----------
        history_id : int
            The unique identifier for the channel's history.
        user : str
            The user who sent the message.
        message : str
            The content of the message sent by the user.

        """
        num_tokens = get_token_count(App.get_config("AI_CHAT_CHAT_MODEL"), message)
        self.channel_histories[history_id].add_message(message, escape_markdown(user), num_tokens)

        # keep it under the token limit
        while self.channel_histories[history_id].tokens > App.get_config("AI_CHAT_TOKEN_WINDOW_SIZE"):
            self.channel_histories[history_id].remove_message(0)

    async def respond_to_unprompted_message(self, message: disnake.Message) -> None:
        """Respond to a single message with no context.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to.

        """
        history_id = get_history_id(message)
        messages = [
            {"role": "system", "content": self.conversations[history_id].system_prompt},
            {"role": "user", "content": message.clean_content},
        ]
        response, _ = await generate_text(App.get_config("AI_CHAT_CHAT_MODEL"), messages)
        await send_message_to_channel(response, message, dont_tag_user=True)

    async def get_message_response(self, message: disnake.Message) -> str:
        """Generate a response to a prompt for a conversation of messages.

        Parameters
        ----------
        message : disnake.Message
            The message to generate a response to.

        Returns
        -------
        str
            The generated response.

        """
        history_id = get_history_id(message)
        conversation = self.conversations[history_id]
        message_contents = message.clean_content.replace(f"@{self.bot.user.name}", "")

        # if the response is a reply, let's find that message and present that as the last
        if message.reference:
            conversation, message = await self.get_conversation(message, conversation)

        images = await get_attached_images_from_message(message)
        conversation.add_message(message_contents, "user", images=images)

        try:
            response, tokens_used = await generate_text(
                App.get_config("AI_CHAT_CHAT_MODEL"),
                conversation.get_conversation(),
            )
            conversation.add_message(response, "assistant", tokens=tokens_used)
        except Exception:
            LOGGER.exception("Failed to get response from OpenAI, revert to random markov sentence")
            response = generate_markov_sentence()

        return response

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def listen_to_messages(self, message: disnake.Message) -> None:
        """Listen for mentions which are prompts for the AI.

        Parameters
        ----------
        message : str
            The message to process for mentions.

        """
        history_id = get_history_id(message)

        # don't record bot interactions
        if message.type != disnake.MessageType.application_command:
            await self.update_channel_message_history(history_id, message.author.display_name, message.clean_content)

        # ignore other bot messages and itself
        if message.author.bot:
            return

        # only respond when mentioned or in DM. mention_string is used for slash
        # commands
        bot_mentioned = self.bot.user in message.mentions
        mention_string = self.bot.user.mention in message.content
        message_in_dm = isinstance(message.channel, disnake.channel.DMChannel)

        # Don't respond to replies, or mentions, which have a reference to a
        # slash command response or interaction UNLESS explicitly mentioned with
        # an @
        if await is_reply_to_slash_command_response(message) and not mention_string:
            return

        if bot_mentioned or message_in_dm:
            async with message.channel.typing():
                # Rate limit
                if check_if_user_rate_limited(self.cooldowns, message.author.id):
                    await send_message_to_channel(
                        f"Stop abusing me, {message.author.mention}!",
                        message,
                        dont_tag_user=True,
                    )
                # If not rate limited, then respond in a conversation
                else:
                    ai_response = await self.get_message_response(message)
                    await send_message_to_channel(
                        ai_response,
                        message,
                        dont_tag_user=message_in_dm,
                    )  # In a DM, we won't @ the user
            return  # early return to avoid situation of randomly responding to itself

        # If we get here, then there's a random chance the bot will respond to a
        # "regular" message
        if random.random() <= App.get_config("AI_CHAT_RANDOM_RESPONSE"):
            await self.respond_to_unprompted_message(message)

    # Commands -----------------------------------------------------------------

    @cooldown_and_slash_command(
        name="summarise_chat_history",
        description="Get a summary of the previous conversation",
        dm_permission=False,
    )
    async def generate_chat_summary(
        self,
        inter: disnake.ApplicationCommandInteraction,
        amount: int = commands.Param(
            default=0,
            name="amount",
            description="The last X amount of messages to summarise",
        ),
    ) -> None:
        """Summarize the chat history.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction object representing the user's command interaction.
        amount : int, optional
            The number of previous messages to include in the summary, by default 0.

        Returns
        -------
        Coroutine
            An asynchronous coroutine representing the summary process.

        """
        history_id = get_history_id(inter)
        channel_history = self.channel_histories[history_id]
        if channel_history.tokens == 0:
            await inter.response.send_message("There are no messages to summarise.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)

        message = "Summarise the following conversation between multiple users.\n" + "\n".join(
            channel_history.get_messages(amount),
        )
        conversation = [
            {"role": "system", "content": App.get_config("AI_CHAT_SUMMARY_PROMPT")},
            {"role": "user", "content": message},
        ]
        LOGGER.debug("Conversation to summarise: %s", conversation)
        summary_message, token_count = await generate_text(App.get_config("AI_CHAT_CHAT_MODEL"), conversation)

        self.conversations[history_id].add_message(
            "Summarise the following conversation between multiple users: [CONVERSATION HISTORY REDACTED]",
            "user",
        )
        self.conversations[history_id].add_message(summary_message, "assistant", tokens=token_count)

        await send_message_to_channel(summary_message, inter, dont_tag_user=True)
        await inter.edit_original_message(content="...")

    @cooldown_and_slash_command(name="reset_chat_history", description="Reset the AI conversation history")
    async def reset_history(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        history_id = get_history_id(inter)
        self.conversations[history_id].clear_conversation()
        await inter.response.send_message("Conversation history cleared.", ephemeral=True)

    @cooldown_and_slash_command(
        name="select_chat_prompt",
        description="Set the AI conversation prompt from a list of choices",
    )
    async def select_existing_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        choice: str = commands.Param(
            autocomplete=lambda _, user_input: [choice for choice in AVAILABLE_PROMPTS if user_input in choice],
            description="The choice of prompt to use",
        ),
    ) -> None:
        """Select a system prompt from a set of pre-defined prompts.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        choice : str
            The choice of system prompt

        """
        prompt = AVAILABLE_PROMPTS.get(choice, None)
        if not prompt:
            await inter.response.send_message(
                "An error with the Discord API has occurred and allowed you to pick a prompt which doesn't exist",
                ephemeral=True,
            )
            return

        history_id = get_history_id(inter)
        self.conversations[history_id].set_prompt(
            prompt,
            get_token_count(App.get_config("AI_CHAT_CHAT_MODEL"), prompt),
        )
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt[:1800]}...",
            ephemeral=True,
        )

    @cooldown_and_slash_command(
        name="set_chat_prompt", description="Change the AI conversation prompt to one you write"
    )
    async def set_chat_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to set", max_length=2000),
    ) -> None:
        """Set a new system message for the location were the interaction came from.

        This typically does not override the default system message, and will
        append a new system message.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        prompt : str
            The new system prompt to set.

        """
        LOGGER.info("%s set new prompt: %s", inter.author.display_name, prompt)
        history_id = get_history_id(inter)
        self.conversations[history_id].set_prompt(
            prompt,
            get_token_count(App.get_config("AI_CHAT_CHAT_MODEL"), prompt),
        )
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt}",
            ephemeral=True,
        )

    @cooldown_and_slash_command(
        name="save_chat_prompt", description="Save a AI conversation prompt to the bot's selection"
    )
    async def save_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: str = commands.Param(description="The name to save the prompt as", max_length=64, min_length=3),
        prompt: str = commands.Param(description="The prompt to save"),
    ) -> None:
        """Add a new prompt to the bot's available prompts.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        name : str
            The name of the new prompt.
        prompt : str
            The contents of the prompt.

        """
        await inter.response.defer(ephemeral=True)
        async with aiofiles.open(f"data/prompts/{name}.json", "w", encoding="utf-8") as file_out:
            await file_out.write(json.dumps({"name": name, "prompt": prompt}))

        await inter.edit_original_message(content=f"Your prompt {name} has been saved.")

    @cooldown_and_slash_command(
        name="show_chat_prompt", description="Print information about the current AI conversation"
    )
    async def show_chat_prompt(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Print the system prompt to the screen.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        history_id = get_history_id(inter)

        prompt_name = "Unknown"
        prompt = self.conversations[history_id].system_prompt
        for name, text in AVAILABLE_PROMPTS.items():
            if prompt == text:
                prompt_name = name

        response = ""
        response += f"**Model name**: {App.get_config('AI_CHAT_CHAT_MODEL')}\n"
        response += f"**Token usage**: {self.conversations[history_id].tokens}\n"
        response += f"**Prompt name**: {prompt_name}\n"
        response += f"**Prompt**: {prompt[:1800]}...\n"

        await inter.response.send_message(response, ephemeral=True)


def setup(bot: commands.InteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    if App.get_config("OPENAI_API_KEY"):
        bot.add_cog(TextGeneration(bot))
    else:
        LOGGER.error("No API key found for OpenAI, unable to load AIChatBot cog")


class PromptFileWatcher(FileSystemEventHandler):
    """Event handler for prompt files.

    This event handler is meant to watch the `data/prompts` directory for
    changes.
    """

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle any file system event.

        This method is called when any file system event occurs.
        It updates the `PROMPT_CHOICES` dictionary based on the event type and
        source path.
        """
        global AVAILABLE_PROMPTS  # noqa: PLW0603

        if event.is_directory:
            return

        try:
            if event.event_type in ["created", "modified"] and event.src_path.endswith(".json"):
                prompt = read_in_prompt_json(event.src_path)
                AVAILABLE_PROMPTS[prompt["name"]] = prompt["prompt"]
            if event.event_type == "deleted" and event.src_path.endswith(".json"):
                AVAILABLE_PROMPTS = create_prompt_dict()
        except json.decoder.JSONDecodeError:
            LOGGER.exception("Error reading in prompt file %s", event.src_path)


observer = Observer()
observer.schedule(PromptFileWatcher(), "data/prompts", recursive=True)
observer.start()
