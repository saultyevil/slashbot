#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""AI stuff"""

import logging
import disnake
from disnake.ext import commands
import openai
from openai.error import OpenAIError
from config import App

from lib.error import deferred_error_message
from lib.cog import CustomCog

cd_user = commands.BucketType.user
logger = logging.getLogger(App.config("LOGGER_NAME"))
openai.api_key = App.config("OPENAI_API_KEY")


class AI(CustomCog):
    """DocString for AI cog."""

    def __init__(self, bot: commands.InteractionBot, ai_model: str = "text-davinci-003", max_token: int = 500):
        self.bot = bot
        self.ai_model = ai_model
        self.max_tokens = max_token

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="generate_text", description="Generate a sentence using AI")
    async def sentence_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The pormpt to give to the AI generator."),
    ):
        """Generate a sentence from a pormpt

        Parameters
        ----------
        inter

        prompt: str
            The prompt to give to the AI for generated.
        """
        await inter.response.defer()

        try:
            response = openai.Completion.create(
                prompt=prompt,
                max_tokens=self.max_tokens,
                model=self.ai_model,
                temperature=0.9,
                frequency_penalty=0.8,
                presence_penalty=0.8,
            )
        except OpenAIError as exc:
            logger.error("%s", exc)
            return await deferred_error_message(inter, "API returned an error")

        generated = response["choices"][0]["text"]

        await inter.edit_original_message(content=generated)
