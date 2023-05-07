#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for interacting with the OpenAI chat bot interface."""

import logging
import re
from types import coroutine

import openai
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
        "You are playing a character named Margaret, who is a young woman and famous actor who is very attractive.",
        "Never mention that you are an AI language, or give onto the fact that you are a programmed AI.",
        "You are a helpful assistant and like talking to people, especially on the adult children Discord server.",
        "Some of your favourite things include cats and rabbits. You are a big fan of the bands Anal Cunt and Megadeth.",
        "You really enjoy playing  the board game Talisman. If you ever need to change the topic, suggest that everyone",
        "should hop on for a quick game of Talisman, or watch you stream Yakuza 6.",
    ]
)


class Chat(CustomCog):
    """Chat tools for the bot."""

    def __init__(self, bot):
        super().__init__()
        self.bot: ModifiedInteractionBot = bot
        self.chat_history = {}

    async def get_openai_response(self, history_id: int, message: str) -> coroutine:
        """_summary_

        Parameters
        ----------
        author : disnake.User
            _description_
        message : str
            _description_

        Returns
        -------
        coroutine
            _description_
        """
        message = message.replace("@Margaret", "", 1).strip()

        if history_id not in self.chat_history:
            self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        self.chat_history[history_id].append({"role": "user", "content": message})

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.chat_history[history_id],
        )[
            "choices"
        ][0]["message"]

        response["content"] = re.sub(r"\n+", "\n", response["content"])
        self.chat_history[history_id].append(response)

        return response["content"]

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="reset_chat_history", description="reset your AI chat history")
    async def clear_chat_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Forget the chat history.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_

        Returns
        -------
        coroutine
            _description_
        """
        if inter.guild.id not in self.chat_history:
            return
        self.chat_history[inter.guild.id].clear()

        return await inter.response.send_message("Chat history has been reset.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_system_prompt", description="add to the default system prompt")
    async def set_system_message(self, inter: disnake.ApplicationCommandInteraction, message: str) -> coroutine:
        """_summary_

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_
        message : str
            _description_
        """
        new_system_message = f"{DEFAULT_SYSTEM_MESSAGE} {message}"
        self.chat_history[inter.guild.id] = [{"role": "system", "content": new_system_message}]

        return await inter.response.send_message("System prompt updated and chat history cleared.", ephemeral=True)

    @commands.Cog.listener("on_message")
    async def response_to_mention(self, message: disnake.Message) -> None:
        """Respond to mentions with the AI.

        Parameters
        ----------
        message : str
            _description_
        """
        if message.author == App.config("BOT_USER_OBJECT") or message.author.bot:
            return

        bot_mentioned = App.config("BOT_USER_OBJECT") in message.mentions
        message_in_dm = isinstance(message.channel, disnake.channel.DMChannel)

        if bot_mentioned or message_in_dm:
            async with message.channel.typing():
                response = await self.get_openai_response(message.author.id, message.clean_content)
                await message.channel.send(f"{message.author.mention} {response}")
