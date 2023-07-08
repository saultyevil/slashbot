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
import openai.version
from disnake.ext import commands
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from slashbot.config import App
from slashbot.custom_bot import SlashbotInterationBot
from slashbot.custom_cog import SlashbotCog
from slashbot.util import split_text_into_chunks
from slashbot.util import create_prompt_dict
from slashbot.util import read_in_prompt_json

openai.api_key = App.config("OPENAI_API_KEY")
logger = logging.getLogger(App.config("LOGGER_NAME"))

COOLDOWN_USER = commands.BucketType.user
DEFAULT_SYSTEM_MESSAGE = read_in_prompt_json("data/prompts/split.json")["prompt"]
MAX_MESSAGE_LENGTH = 1920
MAX_CHARS_UNTIL_THREAD = 364
TOKEN_COUNT_UNSET = -1
PROMPT_CHOICES = create_prompt_dict()

# this is global so you can use it as a choice in interactions
AVAILABLE_MODELS = ("gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4")


class Chat(SlashbotCog):
    """AI chat features powered by OpenAI."""

    token_model = "cl100k_base"

    def __init__(self, bot: SlashbotInterationBot):
        super().__init__()
        self.bot = bot

        self.chat_history = defaultdict(list)
        self.token_count = defaultdict(int)
        self.guild_cooldown = defaultdict(dict)

        self.chat_model = "gpt-3.5-turbo"
        self.output_tokens = 512
        self.model_temperature = 0.7
        self.max_tokens_allowed = 2048
        self.trim_faction = 0.5
        self.max_chat_history = 20

        self.default_system_token_count = len(tiktoken.get_encoding(self.token_model).encode(DEFAULT_SYSTEM_MESSAGE))

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
            self.token_count[history_id] = self.default_system_token_count
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

    def __set_max_allowed_tokens(self, model_name: str):
        """Set the max allowed tokens.

        Parameters
        ----------
        model_name : str
            The name of the model.
        """
        if model_name != "gpt-3.5-turbo":
            self.max_tokens_allowed = 8192
        else:
            self.max_tokens_allowed = 4096

    def __create_history_if_missing(self, history_id: str | int):
        """Populate a new dict entry if one doesn't exist for a history_id.

        Parameters
        ----------
        history_id : str | int
            The history_id to make something for.
        """
        if history_id not in self.chat_history:
            self.token_count[history_id] = self.default_system_token_count
            self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

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
        self.token_count[history_id] = int(response["usage"]["total_tokens"])

        channel = await self.bot.fetch_channel(history_id)

        logger.debug(
            "%s is currently at %d tokens with %d messages",
            channel.name if not isinstance(channel, disnake.DMChannel) else f"DM {channel.id}",
            self.token_count[history_id],
            len(self.chat_history[history_id]),
        )

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
        channel = await self.bot.fetch_channel(history_id)
        channel_name = channel.name if not isinstance(channel, disnake.DMChannel) else f"DM {channel.id}"

        # max token count
        if self.token_count[history_id] > self.max_tokens_allowed:
            num_remove = int(self.trim_faction * (len(self.chat_history[history_id]) - 1))
            for i in range(1, num_remove):
                self.chat_history[history_id].pop(i)
            self.token_count[history_id] = TOKEN_COUNT_UNSET
            logger.debug("%s had %d messages removed due to token count", channel_name, num_remove)

        # max history count
        if len(self.chat_history[history_id][1:]) > self.max_chat_history:
            for i in range(1, 3):  # remove two elements to get prompt + response
                self.chat_history[history_id].pop(i)
            self.token_count[history_id] = TOKEN_COUNT_UNSET
            # logger.debug("%s had 1 message and response removed due to message count", channel_name)

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

        await self.__reduce_chat_history(history_id)
        self.chat_history[history_id].append({"role": "user", "content": prompt})

        try:
            return await self.__api_response(history_id)
        except openai.error.RateLimitError as exc:
            logger.exception(
                "OpenAI API failed with exception:\n%s",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            )
            self.chat_history[history_id].pop()
            return "Uh oh! I've hit my rate limit :-(!"
        except openai.error.ServiceUnavailableError:
            self.chat_history[history_id].pop()
            return "Uh oh, my services are currently unavailable!"
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception(
                "OpenAI API failed with exception:\n%s",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            )
            self.chat_history[history_id].pop()
            return str(exc)

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
            history_id = self.history_id(message)
            self.__create_history_if_missing(history_id)

            async with message.channel.typing():
                response = await self.get_message_response(history_id, message.clean_content)
                await self.send_response_to_channel(response, message, message_in_dm)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="reset_chat_history", description="Reset the AI conversation history")
    async def reset_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        history_id = self.history_id(inter)
        self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]
        self.token_count[history_id] = self.default_system_token_count

        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{DEFAULT_SYSTEM_MESSAGE}",
            ephemeral=True,
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="select_chat_prompt", description="Set the AI conversation prompt from a list of choices"
    )
    async def select_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        choice: str = commands.Param(
            autocomplete=lambda _inter, uin: [choice for choice in PROMPT_CHOICES.keys() if choice.startswith(uin)]
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
        if prompt is None:
            return await inter.response.send_message(
                "An error with the Discord API has occurred and allowed you to pick a prompt which doesn't exist",
                ephemeral=True,
            )

        history_id = self.history_id(inter)
        self.chat_history[history_id] = [{"role": "system", "content": prompt}]

        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt[:1928]}",
            ephemeral=True,
        )

        self.token_count[history_id] = TOKEN_COUNT_UNSET

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_system_prompt", description="Change the AI conversation prompt to one you write")
    async def set_prompt(self, inter: disnake.ApplicationCommandInteraction, message: str) -> coroutine:
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

        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{message}",
            ephemeral=True,
        )

        self.token_count[history_id] = len(tiktoken.get_encoding(self.token_model).encode(message))

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_chat_tokens", description="Set the max token length for AI conversation output")
    async def set_output_tokens(
        self, inter: disnake.ApplicationCommandInteraction, num_tokens: int = commands.Param(gt=256, lt=2048)
    ) -> coroutine:
        """Set the number of tokens the model can return.

        Parameters
        ----------
        inter : disnake.Interaction
            The slash command interaction.
        num_tokens : int
            The number of tokens
        """
        self.output_tokens = num_tokens
        self.__set_max_allowed_tokens(self.chat_model)

        await inter.response.send_message(
            f"Max output tokens set to {num_tokens} with a token total of {self.max_tokens_allowed}.", ephemeral=True
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="save_chat_prompt", description="Save a AI conversation prompt to the bot's selection")
    async def save_prompt(self, inter: disnake.ApplicationCommandInteraction, name: str, prompt: str):
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
        if len(name) > 64:
            return await inter.response.send_message("The prompt name should not exceed 64 characters.", epehmeral=True)

        await inter.response.defer(ephemeral=True)

        num_tokens = len(tiktoken.get_encoding(self.token_model).encode(prompt))
        if num_tokens > 256:
            return await inter.edit_original_message(content="The prompt should not exceed 256 tokens.")

        with open(f"data/prompts/prompt-{name}.json", "w", encoding="utf-8") as file_out:
            json.dump(
                {"name": name, "prompt": prompt},
                file_out,
            )

        await inter.edit_original_message(content=f"Your prompt {name} has been saved.")

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="show_ai_info", description="Print information about the current AI conversation")
    async def echo_info(self, inter: disnake.ApplicationCommandInteraction):
        """Print the system prompt to the screen.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        await inter.response.defer(ephemeral=True)
        history_id = self.history_id(inter)
        self.__create_history_if_missing(history_id)

        response = ""

        response += f"**Chat model**: {self.chat_model}\n"
        response += f"**Model temperature**: {self.model_temperature}\n"
        response += f"**OpenAI version**: {openai.version.VERSION}\n"
        response += f"**Current token usage**: {self.token_count[history_id]}\n"
        response += f"**Output tokens**: {self.output_tokens}\n"
        response += f"**Max tokens**: {self.max_tokens_allowed}\n"

        prompt_name = "Unknown"
        prompt = self.chat_history[history_id][0].get("content", None)
        for name, text in PROMPT_CHOICES.items():
            if prompt == text:
                prompt_name = name
        response += "**Prompt name**: " + prompt_name + "\n"
        response += f"**Prompt**: {prompt[:1024] if prompt else 'Unknown'}\n"

        await inter.edit_original_message(content=response)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="select_chat_model", description="Change the current AI conversation model for a set of choices"
    )
    async def select_model(
        self,
        inter: disnake.ApplicationCommandInteraction,
        model_name: str = commands.Param(description="The name of the model to use", choices=AVAILABLE_MODELS),
    ):
        """Change the chat model to generate text.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The disnake command interaction.
        model_name : str
            The name of the model to use.
        """
        if inter.author.id != App.config("ID_USER_SAULTYEVIL"):
            return await inter.response.send_message("You do not have permission to use this command.", ephemeral=True)

        # not really required, as the user should only be able to select from a set of choices
        if model_name not in AVAILABLE_MODELS:
            return await inter.response.send_message(
                f"{model_name} is not a recognized model. Allowed: {AVAILABLE_MODELS}", ephemeral=True
            )

        await inter.response.defer(ephemeral=True)

        self.chat_model = model_name
        self.default_system_token_count = len(tiktoken.get_encoding(self.token_model).encode(DEFAULT_SYSTEM_MESSAGE))

        history_id = self.history_id(inter)
        self.token_count[history_id] = self.default_system_token_count
        self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        self.__set_max_allowed_tokens(self.chat_model)

        await inter.edit_original_message(content=f"Chat model has been switched to {model_name}")


class JsonFileWatcher(FileSystemEventHandler):
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
observer.schedule(JsonFileWatcher(), "data/prompts", recursive=True)
observer.start()
