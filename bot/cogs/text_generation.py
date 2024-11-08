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
from disnake.ext import commands
from disnake.utils import escape_markdown
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from bot.custom_cog import SlashbotCog
from bot.custom_command import cooldown_and_slash_command
from bot.messages import get_attached_images_from_message, send_message_to_channel
from bot.responses import is_reply_to_slash_command_response
from slashbot.config import Bot
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

LOGGER = logging.getLogger(Bot.get_config("LOGGER_NAME"))
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

    async def get_referenced_message(
        self, original_message: disnake.Message, conversation: Conversation
    ) -> tuple[Conversation, disnake.Message]:
        """Retrieve a list of messages up to a reference point.

        Parameters
        ----------
        original_message : disnake.Message
            The message containing the reference
        conversation : Conversation
            The conversation to retrieve messages from

        Returns
        -------
        list
            List of messages up to the reference point.

        """
        # we need the message first, to find it in the messages list
        message_reference = original_message.reference
        previous_message = message_reference.cached_message
        if not previous_message:
            try:
                channel = await self.bot.fetch_channel(message_reference.channel_id)
                previous_message = await channel.fetch_message(message_reference.message_id)
            except disnake.NotFound:
                return conversation, original_message

        # early exit if we don't want to go back in time to change the
        # conversation -- potentially we can combine with the logic below, but
        # for now this is easier to read and understand
        if not Bot.get_config("AI_CHAT_USE_HISTORIC_REPLIES"):
            return conversation, previous_message

        # early exit if the message is not from the bot. we still want the
        # message being referenced so we can, e.g., find images, but we don't
        # want to change the conversation history
        if previous_message.author.id != self.bot.user.id:
            LOGGER.debug(
                "Message not from the bot: message.author.id = %s, bot.user.id = %s",
                original_message.author.id,
                self.bot.user.id,
            )
            return conversation, previous_message

        # the bot will only ever respond to one person, so we can do something
        # vile to remove the first word which is always a mention to the user
        # it is responding to. This is not included in the prompt history.
        LOGGER.debug("message to find: %s", previous_message.clean_content)
        message_to_find = previous_message.clean_content
        if message_to_find.startswith("@"):
            message_to_find = " ".join(previous_message.content.split()[1:])
        conversation.set_conversation_point(message_to_find, role="assistant")

        return conversation, previous_message

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

    async def respond_to_unprompted_message(self, message: disnake.Message) -> None:
        """Respond to a single message with no context.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to.

        """
        try:
            with Path.open(Bot.get_config("AI_CHAT_RANDOM_RESPONSE_PROMPT")) as file_in:
                prompt = json.load(file_in)["prompt"]
        except OSError:
            LOGGER.exception(
                "Failed to open random response prompt: %s", Bot.get_config("AI_CHAT_RANDOM_RESPONSE_PROMPT")
            )
            return
        except json.JSONDecodeError:
            LOGGER.exception(
                "Failed to decode random response prompt: %s", Bot.get_config("AI_CHAT_RANDOM_RESPONSE_PROMPT")
            )
            return
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": message.clean_content},
        ]
        response, _ = await generate_text(Bot.get_config("AI_CHAT_CHAT_MODEL"), messages)
        await send_message_to_channel(response, message, dont_tag_user=True)

    async def send_response_to_prompt(self, discord_message: disnake.Message, *, send_to_dm: bool) -> None:
        """Generate a response to a prompt for a conversation of messages.

        Parameters
        ----------
        discord_message : disnake.Message
            The message to generate a response to.
        send_to_dm: bool
            Whether or not the prompt was sent in a direct message, optional

        """
        # Take a copy of the conversation, so we don't modify the original. We
        # need to do this to avoid race conditions when multiple people are
        # talking to the bot at once
        conversation = self.conversations[get_history_id(discord_message)]
        new_conversation = copy.deepcopy(conversation)

        # Get the message contents and images from the *original* message. We
        # do this first to avoid any issues arising from message replies and
        # previous conversation history
        message_contents = discord_message.clean_content.replace(f"@{self.bot.user.name}", "")
        message_images = await get_attached_images_from_message(discord_message)

        # A referenced message is one which has been replied to using the reply
        # button. We'll find that message either because we want to get
        # something from the message (e.g. images) or because we want to go back
        # in time to the context earlier in the conversation
        if discord_message.reference:
            new_conversation, referenced_message = await self.get_referenced_message(discord_message, new_conversation)
            message_images += await get_attached_images_from_message(referenced_message)

        # Update the conversation with the *original* message and the images
        # from the *original* and the *referenced* message
        new_conversation.add_message(message_contents, "user", images=message_images, discord_message=discord_message)

        # Now get the actual response from the OpenAI API and return that. There
        # are a number of exceptions which can be raised, so we'll catch them
        # all and report the actual error instead of falling over
        try:
            response, tokens_used = await generate_text(
                Bot.get_config("AI_CHAT_CHAT_MODEL"),
                new_conversation.get_messages(),
            )
            # todo: if a reference message, we should insert the message in the appropriate place
            conversation.add_message(message_contents, "user", images=message_images, discord_message=discord_message)
        except Exception as exc:
            LOGGER.exception("Failed to get response from OpenAI, reverting to markov sentence with no seed word")
            await send_message_to_channel(
                generate_markov_sentence(),
                discord_message,
                dont_tag_user=send_to_dm,  # In a DM, we won't @ the user
            )
            LOGGER.info("The response is: %s", exc.response)
            with Path.open(
                f"_debug-conversation-{get_history_id(discord_message)}.json", "w", encoding="utf-8"
            ) as file:
                json.dump(conversation.get_messages(), file, indent=4)
            return

        # This is the most helpful way to debug problems with the conversation
        if LOGGER.level == logging.DEBUG:
            with Path.open("_debug-conversation.txt", "w", encoding="utf-8") as file:
                json.dump(conversation.get_messages(), file, indent=4)

        sent_messages = await send_message_to_channel(
            response,
            discord_message,
            dont_tag_user=send_to_dm,  # In a DM, we won't @ the user
        )

        conversation.add_message(response, "assistant", tokens=tokens_used, discord_message=sent_messages)

    async def respond_to_markov_prompt(self, message: disnake.Message) -> bool:
        """Respond to a prompt for a Markov sentence.

        The prompt symbol is '?', followed by the seed word. For example,
        '?donald' will generate a sentence that includes the word 'donald'.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to.

        Returns
        -------
        bool
            Whether or not the message was responded to.

        """
        if not message.content.startswith("?"):
            return False
        if len(message.content) == 1:
            return False
        if message.content.count("?") > 1:
            return False

        seed_word = message.content.split()[0][1:]
        sentence = await self.async_get_markov_sentence(seed_word)
        await message.channel.send(sentence)

        return True

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

        # look for ?seed markov prompts
        markov_response = await self.respond_to_markov_prompt(discord_message)
        if markov_response:
            return

        if discord_message.clean_content.strip() == f"@{self.bot.user.name}":
            await send_message_to_channel("?", discord_message)
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

        if bot_mentioned or message_in_dm:
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
            return  # early return to avoid situation of randomly responding to itself

        # If we get here, then there's a random chance the bot will respond to a
        # "regular" message
        if random.random() <= Bot.get_config("AI_CHAT_RANDOM_RESPONSE_CHANCE"):
            await self.respond_to_unprompted_message(discord_message)

    # Commands -----------------------------------------------------------------

    @cooldown_and_slash_command(
        name="clear_chat_messages",
        description="Delete all messages in AI chat history",
        dm_permission=False,
    )
    async def clear_chat_messages(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Remove the conversation history in Discord.

        This only deletes the messages displayed in Discord, but shouldn't clear
        the conversation history.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interation object representing the user's command interaction.

        """
        await inter.response.send_message(
            f"{inter.user.name} requested for the AI conversation to be cleaned up",
            delete_after=10,
        )
        messages = self.conversations[get_history_id(inter)].get_messages()
        discord_message_ids = [
            item
            for sublist in [message["discord_message_ids"] for message in messages if message["discord_message_ids"]]
            for item in sublist
        ]
        for i in range(0, len(discord_message_ids), 100):
            messages_to_delete = [
                inter.channel.get_partial_message(message_id)
                for message_id in discord_message_ids[i : i + 100]
                if message_id is not None
            ]
            await inter.channel.delete_messages(messages_to_delete)

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
        channel_prompt = self.conversations[history_id].system_prompt
        channel_history = self.channel_histories[history_id]
        if channel_history.tokens == 0:
            await inter.response.send_message("There are no messages to summarise.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)

        try:
            with Path.open(Bot.get_config("AI_CHAT_SUMMARY_PROMPT")) as file_in:
                summary_prompt = json.load(file_in)["prompt"]
        except OSError:
            LOGGER.exception("Failed to open summary prompt: %s", Bot.get_config("AI_CHAT_SUMMARY_PROMPT"))
            return
        except json.JSONDecodeError:
            LOGGER.exception("Failed to decode summary prompt: %s", Bot.get_config("AI_CHAT_SUMMARY_PROMPT"))
            return

        sent_messages = "Summarise the following conversation between multiple users: " + "; ".join(
            channel_history.get_messages(amount),
        )
        conversation = [
            {
                "role": "system",
                "content": Bot.get_config("AI_CHAT_PROMPT_PREPEND")
                + channel_prompt
                + ". "
                + summary_prompt
                + Bot.get_config("AI_CHAT_PROMPT_APPEND"),
            },
            {"role": "user", "content": sent_messages},
        ]
        LOGGER.debug("Conversation to summarise: %s", conversation)
        summary_message, token_count = await generate_text(Bot.get_config("AI_CHAT_CHAT_MODEL"), conversation)

        self.conversations[history_id].add_message(
            "Summarise the following conversation between multiple users: [CONVERSATION HISTORY REDACTED]",
            "user",
            None,
        )

        sent_messages = await send_message_to_channel(summary_message, inter, dont_tag_user=True)
        self.conversations[history_id].add_message(summary_message, "assistant", sent_messages, tokens=token_count)
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
        self.conversations[history_id].clear_messages()
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
            get_token_count(Bot.get_config("AI_CHAT_CHAT_MODEL"), prompt),
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
            get_token_count(Bot.get_config("AI_CHAT_CHAT_MODEL"), prompt),
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
    if Bot.get_config("OPENAI_API_KEY"):
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
