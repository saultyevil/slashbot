"""Commands for searching WikiFeet."""

import json
import random

import disnake
import httpx
from disnake.ext import commands

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown


class WikiFeet(CustomCog):
    """Cog for searching WikiFeet."""

    @staticmethod
    def _make_url_model_name(name: str) -> str:
        """Convert a model's name to the WikiFeet URL format.

        Parameters
        ----------
        name : str
            The name of the model.

        Returns
        -------
        str
            The formatted model name for the URL.

        """
        return "_".join(part.capitalize() for part in name.split())

    @staticmethod
    def _build_picture_id_list(html: str) -> list[str]:
        """Extract a list of picture IDs from the WikiFeet HTML page.

        Parameters
        ----------
        html : str
            The HTML content of the WikiFeet model page.

        Returns
        -------
        list[str]
            A list of picture IDs found in the gallery.

        """
        json_symbol = "tdata = "
        start_index = html.find(json_symbol)
        start_index = start_index + len(json_symbol) - 1
        end_index = html.find("\n", start_index) - 1
        actress_json_data_string = html[start_index:end_index]
        json_dict = json.loads(actress_json_data_string)

        pids = []
        for index, _element in enumerate(json_dict["gallery"]):
            pids.append(json_dict["gallery"][index]["pid"])

        return pids

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
        model_name = self._make_url_model_name(model_name)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"https://wikifeet.com/{model_name}", timeout=2)
            except httpx.TimeoutException:
                await inter.response.send_message(
                    f"Your request for {model_name.replace('_', ' ')} feet pics timed out.", ephemeral=True
                )
                return

        if response.status_code != httpx.codes.OK:
            await inter.response.send_message(
                f"Your request for {model_name.replace('_', ' ')} feet pics returned error code {response.status_code}.",
                ephemeral=True,
            )
            return

        try:
            picture_ids = self._build_picture_id_list(response.text)
        except KeyError:
            await inter.response.send_message(f"No feet found for {model_name.replace('_', ' ')}.", ephemeral=True)
            return
        random_image = "https://pics.wikifeet.com/" + model_name + "-Feet-" + str(random.choice(picture_ids)) + ".jpg"

        await inter.response.send_message(f"{random_image}")


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(WikiFeet(bot))
