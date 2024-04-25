"""AI chat and text-to-image features.

The purpose of this cog is to enable AI features in the Discord chat. This
currently implements AI chat/vision using ChatGPT and Claude, as well as
text-to-image generation using Monster API.
"""

from __future__ import annotations

import asyncio
import copy
import datetime
import json
import logging
import random
import time
from collections import defaultdict
from typing import TYPE_CHECKING

import aiofiles
import anthropic
import disnake
import requests
import tiktoken
from disnake.ext import commands
from disnake.utils import escape_markdown
from openai import AsyncOpenAI
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.markov import generate_markov_sentence
from slashbot.models import ChannelHistory, Conversation
from slashbot.util import (
    create_prompt_dict,
    get_image_from_url,
    read_in_prompt_json,
    resize_image,
    split_text_into_chunks,
)

if TYPE_CHECKING:
    from slashbot.custom_bot import SlashbotInterationBot

logger = logging.getLogger(App.get_config("LOGGER_NAME"))

COOLDOWN_USER = commands.BucketType.user

# this is all global so you can use it as a choice in interactions
DEFAULT_SYSTEM_PROMPT = read_in_prompt_json("data/prompts/clyde.json")["prompt"]
MAX_MESSAGE_LENGTH = 1920
PROMPT_CHOICES = create_prompt_dict()
DEFAULT_SYSTEM_TOKEN_COUNT = len(DEFAULT_SYSTEM_PROMPT.split())


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
        global PROMPT_CHOICES  # noqa: PLW0603

        if event.is_directory:
            return
        if event.event_type in ["created", "modified"] and event.src_path.endswith(".json"):
            prompt = read_in_prompt_json(event.src_path)
            PROMPT_CHOICES[prompt["name"]] = prompt["prompt"]
        if event.event_type == "deleted" and event.src_path.endswith(".json"):
            PROMPT_CHOICES = create_prompt_dict()


observer = Observer()
observer.schedule(PromptFileWatcher(), "data/prompts", recursive=True)
observer.start()


