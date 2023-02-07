#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for getting the weather."""

import datetime
import logging
from types import coroutine
from typing import Tuple

import disnake
import pyowm
from disnake.ext import commands
from sqlalchemy.orm import Session

from slashbot.config import App
from slashbot.custom_cog import CustomCog
from slashbot.error import deferred_error_message
from slashbot.db import get_user
from slashbot.db import connect_to_database_engine
from slashbot.markov import generate_sentence


logger = logging.getLogger(App.config("LOGGER_NAME"))


COOLDOWN_USER = commands.BucketType.user
WEATHER_UNITS = ["metric", "imperial"]
WEATHER_COMMAND_CHOICES = ["forecast", "temperature", "rain", "wind"]


class WeatherCommands(CustomCog):
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
        self.bot = bot

        self.weather_api = pyowm.OWM(App.config("OWM_API_KEY"))
        self.city_register = self.weather_api.city_id_registry()
        self.weather_manager = self.weather_api.weather_manager()

    # Private ------------------------------------------------------------------

    @staticmethod
    def __convert_degrees_to_cardinal_direction(degrees: float) -> str:
        """Convert a degrees value to a cardinal direction.

        Parameters
        ----------
        degrees: float
            The degrees direction.

        Returns
        -------
        The cardinal direction as a string.
        """
        dirs = [
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
        idx = round(degrees / (360.0 / len(dirs)))
        return dirs[idx % 16]

    @staticmethod
    def __convert_uk_to_gb(choice: str) -> str:
        """Convert UK to GB for use in OWM.

        Parameters
        ----------
        choice: str
            The choice to convert.

        Returns
        -------
        choice: str
            The converted choice.
        """
        if choice.lower() == "uk":
            return "GB"

        return choice

    def __get_user_city(self, user_id: str, user_name: str) -> str:
        """Return the stored location set by a user.

        Parameters
        ----------
        user_id : str
            _description_
        user_name : str
            _description_

        Returns
        -------
        _type_
            _description_
        """
        with Session(connect_to_database_engine()) as session:
            user = get_user(session, user_id, user_name)

            return user.city

    def __get_country_from_location(self, user_id: str, user_name: str, location: str) -> Tuple[str, str]:
        """_summary_

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_
        location : str
            _description_

        Returns
        -------
        Tuple[str, str]
            _description_
        """
        split_location = location.split(",")  # will split london, uk etc

        if len(split_location) == 2:
            location = split_location[0].strip()
            country = split_location[1].strip().upper()
        else:
            with Session(connect_to_database_engine()) as session:
                user = get_user(session, user_id, user_name)
                country = user.country_code.upper() if user.country_code else None

        country = self.__convert_uk_to_gb(country)

        return location, country

    def __get_units_for_system(self, system: str) -> dict:
        """Get the units for the system.

        Parameters
        ----------
        system: str
            The system of units to use, either metric or imperial.

        Returns
        -------
        units: dict
            The units in use, with keys t_units, t_units_fmt, w_units,
            w_units_fmt.
        """
        if system == "imperial":
            return {
                "t_units": "fahrenheit",
                "t_units_fmt": "F",
                "w_units": "miles_hour",
                "w_units_fmt": "mph",
            }

        return {
            "t_units": "celsius",
            "t_units_fmt": "C",
            "w_units": "meters_sec",
            "w_units_fmt": "km/h",
        }

    def __add_temperature_to_embed(
        self, weather: pyowm.weatherapi25.observation.Observation, embed: disnake.Embed, units: dict
    ) -> disnake.Embed:
        """Put the temperature into the embed.

        Parameters
        ----------
        weather: pyowm.weatherapi25.observation.Observation
            The weather object.
        embed: disnake.Embed
            The embed to put the temperature into.
        units: dict
            The units to use.

        Returns
        -------
        embed: disnake.Embed
            The updated Embed.
        """

        temperature = weather.temperature(units["t_units"])
        embed.add_field(
            name="Temperature",
            value=f"{temperature['temp']:.1f} °{units['t_units_fmt']}",
            inline=False,
        )
        embed.add_field(
            name="Min/Max",
            value=f"{temperature['temp_min']:.1f}/{temperature['temp_max']:.1f} °{units['t_units_fmt']}",
            inline=False,
        )
        embed.add_field(name="Humidity", value=f"{weather.humidity:.0f}%", inline=False)

        return embed

    def __add_rain_to_embed(
        self, weather: pyowm.weatherapi25.observation.Observation, embed: disnake.Embed, _units: dict
    ) -> disnake.Embed:
        """Put the rain into the embed.

        Parameters
        ----------
        weather: pyowm.weatherapi25.observation.Observation
            The weather object.
        embed: disnake.Embed
            The embed to put the temperature into.
        _units: dict
            The units to use. Currently unused.

        Returns
        -------
        embed: disnake.Embed
            The updated Embed.
        """
        rain = weather.rain

        if not rain:
            return embed.add_field(
                name="Rain",
                value="There is no rain forecast",
                inline=False,
            )

        if "1h" in rain:
            embed.add_field(
                name="Precipitation in 1 hour",
                value=f"{rain['1h']:.1f} mm",
                inline=False,
            )
        if "3h" in rain:
            embed.add_field(
                name="Precipitation in 3 hours",
                value=f"{rain['3h']:.1f} mm",
                inline=False,
            )

        return embed

    def __add_wind_to_embed(
        self, weather: pyowm.weatherapi25.observation.Observation, embed: disnake.Embed, units: dict
    ) -> disnake.Embed:
        """Put temperature into the embed.

        Parameters
        ----------
        weather: pyowm.weatherapi25.observation.Observation
            The weather object.
        embed: disnake.Embed
            The embed to put the temperature into.
        units: dict
            The units to use.

        Returns
        -------
        embed: disnake.Embed
            The updated Embed.
        """

        wind = weather.wind(units["w_units"])

        if units["w_units"] == "meters_sec":  # convert m/s to km/h
            wind["speed"] *= 3.6

        embed.add_field(name="Wind speed", value=f"{wind['speed']:.1f} {units['w_units_fmt']}", inline=False)
        embed.add_field(
            name="Wind bearing",
            value=f"{wind['deg']:.01f}° ({self.__convert_degrees_to_cardinal_direction(wind['deg'])})",
            inline=False,
        )

        return embed

    def __add_everything_to_embed(
        self, weather: pyowm.weatherapi25.observation.Observation, embed: disnake.Embed, units: dict
    ) -> disnake.Embed:
        """Put all three observables into a single embed.

        Parameters
        ----------
        weather: pyowm.weatherapi25.observation.Observation
            The weather object.
        embed: disnake.Embed
            The embed to put the temperature into.
        units: dict
            The units to use.

        Returns
        -------
        embed: disnake.Embed
            The updated Embed.
        """

        embed = self.__add_temperature_to_embed(weather, embed, units)
        embed = self.__add_rain_to_embed(weather, embed, None)
        embed = self.__add_wind_to_embed(weather, embed, units)

        return embed

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="forecast", description="get the weather forecast")
    async def forecast(  # pylint: disable=too-many-locals
        self,
        inter: disnake.ApplicationCommandInteraction,
        city: str = commands.Param(
            description="The city to get weather at, default is your saved location.", default=None
        ),
        days: int = commands.Param(description="The number of days to get the weather for.", default=4, gt=0, lt=8),
    ) -> coroutine:
        """Print the weather forecast for a location.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        location: str
            The location to get the weather forecast for.
        days: int
            The number of days to return the forecast for.
        """
        await inter.response.defer()

        if not city:
            city = self.__get_user_city(inter.author.id, inter.author.name)
            if not city:
                return await deferred_error_message(
                    inter, "You need to either specify a city, or set your city and/or country using /set_info."
                )

        city, country = self.__get_country_from_location(inter.author.id, inter.author.name, city)
        if len(country) != 2:
            return await deferred_error_message(inter, f"{country} is not a valid 2 character country code.")

        locations_for = self.city_register.locations_for(city, country=country)

        if not locations_for:
            return await deferred_error_message(
                inter, f"The location {city}{f', {country}' if country else ''} wasn't found in OpenWeatherMap."
            )

        # locations_for returns a list of places ordered by distance
        city, location_country = locations_for[0].name, locations_for[0].country
        lat, lon = locations_for[0].lat, locations_for[0].lon

        try:
            forecast_one_call = self.weather_manager.one_call(lat, lon)
        except Exception:  # pylint: disable=broad-except
            return await deferred_error_message(
                inter, "OpenWeatherMap failed. You can check the exact error using /logfile."
            )

        embed = disnake.Embed(title=f"Weather for {city}, {location_country}", color=disnake.Color.default())

        for day in forecast_one_call.forecast_daily[:days]:
            date = datetime.datetime.utcfromtimestamp(day.reference_time())
            date = date.strftime(r"%A %d %B, %Y")
            weather = day.detailed_status.capitalize()
            temperature = day.temperature("celsius")
            wind = day.wind("miles_hour")
            embed.add_field(
                name=f"{date}",
                value=f"• {weather}\n• {temperature['max']:.1f}/{temperature['min']:.1f} °C\n"
                f"• {wind['speed']:.1f} mph",
                inline=False,
            )

        embed.set_thumbnail(url=forecast_one_call.forecast_daily[0].weather_icon_url())
        embed.set_footer(text=f"{generate_sentence(seed_word='forecast')}")

        return await inter.edit_original_message(embed=embed)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="weather", description="get the current weather")
    async def weather(
        self,
        inter: disnake.ApplicationCommandInteraction,
        city: str = commands.Param(
            description="The city to get weather for, default is your saved location.", default=None
        ),
        weather_type: str = commands.Param(
            description="The type of weather report to get.", default="forecast", choices=WEATHER_COMMAND_CHOICES
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
        where: str
            The location to get the weather for.
        what: str
            What to get, either the whole forecast, temperature, rain or wind.
        units: str
            The units to use, either metric or imperial.
        """
        await inter.response.defer()

        if not city:
            city = self.__get_user_city(inter.author.id, inter.author.name)
            if not city:
                return await deferred_error_message(
                    inter, "You need to specify a city, or set your city and/or country using /set_info."
                )

        try:
            weather_at_place = self.weather_manager.weather_at_place(city)
        except pyowm.commons.exceptions.NotFoundError:
            return await deferred_error_message(
                inter, f"OpenWeatherMap couldn't find {city}. Try separating the city and country with a comma."
            )
        except Exception:  # pylint: disable=broad-except
            return await deferred_error_message(
                inter, "OpenWeatherMap failed. You can check the exact error using /logfile."
            )

        weather = weather_at_place.weather
        units = self.__get_units_for_system(units)

        embed = disnake.Embed(
            title=f"{weather_type.capitalize()} in {weather_at_place.location.name}, {weather_at_place.location.country}",
            color=disnake.Color.default(),
        )

        match weather_type:
            case "forecast":
                embed.add_field(
                    name="Description",
                    value=f"{weather.detailed_status.capitalize()}",
                    inline=False,
                )
                embed = self.__add_everything_to_embed(weather, embed, units)
            case "temperature":
                embed = self.__add_temperature_to_embed(weather, embed, units)
            case "rain":
                embed = self.__add_rain_to_embed(weather, embed, "mm")
            case "wind":
                embed = self.__add_wind_to_embed(weather, embed, units)

        embed.set_footer(text=f"{generate_sentence(seed_word='weather')}")
        embed.set_thumbnail(url=weather.weather_icon_url())

        return await inter.edit_original_message(embed=embed)
