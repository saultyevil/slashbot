"""Commands for searching for stuff on the internet, and etc."""

import random

import aiofiles
import disnake
import wolframalpha
from disnake.ext import commands

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.settings import BotSettings


class Tools(CustomCog):  # pylint: disable=too-many-instance-attributes
    """Query information from the internet."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        bot: CustomInteractionBot,
    ) -> None:
        """Initialize the bot.

        Parameters
        ----------
        bot: CustomInteractionBot
            The bot object.

        """
        super().__init__(bot)
        self.worlfram_alpha_client = wolframalpha.Client(BotSettings.keys.wolframalpha)

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(name="die_roll", description="roll a dice")
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

    @slash_command_with_cooldown(name="wolfram", description="ask wolfram a question")
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

        results = self.worlfram_alpha_client.query(question)

        if not results["@success"]:
            async with aiofiles.open(BotSettings.file_locations.bad_words, encoding="utf-8") as file_in:
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
        num_solutions = min(num_solutions, len(results))

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


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Tools(bot))
