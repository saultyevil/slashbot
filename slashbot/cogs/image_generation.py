"""AI chat and text-to-image features.

The purpose of this cog is to enable AI features in the Discord chat. This
currently implements AI chat/vision using ChatGPT and Claude, as well as
text-to-image generation using Monster API.
"""

from __future__ import annotations

import logging

import requests
from disnake.ext import commands
from slashlib.config import Bot
from slashlib.image_generation import retrieve_image_request, send_image_request
from slashlib.types import ApplicationCommandInteraction  # noqa: TCH001

from slashbot.custom_cog import SlashbotCog
from slashbot.custom_command import slash_command_with_cooldown

LOGGER = logging.getLogger(Bot.get_config("LOGGER_NAME"))


class ImageGeneration(SlashbotCog):
    """Cog for text to image generation using Monster API."""

    @slash_command_with_cooldown(description="Generate an image from a text prompt.")
    async def text_to_image(
        self,
        inter: ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to generate an image for"),
        steps: int = commands.Param(default=30, ge=30, lt=500, description="The number of sampling steps"),
        aspect_ratio: str = commands.Param(
            default="square",
            choices=["square", "landscape", "portrait"],
            description="The aspect ratio of the image",
        ),
    ) -> None:
        """Generate an image from a text prompt.

        Uses Monster API. The request to the API is not made asynchronously.

        Parameters
        ----------
        inter : ApplicationCommandInteraction
            The interaction to respond to.
        prompt : str, optional
            The prompt to generate an image for.
        steps : int, optional
            The number of sampling steps
        aspect_ratio : str, optional
            The aspect ratio of the image.

        """
        next_interaction = inter.followup
        await inter.response.defer(ephemeral=True)

        try:
            process_id, response = send_image_request(prompt, steps, aspect_ratio)
        except requests.exceptions.Timeout:
            await inter.edit_original_message(content="The image generation API took too long to respond.")
            return
        if not process_id:
            LOGGER.error("Image generation request did not return a process ID: %s", response)
            await inter.edit_original_message(f"There was an error when submitting your request: {response}.")
            return
        await inter.edit_original_message(content=f"Request submitted with process ID {process_id}")

        status, result = await retrieve_image_request(process_id)
        if status == "COMPLETED":
            await next_interaction.send(f'{inter.author.display_name}\'s request for "{prompt}" {result}')
        if status == "FAILED":
            next_interaction.send(f'Your request ({process_id}) for "{prompt}" failed due to: {result}', ephemeral=True)


def setup(bot: commands.InteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    key = Bot.get_config("MONSTER_API_KEY")
    if key:
        bot.add_cog(ImageGeneration(bot))
    else:
        LOGGER.error("No API key for Monster AI, not loading image generation cog")
