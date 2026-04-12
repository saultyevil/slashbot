"""Commands for tracking media logging, such as Letterboxd."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.media_tracker.cog import MediaTrackers
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.media_tracker.enabled:
        bot.log_warning("%s has been disabled in the configuration file", MediaTrackers.__cog_name__)
        return
    bot.add_cog(MediaTrackers(bot))
