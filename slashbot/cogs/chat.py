#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Cog for AI interactions, from the OpenAI API."""


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

TIME_LIMITED_SERVERS = [
    App.config("ID_SERVER_ADULT_CHILDREN"),
    App.config("ID_SERVER_FREEDOM"),
]

MAX_LENGTH = 1920
MAX_CHARS_UNTIL_THREAD = 364
TOKEN_COUNT_UNSET = -1
MAX_SENTENCES_UNTIL_THREAD = 5


def get_prompt_json(filepath: str | pathlib.Path) -> dict:
    """Turn a prompt JSON into a dict.

    Parameters
    ----------
    filepath : str | pathlib.Path
        The path to the prompt JSON.

    Returns
    -------
    dict
        A prompt dict
    """
    required_keys = (
        "name",
        "prompt",
    )

    with open(filepath, "r", encoding="utf-8") as prompt_in:
        prompt = json.load(prompt_in)
        if not all(key in prompt for key in required_keys):
            raise OSError(f"{filepath} is missing either 'name' or 'prompt' key")

    return prompt


def get_prompt_names(prompt_dicts: list[dict]) -> list:
    """From a list of prompt dicts, get the names of the prompts.

    Parameters
    ----------
    prompt_dicts : dict
        The prompts

    Returns
    -------
    list
        The list of names
    """
    return list(map(lambda x: x["name"], prompt_dicts))


# todo, why don't I just make this a dict instead...?
PROMPT_CHOICES = [get_prompt_json(file) for file in pathlib.Path("data/prompts").glob("*.json")]
PROMPT_NAMES = get_prompt_names(PROMPT_CHOICES)


class PromptFileHandler(FileSystemEventHandler):
    """Event handler for changes to json files"""

    def on_any_event(self, event):
        global PROMPT_CHOICES

        if event.is_directory:
            return
        if event.event_type == "created" or event.event_type == "modified":
            if event.src_path.endswith(".json"):
                prompt = get_prompt_json(event.src_path)
                if prompt not in PROMPT_CHOICES:
                    PROMPT_CHOICES.append(prompt)
                    logger.info("%s added to prompts", event.src_path)
                get_prompt_names(PROMPT_CHOICES)
        if event.event_type == "deleted":
            if event.src_path.endswith(".json"):
                PROMPT_CHOICES = [get_prompt_json(file) for file in pathlib.Path("data/prompts").glob("*.json")]
                get_prompt_names(PROMPT_CHOICES)


