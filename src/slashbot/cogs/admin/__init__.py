"""Commands for administrating the server."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.admin.cog import AdminTools
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.admin.enabled:
        bot.log_warning("%s has been disabled in the configuration file", AdminTools.__cog_name__)
        return
    bot.add_cog(AdminTools(bot))
