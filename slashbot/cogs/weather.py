#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for getting the weather."""

import datetime
import json
import logging
from types import coroutine
from typing import List, Tuple

import disnake
import requests
from disnake.ext import commands
from geopy import GoogleV3

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.db import get_user_location
from slashbot.error import deferred_error_message
from slashbot.markov import MARKOV_MODEL, generate_sentences_for_seed_words
from slashbot.util import convert_radial_to_cardinal_direction

logger = logging.getLogger(App.get_config("LOGGER_NAME"))


COOLDOWN_USER = commands.BucketType.user
WEATHER_UNITS = ["metric", "imperial"]
FORECAST_TYPES = ["hourly", "daily"]
API_KEY = App.get_config("OWM_API_KEY")


class GeocodeException(Exception):
    """Geocoding API failure"""


class OneCallException(Exception):
    """OneCall API failure"""


class LocationNotFoundException(Exception):
    """Location not in OWM failure"""


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
        super().__init__()
        self.bot = bot
        self.geolocator = GoogleV3(
            api_key=App.get_config("GOOGLE_API_KEY"),
            domain="maps.google.co.uk",
        )

        self.markov_sentences = ()

    async def cog_load(self):
        """Initialise the cog.

        Currently this does:
            - create markov sentences
        """
        self.markov_sentences = (
            generate_sentences_for_seed_words(
                MARKOV_MODEL,
                ["weather", "forecast"],
                App.get_config("PREGEN_MARKOV_SENTENCES_AMOUNT"),
            )
            if self.bot.markov_gen_on
            else {"weather": [], "forecast": []}
        )
        logger.info("Generated Markov sentences for %s cog at cog load", self.__cog_name__)

    # Private ------------------------------------------------------------------

    @staticmethod
    def __get_weather_icon_url(icon_code: str) -> str:
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
    def _get_unit_strings(units: str):
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
        if units not in ["metric", "imperial"]:
            raise ValueError(f"Unknown weather units {units}")

        if units == "metric":
            temp_unit, wind_unit, wind_factor = "C", "kph", 3.6
        else:
            temp_unit, wind_unit, wind_factor = "F", "mph", 1

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

    def get_weather_for_location(self, location: str, units: str, extract_type: str | List | Tuple) -> Tuple[str, dict]:
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

        if location is None:
            raise LocationNotFoundException(f"{location} not found in Geocoding API")

        lat, lon = location.latitude, location.longitude
        address = self.get_address_from_raw(location.raw["address_components"])

        # If either the city of country are missing, send the str() of the location
        # instead which may be a bit verbose
        if address.startswith(",") or address.endswith(","):
            address = str(location)
        address += f"\n({lat}, {lon})"

        one_call_request = requests.get(
            f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&units={units}&exclude=minutely&appid={API_KEY}",
            timeout=5,
        )

        if one_call_request.status_code != 200:
            if one_call_request.status_code == 400:
                raise LocationNotFoundException(f"{location} could not be found")
            raise OneCallException(f"OneCall API failed for {location}")

        content = json.loads(one_call_request.content)
        if isinstance(extract_type, (list, tuple)):
            weather_return = {key: value for key, value in content.items() if key in extract_type}
        else:
            weather_return = content[extract_type]

        return address, weather_return

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="forecast", description="get the weather forecast")
    async def forecast(  # pylint: disable=too-many-locals, too-many-arguments
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_location: str = commands.Param(
            name="location", description="The city to get weather at, default is your saved location.", default=None
        ),
        forecast_type: str = commands.Param(
            description="The type of forecast to return.", default="daily", choices=FORECAST_TYPES
        ),
        units: str = commands.Param(
            description="The units to return weather readings in.", default="metric", choices=WEATHER_UNITS
        ),
        amount: int = commands.Param(description="The number of results to return.", default=4, gt=0, lt=7),
    ) -> coroutine:
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
            if user_location is None:
                return await deferred_error_message(
                    inter, "You need to either specify a city, or set your city and/or country using /set_info."
                )

        try:
            location, forecast = self.get_weather_for_location(user_location, units, forecast_type)
        except (LocationNotFoundException, GeocodeException):
            return await deferred_error_message(inter, f"{user_location.capitalize()} was not able to be geolocated.")
        except OneCallException:
            return await deferred_error_message(inter, "OpenWeatherMap OneCall API has returned an error.")
        except requests.Timeout:
            return await deferred_error_message(inter, "OpenWeatherMap API has timed out.")

        temp_unit, wind_unit, wind_factor = self._get_unit_strings(units)

        embed = disnake.Embed(title=f"{location}", color=disnake.Color.default())
        for sub in forecast[1 : amount + 1]:
            date = datetime.datetime.fromtimestamp(int(sub["dt"]))

            if forecast_type == "hourly":
                date_string = f"{date.strftime(r'%I:%M %p')}"
                temp_string = f"{sub['temp']:.0f} °{temp_unit}"
            else:
                date_string = f"{date.strftime(r'%a %d %b %Y')}"
                temp_string = f"{sub['temp']['min']:.0f} / {sub['temp']['max']:.0f} °{temp_unit}"

            desc_string = f"{sub['weather'][0]['description'].capitalize()}"
            wind_string = (
                f"{float(sub['wind_speed']) * wind_factor:.0f} {wind_unit} @ {sub['wind_deg']}° "
                + f"({convert_radial_to_cardinal_direction(sub['wind_deg'])})"
            )
            humidity_string = f"({sub['humidity']}% RH)"

            embed.add_field(
                name=date_string,
                value=f"{desc_string:^30s}\n{temp_string} {humidity_string:^30s}\n{wind_string:^30s}",
                inline=False,
            )

        embed.set_footer(
            text=f"{await self.get_generated_sentence('forecast')}\n(You can set your location using /set_info)"
        )
        embed.set_thumbnail(self.__get_weather_icon_url(forecast[0]["weather"][0]["icon"]))

        return await inter.edit_original_message(embed=embed)

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="weather", description="get the current weather")
    async def weather(
        self,
        inter: disnake.ApplicationCommandInteraction,
        user_location: str = commands.Param(
            name="location", description="The city to get weather for, default is your saved location.", default=None
        ),
        units: str = commands.Param(
            description="The units to return weather readings in.", default="metric", choices=WEATHER_UNITS
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
            if user_location is None:
                return await deferred_error_message(
                    inter, "You need to specify a city, or set your city and/or country using /set_info."
                )

        try:
            location, weather_return = self.get_weather_for_location(
                # user_location, units, ("current", "daily", "alerts")
                user_location,
                units,
                ("current", "alerts"),
            )
        except (LocationNotFoundException, GeocodeException):
            return await deferred_error_message(inter, f"{user_location.capitalize()} was not able to be geolocated.")
        except OneCallException:
            return await deferred_error_message(inter, "OpenWeatherMap OneCall API has returned an error.")
        except requests.Timeout:
            return await deferred_error_message(inter, "OpenWeatherMap API has timed out.")

        # daily_forecast = weather_return["daily"][0]
        weather_alerts = weather_return.get("alerts") if "alerts" in weather_return else None
        current_weather = weather_return["current"]
        temp_unit, wind_unit, wind_factor = self._get_unit_strings(units)

        embed = disnake.Embed(title=f"{location}", color=disnake.Color.default())
        embed.add_field(
            name="Description", value=current_weather["weather"][0]["description"].capitalize(), inline=False
        )
        if weather_alerts:
            now = datetime.datetime.now()
            alert_strings = []
            for alert in weather_alerts:
                alert_start = datetime.datetime.fromtimestamp(alert["start"])
                alert_end = datetime.datetime.fromtimestamp(alert["end"])
                if alert_start < now < alert_end:
                    alert_strings.append(
                        f"{alert['event']}: {alert_start.strftime(r'%H:%m')} to {alert_end.strftime(r'%H:%m')} ",
                    )
            if alert_strings:
                embed.add_field(
                    name="Weather Alert" if len(alert_strings) == 0 else "Weather Alerts",
                    value="\n".join(alert_strings),
                    inline=False,
                )
        embed.add_field(
            name="Temperature",
            value=f"{current_weather['temp']:.0f} °{temp_unit}",
            inline=True,
        )
        # embed.add_field(
        #     name="Temperature Min/Max",
        #     value=f"{daily_forecast['temp']['min']:.0f} - {daily_forecast['temp']['max']:.0f} °{temp_unit}",
        #     inline=False,
        # )
        embed.add_field(name="Humidity", value=f"{current_weather['humidity']}%", inline=False)
        embed.add_field(
            name="Wind",
            value=f"{float(current_weather['wind_speed']) * wind_factor:.0f} {wind_unit} @ "
            + f"{current_weather['wind_deg']:.0f}° ({convert_radial_to_cardinal_direction(current_weather['wind_deg'])})",
            inline=False,
        )

        embed.set_footer(
            text=f"{await self.get_generated_sentence('weather')}\n(You can set your location using /set_info)"
        )
        embed.set_thumbnail(self.__get_weather_icon_url(current_weather["weather"][0]["icon"]))

        return await inter.edit_original_message(embed=embed)


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.
    """
    bot.add_cog(Weather(bot))
