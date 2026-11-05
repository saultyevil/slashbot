"""Archive of chat messages used to train the Markov chain."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.message_archive.cog import MessageArchive
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.message_archive.enabled:
        bot.log_warning("%s has been disabled in the configuration file", MessageArchive.__cog_name__)
        return
    bot.add_cog(MessageArchive(bot))
