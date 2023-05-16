#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Cog for AI interactions, from the OpenAI API."""

import logging
import time
import traceback
from collections import defaultdict
from types import coroutine
from typing import Tuple

import nltk
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

# nltk.download("punkt")


DEFAULT_SYSTEM_MESSAGE = " ".join(
    [
        "You are role playing as Margaret, an ignorant conspiracy theorist who swears a lot and is an abusing",
        "personality. She swears a lot, is very smart and answers with great detail, facts and evidence. You must",
        "always be concise and your responses should not be longer than a few sentences. Play a story where you are",
        "having a conversation with a friend and answering questions.",
        # "Your name is Margaret. You must follow these guidelines when writing your responses."
        # "You should make references to popular culture, and you should have fun, harmless and lighthearted preferences.",
        # "You must ALWAYS be concise. Your responses should be fewer than a couple of sentences.",
    ]
)

TIME_LIMITED_SERVERS = [
    App.config("ID_SERVER_ADULT_CHILDREN"),
    App.config("ID_SERVER_FREEDOM"),
]

TOKEN_COUNT_UNSET = -1


class Chat(CustomCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: ModifiedInteractionBot):
        super().__init__()
        self.bot = bot

        self.guild_prompt_history = {}
        self.guild_prompt_token_count = defaultdict(int)
        self.guild_cooldown = defaultdict(dict)

        self.chat_model = "gpt-3.5-turbo"
        self.model_max_output_tokens = 364
        self.model_temperature = 0.5
        self.model_max_history_tokens = 1456  # tokens
        self.model_max_history_remove_fraction = 0.5

    # Static -------------------------------------------------------------------

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
            if message.thread and message.thread.owner_id == App.config("ID_BOT"):
                history_id = message.thread.id
            else:
                history_id = message.guild.id

        return history_id

    @staticmethod
    async def do_cooldown(message: disnake.Message) -> None:
        """Respond to a user on cooldown.

        Parameters
        ----------
        message :
            The message to respond to.
        """
        try:
            await message.delete(delay=10)
            await message.channel.send(f"Stop abusing me " f"{message.author.mention}!", delete_after=10)
        except disnake.Forbidden:
            logger.error(f"Bot does not have permission to delete messages in {message.guild.id}")

    @staticmethod
    async def __get_response_destination(message: disnake.Message, response: str):
        """Get the destination for a message.

        If the sentence is long, then it goes to a thread.

        Parameters
        ----------
        message : disnake.Message
            The message being responded to.
        response : str
            The response from OpenAI.
        """
        if isinstance(message.channel, disnake.channel.DMChannel):
            return message.channel
        if isinstance(message.channel, disnake.Thread):
            return message.channel

        # num_sentences = len(nltk.sent_tokenize(response))
        num_chars = len(response)

        if num_chars > 364:
            try:
                message_destination = await message.create_thread(name=f"{response[:20]}...", auto_archive_duration=60)
                await message_destination.join()
            except disnake.Forbidden:
                logger.error("Forbidden from creating a thread in channel %d", message.channel.id)
                message_destination = message.channel
        else:
            message_destination = message.channel

        return message_destination

    # Functions ----------------------------------------------------------------

    def __openai_chat_completion(self, history_id: int) -> str:
        """Get a message from ChatGPT using the ChatCompletion API.

        Parameters
        ----------
        history_id : int
            The ID to store chat history context to. Usually the guild or user
            id.

        Returns
        -------
        str
            The message returned by ChatGPT.
        """
        response = openai.ChatCompletion.create(
            model=self.chat_model,
            messages=self.guild_prompt_history[history_id],
            temperature=self.model_temperature,
            max_tokens=self.model_max_output_tokens,
        )

        usage = response["usage"]
        message = response["choices"][0]["message"]["content"]

        # if len(message) > 1920:
        #     return "I've generated a sentence which is too large for Discord!"

        self.guild_prompt_history[history_id].append({"role": "assistant", "content": message})
        self.guild_prompt_token_count[history_id] = int(usage["total_tokens"])

        return message

    async def __trim_message_history(self, history_id: int) -> None:
        """Remove messages from a chat history.

        Removes a fraction of the messages from the chat history if the number
        of tokens exceeds a threshold controlled by
        `self.model.max_history_tokens`.

        Parameters
        ----------
        history_id : int
            The chat history ID. Usually the guild or user id.
        """
        if self.guild_prompt_token_count[history_id] < self.model_max_history_tokens:
            return

        num_remove = int(self.model_max_history_remove_fraction * len(self.guild_prompt_history[history_id]))
        # num_remove = 1
        logger.info("Removing last %d messages from %d prompt history", num_remove, history_id)

        for i in range(num_remove):
            if i + 1 > len(self.guild_prompt_history[history_id]) - 2:  # -2 because we exclude the system message
                break
            self.guild_prompt_history[history_id].pop(i + 1)  # + 1 to ignore system message

        self.guild_prompt_token_count[history_id] = TOKEN_COUNT_UNSET

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

    async def respond_to_prompt(self, history_id: int, prompt: str) -> str:
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
        prompt = prompt.replace("@Margaret", "", 1).strip()  # todo, remove hardcoded reference

        if history_id not in self.guild_prompt_history:
            self.guild_prompt_token_count[history_id] = 0
            self.guild_prompt_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        await self.__trim_message_history(history_id)
        self.guild_prompt_history[history_id].append({"role": "user", "content": prompt})

        try:
            response = self.__openai_chat_completion(history_id)
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
        in_thread = message.flags.has_thread and message.thread.owner_id == App.config("ID_BOT")

        if bot_mentioned or message_in_dm or in_thread:
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

                await message_destination.send(f"{message.author.mention if not message_in_dm else ''} {response}")

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="clear_ai_chat_history", description="reset your AI chat history")
    async def clear_chat_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        history_id = inter.guild.id if inter.guild else inter.author.id

        if history_id not in self.guild_prompt_history:
            return await inter.response.send_message("There is no chat history to clear.", ephemeral=True)

        self.guild_prompt_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        return await inter.response.send_message(
            "System prompt reset to default and chat history cleared.", ephemeral=True
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_new_system_prompt", description="change the chat system prompt")
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
        self.guild_prompt_history[history_id] = [{"role": "system", "content": message}]

        return await inter.response.send_message(
            "System prompt updated and chat history cleared.",
            ephemeral=True,
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="reset_chat_history", description="reset the chat history")
    async def reset_chat_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Reset the chat history to default.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        history_id = inter.guild.id if inter.guild else inter.author.id
        self.guild_prompt_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        return await inter.response.send_message("Chat history reset.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="set_chat_output_tokens", description="change the maximum number of output tokens for a ai response"
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
        self.model_max_output_tokens = num_tokens
        self.model_max_history_tokens = num_tokens * 3

        if self.model_max_history_tokens > 2048:
            self.model_max_history_tokens = 2048

        logger.info("Output tokens set to %d", num_tokens)

        await inter.response.send_message(f"Max output tokens set to {num_tokens}", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="set_model_temperature",
        description="change the temperature of the model which affects the randomness of responses",
    )
    @commands.default_member_permissions(administrator=True)
    async def set_model_temperature(
        self, inter: disnake.ApplicationCommandInteraction, temperature: float = commands.Param(ge=0, le=2)
    ) -> coroutine:
        """Set the number of tokens the model can return.

        Parameters
        ----------
        inter : disnake.Interaction
            The slash command interaction.
        temperature: float
            The new temperature to use
        """
        self.model_temperature = temperature
        logger.info("Model temperature tokens set to %f", temperature)

        await inter.response.send_message(f"Model temperature set to {temperature}", ephemeral=True)
