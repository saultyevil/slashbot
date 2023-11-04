#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for searching for stuff on the internet, and etc."""

import logging
import random
from types import coroutine

import disnake
import wolframalpha
from disnake.ext import commands
from sqlalchemy.orm import Session

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.db import BadWord, connect_to_database_engine
from slashbot.markov import MARKOV_MODEL, generate_sentences_for_seed_words

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


class Info(SlashbotCog):  # pylint: disable=too-many-instance-attributes
    """Query information from the internet."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        bot: commands.InteractionBot,
        attempts: int = 10,
    ) -> None:
        """Initialize the bot.
        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.
        attempts: int
            The number of attempts to try and generate a sentence for.
        """
        super().__init__()
        self.bot = bot
        self.attempts = attempts
        self.wolfram_api = wolframalpha.Client(App.config("WOLFRAM_API_KEY"))
        self.markov_sentences = (
            generate_sentences_for_seed_words(
                MARKOV_MODEL,
                ["wolfram"],
                App.config("PREGEN_MARKOV_SENTENCES_AMOUNT"),
            )
            if self.bot.markov_gen_on
            else {"wolfram": []}
        )

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="die_roll", description="roll a dice")
    async def die_roll(
        self,
        inter: disnake.ApplicationCommandInteraction,
        num_sides: int = commands.Param(default=6, description="The number of sides to the dice.", min_value=1),
    ) -> coroutine:
        """Roll a random number from 1 to num_sides.

        Parameters
        ----------
        num_sides: int
            The number of sides of the dice.
        """
        return await inter.response.send_message(f"{inter.author.name} rolled a {random.randint(1, int(num_sides))}.")

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
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
        num_solutions: int
            The number of solutions to return.
        """
        await inter.response.defer()
        embed = disnake.Embed(title="Stephen Wolfram says...", color=disnake.Color.default())
        embed.set_footer(text=f"{self.get_generated_sentence('wolfram')}")
        embed.set_thumbnail(
            url=r"https://upload.wikimedia.org/wikipedia/commons/4/44/Stephen_Wolfram_PR_%28cropped%29.jpg"
        )

        results = self.wolfram_api.query(question)

        if not results["@success"]:
            with Session(connect_to_database_engine()) as session:
                bad_word = random.choice(session.query(BadWord).all()).word
            embed.add_field(
                name=f"{question}",
                value=f"You {bad_word}, you asked a question Stephen Wolfram couldn't answer.",
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


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.
    """
    bot.add_cog(Info(bot))
