from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.logger import logger
from slashbot.settings import BotSettings


class ImageGeneration(CustomCog):
    """Cog for generating images using OpenAI."""


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
    bot.add_cog(ImageGeneration(bot))
