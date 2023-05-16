#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Cog for AI interactions, from the OpenAI API."""

import copy
import logging
import time
import traceback
from collections import defaultdict
from types import coroutine
from typing import Tuple

import disnake
import openai
import openai.error
from disnake.ext import commands

from slashbot.config import App
from slashbot.custom_bot import ModifiedInteractionBot
from slashbot.custom_cog import CustomCog

openai.api_key = App.config("OPENAI_API_KEY")

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


DEFAULT_SYSTEM_MESSAGE = " ".join(
    [
        "You are role playing as Margaret, an ignorant conspiracy theorist who wholeheartedly believes the",
        "conspiracies. Margaret swears a lot and is an abusing personality",
        "She swears a lot, is very smart and answers with great detail, facts and evidence. You must",
        "always be concise and your responses should not be longer than a few sentences. Play a story where you are",
        "having a conversation with a friend and answering questions.",
    ]
)

TIME_LIMITED_SERVERS = [
    App.config("ID_SERVER_ADULT_CHILDREN"),
    App.config("ID_SERVER_FREEDOM"),
]

MAX_LENGTH = 1920
MAX_CHARS_UNTIL_THREAD = 364
TOKEN_COUNT_UNSET = -1


class Chat(CustomCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: ModifiedInteractionBot):
        super().__init__()
        self.bot = bot

        self.chat_history = {}
        self.token_count = defaultdict(list)
        self.guild_cooldown = defaultdict(dict)

        self.threads_enabled = False

        self.chat_model = "gpt-3.5-turbo"
        self.max_output_tokens = 364
        self.model_temperature = 0.7
        self.max_tokens_allowed = 1456
        self.trim_faction = 0.25
        self.max_chat_history = 20

    # Static -------------------------------------------------------------------

    @staticmethod
    def __chunk_messages(message: str) -> list:
        """Split a message into smaller chunks.

        Parameters
        ----------
        message : str
            The message to split.

        Returns
        -------
        list
            A list of strings of smaller messages.
        """

        i = 0
        result = []
        while i < len(message):
            start = i
            i += MAX_LENGTH

            # At end of string
            if i >= len(message):
                result.append(message[start:i])
                return result

            # Back up until space
            while message[i - 1] != " ":
                i -= 1
            result.append(message[start:i])

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
    async def do_cooldown(message: disnake.Message) -> None:
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

        # response = openai.ChatCompletion.create(
        #     model=self.chat_model,
        #     messages=self.chat_history[history_id],
        #     temperature=self.model_temperature,
        #     max_tokens=self.max_output_tokens,
        # )

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
                tokens_removed += self.token_count[history_id].pop(i)

            for i in range(1, len(self.chat_history[history_id])):
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
        if len(response) > MAX_CHARS_UNTIL_THREAD:
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
            self.token_count[history_id] = [0]
            self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        await self.__trim_message_history(history_id)
        self.chat_history[history_id].append({"role": "user", "content": prompt})

        try:
            response = await self.__openai_chat_completion(history_id)
        except openai.error.RateLimitError:
            return "Uh oh! I've hit OpenAI's rate limit :-("
        except Exception as exc:  # pylint: disable=broad-exception-caught
            stack = traceback.format_exception(type(exc), exc, exc.__traceback__)
            logger.exception("OpenAI API failed with exception:\n%s", "".join(stack))
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
                    await self.do_cooldown(message)
                    return

            # if everything ok, type and send
            async with message.channel.typing():
                response = await self.respond_to_prompt(history_id, message.clean_content)
                message_destination = await self.__get_response_destination(message, response)

                if len(response) > MAX_LENGTH:
                    responses = self.__chunk_messages(response)
                    for response in responses:
                        await message_destination.send(
                            f"{message.author.mention if not message_in_dm else ''} {response}"
                        )
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
        history_id = inter.guild.id if inter.guild else inter.author.id
        if history_id not in self.chat_history:
            return await inter.response.send_message("There is no chat history to clear.", ephemeral=True)
        self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        return await inter.response.send_message(
            "System prompt reset to default and chat history cleared.", ephemeral=True
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
        history_id = inter.guild.id if inter.guild else inter.author.id
        self.chat_history[history_id] = [{"role": "system", "content": message}]

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
