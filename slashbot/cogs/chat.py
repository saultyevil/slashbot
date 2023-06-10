#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
The purpose of this cog is to enable the bot to communicate with the OpenAI API
and to generate responses to prompts given.
"""

import json
import logging
import traceback
from collections import defaultdict
from types import coroutine

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
from slashbot.util import split_text_into_chunks
from slashbot.util import create_prompt_dict
from slashbot.util import read_in_prompt_json

openai.api_key = App.config("OPENAI_API_KEY")
logger = logging.getLogger(App.config("LOGGER_NAME"))

COOLDOWN_USER = commands.BucketType.user
DEFAULT_SYSTEM_MESSAGE = json.load(open("data/prompts/split.json"))["prompt"]
MAX_MESSAGE_LENGTH = 1920
MAX_CHARS_UNTIL_THREAD = 364
TOKEN_COUNT_UNSET = -1
PROMPT_CHOICES = create_prompt_dict()


class JsonFileWatcher(FileSystemEventHandler):
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

    # Disnake method -----------------------------------------------------------

    async def cog_before_slash_command_invoke(
        self, inter: disnake.ApplicationCommandInteraction
    ) -> disnake.ApplicationCommandInteraction:
        """Populate empty history on slash invoke.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteration
            The interation to do something before.
        """
        if isinstance(inter.channel, disnake.channel.DMChannel):
            history_id = inter.author.id
        else:
            history_id = inter.channel.id

        if history_id not in self.chat_history:
            self.token_count[history_id] = [self.default_system_token_count]
            self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        return await super(Chat, self).cog_before_slash_command_invoke(inter)

    # Static -------------------------------------------------------------------

    @staticmethod
    def history_id(obj: disnake.Message | disnake.ApplicationCommandInteraction) -> str | int:
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
    async def send_response_to_channel(response: str, message: disnake.Message, in_dm: bool):
        """Send a response to the provided message channel and author.

        Parameters
        ----------
        response : str
            The response to send to chat.
        message : disnake.Message
            The message to respond to.
        in_dm : bool
            Boolean to indicate if DM channel.
        """
        if len(response) > MAX_MESSAGE_LENGTH:
            responses = split_text_into_chunks(response, MAX_MESSAGE_LENGTH)
            for n, response in enumerate(responses):
                mention_user = message.author.mention if not in_dm else ""
                await message.channel.send(f"{mention_user if n == 0 else ''} {response}")
        else:
            await message.channel.send(f"{message.author.mention if not in_dm else ''} {response}")

    # Private methods ----------------------------------------------------------

    async def __api_response(self, history_id: int | str) -> str:
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

    async def __reduce_chat_history(self, history_id: int | str) -> None:
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

    async def get_message_response(self, history_id: int | str, prompt: str) -> str:
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

        if history_id not in self.chat_history:
            self.token_count[history_id] = [self.default_system_token_count]
            self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        await self.__reduce_chat_history(history_id)
        self.chat_history[history_id].append({"role": "user", "content": prompt})

        try:
            return await self.__api_response(history_id)
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

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def listen_for_mentions(self, message: disnake.Message) -> None:
        """Listen for mentions which are prompts for the AI.

        Parameters
        ----------
        message : str
            The message to process for mentions.
        """
        # ignore other bot messages and itself
        if message.author.bot:
            return

        # only respond when mentioned, in DMs or when in own thread
        bot_mentioned = App.config("BOT_USER_OBJECT") in message.mentions
        message_in_dm = isinstance(message.channel, disnake.channel.DMChannel)

        if bot_mentioned or message_in_dm:
            async with message.channel.typing():
                response = await self.get_message_response(self.history_id(message), message.clean_content)
                await self.send_response_to_channel(response, message, message_in_dm)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="reset_chat_history", description="reset the AI chat history")
    async def reset_chat_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        history_id = self.history_id(inter)
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

        history_id = self.history_id(inter)
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
        history_id = self.history_id(inter)
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
        self.max_output_tokens = num_tokens
        self.max_tokens_allowed = max(num_tokens * 2, 256)

        await inter.response.send_message(
            f"Max output tokens set to {num_tokens} with a token total of {self.max_tokens_allowed}.", ephemeral=True
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="add_chat_prompt", description="add a system prompt to the bot's selection")
    async def add_chat_prompt(self, inter: disnake.ApplicationCommandInteraction, name: str, prompt: str):
        """

        Parameters
        ----------
        inter
        name
        prompt

        Returns
        -------

        """
        if len(name) > 64:
            return await inter.response.send_message("The prompt name should not exceed 64 characters.", epehmeral=True)

        num_tokens = len(tiktoken.encoding_for_model(self.chat_model).encode(prompt))
        if num_tokens > 256:
            return await inter.response.send_message("The prompt should not exceed 256 tokens.", epehmeral=True)

        with open(f"prompt-{name}.json", "w", encoding="utf-8") as file_out:
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
        try:
            prompt = self.chat_history[self.history_id(inter)][0].get("content", None)
        except IndexError:
            return await inter.response.send_message(
                "The chat cog has not been initialized yet, send a prompt request first.", ephemeral=True
            )

        if prompt is None:
            return await inter.response.send_message(
                "There is currently no system prompt set or chat history.", ephemeral=True
            )

        await inter.response.send_message(f"The current prompt is:\n\n{prompt}", ephemeral=True)


observer = Observer()
observer.schedule(JsonFileWatcher(), "data/prompts", recursive=True)
observer.start()
