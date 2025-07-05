import json
import random

import disnake
import httpx
from disnake.ext import commands

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown


class JSONExtractor:
    """Class for extracting javascript associated array."""

    js_variable = "tdata = "

    def __init__(self, text=""):
        self.text = text

    def get_json_dict(self) -> dict:
        # pinpointing the exact location of the json dictionary containing the picture ids
        start_index = self.text.find(self.js_variable)
        start_index = start_index + len(self.js_variable) - 1
        end_index = self.text.find("\n", start_index) - 1
        actress_json_data_string = self.text[start_index:end_index]
        return json.loads(actress_json_data_string)


class WikiFeet(CustomCog):
    """Cog for searching WikiFeet."""

    @staticmethod
    def _create_model_name(name: str) -> str:
        return "_".join(part.capitalize() for part in name.split())

    @staticmethod
    def _build_pid_list(json_dict: dict) -> list[str]:
        pids = []
        for index, _element in enumerate(json_dict["gallery"]):
            pids.append(json_dict["gallery"][index]["pid"])
        pids.sort()

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
        model_name = self._create_model_name(model_name)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"https://wikifeet.com/{model_name}", timeout=2)
            except httpx.TimeoutException:
                await inter.response.send_message(f"Your request for {model_name} feet pics timed out.", ephemeral=True)
                return

        if response.status_code != httpx.codes.OK:
            await inter.response.send_message(
                f"Your request for {model_name} feet pics returned error code {response.status_code}", ephemeral=True
            )
            return

        json_extractor = JSONExtractor(response.text)
        extracted_json = json_extractor.get_json_dict()
        try:
            pids = self._build_pid_list(extracted_json)
        except KeyError:
            await inter.response.send_message(f"No feet found for {model_name}", ephemeral=True)
            return

        random_pid = random.choice(pids)
        link = "https://pics.wikifeet.com/" + model_name + "-Feet-" + str(random_pid) + ".jpg"

        await inter.response.send_message(f"{link}")


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(WikiFeet(bot))
