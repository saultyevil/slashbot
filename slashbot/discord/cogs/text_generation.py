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
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import disnake
import openai
from disnake.ext import commands
from disnake.utils import escape_markdown
from pyinstrument import Profiler
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from slashbot.config import Bot
from slashbot.discord.custom_cog import SlashbotCog
from slashbot.discord.custom_command import slash_command_with_cooldown
from slashbot.discord.messages import get_attached_images_from_message, send_message_to_channel
from slashbot.discord.responses import is_reply_to_slash_command_response
from slashbot.markov import MARKOV_MODEL, generate_text_from_markov_chain
from slashbot.models import ChannelHistory, Conversation
from slashbot.text_generation import (
    check_if_user_rate_limited,
    generate_text_from_llm,
    get_prompts_at_launch,
    get_token_count,
)
from slashbot.util import create_prompt_dict, read_in_prompt_json

if TYPE_CHECKING:
    from slashbot.discord.custom_bot import SlashbotInterationBot
    from slashbot.discord.types import ApplicationCommandInteraction, Message

MAX_MESSAGE_LENGTH = Bot.get_config("MAX_CHARS")
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


# Set up logger for profiler
profile_logger = logging.getLogger("ProfilerLogger")
profile_logger.handlers.clear()
file_handler = logging.FileHandler("profile.log")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
profile_logger.addHandler(file_handler)
profile_logger.setLevel(logging.INFO)


