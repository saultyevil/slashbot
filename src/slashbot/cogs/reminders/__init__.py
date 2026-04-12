"""Commands for setting, viewing and removing reminders."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.reminders.cog import Reminders
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.reminders.enabled:
        bot.log_warning("%s has been disabled in the configuration file", Reminders.__cog_name__)
        return
    bot.add_cog(Reminders(bot))
