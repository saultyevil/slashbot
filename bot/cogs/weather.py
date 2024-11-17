#!/usr/bin/env python3

"""Commands for getting the weather."""

import datetime
import json
import logging
from types import coroutine

import disnake
import requests
from disnake.ext import commands
from geopy import GoogleV3

from bot.custom_cog import SlashbotCog
from slashbot.config import Bot
from slashbot.db import get_user_location
from slashbot.error import deferred_error_message
from slashbot.markov import MARKOV_MODEL, generate_markov_sentences
from slashbot.util import convert_radial_to_cardinal_direction

logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))


COOLDOWN_USER = commands.BucketType.user
WEATHER_UNITS = ["mixed", "metric", "imperial"]
WEATHER_UNITS = ["mixed", "metric", "imperial"]
FORECAST_TYPES = ["hourly", "daily"]
API_KEY = Bot.get_config("OWM_API_KEY")


class GeocodeError(Exception):
    """Raise when the Geocoding API fails."""


class OneCallError(Exception):
    """Raise when the OWM OneCall API fails."""


class LocationNotFoundError(Exception):
    """Raise when OWM cannot find the provided location."""


class Weather(SlashbotCog):
    """Query information about the weather."""

    def __init__(
        self,
        bot: commands.InteractionBot,
    ) -> None:
        """Initialize the cog.

        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.

        """
        super().__init__(bot)
        self.geolocator = GoogleV3(
            api_key=Bot.get_config("GOOGLE_API_KEY"),
            domain="maps.google.co.uk",
        )

        self.premade_markov_sentences = ()

    async def cog_load(self) -> None:
        """Initialise the cog.

        Currently, this does:
            - create markov sentences
        """
        if MARKOV_MODEL:
            self.premade_markov_sentences = (
                generate_markov_sentences(
                    MARKOV_MODEL,
                    ["weather", "forecast"],
                    Bot.get_config("PREGEN_MARKOV_SENTENCES_AMOUNT"),
                )
                if self.bot.markov_gen_enabled
                else {"weather": [], "forecast": []}
            )
            logger.info("Generated Markov sentences for %s cog at cog load", self.__cog_name__)

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
        if units not in WEATHER_UNITS:
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
    def get_address_from_raw(raw: dict) -> str:
        """Convert a Google API address components into an address.

        Parameters
        ----------
        raw : dict
            A dictionary of address components from the Google API.

        Returns
        -------
        str
            The processed address.

        """
        locality = next((comp["long_name"] for comp in raw if "locality" in comp["types"]), "")
        country = next((comp["short_name"] for comp in raw if "country" in comp["types"]), "")

        return f"{locality}, {country}"

    def get_weather_for_location(self, location: str, units: str, extract_type: str | list | tuple) -> tuple[str, dict]:
        """Query the OpenWeatherMap API for the weather.

        Parameters
        ----------
        location : str
            The location in format City, Country where country is the two letter
            country code.
        units : str
            The units to return the weather in. Either imperial or metric.
        extract_type : str | List | Tuple
            The type of weather to return. Either current, hourly or daily.

        Returns
        -------
        Tuple
            The location, as from the API, and the weather requested as a dict
            of the key provided in extract_type.

        """
        location = self.geolocator.geocode(location, region="GB")

        if not location:
            msg = f"{location} not found in Geocoding API"
            raise LocationNotFoundError(msg)

        lat, lon = location.latitude, location.longitude
        address = self.get_address_from_raw(location.raw["address_components"])

        # If either the city of country are missing, send the str() of the location
        # instead which may be a bit verbose
        if address.startswith(",") or address.endswith(","):
            address = str(location)
        address += f"\n({lat}, {lon})"

        api_units = "metric" if units == "mixed" else units
        one_call_request = requests.get(
            f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&units={api_units}&exclude=minutely&appid={API_KEY}",
            timeout=5,
        )

        if one_call_request.status_code != requests.codes.ok:
            if one_call_request.status_code == requests.codes.not_found:
                msg = f"{location} could not be found"
                raise LocationNotFoundError(msg)
            msg = f"OneCall API failed for {location}"
            raise OneCallError(msg)

        content = json.loads(one_call_request.content)
        if isinstance(extract_type, list | tuple):
            weather_return = {key: value for key, value in content.items() if key in extract_type or "timezone" in key}
        else:
            weather_return = content[extract_type]

        return address, weather_return

    # Commands -----------------------------------------------------------------

    @commands.cooldown(Bot.get_config("COOLDOWN_RATE"), Bot.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="forecast", description="get the weather forecast")
    async def forecast(  # pylint: disable=too-many-locals, too-many-arguments  # noqa: PLR0913
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_location: str = commands.Param(
            name="location",
            description="The city to get weather at, default is your saved location.",
            default=None,
        ),
        forecast_type: str = commands.Param(
            description="The type of forecast to return.",
            default="daily",
            choices=FORECAST_TYPES,
        ),
        units: str = commands.Param(
            description="The units to return weather readings in.",
            default="mixed",
            choices=WEATHER_UNITS,
        ),
        amount: int = commands.Param(description="The number of results to return.", default=4, gt=0, lt=7),
    ) -> None:
        """Send the weather forecast to chat, either daily or hourly.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        user_location: str
            The location to get the weather forecast for.
        forecast_type: str
            Either daily or hourly.
        units: str
            The units to get the forecast for.
        amount: int
            The number of items to return the forecast for, e.g. 4 days or 4
            hours.

        """
        await inter.response.defer()

        if not user_location:
            user_location = get_user_location(inter.author)
            if not user_location:
                await deferred_error_message(
                    inter,
                    "You need to either specify a city, or set your city and/or country using /set_info.",
                )
                return

        try:
            location, forecast = self.get_weather_for_location(user_location, units, forecast_type)
        except (LocationNotFoundError, GeocodeError):
            await deferred_error_message(inter, f"{user_location.capitalize()} was not able to be geolocated.")
            return
        except OneCallError:
            await deferred_error_message(inter, "OpenWeatherMap OneCall API has returned an error.")
            return
        except requests.Timeout:
            await deferred_error_message(inter, "OpenWeatherMap API has timed out.")
            return

        temp_unit, wind_unit, wind_factor = self.get_unit_strings(units)

        embed = disnake.Embed(title=f"{location}", color=disnake.Color.default())
        for sub in forecast[1 : amount + 1]:
            date = datetime.datetime.fromtimestamp(int(sub["dt"]), tz=datetime.UTC)

            if forecast_type == "hourly":
                date_string = f"{date.strftime(r'%I:%M %p')}"
                temp_string = f"{sub['temp']:.0f} °{temp_unit}"
            else:
                date_string = f"{date.strftime(r'%a %d %b %Y')}"
                temp_string = f"{sub['temp']['min']:.0f} / {sub['temp']['max']:.0f} °{temp_unit}"

            desc_string = f"{sub['weather'][0]['description'].capitalize()}"
            wind_string = (
                f"{float(sub['wind_speed']) * wind_factor:.0f} {wind_unit} @ {sub['wind_deg']}° "
                f"({convert_radial_to_cardinal_direction(sub['wind_deg'])})"
            )
            humidity_string = f"({sub['humidity']}% RH)"

            embed.add_field(
                name=date_string,
                value=f"{desc_string:^30s}\n{temp_string} {humidity_string:^30s}\n{wind_string:^30s}",
                inline=False,
            )

        embed.set_footer(
            text=f"{self.get_markov_sentence('forecast')}\n(You can set your location using /set_info)",
        )
        embed.set_thumbnail(self.get_weather_icon_url(forecast[0]["weather"][0]["icon"]))

        await inter.edit_original_message(embed=embed)

    @commands.cooldown(Bot.get_config("COOLDOWN_RATE"), Bot.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="weather", description="get the current weather")
    async def weather(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_location: str = commands.Param(
            name="location",
            description="The city to get weather for, default is your saved location.",
            default=None,
        ),
        units: str = commands.Param(
            description="The units to return weather readings in.",
            default="mixed",
            choices=WEATHER_UNITS,
        ),
    ) -> coroutine:
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

        if not user_location:
            user_location = get_user_location(inter.author)
            if not user_location:
                await deferred_error_message(
                    inter,
                    "You need to specify a city, or set your city and/or country using /set_info.",
                )
                return

        try:
            location, weather_return = self.get_weather_for_location(
                user_location,
                units,
                ("current", "daily", "alerts"),
            )
        except (LocationNotFoundError, GeocodeError):
            await deferred_error_message(inter, f"{user_location.capitalize()} was not able to be geolocated.")
            return
        except OneCallError:
            await deferred_error_message(inter, "OpenWeatherMap OneCall API has returned an error.")
            return
        except requests.Timeout:
            await deferred_error_message(inter, "OpenWeatherMap API has timed out.")
            return

        logger.debug("Got weather for %s: %s", location, weather_return)

        weather_alerts = weather_return.get("alerts") if "alerts" in weather_return else None
        current_weather = weather_return["current"]
        forecast_today = weather_return["daily"][0]
        temp_unit, wind_unit, wind_factor = self.get_unit_strings(units)

        temperature = current_weather["temp"]
        feels_like = current_weather["feels_like"]
        current_conditions = f"{current_weather['weather'][0]['description'].capitalize()}, "
        current_conditions += f"{temperature:.0f} °{temp_unit} and feels like {feels_like:.0f} °{temp_unit}"

        embed = disnake.Embed(title=f"{location}", color=disnake.Color.default())
        embed.add_field(name="Conditions", value=current_conditions, inline=False)
        # todo: make this a function
        if weather_alerts:
            now = datetime.datetime.now(tz=datetime.UTC)
            alert_strings = []
            tz_offset = datetime.timedelta(seconds=weather_return["timezone_offset"])
            for alert in weather_alerts:
                alert_start = datetime.datetime.fromtimestamp(alert["start"], tz=datetime.UTC)
                alert_end = datetime.datetime.fromtimestamp(alert["end"], tz=datetime.UTC)
                if alert_start < now < alert_end:
                    alert_strings.append(
                        f"{alert['event']}: {(alert_start + tz_offset).strftime(r'%H:%m')} to {(alert_end + tz_offset).strftime(r'%H:%m')} ",
                    )
            if alert_strings:
                alert_date = (alert_start + tz_offset).strftime(r"%d %B %Y")
                embed.add_field(
                    name=f"Weather Alert [{alert_date}]"
                    if len(alert_strings) == 1
                    else f"Weather Alerts [{alert_date}]",
                    value="\n".join(alert_strings),
                    inline=False,
                )
        min_temp = forecast_today["temp"]["min"]
        max_temp = forecast_today["temp"]["max"]
        embed.add_field(name="Temperature", value=f"{min_temp:0.0f} / {max_temp:.0f} °{temp_unit}", inline=False)
        embed.add_field(name="Humidity", value=f"{current_weather['humidity']}%", inline=False)
        embed.add_field(
            name="Wind",
            value=f"{float(current_weather['wind_speed']) * wind_factor:.0f} {wind_unit} @ "
            f"{current_weather['wind_deg']:.0f}° ({convert_radial_to_cardinal_direction(current_weather['wind_deg'])})",
            inline=False,
        )

        embed.set_footer(
            text=f"{self.get_markov_sentence('weather')}\n(You can set your location using /set_info)",
        )
        embed.set_thumbnail(self.get_weather_icon_url(current_weather["weather"][0]["icon"]))

        await inter.edit_original_message(embed=embed)


def setup(bot: commands.InteractionBot) -> None:
    """Set up the cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Weather(bot))
