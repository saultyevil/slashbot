#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
The purpose of this cog is to enable the bot to communicate with the OpenAI API
and to generate responses to prompts given.
TODO: need to tokenize messages for Claude somehow
"""

import asyncio
import copy
import datetime
import json
import logging
import random
import time
from collections import defaultdict
from types import coroutine
from typing import Dict, List, Tuple

import anthropic
import disnake
import requests
import tiktoken
from disnake.ext import commands
from openai import AsyncOpenAI
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from slashbot.config import App
from slashbot.custom_bot import SlashbotInterationBot
from slashbot.custom_cog import SlashbotCog
from slashbot.markov import generate_markov_sentence
from slashbot.util import (
    create_prompt_dict,
    get_image_from_url,
    read_in_prompt_json,
    resize_image,
    split_text_into_chunks,
)

logger = logging.getLogger(App.get_config("LOGGER_NAME"))

COOLDOWN_USER = commands.BucketType.user

# this is all global so you can use it as a choice in interactions
DEFAULT_SYSTEM_PROMPT = read_in_prompt_json("data/prompts/clyde.json")["prompt"]
MAX_MESSAGE_LENGTH = 1920
PROMPT_CHOICES = create_prompt_dict()
DEFAULT_SYSTEM_TOKEN_COUNT = len(DEFAULT_SYSTEM_PROMPT.split())


class PromptFileWatcher(FileSystemEventHandler):
    """FileSystemEventHandler specifically for JSON files in the data/prompts
    directory."""

    def on_any_event(self, event):
        global PROMPT_CHOICES  # pylint: disable=W0603

        if event.is_directory:
            return
        if event.event_type in ["created", "modified"]:
            if event.src_path.endswith(".json"):
                prompt = read_in_prompt_json(event.src_path)
                PROMPT_CHOICES[prompt["name"]] = prompt["prompt"]
        if event.event_type == "deleted":
            if event.src_path.endswith(".json"):
                PROMPT_CHOICES = create_prompt_dict()


observer = Observer()
observer.schedule(PromptFileWatcher(), "data/prompts", recursive=True)
observer.start()


class AIChatbot(SlashbotCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: SlashbotInterationBot):
        super().__init__(bot)
        self.claude = anthropic.AsyncAnthropic(api_key=App.get_config("ANTHROPIC_API_KEY"))
        self.chat_gpt = AsyncOpenAI(api_key=App.get_config("OPENAI_API_KEY"))

        # todo: this data structure should be a class
        self.channel_histories = defaultdict(
            lambda: {
                "history": {"tokens": 0, "messages": [], "last_summary": ""},
                "prompts": {
                    "tokens": DEFAULT_SYSTEM_TOKEN_COUNT,
                    "system": DEFAULT_SYSTEM_PROMPT,
                    "messages": [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}],
                },
            }
        )

        # track user interactions with ai chat
        self.user_cooldowns = defaultdict(lambda: {"count": 0, "last_interaction": datetime.datetime.now()})

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
    async def send_response_to_channel(
        response: str, obj: disnake.Message | disnake.ApplicationCommandInteraction, dont_tag_user: bool
    ):
        """Send a response to the provided message channel and author.

        Parameters
        ----------
        response : str
            The response to send to chat.
        message : disnake.Message | disnake.ApplicationCommandInteraction
            The message to respond to.
        in_dm : bool
            Boolean to indicate if DM channel.
        """
        if len(response) > MAX_MESSAGE_LENGTH:
            response_chunks = split_text_into_chunks(response, MAX_MESSAGE_LENGTH)
            for i, response_chunk in enumerate(response_chunks):
                user_mention = obj.author.mention if not dont_tag_user else ""
                await obj.channel.send(f"{user_mention if i == 0 else ''} {response_chunk}")
        else:
            await obj.channel.send(f"{obj.author.mention if not dont_tag_user else ''} {response}")

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
        if "claude-3" not in model:
            return len(tiktoken.encoding_for_model(model).encode(message))
        else:
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
    async def get_attached_images_for_message(model: str, message: disnake.Message) -> List[str]:
        """Retrieve the URLs for images attached or embedded in a Discord
        message.

        If the current LLM model is OpenAI (e.g. gpt-3.5-turbo), then this will
        return an empty string as it does not support vision.

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
        if "claude-3" not in model:  # only claude 3 has vision capability
            return []

        image_urls = []
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type.startswith("image/"):
                    image_urls.append(attachment.url)
        if message.embeds:
            for embed in message.embeds:
                if embed.image:  # for one image
                    image_urls.append(embed.image.proxy_url)
                elif embed.thumbnail:  # for multiple images
                    image_urls.append(embed.thumbnail.proxy_url)
        num_found = len(image_urls)
        if num_found == 0:
            return []

        images = await get_image_from_url(image_urls)

        return [{"type": image["type"], "image": resize_image(image["image"], image["type"])} for image in images]

    @staticmethod
    def prepare_next_prompt(
        new_prompt: str, images: List[Dict[str, str]], messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """Prepare the next prompt by adding images and the next prompt
        requested.

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
        if images:
            # add base64 encoded images
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": image["type"], "data": image["image"]},
                        }
                        for image in images
                    ],
                }
            )
            # We also need a required text prompt -- if one isn't provided (
            # e.g. the message is just an image) then we add a vague message
            messages += [{"type": "text", "text": new_prompt if new_prompt else "describe the image(s)"}]
        else:
            messages.append({"role": "user", "content": new_prompt})

        return messages

    async def get_api_response(self, model: str, messages: list) -> str:
        """Get the response from an LLM API for a given model and list of
        messages.

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
        """
        if "claude-3" not in model:
            response = await self.chat_gpt.chat.completions.create(
                messages=messages,
                model=model,
                temperature=App.get_config("AI_CHAT_MODEL_TEMPERATURE"),
                max_tokens=App.get_config("AI_CHAT_MAX_OUTPUT_TOKENS"),
            )
            message = response.choices[0].message.content
            token_usage = response.usage.total_tokens
        else:
            response = await self.claude.messages.create(
                system=messages[0]["content"],
                messages=messages[1:],
                model=model,
                temperature=App.get_config("AI_CHAT_MODEL_TEMPERATURE"),
                max_tokens=App.get_config("AI_CHAT_MAX_OUTPUT_TOKENS"),
            )
            message = response.content[0].text
            token_usage = response.usage.input_tokens + response.usage.output_tokens

        return message, token_usage

    def reset_message_history(self, history_id: str | int):
        """Clear chat history and reset the token counter.

        Parameters
        ----------
        history_id : str | int
            The index to reset in chat history.
        """
        model = App.get_config("AI_CHAT_MODEL")
        current_prompt = self.channel_histories[history_id]["prompts"]["messages"][0]
        self.channel_histories[history_id]["prompts"]["tokens"] = self.get_token_count_for_string(
            model, current_prompt["content"]
        )

        self.channel_histories[history_id]["prompts"]["messages"] = [current_prompt]

    async def get_messages_from_reference_point(
        self, message: disnake.Message, prompt_history: list
    ) -> Tuple[List[dict[str, str]], disnake.Message]:
        """Retrieve a list of messages up to a reference point.

        Parameters
        ----------
        message : disnake.Message
            The message containing the reference
        messages : list
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

    def rate_limit_chat_response(self, user_id: int) -> bool:
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
        current_time = datetime.datetime.now()
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
            else:
                # still under cooldown
                return True
        else:
            # hasn't exceeded rate limit, update count and last_interaction
            user_data["count"] += 1
            user_data["last_interaction"] = current_time
            return False

    async def get_chat_prompt_response(self, message: disnake.Message) -> str:
        """Generate a response based on the given message.

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
        clean_content = message.clean_content.replace(f"@{self.bot.user.name}", "")

        # we work on a copy, to try and avoid race conditions
        prompt_messages = copy.deepcopy(self.channel_histories[history_id]["prompts"]["messages"])

        # if the response is a reply, let's find that message and present that as the last
        if message.reference:
            prompt_messages, message = await self.get_messages_from_reference_point(message, prompt_messages)

        images = await self.get_attached_images_for_message(App.get_config("AI_CHAT_MODEL"), message)
        prompt_messages = self.prepare_next_prompt(clean_content, images, prompt_messages)

        try:
            response, tokens_used = await self.get_api_response(App.get_config("AI_CHAT_MODEL"), prompt_messages)
            self.channel_histories[history_id]["prompts"]["messages"] += [
                {"role": "user", "content": clean_content},
                {"role": "assistant", "content": response},
            ]
            self.channel_histories[history_id]["prompts"]["tokens"] = tokens_used
        except Exception as e:
            logger.exception("`get_chat_prompt_response` failed with %s", e)
            response = generate_markov_sentence()

        return response

    async def reduce_prompt_history(self, history_id: int | str) -> None:
        """Remove messages from a chat history.

        Removes a fraction of the messages from the chat history if the number
        of tokens exceeds a threshold controlled by
        `self.model.max_history_tokens`.

        Parameters
        ----------
        history_id : int | str
            The chat history ID. Usually the guild or user id.
        """
        removed_count = 0
        while self.channel_histories[history_id]["prompts"]["tokens"] > App.get_config("AI_CHAT_TOKEN_WINDOW_SIZE"):
            message = self.channel_histories[history_id]["prompts"]["messages"][1]
            self.channel_histories[history_id]["prompts"]["tokens"] -= self.get_token_count_for_string(
                App.get_config("AI_CHAT_MODEL"), message
            )
            self.channel_histories[history_id]["prompts"]["messages"].pop(1)
            removed_count += 1
        logger.debug(
            "%d messages removed from channel %s due to token limit. There are now %d messages.",
            removed_count,
            history_id,
            len(self.channel_histories[history_id]["prompts"]["messages"][1:]),
        )

    async def record_channel_history(self, history_id: int, user: str, message: str) -> None:
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
        message = (
            f"{disnake.utils.escape_markdown(user) if user != self.bot.user.display_name else 'Assistant'}: {message}"
        )
        num_tokens = self.get_token_count_for_string(App.get_config("AI_CHAT_MODEL"), message)
        self.channel_histories[history_id]["history"]["messages"].append({"tokens": num_tokens, "message": message})
        # increment number of tokens of latest message
        self.channel_histories[history_id]["history"]["tokens"] += num_tokens

        # remove last summary if set
        summary_removed = False
        for i, message in enumerate(self.channel_histories[history_id]["history"]["messages"]):
            if message["message"] == self.channel_histories[history_id]["history"]["last_summary"]:
                self.channel_histories[history_id]["history"]["tokens"] -= message["tokens"]
                self.channel_histories[history_id]["history"]["messages"].pop(i)
                summary_removed = True
        if summary_removed:
            self.channel_histories[history_id]["history"]["last_summary"] = ""

        logger.debug("%d history: %s", history_id, self.channel_histories[history_id]["history"])

        # if over the limit, remove messages until under the limit
        while self.channel_histories[history_id]["history"]["tokens"] > App.get_config("AI_CHAT_TOKEN_WINDOW_SIZE"):
            self.channel_histories[history_id]["history"]["tokens"] -= self.channel_histories[history_id]["history"][
                "messages"
            ][0]["tokens"]
            self.channel_histories[history_id]["history"]["messages"].pop(0)

    async def respond_to_message(self, message: disnake.Message):
        """Respond to a message.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to.
        """
        history_id = self.get_history_id(message)
        messages = [
            {"role": "system", "content": self.channel_histories[history_id]["prompts"]["system"]},
            {"role": "user", "content": message.clean_content},
        ]
        response, _ = await self.get_api_response(App.get_config("AI_CHAT_MODEL"), messages)
        await self.send_response_to_channel(response, message, True)

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def listen_to_channel(self, message: disnake.Message) -> None:
        """Listen for mentions which are prompts for the AI.

        Parameters
        ----------
        message : str
            The message to process for mentions.
        """
        history_id = self.get_history_id(message)

        # don't record bot interactions
        if message.type != disnake.MessageType.application_command:
            await self.record_channel_history(history_id, message.author.display_name, message.clean_content)

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
                if self.rate_limit_chat_response(message.author.id):
                    await self.send_response_to_channel(f"Stop abusing me, {message.author.mention}!", message, True)
                else:
                    ai_response = await self.get_chat_prompt_response(message)
                    await self.send_response_to_channel(
                        ai_response, message, message_in_dm
                    )  # In a DM, we won't @ the user
            return  # early return to avoid situation of randomly responding to itself

        # If we get here, then there's a random chance the bot will respond to a
        # "regular" message
        if random.random() <= App.get_config("AI_CHAT_RANDOM_RESPONSE"):
            await self.respond_to_message(message)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="summarise_chat_history", description="Get a summary of the previous conversation", dm_permission=False
    )
    async def summarise_chat_history(
        self,
        inter: disnake.ApplicationCommandInteraction,
        amount: int = commands.Param(
            default=0, name="amount", description="The last X amount of messages to summarise"
        ),
    ) -> coroutine:
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
        if self.channel_histories[history_id]["history"]["tokens"] == 0:
            return await inter.response.send_message("There are no messages to summarise.", ephemeral=True)

        await inter.response.defer(ephemeral=True)

        messages = [e["message"] for e in self.channel_histories[history_id]["history"]["messages"][-amount:]]
        user_prompt = "Summarise the following conversation between multiple users.\n\n" + "\n".join(messages)
        summary_prompt = [
            {"role": "system", "content": App.get_config("AI_SUMMARY_PROMPT")},
            {"role": "user", "content": user_prompt},
        ]
        summary_message, token_count = await self.get_api_response(App.get_config("AI_CHAT_MODEL"), summary_prompt)

        self.channel_histories[history_id]["prompts"]["messages"] += [
            {
                "role": "user",
                "content": "Summarise the the following conversation between multiple users: [CONVERSATION HISTORY REDACTED]",
            },
            {"role": "assistant", "content": summary_message},
        ]
        self.channel_histories[history_id]["prompts"]["tokens"] += token_count
        self.channel_histories[history_id]["history"]["last_summary"] = f"{self.bot.user.name}: {summary_message}"

        await self.send_response_to_channel(summary_message, inter, True)
        await inter.edit_original_message(content="...")

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="reset_chat_history", description="Reset the AI conversation history")
    async def reset_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        self.reset_message_history(self.get_history_id(inter))
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{DEFAULT_SYSTEM_PROMPT}",
            ephemeral=True,
        )

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="select_chat_prompt", description="Set the AI conversation prompt from a list of choices"
    )
    async def select_existing_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        choice: str = commands.Param(
            autocomplete=lambda _inter, user_input: [
                choice for choice in PROMPT_CHOICES.keys() if user_input in choice
            ],
            description="The choice of prompt to use",
        ),
    ) -> coroutine:
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
            return await inter.response.send_message(
                "An error with the Discord API has occurred and allowed you to pick a prompt which doesn't exist",
                ephemeral=True,
            )

        history_id = self.get_history_id(inter)
        self.channel_histories[history_id]["prompts"]["system"] = prompt
        self.channel_histories[history_id]["prompts"]["messages"] = [{"role": "system", "content": prompt}]
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt[:1928]}",
            ephemeral=True,
        )
        # calculate token count after responding to interaction, as it may take a little time
        self.channel_histories[history_id]["prompts"]["tokens"] = self.get_token_count_for_string(
            App.get_config("AI_CHAT_MODEL"), prompt
        )

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_chat_prompt", description="Change the AI conversation prompt to one you write")
    async def set_chat_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        new_prompt: str = commands.Param(description="The prompt to set"),
    ) -> coroutine:
        """Set a new system message for the location were the interaction came
        from.

        This typically does not override the default system message, and will
        append a new system message.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        message : str
            The new system prompt to set.
        """
        history_id = self.get_history_id(inter)
        self.channel_histories[history_id]["prompts"]["system"] = new_prompt
        self.channel_histories[history_id]["prompts"]["messages"] = [{"role": "system", "content": new_prompt}]
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{new_prompt}",
            ephemeral=True,
        )
        self.channel_histories[history_id]["prompts"]["tokens"] = self.get_token_count_for_string(
            App.get_config("AI_CHAT_MODEL"), new_prompt
        )
        logger.info("%s set the new prompt: %s", inter.author.display_name, new_prompt)

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="save_chat_prompt", description="Save a AI conversation prompt to the bot's selection")
    async def save_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: str = commands.Param(description="The name to save the prompt as", max_length=64, min_length=3),
        prompt: str = commands.Param(description="The prompt to save"),
    ):
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
        with open(f"data/prompts/{name}.json", "w", encoding="utf-8") as file_out:
            json.dump(
                {"name": name, "prompt": prompt},
                file_out,
            )
        await inter.edit_original_message(content=f"Your prompt {name} has been saved.")

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="show_chat_prompt", description="Print information about the current AI conversation")
    async def show_chat_prompt(self, inter: disnake.ApplicationCommandInteraction):
        """Print the system prompt to the screen.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        await inter.response.defer(ephemeral=True)
        history_id = self.get_history_id(inter)

        prompt_name = "Unknown"
        prompt = self.channel_histories[history_id]["prompts"]["system"]
        for name, text in PROMPT_CHOICES.items():
            if prompt == text:
                prompt_name = name

        response = ""
        response += f"**Model name**: {App.get_config('AI_CHAT_MODEL')}\n"
        response += f"**Token usage**: {self.channel_histories[history_id]['prompts']['tokens']}\n"
        response += f"**Prompt name**: {prompt_name}\n"
        response += f"**Prompt**: {prompt[:1024] if prompt else '???'}\n"

        await inter.edit_original_message(content=response)


MAX_ELAPSED_TIME = 300
logger = logging.getLogger(App.get_config("LOGGER_NAME"))

HEADER = {
    "accept": "application/json",
    "content-type": "application/json",
    "authorization": f"Bearer {App.get_config('MONSTER_API_KEY')}",
}


class AIImageGeneration(SlashbotCog):
    """Cog for text to image generation using Monster API.

    Possibly in the future, we'll use OpenAI instead.
    """

    def __init__(self, bot: SlashbotInterationBot):
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
            "GET", f"https://api.monsterapi.ai/v1/status/{process_id}", headers=headers, timeout=5
        )

        response_data = json.loads(response.text)
        response_status = response_data.get("status", None)

        if response_status == "COMPLETED":
            url = response_data["result"]["output"][0]
        else:
            url = ""

        return url

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
        process_id = response_data.get("process_id", "")

        return process_id

    @commands.cooldown(
        rate=App.get_config("COOLDOWN_RATE"), per=App.get_config("COOLDOWN_STANDARD"), type=commands.BucketType.user
    )
    @commands.slash_command(description="Generate an image from a text prompt", dm_permission=False)
    async def text_to_image(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to generate an image for"),
        steps: int = commands.Param(default=30, ge=30, lt=500, description="The number of sampling steps"),
        aspect_ratio: str = commands.Param(
            default="square", choices=["square", "landscape", "portrait"], description="The aspect ratio of the image"
        ),
    ):
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
            return await inter.response.send_message("You already have a request processing.", ephemeral=True)

        next_interaction = inter.followup
        await inter.response.defer(ephemeral=True)

        try:
            process_id = self.send_image_request(prompt, steps, aspect_ratio)
        except requests.exceptions.Timeout:
            return inter.edit_original_message(content="The image generation API took too long to respond.")

        if process_id == "":
            return await inter.edit_original_message("There was an error when submitting your request.")

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


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

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
