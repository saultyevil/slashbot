"""Commands for searching WikiFeet."""

import random
import re

import disnake
import httpx
from disnake.ext import commands

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.core.database.wikifeet import (
    ModelNotFoundInDatabaseError,
    ModelNotFoundOnWikiFeetError,
    WikiFeetDatabase,
    WikiFeetScraper,
)
from slashbot.errors import deferred_error_message
from slashbot.settings import BotSettings

GLOBAL_WIKIFEET_DATABASE = WikiFeetDatabase(BotSettings.cogs.wikifeet.database_url, WikiFeetScraper())


async def autocomplete_model_names(_: disnake.ApplicationCommandInteraction, user_input: str) -> list[str]:
    """Auto-completion for populating with model names in the database.

    Parameters
    ----------
    _ : disnake.ApplicationCommandInteraction
        The interaction the autocompletion is for.
    user_input : str
        The user input.

    Returns
    -------
    list[str]
        A list of model names.

    """
    model_names = [name for name in await GLOBAL_WIKIFEET_DATABASE.get_model_names() if user_input in name]
    return sorted(random.sample(model_names, k=min(25, len(model_names))))


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
        self.database = GLOBAL_WIKIFEET_DATABASE

    @staticmethod
    def clean_comment_for_discord(text: str) -> str:
        """Clean up a WikiFeet comment ready for discord.

        This removes links and newline characters.

        Parameters
        ----------
        text : str
            The input text to clean up.

        Returns
        -------
        str
            The cleaned up text.

        """
        text = re.sub(r"(https?://\S+)", r"<\1>", text)
        return re.sub(r"\s+", " ", text).strip()

    @slash_command_with_cooldown(name="wikifeet", description="Get a random foot picture.")
    async def get_random_picture(
        self,
        inter: disnake.ApplicationCommandInteraction,
        model_name: str = commands.Param(description="The name of the model.", autocomplete=autocomplete_model_names),
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
        model_name_pretty = self.database.scraper.capitalise_name(model_name)

        if not self.database_init:
            await self.database.init_database()
        try:
            model = await self.database.get_model(model_name)
            model_pictures = await self.database.get_model_pictures(model.name)
            model_comments = await self.database.get_model_comments(model.name)
        except httpx.TimeoutException:
            await deferred_error_message(
                inter, f"No feet pics for you. It took too long to get them for {model_name_pretty}!"
            )
            return
        except ModelNotFoundOnWikiFeetError:
            await deferred_error_message(inter, f"Idiot, fool, fopdoodle. {model_name_pretty} is not on WikiFeet.")
            return
        except ModelNotFoundInDatabaseError:
            await deferred_error_message(inter, f"Failed to store {model_name_pretty} feet pictures... uh oh!")
            return
        except Exception as e:  # noqa: BLE001
            self.log_exception("An unknown error occurred in WikiFeet.get_random_picture()")
            await deferred_error_message(
                inter, f"An unknown error occurred trying to get delicious feet for you!!!\n>>> {e}"
            )
            return

        random_image = (
            "https://pics.wikifeet.com/"
            + self.database.scraper.make_url_model_name(model_name)
            + "-Feet-"
            + str(random.choice(model_pictures).picture_id)
            + ".jpg"
        )

        if model_comments:
            random_comment = random.choice(model_comments)
            comment = self.clean_comment_for_discord(random_comment.comment)
            comment = (
                f"> Random comment: {comment} *[{random_comment.user}"
                f"{f' - {random_comment.user_title}' if random_comment.user_title else ''}]*\n"
            )
        else:
            comment = ""

        await inter.followup.send(f"> {model.name}\n> Foot score: {model.foot_score}/5\n{comment}{random_image}")


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(WikiFeet(bot))
