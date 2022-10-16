#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import json
import logging

import disnake
import pyowm
from disnake.ext import commands
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

logger = logging.getLogger("slashbot")

import config

cd_user = commands.BucketType.user
weather_units = ["metric", "imperial"]
weather_choices = ["forecast", "temperature", "rain", "wind"]


def degrees_to_cardinal(d):
    """
    note: this is highly approximate...
    """
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    ix = round(d / (360.0 / len(dirs)))
    return dirs[ix % 16]


def owm_convert_uk_to_gb(_, choice: str) -> str:
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
        return "gb"
    return choice


class Weather(commands.Cog):
    """Query information about the weather."""

    def __init__(
        self,
        bot,
        generate_sentence,
    ):
        self.bot = bot
        self.generate_sentence = generate_sentence

        self.weather_api = pyowm.OWM(config.OWN_API_KEY)
        self.weather_api_city_register = self.weather_api.city_id_registry()
        self.weather_api_manager = self.weather_api.weather_manager()

        with open("data/users.json", "r", encoding="utf-8") as fp:
            self.userdata = json.load(fp)

        def on_modify(_):
            with open(config.USERS_FILES, "r", encoding="utf-8") as fp:
                self.userdata = json.load(fp)
            logger.info("Reloaded userdata")

        observer = Observer()
        event_handler = PatternMatchingEventHandler(["*"], None, False, True)
        event_handler.on_modified = on_modify
        observer.schedule(event_handler, config.USERS_FILES, False)
        observer.start()

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, inter):
        """Reset the cooldown for some users and servers."""
        if inter.guild and inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOLDOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Commands -----------------------------------------------------------------

    def get_units_for_system(self, system):
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

    def _add_temperature_to_embed(self, weather, embed, units):
        """Put the temperature into the embed.

        Parameters
        ----------
        weather: pyowm.weather.Weather
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
        # embed.add_field(
        #     name="Feels Like", value=f"{temperature['feels_like']:.1f} °{units['t_units_fmt']}", inline=False
        # )
        embed.add_field(
            name="Min/Max",
            value=f"{temperature['temp_min']:.1f}/{temperature['temp_max']:.1f} °{units['t_units_fmt']}",
            inline=False,
        )
        embed.add_field(name="Humidity", value=f"{weather.humidity:.0f}%", inline=False)

        return embed

    def _add_rain_to_embed(self, weather, embed, _units):
        """Put the rain into the embed.

        Parameters
        ----------
        weather: pyowm.weather.Weather
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
        rain = weather.rain

        if not rain:
            if _units:
                embed.add_field(
                    name="Rain",
                    value="There is no rain forecast",
                    inline=False,
                )
        else:
            embed.add_field(
                name="Rain 1 hour",
                value=f"{rain['1h']:.1f} mm",
                inline=False,
            )
            embed.add_field(
                name="Rain 3 hours",
                value=f"{rain['3h']:.1f} mm",
                inline=False,
            )

        return embed

    def _add_wind_to_embed(self, weather, embed, units):
        """Put temperature into the embed.

        Parameters
        ----------
        weather: pyowm.weather.Weather
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

        if units["w_units"] == "meters_sec":  # conver m/s to km/h
            wind["speed"] *= 3.6

        embed.add_field(name="Wind speed", value=f"{wind['speed']:.1f} {units['w_units_fmt']}", inline=False)
        embed.add_field(
            name="Wind bearing", value=f"{wind['deg']:.01f}° ({degrees_to_cardinal(wind['deg'])})", inline=False
        )

        return embed

    def _add_everything_to_embed(self, weather, embed, units):
        """Put all three observables into a single embed.

        Parameters
        ----------
        weather: pyowm.weather.Weather
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

        embed = self._add_temperature_to_embed(weather, embed, units)
        embed = self._add_rain_to_embed(weather, embed, None)
        embed = self._add_wind_to_embed(weather, embed, units)

        return embed

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="weather", description="get the weather", guild_ids=config.SLASH_SERVERS)
    async def weather(
        self,
        inter,
        where=commands.Param(default=None),
        what=commands.Param(default="forecast", choices=weather_choices),
        units=commands.Param(default="metric", choices=weather_units),
    ):
        """Get the weather for a location.

        Parameters
        ----------
        where: str
            The location to get the weather for.
        what: str
            What to get, either the whole forecast, temperature, rain or wind.
        units: str
            The units to use, either metric or imperial.
        """

        await inter.response.defer()

        if where is None:
            if str(inter.author.id) not in self.userdata or "location" not in self.userdata[str(inter.author.id)]:
                return await inter.edit_original_message(
                    content="You need to specify a location, or set your location and/or country using /remember."
                )
            where = self.userdata[str(inter.author.id)].get("location")

        try:
            observation = self.weather_api_manager.weather_at_place(where)
        except Exception:  # pylint: disable=broad-except
            return await inter.edit_original_message(content=f"Could not find {where} in OpenWeatherMap.")

        weather = observation.weather
        units = self.get_units_for_system(units)

        embed = disnake.Embed(
            title=f"{what.capitalize()} in {observation.location.name}, {observation.location.country}",
            color=disnake.Color.default(),
        )

        match what:
            case "forecast":
                embed.add_field(
                    name="Description",
                    value=f"{weather.detailed_status.capitalize()}",
                    inline=False,
                )
                embed = self._add_everything_to_embed(weather, embed, units)
            case "temperature":
                embed = self._add_temperature_to_embed(weather, embed, units)
            case "rain":
                embed = self._add_rain_to_embed(weather, embed, "mm")
            case "wind":
                embed = self._add_wind_to_embed(weather, embed, units)
            case _:
                return await inter.edit_original_message(content="Somehow got to an 'unreachable' branch.")

        embed.set_footer(text=f"{self.generate_sentence('weather')}")
        embed.set_thumbnail(url=weather.weather_icon_url())

        await inter.edit_original_message(embed=embed)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="forecast", description="get the weather forecast")
    async def forecast(  # pylint: disable=too-many-locals
        self,
        inter,
        where=commands.Param(default=None),
        country=commands.Param(default=None, converter=owm_convert_uk_to_gb),
    ):
        """logger.info the weather forecast for a location.

        Parameters
        ----------
        where: str
            The location to get the weather forecast for.
        country: str [optional]
            The country the location is in.
        """
        await inter.response.defer()

        if where is None:
            if str(inter.author.id) not in self.userdata or "location" not in self.userdata[str(inter.author.id)]:
                return await inter.edit_original_message(
                    content="You need to either specify a location, or set your location and/or country using /remember."
                )
            where = self.userdata[str(inter.author.id)].get("location")

        if country is None:
            if str(inter.author.id) not in self.userdata or "country" not in self.userdata[str(inter.author.id)]:
                return await inter.edit_original_message(
                    content="You need to specify a country, or set your location and/or country using /remember."
                )
            country = self.userdata[str(inter.author.id)].get("country", "gb")
        else:
            if len(country) != 2:
                await inter.edit_original_message(content="Country has to be a 2 character symbol, e.g. GB or US.")

        locations = self.weather_api_city_register.locations_for(where, country=country.upper())
        if len(locations) == 0:
            return await inter.edit_original_message(content="Location not found in forecast database.")

        location, country = locations[0].name, locations[0].country
        lat, lon = locations[0].lat, locations[0].lon

        try:
            one_call = self.weather_api_manager.one_call(lat, lon)
        except Exception as exception:  # pylint: disable=broad-except
            logger.info("weather one_call error: %s", exception)
            return await inter.edit_original_message(
                content="Could not find that location in one call forecast database."
            )

        embed = disnake.Embed(title=f"Weather for {location}, {country}", color=disnake.Color.default())

        for day in one_call.forecast_daily[:4]:
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

        embed.set_thumbnail(url=one_call.forecast_daily[0].weather_icon_url())
        embed.set_footer(text=f"{self.generate_sentence('forecast')}")

        await inter.edit_original_message(embed=embed)
