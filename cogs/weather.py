#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for getting the weather."""

import datetime
import logging
from types import coroutine

import disnake
import pyowm
from disnake.ext import commands

from config import App

logger = logging.getLogger(App.config("LOGGER_NAME"))


cd_user = commands.BucketType.user
weather_units = ["metric", "imperial"]
weather_choices = ["forecast", "temperature", "rain", "wind"]


def degrees_to_cardinal(degrees: float) -> str:
    """Convert a degrees value to a cardinal direction.

    Parameters
    ----------
    degrees: float
        The degrees direction.

    Returns
    -------
    The cardinal direction as a string.
    """
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    arr_idx = round(degrees / (360.0 / len(dirs)))
    return dirs[arr_idx % 16]


def owm_convert_uk_to_gb(_: disnake.ApplicationCommandInteraction, choice: str) -> str:
    """Convert UK to GB for use in OWM.

    Parameters
    ----------
    _: disnake.ApplicationCommandInteraction
        The interaction.
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
        bot: commands.InteractionBot,
        generate_sentence: callable,
    ) -> None:
        """Initialize the cog.

        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.
        generate_sentence: callable
            A function to generate a sentence given a seed word.
        """
        self.bot = bot
        self.generate_sentence = generate_sentence

        self.weather_api = pyowm.OWM(App.config("OWM_API_KEY"))
        self.weather_api_city_register = self.weather_api.city_id_registry()
        self.weather_api_manager = self.weather_api.weather_manager()

        self.user_data = App.config("USER_INFO_FILE_STREAM")

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(
        self, inter: disnake.ApplicationCommandInteraction
    ) -> disnake.ApplicationCommandInteraction:
        """Reset the cooldown for some users and servers.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        if inter.guild and inter.guild.id != App.config("ID_SERVER_ADULT_CHILDREN"):
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in App.config("NO_COOL_DOWN_USERS"):
            return inter.application_command.reset_cooldown(inter)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="weather", description="get the current weather")
    async def weather(
        self,
        inter: disnake.ApplicationCommandInteraction,
        where: str = commands.Param(
            description="The location to get weather, default is your saved location.", default=None
        ),
        what: str = commands.Param(
            description="The part of the weather to get.", default="forecast", choices=weather_choices
        ),
        units: str = commands.Param(
            description="The units to return weather readings in.", default="metric", choices=weather_units
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

        if where is None:
            if str(inter.author.id) not in self.user_data or "location" not in self.user_data[str(inter.author.id)]:
                return await inter.edit_original_message(
                    content="You need to specify a location, or set your location and/or country using /set_info."
                )
            where = self.user_data[str(inter.author.id)].get("location")

        try:
            observation = self.weather_api_manager.weather_at_place(where)
        except Exception as exception:  # pylint: disable=broad-except
            logger.info("PyOWM failed with %s", exception)
            # pylint: disable=line-too-long
            return await inter.edit_original_message(
                content=f"OpenWeatherMap failed, probably because it couldn't find the {where}. You can probably check the exact error using /logfile."
            )

        weather = observation.weather
        units = self.get_units_for_system(units)

        embed = disnake.Embed(
            title=f"{what.capitalize()} in {observation.location.name}, {observation.location.country}",
            color=disnake.Color.default(),
        )

        if what == "forecast":
            embed.add_field(
                name="Description",
                value=f"{weather.detailed_status.capitalize()}",
                inline=False,
            )
            embed = self.__add_everything_to_embed(weather, embed, units)
        elif what == "temperature":
            embed = self.__add_temperature_to_embed(weather, embed, units)
        elif what == "rain":
            embed = self.__add_rain_to_embed(weather, embed, "mm")
        elif what == "wind":
            embed = self.__add_wind_to_embed(weather, embed, units)
        else:
            return await inter.edit_original_message(content="Somehow got to an 'unreachable' branch.")

        embed.set_footer(text=f"{self.generate_sentence('weather')}")
        embed.set_thumbnail(url=weather.weather_icon_url())

        return await inter.edit_original_message(embed=embed)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="forecast", description="get the weather forecast")
    async def forecast(  # pylint: disable=too-many-locals
        self,
        inter: disnake.ApplicationCommandInteraction,
        where: str = commands.Param(
            description="The location to get weather, default is your saved location.", default=None
        ),
        country: str = commands.Param(
            description="The country your location in, as a 2 letter acronym e.g. GB or US.",
            default=None,
            converter=owm_convert_uk_to_gb,
        ),
    ) -> coroutine:
        """Print the weather forecast for a location.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        where: str
            The location to get the weather forecast for.
        country: str [optional]
            The country the location is in.
        """
        await inter.response.defer()

        if where is None:
            if str(inter.author.id) not in self.user_data or "location" not in self.user_data[str(inter.author.id)]:
                return await inter.edit_original_message(
                    # pylint: disable=line-too-long
                    content="You need to either specify a location, or set your location and/or country using /set_info."
                )
            where = self.user_data[str(inter.author.id)].get("location")

        if str(inter.author.id) in self.user_data:
            if where == self.user_data[str(inter.author.id)].get("location", None):
                country = self.user_data[str(inter.author.id)].get("country", None)

        logger.info("where %s country %s", where, country)

        locations = self.weather_api_city_register.locations_for(
            where, country=country.upper() if isinstance(country, str) else country
        )
        if len(locations) == 0:
            return await inter.edit_original_message(
                content=f"{where} {country if country else ''} wasn't found in OpenWeatherMap's city database."
            )

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

        return await inter.edit_original_message(embed=embed)

    # Functions ----------------------------------------------------------------

    def get_units_for_system(self, system: str) -> dict:
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

    # Private functions --------------------------------------------------------

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
        units: dict
            The units to use.

        Returns
        -------
        embed: disnake.Embed
            The updated Embed.
        """
        rain = weather.rain

        logger.debug("rain %s", rain)

        if not rain:
            if _units:
                embed.add_field(
                    name="Rain",
                    value="There is no rain forecast",
                    inline=False,
                )
        else:
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

        if units["w_units"] == "meters_sec":  # conver m/s to km/h
            wind["speed"] *= 3.6

        embed.add_field(name="Wind speed", value=f"{wind['speed']:.1f} {units['w_units_fmt']}", inline=False)
        embed.add_field(
            name="Wind bearing", value=f"{wind['deg']:.01f}° ({degrees_to_cardinal(wind['deg'])})", inline=False
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
