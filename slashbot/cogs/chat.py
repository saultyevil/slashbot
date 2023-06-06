#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
The purpose of this cog is to enable the bot to communicate with the OpenAI API
and to generate responses to prompts given.
"""

import json
import pathlib
import re
import logging
import time
import traceback
from collections import defaultdict
from types import coroutine
from typing import Tuple

import disnake
import openai
import tiktoken
import openai.error
from disnake.ext import commands
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from slashbot.config import App
from slashbot.custom_bot import ModifiedInteractionBot
from slashbot.custom_cog import CustomCog

openai.api_key = App.config("OPENAI_API_KEY")
logger = logging.getLogger(App.config("LOGGER_NAME"))

COOLDOWN_USER = commands.BucketType.user
DEFAULT_SYSTEM_MESSAGE = json.load(open("data/prompts/split.json"))["prompt"]
MAX_MESSAGE_LENGTH = 1920
MAX_CHARS_UNTIL_THREAD = 364
TOKEN_COUNT_UNSET = -1
MAX_SENTENCES_UNTIL_THREAD = 5

TIME_LIMITED_SERVERS = [
    # App.config("ID_SERVER_ADULT_CHILDREN"),
    # App.config("ID_SERVER_FREEDOM"),
]


def read_in_prompt_json(filepath: str | pathlib.Path) -> dict:
    """Read in a prompt and check for keys."""
    required_keys = (
        "name",
        "prompt",
    )

    with open(filepath, "r", encoding="utf-8") as prompt_in:
        prompt = json.load(prompt_in)
        if not all(key in prompt for key in required_keys):
            raise OSError(f"{filepath} is missing either 'name' or 'prompt' key")

    return prompt


def get_prompt_json() -> list[dict]:
    """Create a list of prompt dicts."""
    return [read_in_prompt_json(file) for file in pathlib.Path("data/prompts").glob("*.json")]


def create_prompt_dict() -> dict:
    """Creates a dict of prompt_name: prompt."""
    return {prompt_dict["name"]: prompt_dict["prompt"] for prompt_dict in get_prompt_json()}


PROMPT_CHOICES = create_prompt_dict()


class PromptFileHandler(FileSystemEventHandler):
    """Event handler for changes to json files"""

    def on_any_event(self, event):
        global PROMPT_CHOICES

        if event.is_directory:
            return
        if event.event_type == "created" or event.event_type == "modified":
            if event.src_path.endswith(".json"):
                prompt = read_in_prompt_json(event.src_path)
                PROMPT_CHOICES[prompt["name"]] = prompt["prompt"]
        if event.event_type == "deleted":
            if event.src_path.endswith(".json"):
                PROMPT_CHOICES = create_prompt_dict()


observer = Observer()
observer.schedule(PromptFileHandler(), "data/prompts", recursive=True)
observer.start()


class Chat(CustomCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: ModifiedInteractionBot):
        super().__init__()
        self.bot = bot

        self.chat_history = defaultdict(list)
        self.token_count = defaultdict(lambda: [0])
        self.guild_cooldown = defaultdict(dict)
        self.threads_enabled = False

        self.chat_model = "gpt-3.5-turbo"
        self.max_output_tokens = 364
        self.model_temperature = 0.7
        self.max_tokens_allowed = 1456
        self.trim_faction = 0.25
        self.max_chat_history = 20

        self.default_system_token_count = len(
            tiktoken.encoding_for_model(self.chat_model).encode(DEFAULT_SYSTEM_MESSAGE)
        )

        self.prompt_choices = []

    # Static -------------------------------------------------------------------

    @staticmethod
    def __split_message_into_chunks(text: str, chunk_length: int) -> list:
        """
        Split text into smaller chunks of a set length while preserving sentences.

        Parameters
        ----------
        text : str
            The input text to be split into chunks.
        chunk_length : int, optional
            The maximum length of each chunk. Default is 1648.

        Returns
        -------
        list
            A list of strings where each string represents a chunk of the text.
        """
        chunks = []
        current_chunk = ""

        while len(text) > 0:
            # Find the nearest sentence end within the chunk length
            end_index = min(len(text), chunk_length)
            while end_index > 0 and text[end_index - 1] not in (".", "!", "?"):
                end_index -= 1

            # If no sentence end found, break at chunk length
            if end_index == 0:
                end_index = chunk_length

            current_chunk += text[:end_index]
            text = text[end_index:]

            if len(text) == 0 or len(current_chunk) + len(text) > chunk_length:
                chunks.append(current_chunk)
                current_chunk = ""

        return chunks

    @staticmethod
    def __get_cooldown_length(guild_id: int, user: disnake.User | disnake.Member) -> Tuple[int, int]:
        """Returns the cooldown length and interaction amount fo a user in a
        guild.

        What returns depends on the guild and the role of the user.

        Parameters
        ----------
        guild_id : int
            The ID of the guild the message was sent in.
        user : disnake.User | disnake.Member
            The User or Member object of the user who sent the prompt.

        Returns
        -------
        int
            The cooldown time in minutes
        int
            The max number of interactions before a cooldown is applied
        """
        if guild_id == App.config("ID_SERVER_ADULT_CHILDREN"):
            if App.config("ID_ROLE_TOP_GAY") in [role.id for role in user.roles]:
                return 0, 999
            return App.config("COOLDOWN_STANDARD"), App.config("COOLDOWN_RATE")

        return App.config("COOLDOWN_STANDARD"), App.config("COOLDOWN_RATE")

    @staticmethod
    def __get_history_id(message: disnake.Message) -> int:
        """Determine the history ID to use given the origin of the message.

        Will either be the user id for direct messages, or the id for the
        channel.

        Parameters
        ----------
        message : disnake.Message
            The recent message.
        Returns
        -------
        int
            The ID to use for history purposes.
        """
        if isinstance(message.channel, disnake.channel.DMChannel):
            history_id = message.author.id
        else:
            history_id = message.channel.id

        return history_id

    @staticmethod
    async def __do_cooldown(message: disnake.Message) -> None:
        """Respond to a user on cooldown.

        Parameters
        ----------
        message :
            The message to respond to.
        """
        await message.channel.send(f"Stop abusing me " f"{message.author.mention}!", delete_after=10)

        try:
            await message.delete(delay=10)
        except disnake.Forbidden:
            logger.error(f"Bot does not have permission to delete messages in {message.guild.id}")

    # Functions ----------------------------------------------------------------

    async def __openai_chat_completion(self, history_id: int | str) -> str:
        """Get a message from ChatGPT using the ChatCompletion API.

        Parameters
        ----------
        history_id : int | str
            The ID to store chat history context to. Usually the guild or user
            id.

        Returns
        -------
        str
            The message returned by ChatGPT.
        """

        response = await openai.ChatCompletion.acreate(
            model=self.chat_model,
            messages=self.chat_history[history_id],
            temperature=self.model_temperature,
            max_tokens=self.max_tokens_allowed,
        )

        message = response["choices"][0]["message"]["content"]
        self.chat_history[history_id].append({"role": "assistant", "content": message})
        self.token_count[history_id].append(int(response["usage"]["total_tokens"]))

        return message

    async def __trim_message_history(self, history_id: int | str) -> None:
        """Remove messages from a chat history.

        Removes a fraction of the messages from the chat history if the number
        of tokens exceeds a threshold controlled by
        `self.model.max_history_tokens`.

        Parameters
        ----------
        history_id : int | str
            The chat history ID. Usually the guild or user id.
        """
        if len(self.chat_history[history_id][1:]) > self.max_chat_history:
            self.chat_history[history_id].pop(1)

        if self.token_count[history_id][-1] > self.max_tokens_allowed:
            num_remove = int(self.trim_faction * len(self.chat_history[history_id]))

            tokens_removed = 0
            for i in range(1, num_remove + 1):
                if i > len(self.chat_history[history_id]) - 2:  # -2 because we exclude the system message
                    break
                self.chat_history[history_id].pop(i)
                try:
                    if i < len(self.token_count[history_id]) - 1:
                        tokens_removed += self.token_count[history_id].pop(i)
                except IndexError:
                    logger.error(
                        "Index error when removing tokens: index = %d, len = %d len history = %d",
                        i - 1,
                        len(self.token_count[history_id]),
                        len(self.chat_history[history_id]),
                    )
                    self.chat_history = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]
                    self.token_count[history_id] = [self.default_system_token_count]

            for i in range(1, len(self.token_count[history_id])):
                self.token_count[history_id][i] -= tokens_removed

    async def __check_for_cooldown(self, message: disnake.Message) -> bool:
        """Check if a message author is on cooldown.

        Parameters
        ----------
        message : disnake.Message
            The message recently sent to the bot.

        Returns
        -------
        bool
            True if the use is on cooldown, False if not.
        """
        if isinstance(message.channel, disnake.DMChannel):
            return False

        current_time = time.time()
        last_message_time, message_count = self.guild_cooldown[message.guild.id].get(message.author.id, (0, 0))
        elapsed_time = current_time - last_message_time
        cooldown_length, max_message_count = self.__get_cooldown_length(message.guild.id, message.author)

        if elapsed_time <= cooldown_length and message_count >= max_message_count:
            return True

        if message_count >= cooldown_length:
            message_count = 0
        message_count += 1

        self.guild_cooldown[message.guild.id][message.author.id] = (current_time, message_count)

        return False

    async def __get_response_destination(self, message: disnake.Message, response: str):
        """Get the destination for a message.

        If the sentence is long, then it goes to a thread.

        Parameters
        ----------
        message : disnake.Message
            The message being responded to.
        response : str
            The response from OpenAI.
        """
        # can't create threads in DMs or Threads
        if isinstance(message.channel, disnake.channel.DMChannel):
            return message.channel

        if not self.threads_enabled:
            return message.channel

        if isinstance(message.channel, disnake.Thread):
            return message.channel

        # but we can create threads in channels, unless we don't have permission

        sentences = re.split(r"(?<=[.!?])\s+", response)

        if len(sentences) > MAX_SENTENCES_UNTIL_THREAD:
            try:
                message_destination = await message.create_thread(name=f"{response[:20]}...", auto_archive_duration=60)
            except disnake.Forbidden:
                message_destination = message.channel
                logger.error("Forbidden from creating a thread in channel %d", message.channel.id)
        else:
            message_destination = message.channel

        return message_destination

    def prepare_history(self, history_id: int | str):
        if history_id not in self.chat_history:
            self.token_count[history_id] = [self.default_system_token_count]
            self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

    async def respond_to_prompt(self, user_name: str, history_id: int | str, prompt: str) -> str:
        """Process a prompt and get a response.

        This function is the main steering function for getting a response from
        OpenAI ChatGPT. The prompt is prepared, the chat history updated, and
        a response is retrieved and returned.

        If something goes wrong due to, e.g. rate limiting from OpenAI, special
        strings are returned which can be sent to chat.

        Parameters
        ----------
        user_name : str
            The name of the user who sent the prompt
        history_id: int
            An ID to store chat history to. Usually the guild or user id.
        prompt : str
            The latest prompt to give to ChatGPT.

        Returns
        -------
        str
            The generated response to the given prompt.
        """
        self.prepare_history(history_id)
        await self.__trim_message_history(history_id)
        self.chat_history[history_id].append({"role": "user", "content": prompt})

        try:
            response = await self.__openai_chat_completion(history_id)
        except openai.error.RateLimitError:
            self.chat_history[history_id].pop()
            return "Uh oh! I've hit OpenAI's rate limit :-("
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(
                "OpenAI API failed with exception:\n%s",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            )
            self.chat_history[history_id].pop()
            return "Uh oh! Something went wrong with that request :-("

        return response

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def listen_for_mentions(self, message: disnake.Message) -> None:
        """Listen for mentions which are prompts for the AI.

        Parameters
        ----------
        message : str
            The message to process for mentions.
        """
        # ignore other both messages and itself
        if message.author.bot:
            return

        # only respond when mentioned, in DMs or when in own thread
        bot_mentioned = App.config("BOT_USER_OBJECT") in message.mentions
        message_in_dm = isinstance(message.channel, disnake.channel.DMChannel)

        if bot_mentioned or message_in_dm:
            history_id = self.__get_history_id(message)

            if not message_in_dm and message.guild.id in TIME_LIMITED_SERVERS:
                on_cooldown = await self.__check_for_cooldown(message)

                if on_cooldown:
                    await self.__do_cooldown(message)
                    return

            # if everything ok, type and send
            async with message.channel.typing():
                response = await self.respond_to_prompt(message.author.name, history_id, message.clean_content)
                message_destination = await self.__get_response_destination(message, response)
                if len(response) > MAX_MESSAGE_LENGTH:
                    responses = self.__split_message_into_chunks(response, MAX_MESSAGE_LENGTH)
                    for n, response in enumerate(responses):
                        mention_user = message.author.mention if not message_in_dm else ""
                        await message_destination.send(f"{mention_user if n == 0 else ''} {response}")
                else:
                    await message_destination.send(f"{message.author.mention if not message_in_dm else ''} {response}")

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="reset_chat", description="reset the AI chat history")
    async def reset_chat(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        history_id = inter.channel.id if inter.guild else inter.author.id
        self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]
        self.token_count[history_id] = [self.default_system_token_count]

        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{DEFAULT_SYSTEM_MESSAGE}",
            ephemeral=True,
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="select_system_prompt", description="set the chat system prompt from a list of pre-defined ones"
    )
    async def select_system_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        choice: str = commands.Param(autocomplete=lambda _inter, _input: PROMPT_CHOICES.keys()),
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
        if prompt is None:
            return await inter.response.send_message(
                "An error with the Discord API has occurred and allowed you to pick a prompt which doesn't exist",
                ephemeral=True,
            )

        history_id = inter.channel.id if inter.guild else inter.author.id
        self.chat_history[history_id] = [{"role": "system", "content": prompt}]
        self.token_count[history_id] = [len(tiktoken.encoding_for_model(self.chat_model).encode(prompt))]

        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt}",
            ephemeral=True,
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_system_prompt", description="change the chat system prompt")
    async def set_system_prompt(self, inter: disnake.ApplicationCommandInteraction, message: str) -> coroutine:
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
        history_id = inter.channel.id if inter.guild else inter.author.id
        self.chat_history[history_id] = [{"role": "system", "content": message}]
        self.token_count[history_id] = [len(tiktoken.encoding_for_model(self.chat_model).encode(message))]

        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{message}",
            ephemeral=True,
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="set_chat_tokens", description="change the maximum number of output tokens for an ai response"
    )
    async def set_chat_tokens(
        self, inter: disnake.ApplicationCommandInteraction, num_tokens: int = commands.Param(gt=25, lt=1024)
    ) -> coroutine:
        """Set the number of tokens the model can return.

        Parameters
        ----------
        inter : disnake.Interaction
            The slash command interaction.
        num_tokens : int
            The number of tokens
        """
        history_id = inter.channel.id if inter.guild else inter.author.id
        self.prepare_history(history_id)

        self.max_output_tokens = num_tokens
        self.max_tokens_allowed = max(num_tokens * 2, 256)

        await inter.response.send_message(
            f"Max output tokens set to {num_tokens} with a token total of {self.max_tokens_allowed}.", ephemeral=True
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="add_chat_prompt", description="add a system prompt to the bot's selection")
    async def save_prompt(self, inter: disnake.ApplicationCommandInteraction, name: str, prompt: str):
        """

        Parameters
        ----------
        inter
        name
        prompt

        Returns
        -------

        """
        history_id = inter.channel.id if inter.guild else inter.author.id
        self.prepare_history(history_id)

        if len(name) > 64:
            return await inter.response.send_message("The prompt name should not exceed 64 characters.", epehmeral=True)

        num_tokens = len(tiktoken.encoding_for_model(self.chat_model).encode(prompt))
        if num_tokens > 256:
            return await inter.response.send_message("The prompt should not exceed 256 tokens.", epehmeral=True)

        with open(f"data/prompts/prompt-{name}.json", "w", encoding="utf-8") as file_out:
            json.dump(
                {"name": name, "prompt": prompt},
                file_out,
            )

        await inter.response.send_message(f"Your prompt {name} has been saved.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="echo_system_prompt", description="echo the current system prompt")
    async def echo_system_prompt(self, inter: disnake.ApplicationCommandInteraction):
        """

        Parameters
        ----------
        inter

        Returns
        -------

        """
        history_id = inter.channel.id if inter.guild else inter.author.id
        self.prepare_history(history_id)

        # the system prompt is always the first entry
        try:
            prompt = self.chat_history[history_id][0].get("content", None)
        except IndexError:
            return await inter.response.send_message(
                "The chat cog has not been initialized yet, send a prompt request first.", ephemeral=True
            )

        if prompt is None:
            return await inter.response.send_message(
                "There is currently no system prompt set or chat history.", ephemeral=True
            )

        await inter.response.send_message(f"The current prompt is:\n\n{prompt}", ephemeral=True)