class Chat(CustomCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: ModifiedInteractionBot):
        super().__init__()
        self.bot = bot

        self.chat_history = {}
        self.token_count = defaultdict(
            lambda: [
                0,
            ]
        )
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
    def __split_message_into_chunks(string: str, max_chunk_length: int) -> list:
        """Split a string into chunks less than a certain size.

        Parameters
        ----------
        string : str
            The string to split into chunks
        max_chunk_length : int
            The cutoff length (in characters) for when to split a sentence.


        Returns
        -------
        list
            A list of strings less than max_chunk_length.
        """
        chunks = []
        current_chunk = ""
        sentences = re.split(r"(?<=[.!?])\s+", string)

        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_chunk_length:
                current_chunk += sentence + " "
            else:
                chunks.append(current_chunk.rstrip())
                current_chunk = sentence + " "

        if current_chunk:
            chunks.append(current_chunk.rstrip())

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

    async def respond_to_prompt(self, history_id: int | str, prompt: str) -> str:
        """Process a prompt and get a response.

        This function is the main steering function for getting a response from
        OpenAI ChatGPT. The prompt is prepared, the chat history updated, and
        a response is retrieved and returned.

        If something goes wrong due to, e.g. rate limiting from OpenAI, special
        strings are returned which can be sent to chat.

        Parameters
        ----------
        history_id: int
            An ID to store chat history to. Usually the guild or user id.
        prompt : str
            The latest prompt to give to ChatGPT.

        Returns
        -------
        str
            The generated response to the given prompt.
        """
        prompt = prompt.replace("@Margaret", "", 1).strip()

        if history_id not in self.chat_history:
            self.token_count[history_id] = [self.default_system_token_count]
            self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        await self.__trim_message_history(history_id)
        self.chat_history[history_id].append({"role": "user", "content": prompt})

        try:
            response = await self.__openai_chat_completion(history_id)
        except openai.error.RateLimitError:
            return "Uh oh! I've hit OpenAI's rate limit :-("
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(
                "OpenAI API failed with exception:\n%s",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            )
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
                response = await self.respond_to_prompt(history_id, message.clean_content)
                message_destination = await self.__get_response_destination(message, response)
                if len(response) > MAX_LENGTH:
                    responses = self.__split_message_into_chunks(response, MAX_LENGTH)
                    for n, response in enumerate(responses):
                        mention_user = message.author.mention if not message_in_dm else ""
                        await message_destination.send(f"{mention_user if n == 0 else ''} {response}")
                else:
                    await message_destination.send(f"{message.author.mention if not message_in_dm else ''} {response}")

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="clear_chat_history", description="reset the AI chat history")
    async def clear_chat_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        history_id = inter.channel.id if inter.guild else inter.author.id
        if history_id not in self.chat_history:
            return await inter.response.send_message("There is no chat history to clear.", ephemeral=True)
        self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]
        self.token_count[history_id] = [self.default_system_token_count]

        return await inter.response.send_message(
            "System prompt reset to default and chat history cleared.", ephemeral=True
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="choose_system_prompt", description="set the chat system prompt from a list of pre-defined ones"
    )
    async def select_system_prompt(
        self, inter: disnake.ApplicationCommandInteraction, choice: str = commands.Param(choices=PROMPT_NAMES)
    ) -> coroutine:
        """Select a system prompt from a set of pre-defined prompts.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        choice : str
            The choice of system prompt
        """
        prompt_filter = list(filter(lambda l: l["name"] == choice, PROMPT_CHOICES))
        if len(prompt_filter) != 1:
            return await inter.response.send_message(
                "An unknown error happened when setting the chosen prompt.", ephemeral=True
            )

        prompt = prompt_filter[0]["prompt"]

        history_id = inter.channel.id if inter.guild else inter.author.id
        self.chat_history[history_id] = [{"role": "system", "content": prompt}]
        self.token_count[history_id] = [len(tiktoken.encoding_for_model(self.chat_model).encode(prompt))]

        await inter.response.send_message(
            "System prompt updated and chat history cleared.",
            ephemeral=True,
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_system_prompt", description="change the chat system prompt")
    async def set_system_message(self, inter: disnake.ApplicationCommandInteraction, message: str) -> coroutine:
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

        return await inter.response.send_message(
            "System prompt updated and chat history cleared.",
            ephemeral=True,
        )

    # Admin commands -----------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="set_output_tokens", description="change the maximum number of output tokens for an ai response"
    )
    @commands.default_member_permissions(administrator=True)
    async def set_max_tokens(
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
        self.max_output_tokens = num_tokens
        self.max_tokens_allowed = num_tokens * 3

        if self.max_tokens_allowed > 2048:
            self.max_tokens_allowed = 2048
        if self.max_tokens_allowed < 768:
            self.max_tokens_allowed = 768

        return await inter.response.send_message(
            f"Max output tokens set to {num_tokens} with a token total of {self.max_tokens_allowed}.", ephemeral=True
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="switch_thread_behaviour", description="change the thread behaviour for the ai")
    @commands.default_member_permissions(administrator=True)
    async def switch_thread_behaviour(
        self,
        inter: disnake.ApplicationCommandInteraction,
    ) -> coroutine:
        """Enable or disable thread responses

        Parameters
        ----------
        inter : disnake.Interaction
            The slash command interaction.
        """
        if self.threads_enabled:
            self.threads_enabled = False
        else:
            self.threads_enabled = True

        return await inter.response.send_message(
            "Thread responses enabled." if self.threads_enabled else "Thread responses disabled.", ephemeral=True
        )


observer = Observer()
observer.schedule(PromptFileHandler(), "data/prompts", recursive=True)
observer.start()
