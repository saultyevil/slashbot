"""Commands for searching for stuff on the internet, and etc."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.tools.cog import Tools
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.tools.enabled:
        bot.log_warning("%s has been disabled in the configuration file", Tools.__cog_name__)
        return
    bot.add_cog(Tools(bot))
