"""Commands designed to spam the chat with various things."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.spam.cog import Spam
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.spam.enabled:
        bot.log_warning("%s has been disabled in the configuration file", Spam.__cog_name__)
        return
    bot.add_cog(Spam(bot))
