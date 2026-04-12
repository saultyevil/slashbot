"""Commands for interacting with the Markov Chain text generator."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.markov.cog import Markov
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.markov.enabled:
        bot.log_warning("%s has been disabled in the configuration file", Markov.__cog_name__)
        return
    bot.add_cog(Markov(bot))
