"""Commands for querying the current weather and weather forecast.

This uses OpenWeatherMap for the weather and Google to geocode the user provided
location into a latitude and longitude for OpenWeatherMap.
"""

import disnake
import httpx
from disnake.ext import commands

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.settings import BotSettings


class Weather(CustomCog):
    """Query information about the weather."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialize the cog.

        Parameters
        ----------
        bot: CustomInteractionBot
            The bot object.

        """
        super().__init__(bot)
        self.markov_seed_words = ["weather", "forecast"]

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(name="forecast", description="Get a the weather forecast for a location.")
    async def forecast(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_location: str = commands.Param(
            name="location",
            description="The location to get the forecast for, default is your saved location.",
            default=None,
        ),
        forecast_type: str = commands.Param(
            name="type", description="The forecast type to return.", choices=["daily", "hourly"], default="daily"
        ),
        amount: int = commands.Param(
            name="amount", description="The number of results to return.", default=3, gt=0, lt=8
        ),
        units: str = commands.Param(
            description="The units to return weather readings in.",
            default="mixed",
            choices=WEATHER_UNITS,
        ),
    ) -> None:
        """Send the weather forecast to chat, either daily or hourly.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        user_location: str
            The location to get the weather forecast for.
        forecast_type: str
            The type of forecast to get, either daily or hourly.
        amount: int
            The number of items to return the forecast for, e.g. 4 days or 4
            hours.
        units: str
            The units to get the forecast for.

        """
        await inter.response.defer()

        try:
            location, forecast = await self.get_weather_forecast_for_location(
                inter, user_location, units, forecast_type
            )
        except (NoLocationProvidedError, LocationNotFoundError, GeocodeError, OneCallError, httpx.TimeoutException):
            return

        embed = disnake.Embed(title=f"{location}", color=disnake.Color.default())
        embed.set_footer(
            text=f"{self.get_random_markov_sentence('forecast', 1)}\n(You can set your location using /set_info)",
        )
        embed.set_thumbnail(self.get_weather_icon_url(forecast[forecast_type][0]["weather"][0]["icon"]))
        embed = self.add_forecast_to_embed(
            embed, forecast[forecast_type][0 : amount + 1], forecast["timezone_offset"], units
        )

        await inter.edit_original_message(embed=embed)

    @slash_command_with_cooldown(name="weather", description="Get a weather report for a location.")
    async def current(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_location: str = commands.Param(
            name="location",
            description="The location to get the weather for, default is your saved location.",
            default=None,
        ),
        units: str = commands.Param(
            description="The units to return weather readings in.",
            default="mixed",
            choices=WEATHER_UNITS,
        ),
    ) -> None:
        """Get the weather for a location.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        user_location: str
            The location to get the weather for.
        units: str
            The units to use, either metric or imperial.

        """
        await inter.response.defer()

        try:
            location, weather_return = await self.get_weather_forecast_for_location(
                inter, user_location, units, ["current", "daily", "alerts"]
            )
        except (NoLocationProvidedError, LocationNotFoundError, GeocodeError, OneCallError, httpx.TimeoutException):
            return

        embed = disnake.Embed(title=f"{location}", color=disnake.Color.default())
        embed.set_footer(
            text=f"{self.get_random_markov_sentence('weather', 1)}\n(You can set your location using /set_info)",
        )
        embed.set_thumbnail(self.get_weather_icon_url(weather_return["current"]["weather"][0]["icon"]))
        embed = self.add_weather_conditions_to_embed(
            embed,
            weather_return["current"],
            weather_return,
            weather_return.get("alerts"),
            units,
            weather_return["timezone_offset"],
        )

        await inter.edit_original_message(embed=embed)


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
        bot.log_error("No Google API key found, weather cog not loaded.")
