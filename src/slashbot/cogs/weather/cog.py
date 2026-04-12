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
from slashbot.cogs.weather.embed import WeatherEmbedBuilder
from slashbot.cogs.weather.service import (
    GeocodeError,
    LocationNotFoundError,
    OneCallError,
    ResolvedLocation,
    WeatherService,
    get_unit_config,
    parse_active_alerts,
    parse_current_weather,
    parse_daily_forecasts,
    parse_hourly_forecasts,
)
from slashbot.errors import deferred_error_response

WEATHER_UNITS = ["metric", "imperial", "mixed"]


class Weather(CustomCog):
    """Weather slash commands for Discord."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot: CustomInteractionBot
            The bot object.

        """
        super().__init__(bot)
        self.service = WeatherService()
        self.markov_seed_words = ["weather", "forecast"]

    async def _get_weather_for_location(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_location: str | None,
        units: str,
        fields: str | list[str],
    ) -> tuple[ResolvedLocation, dict]:
        """Resolve the location and fetch raw data from the service layer.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The weather forecast interaction.
        user_location : str | None
            The location provided by the user, or None. If None, the database
            is queried (using data in the interaction) for their default
            location.
        units : str
            The choice of units for the weather.
        fields : str | list[str]
            The fields/information to get from the weather service.

        Returns
        -------
        ResolvedLocation
            A ResolvedLocation object for the location requested.
        data : dict
            The return from the weather service as a JSON/dict.

        """
        query = user_location
        error_msg = "Please provide a location or set one with `/set_info`"

        if not query:
            try:
                user = await self.get_user_db_from_inter(inter)
                query = user.city
            except KeyError as exc:
                await deferred_error_response(
                    inter,
                    error_msg,
                )
                raise LocationNotFoundError(error_msg) from exc

            if not query:
                await deferred_error_response(
                    inter,
                    error_msg,
                )
                raise LocationNotFoundError(error_msg)

        loc = self.service.resolve_location(query)
        data = await self.service.fetch_weather(loc, units, fields)

        return loc, data

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(name="forecast", description="Get the weather forecast for a location.")
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
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        user_location : str
            The optional location to get the forecast for. If not provided, the
            default value saved for the user is used.
        forecast_type : str
            The type of forecast to get. Either hourly or daily.
        amount : int
            The number of results to return.
        units : str
            The units to return the weather in.

        """
        await inter.response.defer()

        try:
            loc, data = await self._get_weather_for_location(inter, user_location, units, [forecast_type])
            unit_cfg = get_unit_config(units)
            tz_offset = data["timezone_offset"]
            footer = f"{self.get_random_markov_sentence('forecast', 1)}\n(You can set your location using /set_info)"

            if forecast_type == "daily":
                forecasts = parse_daily_forecasts(data["daily"], tz_offset)[:amount]
                embed = WeatherEmbedBuilder.daily_forecast(loc.display, forecasts, unit_cfg, footer)
            else:
                forecasts = parse_hourly_forecasts(data["hourly"], tz_offset)[:amount]
                embed = WeatherEmbedBuilder.hourly_forecast(loc.display, forecasts, unit_cfg, footer)

            await inter.edit_original_message(embed=embed)

        except (GeocodeError, LocationNotFoundError, OneCallError, httpx.TimeoutException) as exc:
            # Only send error if the helper hasn't already handled the message
            await deferred_error_response(inter, f"Error: {exc}")

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
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        user_location : str
            The optional location to get the forecast for. If not provided, the
            default value saved for the user is used.
        units : str
            The units to return the weather in.

        """
        await inter.response.defer()

        try:
            loc, data = await self._get_weather_for_location(
                inter, user_location, units, ["current", "daily", "alerts"]
            )
            unit_cfg = get_unit_config(units)
            tz_offset = data["timezone_offset"]

            current_weather = parse_current_weather(data["current"])
            daily_forecasts = parse_daily_forecasts(data["daily"], tz_offset)
            alerts = parse_active_alerts(data.get("alerts"), tz_offset)

            footer = f"{self.get_random_markov_sentence('weather', 1)}\n(You can set your location using /set_info)"

            embed = WeatherEmbedBuilder.current(loc.display, current_weather, daily_forecasts, alerts, unit_cfg, footer)
            await inter.edit_original_message(embed=embed)

        except (GeocodeError, LocationNotFoundError, OneCallError, httpx.TimeoutException) as exc:
            await deferred_error_response(inter, f"Error: {exc}")