class TextGeneration(SlashbotCog):
    """AI chat features powered by OpenAI."""

    logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))

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

    @staticmethod
    async def send_fallback_response_to_prompt(message: disnake.Message, *, dont_tag_user: bool = False) -> None:
        """Send a fallback response using the markov chain.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to.
        dont_tag_user: bool
            Whether or not to tag the user or not, optional

        """
        await send_message_to_channel(
            generate_text_from_markov_chain(MARKOV_MODEL, "?random", 1),
            message,
            dont_tag_user=dont_tag_user,  # In a DM, we won't @ the user
        )

    def clear_conversation_history(self, history_id: str | int) -> None:
        """Clear chat history and reset the token counter.

        Parameters
        ----------
        history_id : str | int
            The index to reset in chat history.

        """
        self.conversations[history_id].clear_messages()

    async def get_referenced_message(
        self, original_message: disnake.Message, conversation: Conversation
    ) -> tuple[Conversation, disnake.Message, bool]:
        """Retrieve a list of messages up to a reference point.

        Parameters
        ----------
        original_message : disnake.Message
            The message containing the reference
        conversation : Conversation
            The conversation to retrieve messages from

        Returns
        -------
        Conversation:
            The conversation either at the latest message or put back in time
            to the reference point
        disnake.Message:
            The associated meassage in Discord
        bool:
            A flag to indicate if the conversation was set back

        """
        # we need the message first, to find it in the messages list
        message_reference = original_message.reference
        previous_message = message_reference.cached_message
        if not previous_message:
            try:
                channel = await self.bot.fetch_channel(message_reference.channel_id)
                previous_message = await channel.fetch_message(message_reference.message_id)
            except disnake.NotFound:
                return conversation, original_message, False

        # early exit if we don't want to go back in time to change the
        # conversation -- potentially we can combine with the logic below, but
        # for now this is easier to read and understand
        if not Bot.get_config("AI_CHAT_USE_HISTORIC_REPLIES"):
            return conversation, previous_message, False

        # early exit if the message is not from the bot. we still want the
        # message being referenced so we can, e.g., find images, but we don't
        # want to change the conversation history
        if previous_message.author.id != self.bot.user.id:
            TextGeneration.logger.debug(
                "Message not from the bot: message.author.id = %s, bot.user.id = %s",
                original_message.author.id,
                self.bot.user.id,
            )
            return conversation, previous_message, False

        # the bot will only ever respond to one person, so we can do something
        # vile to remove the first word which is always a mention to the user
        # it is responding to. This is not included in the prompt history.
        message_to_find = previous_message.clean_content.strip()
        if message_to_find.startswith("@"):
            message_to_find = " ".join(previous_message.content.split()[1:]).strip()
        TextGeneration.logger.debug("Message to find: %s", message_to_find)
        conversation.set_conversation_point(message_to_find)

        return conversation, previous_message, True

    async def get_response_from_llm(
        self,
        conversation: Conversation,
        conversation_copy: Conversation,
    ) -> tuple[str, int]:
        """Get the response from the LLM and update the conversation history.

        Parameters
        ----------
        conversation : Conversation
            The conversation to update with the response.
        conversation_copy : Conversation
            The copy of the conversation that the LLM is being asked to generate
            a response for. This is used to avoid a race condition when multiple
            people are talking to the bot at once.

        Returns
        -------
        str
            The response from the LLM.
        int
            The number of tokens in the conversation.

        """
        try:
            bot_response, tokens_used = await generate_text_from_llm(
                Bot.get_config("AI_CHAT_CHAT_MODEL"),
                conversation_copy.get_messages(),
            )
        except openai.BadRequestError as exc:
            if "invalid_image_url" in str(exc):
                conversation_copy.remove_images_from_messages()
                conversation.remove_images_from_messages()
                bot_response, tokens_used = await generate_text_from_llm(
                    Bot.get_config("AI_CHAT_CHAT_MODEL"),
                    conversation_copy.get_messages(),
                )
            else:
                raise

        return bot_response, tokens_used

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
        num_tokens = get_token_count(Bot.get_config("AI_CHAT_CHAT_MODEL"), message)
        self.channel_histories[history_id].add_message(message, escape_markdown(user), num_tokens)

        # keep it under the token limit
        while self.channel_histories[history_id].tokens > Bot.get_config("AI_CHAT_TOKEN_WINDOW_SIZE"):
            self.channel_histories[history_id].remove_message(0)

    async def respond_with_random_llm_message(self, message: disnake.Message) -> None:
        """Respond to a single message with no context.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to.

        """
        try:
            with Path.open(Bot.get_config("AI_CHAT_RANDOM_RESPONSE_PROMPT")) as file_in:
                prompt = json.load(file_in)["prompt"]
        except (OSError, json.JJSONDecodeError):
            TextGeneration.logger.exception(
                "Failed to process random response prompt %s", Bot.get_config("AI_CHAT_RANDOM_RESPONSE_PROMPT")
            )
            return
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message.clean_content},
        ]
        response, _ = await generate_text_from_llm(Bot.get_config("AI_CHAT_CHAT_MODEL"), messages)
        await send_message_to_channel(response, message, dont_tag_user=True)

    async def send_response_to_prompt(self, discord_message: disnake.Message, *, send_to_dm: bool) -> None:
        """Generate a response to a prompt for a conversation of messages.

        A copy of the conversation is made before updating it with the user
        prompt and response to avoid a race condition when multiple people are
        talking to the bot at once.

        Parameters
        ----------
        discord_message : disnake.Message
            The message to generate a response to.
        send_to_dm: bool
            Whether or not the prompt was sent in a direct message, optional

        """
        user_prompt = discord_message.clean_content.replace(f"@{self.bot.user.name}", "")
        conversation = self.conversations[get_history_id(discord_message)]
        conversation_copy = copy.deepcopy(conversation)

        message_images = await get_attached_images_from_message(discord_message)
        if discord_message.reference:
            conversation_copy, referenced_message, changed_reference = await self.get_referenced_message(
                discord_message, conversation_copy
            )
            message_images += await get_attached_images_from_message(referenced_message)
            if not changed_reference:
                user_prompt = 'Previous message: "' + referenced_message.clean_content + '"\n' + user_prompt
        conversation_copy.add_message(user_prompt, "user", images=message_images, shrink_conversation=False)

        try:
            bot_response, tokens_used = await self.get_response_from_llm(
                conversation,
                conversation_copy,
            )
        except openai.APIError:
            TextGeneration.logger.exception(
                "Failed to get response from OpenAI, reverting to markov sentence with no seed word",
            )
            await self.send_fallback_response_to_prompt(discord_message, dont_tag_user=send_to_dm)
            return

        await send_message_to_channel(bot_response, discord_message, dont_tag_user=send_to_dm)
        conversation.add_message(user_prompt, "user", images=message_images)
        conversation.add_message(bot_response, "assistant", tokens=tokens_used)

    async def respond_to_prompt(
        self, history_id: int, discord_message: disnake.Message, *, message_in_dm: bool = False
    ) -> None:
        """Respond to a user's message prompt.

        This method handles user prompts by checking for rate limits,
        sending responses, and logging response time if profiling is enabled.

        Parameters
        ----------
        history_id : int
            The ID used to track the conversation history.
        discord_message : disnake.Message
            The Discord message containing the user's prompt.
        message_in_dm : bool, optional
            Whether the prompt was sent in a direct message (default is False).

        """
        if Bot.get_config("AI_CHAT_PROFILE_RESPONSE_TIME"):
            profiler = Profiler(async_mode="enabled")
            profiler.start()
        async with discord_message.channel.typing():
            rate_limited = check_if_user_rate_limited(self.cooldowns, discord_message.author.id)
            if not rate_limited:
                await self.send_response_to_prompt(discord_message, send_to_dm=message_in_dm)
            else:
                await send_message_to_channel(
                    f"Stop abusing me, {discord_message.author.mention}!",
                    discord_message,
                    dont_tag_user=True,
                )
        if Bot.get_config("AI_CHAT_PROFILE_RESPONSE_TIME"):
            profiler.stop()
            profiler_output = profiler.output_text()
            profile_logger.info("\n%s", profiler_output)
            profile_logger.info(
                "Conversation<%d> is %e MB",
                history_id,
                self.conversations[history_id].get_size_of_conversation() / 1.0e6,
            )

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def listen_to_messages(self, discord_message: disnake.Message) -> None:
        """Listen for mentions which are prompts for the AI.

        Parameters
        ----------
        discord_message : str
            The message to process for mentions.

        """
        history_id = get_history_id(discord_message)

        # don't record bot interactions
        if discord_message.type != disnake.MessageType.application_command:
            await self.update_channel_message_history(
                history_id, discord_message.author.display_name, discord_message.clean_content
            )

        # ignore other bot messages and itself
        if discord_message.author.bot:
            return

        # only respond when mentioned or in DM. mention_string is used for slash
        # commands
        bot_mentioned = self.bot.user in discord_message.mentions
        mention_string = self.bot.user.mention in discord_message.content
        message_in_dm = isinstance(discord_message.channel, disnake.channel.DMChannel)

        # Don't respond to replies, or mentions, which have a reference to a
        # slash command response or interaction UNLESS explicitly mentioned with
        # an @
        if await is_reply_to_slash_command_response(discord_message) and not mention_string:
            return

        # If the bot was mentioned or the message was in a DM, respond
        if bot_mentioned or message_in_dm:
            await self.respond_to_prompt(history_id, discord_message, message_in_dm=message_in_dm)
            return

        # If we get here, then there's a random chance the bot will respond to a
        # "regular" message
        if random.random() <= Bot.get_config("AI_CHAT_RANDOM_RESPONSE_CHANCE"):
            await self.respond_with_random_llm_message(discord_message)

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(
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

        try:
            with Path.open(Bot.get_config("AI_CHAT_SUMMARY_PROMPT")) as file_in:
                summary_prompt = json.load(file_in)["prompt"]
        except OSError:
            TextGeneration.logger.exception(
                "Failed to open summary prompt: %s", Bot.get_config("AI_CHAT_SUMMARY_PROMPT")
            )
            return
        except json.JSONDecodeError:
            TextGeneration.logger.exception(
                "Failed to decode summary prompt: %s", Bot.get_config("AI_CHAT_SUMMARY_PROMPT")
            )
            return

        sent_messages = "Summarise the following conversation between multiple users: " + "\n".join(
            channel_history.get_messages(amount),
        )
        conversation = [
            {
                "role": "system",
                "content": Bot.get_config("AI_CHAT_PROMPT_PREPEND")
                + summary_prompt
                + Bot.get_config("AI_CHAT_PROMPT_APPEND"),
            },
            {"role": "user", "content": sent_messages},
        ]
        TextGeneration.logger.debug("Conversation to summarise: %s", conversation)
        summary_message, token_count = await generate_text_from_llm(Bot.get_config("AI_CHAT_CHAT_MODEL"), conversation)
        # We don't want to add the entire conversation to the history, so for
        # context put <HISTORY REDACTED>
        self.conversations[history_id].add_message(
            Bot.get_config("AI_CHAT_PROMPT_PREPEND")
            + "Summarise the following conversation between multiple users: [CONVERSATION HISTORY REDACTED]"
            + Bot.get_config("AI_CHAT_PROMPT_APPEND"),
            "user",
        )
        self.conversations[history_id].add_message(summary_message, "assistant", tokens=token_count)

        await send_message_to_channel(summary_message, inter, dont_tag_user=True)
        original_message = await inter.edit_original_message(content="...")
        await original_message.delete(delay=3)

    @slash_command_with_cooldown(name="reset_chat_history", description="Reset the AI conversation history")
    async def reset_history(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        history_id = get_history_id(inter)
        self.conversations[history_id].clear_messages()
        await inter.response.send_message("Conversation history cleared.", ephemeral=True)

    @slash_command_with_cooldown(
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
            get_token_count(Bot.get_config("AI_CHAT_CHAT_MODEL"), prompt),
        )
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt[:1800]}...",
            ephemeral=True,
        )

    @slash_command_with_cooldown(
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
        TextGeneration.logger.info("%s set new prompt: %s", inter.author.display_name, prompt)
        history_id = get_history_id(inter)
        self.conversations[history_id].set_prompt(
            prompt,
            get_token_count(Bot.get_config("AI_CHAT_CHAT_MODEL"), prompt),
        )
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt}",
            ephemeral=True,
        )

    @slash_command_with_cooldown(
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

    @slash_command_with_cooldown(
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
        response += f"**Model name**: {Bot.get_config('AI_CHAT_CHAT_MODEL')}\n"
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
    if Bot.get_config("OPENAI_API_KEY") or Bot.get_config("DEEPSEEK_API_KEY"):
        bot.add_cog(TextGeneration(bot))
    else:
        TextGeneration.logger.error("No API key found for OpenAI, unable to load AIChatBot cog")


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
            TextGeneration.logger.exception("Error reading in prompt file %s", event.src_path)


observer = Observer()
observer.schedule(PromptFileWatcher(), "data/prompts", recursive=True)
observer.start()
