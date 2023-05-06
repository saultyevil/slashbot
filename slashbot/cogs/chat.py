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


class Chat(CustomCog):
    """Chat tools for the bot."""

    def __init__(self, bot):
        super().__init__()
        self.bot: ModifiedInteractionBot = bot
        self.bot_user = None
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
        if history_id not in self.chat_history:
            self.chat_history[history_id] = []

        message = message.replace("@Margaret", "", 1)
        self.chat_history[history_id].append(f"You: {message}".strip())
        prompt = "\n".join(self.chat_history[history_id])
        logging.info("Prompt: %s", prompt)

        # Call the OpenAI API to generate a response to the prompt, using the chat log to maintain context
        response = openai.Completion.create(
            # engine="babbage",
            engine="davinci",
            prompt=prompt,
            temperature=0.5,
            max_tokens=500,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
        )

        response = response.choices[0].text.replace("AI:", "", 1).strip()
        response = re.sub(r"\n+", "\n", response)
        self.chat_history[history_id].append(f"AI: {response}")

        return response

    @commands.slash_command(name="forget_history", description="reset your AI chat history")
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
        if inter.author.id not in self.chat_history:
            return
        self.chat_history[inter.author.id].clear()

        return await inter.response.send_message("Message history has been reset.")

    @commands.Cog.listener("on_message")
    async def response_to_mention(self, message: disnake.Message) -> None:
        """Respond to mentions with the AI.

        Parameters
        ----------
        message : str
            _description_
        """
        if not self.bot_user:
            self.bot_user = await self.bot.fetch_user(App.config("ID_BOT"))

        if message.author == self.bot_user:
            return

        if self.bot_user not in message.mentions:
            return

        response = await self.get_openai_response(message.author.id, message.clean_content)
        await message.channel.send(f"{message.author.mention} {response}")