class AIChatbot(SlashbotCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: SlashbotInterationBot) -> None:
        """Initialize the AIChatbot class.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The instance of the SlashbotInterationBot class.

        """
        super().__init__(bot)
        self.anthropic_client = anthropic.AsyncAnthropic(api_key=App.get_config("ANTHROPIC_API_KEY"))
        self.openai_client = AsyncOpenAI(api_key=App.get_config("OPENAI_API_KEY"))

        self.history = defaultdict(list)
        self.conversations: dict[Conversation] = defaultdict(
            lambda: Conversation(DEFAULT_SYSTEM_PROMPT, DEFAULT_SYSTEM_TOKEN_COUNT),
        )
        self.channel_histories: dict[ChannelHistory] = defaultdict(lambda: ChannelHistory())

        # track user interactions with ai chat
        self.user_cooldowns = defaultdict(
            lambda: {"count": 0, "last_interaction": datetime.datetime.now(tz=datetime.UTC)},
        )

    # Static -------------------------------------------------------------------

    @staticmethod
    def get_history_id(obj: disnake.Message | disnake.ApplicationCommandInteraction) -> str | int:
        """Determine the history ID to use given the origin of the message.

        Historically, this used to return different values for text channels and
        direct messages.

        Parameters
        ----------
        obj
            The recent message.

        Returns
        -------
        int
            The ID to use for history purposes.

        """
        return obj.channel.id

    @staticmethod
    async def send_message_to_channel(
        message: str,
        obj: disnake.Message | disnake.ApplicationCommandInteraction,
        *,
        dont_tag_user: bool = False,
    ) -> None:
        """Send a response to the provided message channel and author.

        Parameters
        ----------
        message : str
            The message to send to chat.
        obj : disnake.Message | disnake.ApplicationCommandInteraction
            The object (channel or interaction) to respond to.
        dont_tag_user : bool
            Boolean to indicate if a user should be tagged or not. Default is
            False, which would tag the user.

        """
        if len(message) > MAX_MESSAGE_LENGTH:
            response_chunks = split_text_into_chunks(message, MAX_MESSAGE_LENGTH)
            for i, response_chunk in enumerate(response_chunks):
                user_mention = obj.author.mention if not dont_tag_user else ""
                await obj.channel.send(f"{user_mention if i == 0 else ''} {response_chunk}")
        else:
            await obj.channel.send(f"{obj.author.mention if not dont_tag_user else ''} {message}")

    @staticmethod
    def get_token_count_for_string(model: str, message: str) -> int:
        """Get the token count for a given message using a specified model.

        Parameters
        ----------
        model : str
            The name of the tokenization model to use.
        message : str
            The message for which the token count needs to be computed.

        Returns
        -------
        int
            The count of tokens in the given message for the specified model.

        """
        if "gpt-" in model:
            return len(tiktoken.encoding_for_model(model).encode(message))

        # fall back to a simple word count
        return len(message.split())

    @staticmethod
    async def is_slash_interaction_highlight(message: disnake.Message) -> bool:
        """Check if a message is in response to a slash command.

        Parameters
        ----------
        message : disnake.Message
            The message to check.

        Returns
        -------
        bool
            If the message is a reply to a slash command, True is returned.
            Otherwise, False is returned.

        """
        if not message.reference:
            return False

        reference = message.reference
        old_message = (
            reference.cached_message if reference.cached_message else await message.channel.fetch_message(message.id)
        )

        # can't see how this can happen (unless no message intents, but then the
        # chat cog won't work at all) but should take into account just in case
        if not old_message:
            logger.error("Message %d not found in internal cache or through channel.fetch_message()", message.id)
            return False

        # if old_message is an interaction response, this will return true
        return isinstance(old_message.interaction, disnake.InteractionReference)

    @staticmethod
    async def get_attached_images_for_message(message: disnake.Message) -> list[str]:
        """Retrieve the URLs for images attached or embedded in a Discord message.

        Parameters
        ----------
        message : disnake.Message
            The Discord message object to extract image URLs from.

        Returns
        -------
        List[str]
            A list of base64-encoded image data strings for the images attached
            or embedded in the message.

        """
        image_urls = [
            attachment.url for attachment in message.attachments if attachment.content_type.startswith("image/")
        ]
        image_urls += [embed.image.proxy_url for embed in message.embeds if embed.image]
        image_urls += [embed.thumbnail.proxy_url for embed in message.embeds if embed.thumbnail]
        num_found = len(image_urls)

        if num_found == 0:
            return []
        images = await get_image_from_url(image_urls)

        return [{"type": image["type"], "image": resize_image(image["image"], image["type"])} for image in images]

    @staticmethod
    def prepare_next_conversation_prompt(
        new_prompt: str,
        images: list[dict[str, str]],
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Prepare the next prompt by adding images and the next prompt requested.

        Parameters
        ----------
        new_prompt : str
            The new text prompt to add
        images : List[Dict[str, str]]
            A list of images to potentially add to the prompt history
        messages : List[Dict[str, str]]
            The list of prompts to add to

        Returns
        -------
        List[Dict[str, str]]
            The updated prompt messages

        """
        # add base64 encoded images
        # We also need a required text prompt -- if one isn't provided (
        # e.g. the message is just an image) then we add a vague message
        if images:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": image["type"], "data": image["image"]},
                        }
                        for image in images
                    ]
                    + [{"type": "text", "text": new_prompt if new_prompt else "describe the image(s)"}],
                },
            )
        else:
            messages.append({"role": "user", "content": new_prompt + App.get_config("AI_CHAT_PROMPT_APPEND")})

        return messages

    async def get_model_response(self, model: str, messages: list) -> tuple[str, int]:
        """Get the response from an LLM API for a given model and list of messages.

        Allowed models are either claude-* from anthropic or chat-gpt from
        openai.

        Parameters
        ----------
        model : str
            The name of the OpenAI model to use.
        messages : list
            List of messages to be sent to the OpenAI model for generating a
            response.

        Returns
        -------
        str
            The generated response message.
        int
            The number of tokens in the conversation

        """
        if "gpt-" in model:
            response = await self.openai_client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=App.get_config("AI_CHAT_MODEL_TEMPERATURE"),
                max_tokens=App.get_config("AI_CHAT_MAX_OUTPUT_TOKENS"),
            )
            message = response.choices[0].message.content
            token_usage = response.usage.total_tokens
        else:
            logger.debug("Using Claude model %s", model)
            logger.debug("Messages: %s", messages)
            response = await self.anthropic_client.messages.create(
                system=messages[0]["content"],
                messages=messages[1:],
                model=model,
                temperature=App.get_config("AI_CHAT_MODEL_TEMPERATURE"),
                max_tokens=App.get_config("AI_CHAT_MAX_OUTPUT_TOKENS"),
            )
            message = response.content[0].text
            token_usage = response.usage.input_tokens + response.usage.output_tokens

        return message, token_usage

    def rate_limit_conversation_requests(self, user_id: int) -> bool:
        """Check if a user is on cooldown or not.

        Parameters
        ----------
        user_id : int
            The id of the user to rate limit

        Returns
        -------
        bool
            Returns True if the user needs to be rate limited

        """
        current_time = datetime.datetime.now(tz=datetime.UTC)
        user_data = self.user_cooldowns[user_id]
        time_difference = (current_time - user_data["last_interaction"]).seconds

        # Check if exceeded rate limit
        if user_data["count"] > App.get_config("AI_CHAT_RATE_LIMIT"):
            # If exceeded rate limit, check if cooldown period has passed
            if time_difference > App.get_config("AI_CHAT_RATE_INTERVAL"):
                # reset count and update last_interaction time
                user_data["count"] = 1
                user_data["last_interaction"] = current_time
                return False
            # still under cooldown
            return True
        # hasn't exceeded rate limit, update count and last_interaction
        user_data["count"] += 1
        user_data["last_interaction"] = current_time

        return False

    def clear_conversation_history(self, history_id: str | int) -> None:
        """Clear chat history and reset the token counter.

        Parameters
        ----------
        history_id : str | int
            The index to reset in chat history.

        """
        self.conversations[history_id].clear_messages()

    async def reduce_conversation_token_size(self, history_id: int | str) -> None:
        """Remove messages from a chat history.

        Parameters
        ----------
        history_id : int | str
            The chat history ID. Usually the guild or user id.

        """
        removed_count = 0
        while self.conversations[history_id].tokens > App.get_config("AI_CHAT_TOKEN_WINDOW_SIZE"):
            message = self.conversations[history_id][1].content
            self.conversations[history_id].remove_message(1)
            self.conversations[history_id].tokens -= self.get_token_count_for_string(
                App.get_config("AI_CHAT_MODEL"),
                message,
            )
            removed_count += 1
        if removed_count > 0:
            logger.debug(
                "Removed %d messages from channel %s due to token limit: %d messages remaining",
                removed_count,
                history_id,
                len(self.channel_histories[history_id]),
            )

    async def add_new_message_to_conversation(
        self,
        history_id: int,
        new_message: str,
        tokens_used: int,
    ) -> None:
        """Update the prompt history for a given history id.

        Parameters
        ----------
        history_id : int
            The key for the channel
        new_message : str
            The bot response to add to the prompt history
        tokens_used : int
            The number of tokens used by the prompt history

        """
        self.conversations[history_id].tokens = tokens_used
        self.conversations[history_id].add_message(new_message, "assistant")
        logger.debug("%d tokens in prompt history for %d", self.conversations[history_id].tokens, history_id)

    async def get_conversation_from_reference_point(
        self,
        message: disnake.Message,
        prompt_history: list,
    ) -> tuple[list[dict[str, str]], disnake.Message]:
        """Retrieve a list of messages up to a reference point.

        Parameters
        ----------
        message : disnake.Message
            The message containing the reference
        prompt_history : list
            List of messages to search through.

        Returns
        -------
        list
            List of messages up to the reference point.

        """
        # we need the message first, to find it in the messages list
        message_reference = message.reference
        previous_message = message_reference.cached_message
        if not previous_message:
            try:
                channel = await self.bot.fetch_channel(message_reference.channel_id)
                previous_message = await channel.fetch_message(message_reference.message_id)
            except disnake.NotFound:
                return prompt_history, message

        # the bot will only ever respond to one person, so we can do something
        # vile to remove the first word which is always a mention to the user
        # it is responding to. This is not included in the prompt history.
        message_to_find = " ".join(previous_message.content.split()[1:])

        # so now we have the message, let's try and find it in the messages
        # list. We munge it into the dict format for the OpenAI API, so we can
        # use the index method
        to_find = {
            "role": "assistant",
            "content": message_to_find,
        }
        try:
            index = prompt_history.index(to_find)
        except ValueError:
            return prompt_history, previous_message

        return prompt_history[: index + 1], previous_message

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
        num_tokens = self.get_token_count_for_string(App.get_config("AI_CHAT_MODEL"), message)
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
        history_id = self.get_history_id(message)
        messages = [
            {"role": "system", "content": self.conversations[history_id].prompt},
            {"role": "user", "content": message.clean_content},
        ]
        response, _ = await self.get_model_response(App.get_config("AI_CHAT_MODEL"), messages)
        await self.send_message_to_channel(response, message, dont_tag_user=True)

    async def respond_to_conversation(self, message: disnake.Message) -> str:
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
        history_id = self.get_history_id(message)
        await self.reduce_conversation_token_size(history_id)
        clean_content = message.clean_content.replace(f"@{self.bot.user.name}", "")

        # we work on a copy, to try and avoid race conditions
        prompt_messages = copy.deepcopy(self.conversations[history_id].conversation)

        # if the response is a reply, let's find that message and present that as the last
        if message.reference:
            prompt_messages, message = await self.get_conversation_from_reference_point(message, prompt_messages)

        images = await self.get_attached_images_for_message(message)
        prompt_messages = self.prepare_next_conversation_prompt(clean_content, images, prompt_messages)
        chat_model = App.get_config("AI_CHAT_VISION_MODEL") if images else App.get_config("AI_CHAT_MODEL")
        try:
            response, tokens_used = await self.get_model_response(
                chat_model,
                prompt_messages,
            )
            # ChatGPT can't cope with the image prompts, so we won't update the
            # conversation history with the image part
            if chat_model == App.get_config("AI_CHAT_VISION_MODEL"):
                prompt_messages[-1] = {
                    "role": "user",
                    "content": prompt_messages[-1]["content"][-1]["text"],
                }
            await self.add_new_message_to_conversation(
                history_id, response, tokens_used
            )
        except Exception:
            logger.exception("`get_api_response` failed.")
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
        history_id = self.get_history_id(message)

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
        if await self.is_slash_interaction_highlight(message) and not mention_string:
            return

        if bot_mentioned or message_in_dm:
            async with message.channel.typing():
                # Rate limit
                if self.rate_limit_conversation_requests(message.author.id):
                    await self.send_message_to_channel(
                        f"Stop abusing me, {message.author.mention}!",
                        message,
                        dont_tag_user=True,
                    )
                # If not rate limited, then respond in a conversation
                else:
                    ai_response = await self.respond_to_conversation(message)
                    await self.send_message_to_channel(
                        ai_response,
                        message,
                        dont_tag_user=message_in_dm,
                    )  # In a DM, we won't @ the user
            return  # early return to avoid situation of randomly responding to itself

        # If we get here, then there's a random chance the bot will respond to a
        # "regular" message
        if random.random() <= App.get_config("AI_CHAT_RANDOM_RESPONSE"):  # noqa: S311
            await self.respond_to_unprompted_message(message)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
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
        history_id = self.get_history_id(inter)
        channel_history = self.channel_histories[history_id]
        if channel_history.tokens == 0:
            await inter.response.send_message("There are no messages to summarise.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)

        message = "Summarise the following conversation between multiple users.\n" + "\n".join(
            channel_history.get_messages(amount),
        )
        conversation = [
            {"role": "system", "content": App.get_config("AI_SUMMARY_PROMPT")},
            {"role": "user", "content": message},
        ]
        summary_message, token_count = await self.get_model_response(App.get_config("AI_CHAT_MODEL"), conversation)

        self.conversations[history_id].add_message(
            "Summarise the following conversation between multiple users: [CONVERSATION HISTORY REDACTED]",
            "user",
        )
        self.conversations[history_id].add_message(summary_message, "assistant", tokens=token_count)

        await self.send_message_to_channel(summary_message, inter, dont_tag_user=True)
        await inter.edit_original_message(content="...")

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="reset_chat_history", description="Reset the AI conversation history")
    async def reset_history(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        history_id = self.get_history_id(inter)
        self.conversations[history_id].clear_conversation()
        await inter.response.send_message("Conversation history cleared.", ephemeral=True)

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="select_chat_prompt",
        description="Set the AI conversation prompt from a list of choices",
    )
    async def select_existing_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        choice: str = commands.Param(
            autocomplete=lambda _, user_input: [choice for choice in PROMPT_CHOICES if user_input in choice],
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
        prompt = PROMPT_CHOICES.get(choice, None)
        if not prompt:
            await inter.response.send_message(
                "An error with the Discord API has occurred and allowed you to pick a prompt which doesn't exist",
                ephemeral=True,
            )
            return

        history_id = self.get_history_id(inter)
        self.conversations[history_id].set_prompt(
            prompt,
            self.get_token_count_for_string(App.get_config("AI_CHAT_MODEL"), prompt),
        )
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt}",
            ephemeral=True,
        )

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_chat_prompt", description="Change the AI conversation prompt to one you write")
    async def set_chat_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to set"),
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
        logger.info("%s set new prompt: %s", inter.author.display_name, prompt)
        history_id = self.get_history_id(inter)
        self.conversations[history_id].set_prompt(
            prompt,
            self.get_token_count_for_string(App.get_config("AI_CHAT_MODEL"), prompt),
        )
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt}",
            ephemeral=True,
        )

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="save_chat_prompt", description="Save a AI conversation prompt to the bot's selection")
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

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="show_chat_prompt", description="Print information about the current AI conversation")
    async def show_chat_prompt(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Print the system prompt to the screen.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        history_id = self.get_history_id(inter)

        prompt_name = "Unknown"
        prompt = self.conversations[history_id].prompt
        for name, text in PROMPT_CHOICES.items():
            if prompt == text:
                prompt_name = name

        response = ""
        response += f"**Model name**: {App.get_config('AI_CHAT_MODEL')}\n"
        response += f"**Token usage**: {self.conversations[history_id].tokens}\n"
        response += f"**Prompt name**: {prompt_name}\n"
        response += f"**Prompt**: {prompt[:1800]}...\n"

        await inter.response.send_message(response, ephemeral=True)


MAX_ELAPSED_TIME = 300
logger = logging.getLogger(App.get_config("LOGGER_NAME"))

HEADER = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": f"Bearer {App.get_config('MONSTER_API_KEY')}",
}


class AIImageGeneration(SlashbotCog):
    """Cog for text to image generation using Monster API."""

    def __init__(self, bot: SlashbotInterationBot) -> None:
        """Initialize the AIImageGeneration cog.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The instance of the SlashbotInterationBot.

        """
        super().__init__(bot)
        self.running_tasks = {}

    @staticmethod
    def check_request_status(process_id: str) -> str:
        """Check the progress of a request.

        Parameters
        ----------
        process_id : str
            The UUID for the process to check.

        Returns
        -------
        str
            If the process has finished, the URL to the finished process is
            returned. Otherwise an empty string is returned.

        """
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {App.get_config('MONSTER_API_KEY')}",
        }
        response = requests.request(
            "GET",
            f"https://api.monsterapi.ai/v1/status/{process_id}",
            headers=headers,
            timeout=5,
        )

        response_data = json.loads(response.text)
        response_status = response_data.get("status", None)

        return response_data["result"]["output"][0] if response_status == "COMPLETED" else ""

    @staticmethod
    def send_image_request(prompt: str, steps: int, aspect_ratio: str) -> str:
        """Send an image request to the API.

        Parameters
        ----------
        prompt : str
            The prompt to generate an image for.
        steps : int
            The number of sampling steps to use.
        aspect_ratio : str
            The aspect ratio of the image.

        Returns
        -------
        str
            The process ID if successful, or an empty string if unsuccessful.

        """
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {App.get_config('MONSTER_API_KEY')}",
        }
        payload = {
            "prompt": prompt,
            "samples": 1,
            "steps": steps,
            "aspect_ratio": aspect_ratio,
        }
        response = requests.request(
            "POST",
            "https://api.monsterapi.ai/v1/generate/txt2img",
            headers=headers,
            json=payload,
            timeout=5,
        )

        response_data = json.loads(response.text)
        return response_data.get("process_id", "")

    @commands.cooldown(
        rate=App.get_config("COOLDOWN_RATE"),
        per=App.get_config("COOLDOWN_STANDARD"),
        type=commands.BucketType.user,
    )
    @commands.slash_command(description="Generate an image from a text prompt", dm_permission=False)
    async def text_to_image(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to generate an image for"),
        steps: int = commands.Param(default=30, ge=30, lt=500, description="The number of sampling steps"),
        aspect_ratio: str = commands.Param(
            default="square",
            choices=["square", "landscape", "portrait"],
            description="The aspect ratio of the image",
        ),
    ) -> None:
        """Generate an image from a text prompt.

        Uses Monster API. The request to the API is not made asynchronously.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        prompt : str, optional
            The prompt to generate an image for.
        steps : int, optional
            The number of sampling steps
        aspect_ratio : str, optional
            The aspect ratio of the image.

        """
        if inter.author.id in self.running_tasks:
            await inter.response.send_message("You already have a request processing.", ephemeral=True)
            return

        next_interaction = inter.followup
        await inter.response.defer(ephemeral=True)

        try:
            process_id = self.send_image_request(prompt, steps, aspect_ratio)
        except requests.exceptions.Timeout:
            inter.edit_original_message(content="The image generation API took too long to respond.")
            return

        if process_id == "":
            await inter.edit_original_message("There was an error when submitting your request.")
            return

        self.running_tasks[inter.author.id] = process_id
        logger.debug("text2image: Request %s for user %s (%d)", process_id, inter.author.display_name, inter.author.id)
        await inter.edit_original_message(content=f"Request submitted: {process_id}")

        start = time.time()
        elapsed_time = 0

        while elapsed_time < MAX_ELAPSED_TIME:
            try:
                url = self.check_request_status(process_id)
            except requests.exceptions.Timeout:
                url = ""
            if url:
                self.running_tasks.pop(inter.author.id)
                break

            await asyncio.sleep(3)
            elapsed_time = time.time() - start

        if elapsed_time >= MAX_ELAPSED_TIME:
            logger.error("text2image: timed out %s", process_id)
            await next_interaction.send(f'Your request ({process_id}) for "{prompt}" timed out.', ephemeral=True)
        else:
            await next_interaction.send(f'{inter.author.display_name}\'s request for "{prompt}" {url}')


def setup(bot: commands.InteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    # chat
    if App.get_config("ANTHROPIC_API_KEY") and App.get_config("OPENAI_API_KEY"):
        bot.add_cog(AIChatbot(bot))
    else:
        logger.error("No API key found for Anthropic and OpenAI, unable to load AIChatBot cog")
    # image generation
    if App.get_config("MONSTER_API_KEY"):
        bot.add_cog(AIImageGeneration(bot))
    else:
        logger.error("No API key found for Monster AI, unable to load AIImageGeneration cog")
