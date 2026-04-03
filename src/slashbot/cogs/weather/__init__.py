"""Weather commands."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.weather.cog import Weather
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up the cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.weather.enabled:
        bot.log_warning("%s has been disabled in the configuration file", Weather.__cog_name__)
        return

    if BotSettings.keys.google and BotSettings.keys.openweathermap:
        bot.add_cog(Weather(bot))
    else:
        bot.log_error("Missing API keys; weather cog not loaded.")
