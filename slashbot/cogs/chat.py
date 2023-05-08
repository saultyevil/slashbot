#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for interacting with the OpenAI chat bot interface."""

import logging
import re
from types import coroutine

import openai
import openai.error
import disnake
from disnake.ext import commands

from slashbot.config import App
from slashbot.custom_cog import CustomCog
from slashbot.custom_bot import ModifiedInteractionBot


openai.api_key = App.config("OPENAI_API_KEY")

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


DEFAULT_SYSTEM_MESSAGE = " ".join(
    [
        "Your name is Margaret and you are a helpful assistant. Your favourite animal are rabbits. You are a big fan of",
        "the bands Anal Cunt and Megadeth. You really enjoy playing the board game Talisman. If you ever need to",
        "change the topic, suggest that everyone should hop on for a quick game of Talisman, or watch you stream Yakuza"
        "6.",
    ]
)


class Chat(CustomCog):
    """Chat tools for the bot."""

    def __init__(self, bot: ModifiedInteractionBot):
        super().__init__()
        self.bot = bot

        self.guild_prompt_history = {}
        self.guild_prompt_token_count = {}

        self.ignored_users = []

        self.model_temperature = 0.5
        self.model_max_history_tokens = 1024  # tokens
        self.model_max_history_remove_fraction = 0.5

    # Functions ----------------------------------------------------------------

    def __chat_model(self, history_id: int) -> str:
        """_summary_

        Parameters
        ----------
        history_id : int
            _description_

        Returns
        -------
        str
            _description_
        """
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.guild_prompt_history[history_id],
            temperature=self.model_temperature,
            max_tokens=1024,
        )

        usage = response["usage"]
        message = re.sub(r"\n+", "\n", response["choices"][0]["message"]["content"])

        self.guild_prompt_history[history_id].append({"role": "assistant", "content": message})
        self.guild_prompt_token_count[history_id] = float(usage["total_tokens"])

        return message

    async def __cull_long_chat_history(self, history_id: int) -> None:
        """Remove old messages from a chat history when it gets too long.

        Parameters
        ----------
        history_id : int
            _description_
        """
        if self.guild_prompt_token_count[history_id] < self.model_max_history_tokens:
            return

        num_remove = int(self.model_max_history_remove_fraction * len(self.guild_prompt_history[history_id]))
        logger.info("Removing last %d messages from %d prompt history", num_remove, history_id)

        for i in range(num_remove):
            self.guild_prompt_history[history_id].pop(i + 1)  # + 1 to ignore system message

        self.guild_prompt_token_count[history_id] = 0

    async def respond_to_prompt(self, history_id: int, prompt: str) -> coroutine:
        """_summary_

        Parameters
        ----------
        author : disnake.User
            _description_
        prompt : str
            _description_

        Returns
        -------
        coroutine
            _description_
        """
        prompt = prompt.replace("@Margaret", "", 1).strip()  # todo, remove hardcoded reference

        if history_id not in self.guild_prompt_history:
            self.guild_prompt_token_count[history_id] = 0
            self.guild_prompt_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        await self.__cull_long_chat_history(history_id)
        self.guild_prompt_history[history_id].append({"role": "user", "content": prompt})

        try:
            response = self.__chat_model(history_id)
        except openai.error.RateLimitError:
            return "Uh oh! I'm hit my rate limit :-("
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("OpenAI API failed with exception %s", exc)
            return "Uh oh! Something went wrong with that request :-("

        return response

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def listen_for_mentions(self, message: disnake.Message) -> None:
        """Respond to mentions with the AI.

        Parameters
        ----------
        message : str
            _description_
        """
        if message.author.bot:
            return
        if message.author == App.config("BOT_USER_OBJECT"):
            return
        if message.author in self.ignored_users:
            return

        bot_mentioned = App.config("BOT_USER_OBJECT") in message.mentions
        message_in_dm = isinstance(message.channel, disnake.channel.DMChannel)

        if bot_mentioned or message_in_dm:
            async with message.channel.typing():
                response = await self.respond_to_prompt(message.author.id, message.clean_content)
                await message.channel.send(f"{message.author.mention} {response}")

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="clear_chat_context", description="reset your AI chat history")
    async def clear_chat_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """__description__

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_

        Returns
        -------
        coroutine
            _description_
        """
        if inter.guild.id not in self.guild_prompt_history:
            return

        logger.info("System prompt reset to default")
        self.guild_prompt_history[inter.guild.id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        return await inter.response.send_message(
            "System prompt reset to default and chat history cleared.", ephemeral=True
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_chat_system_prompt", description="change the chat system prompt")
    async def set_system_message(self, inter: disnake.ApplicationCommandInteraction, message: str) -> coroutine:
        """_summary_

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_
        message : str
            _description_
        """
        logger.info("New system prompt for chat: %s", message)
        self.guild_prompt_history[inter.guild.id].append([{"role": "system", "content": message}])

        return await inter.response.send_message("System prompt updated and chat history cleared.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(description="Toggle a user in the ignore list")
    @commands.default_member_permissions(administrator=True)
    async def toggle_user_in_ignore_list(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="the user to toggle from the ignore list"),
    ):
        """Add or remove a user from the ignore list.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_
        """
        if member not in self.ignored_users:
            self.ignored_users.append(member)
            return await inter.response.send_message(f"{member} added to the ignore list.")

        self.ignored_users.remove(member)

        return await inter.response.send_message(f"{member} removed from the ignore list.")

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(description="Set the randomness of generated responses")
    @commands.default_member_permissions(administrator=True)
    async def set_model_temperature(
        self,
        inter: disnake.ApplicationCommandInteraction,
        temperature: float = commands.Param(
            description="larger values result in more random responses",
            default=0.5,
            ge=0,
            le=2,
        ),
    ):
        """_summary_

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_
        temperature : float
            _description_
        """
        self.model_temperature = temperature
        logger.info("Model temperature set to %f", temperature)

        return await inter.response.send_message(f"Temperature set to {temperature}", ephemeral=True)
