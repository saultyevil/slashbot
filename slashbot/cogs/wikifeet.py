"""Commands for searching WikiFeet."""

import random

import disnake
import httpx
from disnake.ext import commands

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.core.database.wikifeet import WikiFeetDatabase, WikiFeetScraper
from slashbot.errors import deferred_error_message
from slashbot.settings import BotSettings


class WikiFeet(CustomCog):
    """Cog for searching WikiFeet."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialise the WikiFeet cog.

        Parameters
        ----------
        bot : CustomInteractionBot
            The bot class.

        """
        super().__init__(bot)
        self.database_init = False
        self.scraper = WikiFeetScraper()
        self.database = WikiFeetDatabase(BotSettings.cogs.wikifeet.database_url, self.scraper)

    @slash_command_with_cooldown(name="wikifeet", description="Get a random foot picture.")
    async def get_random_picture(
        self,
        inter: disnake.ApplicationCommandInteraction,
        model_name: str = commands.Param(description="The name of the model."),
    ) -> None:
        """Get a random foot picture for the provided model.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        model_name : str
            The name of the model.

        """
        await inter.response.defer()

        if not self.database_init:
            await self.database.init_database()

        try:
            model = await self.database.get_model(model_name)
            model_pictures = await self.database.get_model_pictures(model_name)
        except httpx.TimeoutException:
            await deferred_error_message(
                inter,
                f"Your request for {model_name} feet pics timed out.",
            )
            return
        except ValueError:
            await deferred_error_message(
                inter,
                f"Your request for {model_name} feet pics failed!",
            )
            return

        if not model:
            await deferred_error_message(
                inter,
                f"Unable to find {model_name} on WikiFeet",
            )
            return

        random_image = (
            "https://pics.wikifeet.com/"
            + self.scraper.make_url_model_name(model_name)
            + "-Feet-"
            + str(random.choice(model_pictures).picture_id)
            + ".jpg"
        )
        await inter.followup.send(
            f"> {model.name}\n> Foot score: {model.foot_score}\n> Shoe size : {model.shoe_size + 3 / 2}\n{random_image}"
        )


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(WikiFeet(bot))
