import base64
import io

import disnake
import openai

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.bot.custom_types import ApplicationCommandInteraction
from slashbot.errors import deferred_error_response
from slashbot.logger import logger
from slashbot.settings import BotSettings


class ImageGeneration(CustomCog):
    """Cog for generating images using OpenAI."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialise the bot.

        Parameters
        ----------
        bot : CustomInteractionBot
            The bot the cog is registered to.

        """
        super().__init__(bot)
        self.client = openai.AsyncClient(api_key=BotSettings.keys.openai)

    @slash_command_with_cooldown(
        name="generate_image",
        description="Generate an image for a given prompt.",
        guild_ids=BotSettings.discord.development_servers,
    )
    async def generate_image(self, inter: ApplicationCommandInteraction, prompt: str) -> None:
        """Generate an image for the given prompt.

        Parameters
        ----------
        inter : ApplicationCommandInteraction
            The slash command interaction to respond to.
        prompt : str
            The prompt to use to generate an image.

        """
        await inter.response.defer()
        try:
            response = await self.client.images.generate(
                model="gpt-image-1-mini", prompt=prompt, size="1024x1024", quality="low"
            )
        except Exception as exc:
            self.log_error("Unable to get response from OpenAI: %s", exc)
            await deferred_error_response(inter, "There was an issue sending your request.", delay=30)
            return

        if not response.data:
            await deferred_error_response(inter, f"There was not output for your image generation: {prompt}", delay=30)
            return
        data = response.data[0].b64_json
        if not data:
            await deferred_error_response(inter, "The AI response did not return the correct data", delay=30)
            return
        image_bytes = base64.b64decode(data)
        image_file = disnake.File(io.BytesIO(image_bytes), filename="generated_image.png")

        await inter.edit_original_message(content=f"> *Prompt*: {prompt}", file=image_file)


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.image_generation.enabled:
        logger.log_warning("%s has been disabled in the configuration file", ImageGeneration.__cog_name__)
        return
    if not BotSettings.keys.openai:
        logger.log_warning("%s has been disabled because OpenAI API key is not available", ImageGeneration.__cog_name__)
        return
    bot.add_cog(ImageGeneration(bot))
