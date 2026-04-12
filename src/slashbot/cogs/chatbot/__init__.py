"""Text generation AI chatbot."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.chatbot.cog import ChatBot
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.chatbot.enabled:
        bot.log_warning("%s has been disabled in the configuration file", ChatBot.__cog_name__)
        return
    try:
        bot.add_cog(ChatBot(bot))
    except:  # noqa: E722
        bot.log_error("Failed to initialise ArtificialIntelligence cog, probably due to a missing API key")
