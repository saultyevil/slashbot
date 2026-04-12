"""Commands for remembering user info."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.users.cog import UserInfo
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.users.enabled:
        bot.log_warning("%s has been disabled in the configuration file", UserInfo.__cog_name__)
        return
    bot.add_cog(UserInfo(bot))
