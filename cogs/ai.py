#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands related to AI generation."""

import logging

import disnake
import openai
from config import App
from disnake.ext import commands
from lib.cog import CustomCog
from lib.error import deferred_error_message
from openai.error import OpenAIError

openai.api_key = App.config("OPENAI_API_KEY")

logger = logging.getLogger(App.config("LOGGER_NAME"))

COOLDOWN_USER = commands.BucketType.user
TEXT_MODELS = [
    "text-davinci-003",
    "text-curie-001",
    "text-babbage-001",
    "text-ada-001",
]


class AI(CustomCog):  # pylint: disable=too-few-public-methods
    """A collection of commands to send AI generated messages and items."""

    def __init__(self, bot: commands.InteractionBot):
        self.bot = bot

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="generate_text", description="Generate a some text from a prompt using OpenAI")
    async def sentence_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to give to the AI generator."),
        model: str = commands.Param(description="The AI model to use.", default=TEXT_MODELS[1], choices=TEXT_MODELS),
        max_tokens: int = commands.Param(description="The maximum number of words/tokens to generate.", le=2048, gt=0),
    ):
        """Generate text from a prompt.

        Parameters
        ----------
        inter: disanke.ApplicationCommandInteraction
            The slash command interaction.
        prompt: str
            The prompt to give to the AI for generated.
        model: str
            The name of the model to use to generate text.
        max_tokens: str
            The number of tokens to be used in the model. Generally translates
            to the maximum number of words to generate.
        """
        await inter.response.defer()

        try:
            response = openai.Completion.create(
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=0.9,
                frequency_penalty=0.8,
                presence_penalty=0.8,
            )
        except OpenAIError as exc:
            logger.error("%s", exc)
            return await deferred_error_message(inter, f"The OpenAI API returned an error: {str(exc)}")

        generated = response["choices"][0]["text"]

        await inter.edit_original_message(content=generated)
