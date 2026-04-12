"""Cog for bullying people about their spelling mistakes."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.spelling.cog import Spelling
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.spelling.enabled:
        bot.log_warning("%s has been disabled in the configuration file", Spelling.__cog_name__)
        return
    bot.add_cog(Spelling(bot))
