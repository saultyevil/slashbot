#!/usr/bin/env python3

"""Commands for searching for stuff on the internet, and etc."""

import logging
import random

import aiofiles
import disnake
import wolframalpha
from disnake.ext import commands

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog

logger = logging.getLogger(App.get_config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


class Tools(SlashbotCog):  # pylint: disable=too-many-instance-attributes
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
        super().__init__(bot)
        self.attempts = attempts
        self.wolfram_api = wolframalpha.Client(App.get_config("WOLFRAM_API_KEY"))
        self.markov_sentences = ()

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="die_roll", description="roll a dice")
    async def die_roll(
        self,
        inter: disnake.ApplicationCommandInteraction,
        num_sides: int = commands.Param(default=6, description="The number of sides to the dice.", min_value=1),
    ) -> None:
        """Roll a random number from 1 to num_sides.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        num_sides: int
            The number of sides of the dice.

        """
        await inter.response.send_message(f"{inter.author.name} rolled a {random.randint(1, int(num_sides))}.")

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="wolfram", description="ask wolfram a question")
    async def wolfram(
        self,
        inter: disnake.ApplicationCommandInteraction,
        question: str = commands.Param(description="The question to ask Stephen Wolfram."),
        num_solutions: int = commands.Param(default=1, description="The number of solutions to display.", min_value=1),
    ) -> None:
        """Submit a query to wolfram alpha.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        question: str
            The question to ask.
        num_solutions: int
            The number of solutions to return.

        """
        await inter.response.defer()
        embed = disnake.Embed(title="Stephen Wolfram says...", color=disnake.Color.default())
        embed.set_thumbnail(
            url=r"https://upload.wikimedia.org/wikipedia/commons/4/44/Stephen_Wolfram_PR_%28cropped%29.jpg",
        )

        results = self.wolfram_api.query(question)

        if not results["@success"]:
            async with aiofiles.open(App.get_config("BAD_WORDS_FILE"), encoding="utf-8") as file_in:
                bad_word = (await file_in.readlines())[random.randint(0, num_solutions - 1)].strip()
            embed.add_field(
                name=f"{question}",
                value=f"You {bad_word.strip()}, you asked a question Stephen Wolfram couldn't answer.",
                inline=False,
            )
            await inter.edit_original_message(embed=embed)
            return

        # only go through the first N results to add to embed
        results = list(results.pods)
        num_solutions += 1
        if num_solutions > len(results):
            num_solutions = len(results)

        # The first result is the question, and the rest are the results
        for n_sol, result in enumerate(results[1:num_solutions]):
            # have to check if the result is a list of results, or just a single result
            # probably a better way to do this
            if isinstance(result["subpod"], list):
                this_result = result["subpod"][0]["plaintext"]
            else:
                this_result = result["subpod"]["plaintext"]

            if n_sol == 0:
                embed.add_field(name=f"{question}", value=this_result, inline=False)
            else:
                embed.add_field(name=f"Result {n_sol}", value=this_result, inline=False)

        await inter.edit_original_message(embed=embed)


def setup(bot: commands.InteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Tools(bot))
