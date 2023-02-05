#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for searching for stuff on the internet, and etc."""

import logging
import random
from types import coroutine
from typing import List

import disnake
import wolframalpha
from disnake.ext import commands

from slashbot.config import App
from slashbot.cog import CustomCog

logger = logging.getLogger(App.config("LOGGER_NAME"))
cd_user = commands.BucketType.user


class Info(CustomCog):  # pylint: disable=too-many-instance-attributes
    """Query information from the internet."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        bot: commands.InteractionBot,
        generate_sentence: callable,
        bad_words: List[str],
        god_words: List[str],
        attempts: int = 10,
    ) -> None:
        """Initialize the bot.
        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.
        generate_sentence: callable
            A function to generate sentences given a seed word.
        bad_words: List[str]
            A list of bad words.
        god_words: List[str]
            A list of god words
        attempts: int
            The number of attempts to try and generate a sentence for.
        """
        self.bot = bot
        self.generate_sentence = generate_sentence
        self.attempts = attempts
        self.bad_words = bad_words
        self.god_words = god_words
        self.user_data = App.config("USER_INFO_FILE_STREAM")

        self.wolfram_api = wolframalpha.Client(App.config("WOLFRAM_API_KEY"))

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="roll", description="roll a dice")
    async def roll(
        self,
        inter: disnake.ApplicationCommandInteraction,
        num_sides: int = commands.Param(default=6, description="The number of sides to the dice.", min_value=1),
    ) -> coroutine:
        """Roll a random number from 1 to num_sides.

        Parameters
        ----------
        n: int
            The number of sides of the dice.
        """
        return await inter.response.send_message(f"{inter.author.name} rolled a {random.randint(1, int(num_sides))}.")

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="wolfram", description="ask wolfram a question")
    async def wolfram(
        self,
        inter: disnake.ApplicationCommandInteraction,
        question: str = commands.Param(description="The question to ask Stephen Wolfram."),
        num_solutions: int = commands.Param(default=1, description="The number of solutions to display.", min_value=1),
    ) -> coroutine:
        """Submit a query to wolfram alpha.

        Parameters
        ----------
        question: str
            The question to ask.
        n_solutions: int
            The number of solutions to return.
        """
        await inter.response.defer()
        embed = disnake.Embed(title="Stephen Wolfram says...", color=disnake.Color.default())
        embed.set_footer(text=f"{self.generate_sentence('wolfram')}")
        embed.set_thumbnail(
            url=r"https://upload.wikimedia.org/wikipedia/commons/4/44/Stephen_Wolfram_PR_%28cropped%29.jpg"
        )

        results = self.wolfram_api.query(question)

        if not results["@success"]:
            embed.add_field(
                name=f"{question}",
                value=f"You {random.choice(self.bad_words)}, you asked a question Stephen Wolfram couldn't answer.",
                inline=False,
            )
            return await inter.edit_original_message(embed=embed)

        # only go through the first N results to add to embed

        results = list(results.pods)

        num_solutions += 1
        if num_solutions > len(results):
            num_solutions = len(results)

        for n_sol, result in enumerate(results[1:num_solutions]):
            # have to check if the result is a list of results, or just a single result
            # probably a better way to do this
            if isinstance(result["subpod"], list):
                result = result["subpod"][0]["plaintext"]
            else:
                result = result["subpod"]["plaintext"]

            if n_sol == 0:
                embed.add_field(name=f"{question}", value=result, inline=False)
            else:
                embed.add_field(name=f"Result {n_sol}", value=result, inline=False)

        return await inter.edit_original_message(embed=embed)
