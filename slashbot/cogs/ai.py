#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands related to AI generation."""

import logging

import disnake
import openai
from disnake.ext import commands
from openai.error import OpenAIError

from slashbot.config import App
from slashbot.custom_cog import CustomCog
from slashbot.error import deferred_error_message

openai.api_key = App.config("OPENAI_API_KEY")
logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


class AICommands(CustomCog):  # pylint: disable=too-few-public-methods
    """A collection of commands to send AI generated messages and items."""

    def __init__(self, bot: commands.InteractionBot):
        self.bot = bot

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="generate_text", description="Generate a some text from a prompt using OpenAI")
    async def sentence_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to give to the AI generator."),
        max_tokens: int = commands.Param(
            description="The maximum number of words/tokens to generate.", le=1024, gt=0, default=200
        ),
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
                model="text-davinci-003",
                max_tokens=max_tokens,
                temperature=0.9,
                frequency_penalty=0.8,
                presence_penalty=0.8,
            )
        except OpenAIError as exc:
            logger.error("%s", exc)
            return await deferred_error_message(inter, f"The OpenAI API returned an error: {str(exc)}")

        generated = response["choices"][0]["text"].lstrip("\n")
        message = f"> {prompt}\n{generated}"

        if len(message) > 2000:
            message = message[:1900] + "...\n*...and the rest is cut off by discord..."

        await inter.edit_original_message(content=message)
