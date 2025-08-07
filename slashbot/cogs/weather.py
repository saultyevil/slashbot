"""Commands for querying the current weather and weather forecast.

This uses OpenWeatherMap for the weather and Google to geocode the user provided
location into a latitude and longitude for OpenWeatherMap.
"""

import datetime
import json

import disnake
import requests
from disnake.ext import commands
from geopy import GoogleV3
from geopy.location import Location

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.errors import deferred_error_message
from slashbot.settings import BotSettings


class GeocodeError(Exception):
    """Raise when the Geocoding API fails."""


class OneCallError(Exception):
    """Raise when the OWM OneCall API fails."""


class LocationNotFoundError(Exception):
    """Raise when OWM cannot find the provided location."""


class NoLocationProvidedError(Exception):
    """Raise when no location was provided."""


def convert_radial_to_cardinal_direction(degrees: float) -> str:
    """Convert a degrees value to a cardinal direction.

    Parameters
    ----------
    degrees: float
        The degrees direction.

    Returns
    -------
    The cardinal direction as a string.

    """
    directions = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]

    return directions[round(degrees / (360.0 / len(directions))) % len(directions)]


WEATHER_UNITS = [
    disnake.OptionChoice("Mixed", "mixed"),
    disnake.OptionChoice("Metric", "metric"),
    disnake.OptionChoice("Imperial", "imperial"),
]


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
        self.geolocator = GoogleV3(
            api_key=BotSettings.keys.google,
            domain="maps.google.co.uk",
        )
        self.markov_seed_words = ["weather", "forecast"]

    # Private ------------------------------------------------------------------

    @staticmethod
    def get_weather_icon_url(icon_code: str) -> str:
        """Get a URL to a weather icon from OpenWeatherMap.

        Parameters
        ----------
        icon_code : str
            The icon code

        Returns
        -------
        str
            The URL top the icon.

        """
        return f"https://openweathermap.org/img/wn/{icon_code}@2x.png"

    @staticmethod
    def get_unit_strings(units: str) -> tuple[str, str, float]:
        """Get unit strings for a unit system.

        Parameters
        ----------
        units : str
            The unit system.

        Raises
        ------
        ValueError
            Raised when an unknown unit system is passed

        """
        if units not in [unit.value for unit in WEATHER_UNITS]:
            msg = f"Unknown weather units {units}"
            raise ValueError(msg)

        if units == "metric":
            temp_unit, wind_unit, wind_factor = "C", "kph", 3.6
        elif units == "mixed":
            temp_unit, wind_unit, wind_factor = "C", "mph", 2.237
        else:
            temp_unit, wind_unit, wind_factor = "F", "mph", 1.0

        return temp_unit, wind_unit, wind_factor

    @staticmethod
    def get_address_from_raw_response(raw_response: dict) -> str:
        """Convert a Google API address components into an address.

        Parameters
        ----------
        raw_response : dict
            A dictionary of address components from the Google API.

        Returns
        -------
        str
            The processed address.

        """
        locality = next((comp["long_name"] for comp in raw_response if "locality" in comp["types"]), "")
        country = next((comp["short_name"] for comp in raw_response if "country" in comp["types"]), "")
        return f"{locality}, {country}"

    @staticmethod
    def add_weather_alert_to_embed(
        embed: disnake.Embed, weather_alerts: list[dict] | None, timezone_offset: int
    ) -> disnake.Embed:
        """Add weather alerts to an embed.

        Parameters
        ----------
        embed : disnake.Embed
            The embed to add alerts to.
        weather_alerts : list[dict]
            The weather alerts, from the OneCall API.
        timezone_offset : int
            The timezone offset from UTC of the location the alerts are for.

        Returns
        -------
        disnake.Embed
            The updated embed.

        """
        if not weather_alerts:
            return embed

        now = datetime.datetime.now(tz=datetime.UTC)
        tz_offset = datetime.timedelta(seconds=timezone_offset)

        # Create alert strings but only for alerts that are active, meaning that
        # they are today
        alert_strings = []
        alert_start = datetime.datetime.now(tz=datetime.UTC)
        for alert in weather_alerts:
            alert_start = datetime.datetime.fromtimestamp(alert["start"], tz=datetime.UTC)
            alert_end = datetime.datetime.fromtimestamp(alert["end"], tz=datetime.UTC)
            if alert_start < now < alert_end:
                alert_strings.append(
                    f"{alert['event']}: {(alert_start + tz_offset).strftime(r'%H:%m')} to {(alert_end + tz_offset).strftime(r'%H:%m')} ",
                )

        # add the  string to the embed, if
        if alert_strings:
            alert_date = (alert_start + tz_offset).strftime(r"%d %B %Y")
            embed.add_field(
                name=f"Weather Alert [{alert_date}]" if len(alert_strings) == 1 else f"Weather Alerts [{alert_date}]",
                value="\n".join(alert_strings),
                inline=False,
            )

        return embed

    def call_api(self, location: str, units: str, forecast_type: str | list | tuple) -> tuple[str, dict]:
        """Query the OpenWeatherMap API for the weather.

        Parameters
        ----------
        location : str
            The location in format City, Country where country is the two letter
            country code.
        units : str
            The units to return the weather in. Either imperial or metric.
        forecast_type : str | List | Tuple
            The type of weather forecast to return. Either current, hourly or daily.

        Returns
        -------
        Tuple
            The location, as from the API, and the weather requested as a dict
            of the key provided in extract_type.

        """
        location = self.geolocator.geocode(location, region="GB")  # type: ignore
        if not location:
            msg = f"{location} not found in Geocoding API"
            raise LocationNotFoundError(msg)
        if not isinstance(location, Location):
            msg = "Location not returned in correct format"
            raise GeocodeError(msg)
        lat, lon = location.latitude, location.longitude
        location_string = self.get_address_from_raw_response(location.raw["address_components"])

        # If either the city of country are missing, send the str() of the location
        # instead which may be a bit verbose
        if location_string.startswith(",") or location_string.endswith(","):
            location_string = str(location)
        location_string += f"\n({lat}, {lon})"
        api_units = "metric" if units == "mixed" else units

        weather_response = requests.get(
            f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&units={api_units}&exclude=minutely&appid={BotSettings.keys.openweathermap}",
            timeout=5,
        )
        if weather_response.status_code != requests.codes.ok:
            if weather_response.status_code == requests.codes.not_found:
                msg = f"{location} could not be found"
                self.log_error("%s", msg)
                raise LocationNotFoundError(msg)
            msg = f"OneCall API failed for {location}"
            self.log_debug("%s", msg)
            raise OneCallError(msg)
        response_content = json.loads(weather_response.content)

        if isinstance(forecast_type, list | tuple):
            weather = {
                key: value for key, value in response_content.items() if key in forecast_type or "timezone" in key
            }
        else:
            weather = {
                f"{forecast_type}": response_content[forecast_type],
                "timezone_offset": response_content["timezone_offset"],
            }

        return location_string, weather

    async def get_weather_forecast_for_location(
        self, inter: disnake.ApplicationCommandInteraction, location: str, units: str, request_type: tuple | list | str
    ) -> tuple[str, dict]:
        """Get the weather response for a location.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        location : str
            The location to get the weather for.
        units : str
            The units to use, either metric or imperial.
        request_type : tuple | list | str
            The type of weather request to make, either daily or hourly.

        Returns
        -------
        tuple[str, dict]
            The location, as from the API, and the weather requested as a dict
            of the key provided in extract_type.

        Raises
        ------
        ValueError
            If the location is invalid, or the request type is invalid.

        """
        if not location:
            exc_msg = "No location provided to forecast"
            error_msg = "You need to either specify a city, or set your location using /set_info."
            try:
                user = await self.db.get_user(inter.user.id)
                location = user.city
            except KeyError as exc:
                await deferred_error_message(
                    inter,
                    error_msg,
                )
                raise NoLocationProvidedError(exc_msg) from exc
            if not location:
                await deferred_error_message(
                    inter,
                    error_msg,
                )
                raise NoLocationProvidedError(exc_msg)

        try:
            location, forecast = self.call_api(location, units, request_type)
        except (LocationNotFoundError, GeocodeError):
            await deferred_error_message(inter, f"Unable to find the location '{location.capitalize()}'.")
            raise
        except (OneCallError, requests.Timeout):
            await deferred_error_message(inter, "Open Weather Map did not respond to the request.")
            raise

        return location, forecast

    def add_forecast_to_embed(
        self, embed: disnake.Embed, forecast: list[dict], timezone_offset: int, units: str
    ) -> disnake.Embed:
        """Add the weather forecast to the embed.

        Parameters
        ----------
        embed : disnake.Embed
            The embed to add the forecast to.
        forecast : list[dict]
            The forecast to add to the embed.
        timezone_offset : int
            The timezone offset of the location from UTC.
        units : str
            The units to use, either "metric" or "imperial".

        Returns
        -------
        disnake.Embed
            The updated embed with the forecast added.

        """
        temp_unit, wind_unit, wind_factor = self.get_unit_strings(units)
        tz_offset = datetime.timedelta(seconds=timezone_offset)

        for sub in forecast:
            desc_string = f"{sub['weather'][0]['description'].capitalize()}"
            date = datetime.datetime.fromtimestamp(int(sub["dt"]), tz=datetime.UTC) + tz_offset
            # Daily forecasts have a summary, whilst a hourly do not
            date_string = f"{date.strftime(r'%a, %d %b %Y')}" if "summary" in sub else f"{date.strftime(r'%H:%M')}"

            # Daily forecasts provides a dict of min and max temperatures
            if isinstance(sub["temp"], dict):
                temp_string = f"{sub['temp']['min']:.0f} / {sub['temp']['max']:.0f} °{temp_unit}"
            else:
                temp_string = f"{sub['temp']} °{temp_unit}"

            humidity_string = f"({sub['humidity']}% RH)"
            wind_string = (
                f"{float(sub['wind_speed']) * wind_factor:.0f} {wind_unit} @ {sub['wind_deg']}° "
                f"({convert_radial_to_cardinal_direction(sub['wind_deg'])})"
            )
            embed.add_field(
                name=date_string,
                value=f"{desc_string:^30s}\n{temp_string} {humidity_string:^30s}\n{wind_string:^30s}",
                inline=False,
            )

        return embed

    def add_weather_conditions_to_embed(  # noqa: PLR0913
        self,
        embed: disnake.Embed,
        weather: dict,
        forecast: dict,
        alerts: list[dict] | None,
        units: str,
        tz_offset: int,
    ) -> disnake.Embed:
        """Add current weather data to an embed.

        Parameters
        ----------
        embed : disnake.Embed
            The embed to add the weather data to.
        weather : dict
            The current weather, from the OneCall API.
        forecast : dict
            The forecast, from the OneCall API.
        alerts: list[dict]
            The weather alerts, from the OneCall API.
        units : str
            The units to use, either metric or imperial.
        tz_offset : int
            The timezone offset from UTC of the location the weather is for.

        Returns
        -------
        disnake.Embed
            The updated embed with the weather data added.

        """
        temp_unit, wind_unit, wind_factor = self.get_unit_strings(units)
        feels_like = weather["feels_like"]
        temperature = weather["temp"]
        current_conditions = f"{weather['weather'][0]['description'].capitalize()}, "
        current_conditions += f"{temperature:.0f} °{temp_unit} and feels like {feels_like:.0f} °{temp_unit}"
        forecast_today = forecast["daily"][0]
        min_temp = forecast_today["temp"]["min"]
        max_temp = forecast_today["temp"]["max"]

        embed.add_field(name="Conditions", value=current_conditions, inline=False)
        self.add_weather_alert_to_embed(embed, alerts, tz_offset)
        embed.add_field(name="Temperature", value=f"{min_temp:0.0f} / {max_temp:.0f} °{temp_unit}", inline=False)
        embed.add_field(name="Humidity", value=f"{weather['humidity']}%", inline=False)
        embed.add_field(
            name="Wind",
            value=f"{float(weather['wind_speed']) * wind_factor:.0f} {wind_unit} @ "
            f"{weather['wind_deg']:.0f}° ({convert_radial_to_cardinal_direction(weather['wind_deg'])})",
            inline=False,
        )

        return embed

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(name="forecast", description="Get a the weather forecast for a location.")
    async def weather_forecast(
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
        except (NoLocationProvidedError, LocationNotFoundError, GeocodeError, OneCallError, requests.Timeout):
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
    async def weather_report(
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
        except (NoLocationProvidedError, LocationNotFoundError, GeocodeError, OneCallError, requests.Timeout):
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
    if BotSettings.keys.google and BotSettings.keys.openweathermap:
        bot.add_cog(Weather(bot))
    else:
        bot.log_error("No Google API key found, weather cog not loaded.")
