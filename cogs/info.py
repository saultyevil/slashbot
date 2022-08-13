#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import json
import random

import disnake
import magic8ball
import pyowm
import requests
import wolframalpha
from disnake.ext import commands
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from newsapi import NewsApiClient

import config

cd_user = commands.BucketType.user
weather_units = ["metric", "imperial"]
remember_options = ["location", "country", "badword", "fxtwitter"]
news_sources = [
    "abc-news",
    "al-jazeera-english",
    "ars-technica",
    "associated-press",
    "bbc-news",
    "blasting-news-br",
    "breitbart-news",
    "buzzfeed",
    "crypto-coins-news",
    "fortune",
    "fox-news",
    "google-news",
    "hacker-news",
    "ign",
    "independent",
    "new-scientist",
    "reddit-r-all",
    "reuters",
    "techradar",
    "the-huffington-post",
    "the-jerusalem-post",
    "the-lad-bible",
    "the-verge",
    "the-wall-street-journal",
    "vice-news",
]


async def autocomplete_remember_choices(ctx, _):
    """Autocompletion for choices for the remember command.

    Returns
    -------
    choice: Union[str, List[str]]
        The converted choice.
    """
    thing_chosen = ctx.filled_options["thing"]
    return ["enable", "disable"] if thing_chosen == "fxtwitter" else ""


async def convert_fxtwitter_to_bool(ctx, choice):
    """Convert the fxtwitter option (enable/disable) to a bool.

    Parameters
    ----------
    choice: str
        The choice to convert.

    Returns
    -------
    choice: Union[str, bool]
        The converted choice.
    """
    if ctx.filled_options["thing"] == "fxtwitter":
        return choice == "enable"

    return choice


def owm_convert_uk_to_gb(ctx, choice):
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


class Info(commands.Cog):
    """Query information from the internet."""

    def __init__(self, bot, generate_sentence, badwords, godwords, attempts=10):
        self.bot = bot
        self.generate_sentence = generate_sentence
        self.attempts = attempts
        self.badwords = badwords
        self.godwords = godwords
        with open("data/users.json", "r") as fp:
            self.userdata = json.load(fp)
        self.wolfram = wolframalpha.Client(config.wolfram_api_key)
        self.youtube = build("youtube", "v3", developerKey=config.google_api_key)
        self.weather = pyowm.OWM(config.openweathermap_api_key)
        self.weather_city_register = self.weather.city_id_registry()
        self.weather_manager = self.weather.weather_manager()
        self.news = NewsApiClient(api_key=config.newsapi_key)
        self.news_sources = [source["id"] for source in self.news.get_sources()["sources"]]

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, ctx):
        """Reset the cooldown for some users and servers."""
        if ctx.guild and ctx.guild.id != config.id_server_adult_children:
            return ctx.application_command.reset_cooldown(ctx)

        if ctx.author.id in config.no_cooldown_users:
            return ctx.application_command.reset_cooldown(ctx)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="8ball", description="ask the magicall ball a question")
    async def ball(self, ctx, question):
        """Ask the magicall ball a question.

        Parameters
        ----------
        question : str
            The question to ask.
        """
        question = question.capitalize()
        if question[-1] != "?":
            question += "?"
        await ctx.response.send_message(f"*{question}* {random.choice(magic8ball.list)}")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="forecast", description="get the weather forecast")
    async def forecast(self, ctx, where=None, country=commands.Param(converter=owm_convert_uk_to_gb)):
        """Print the weather forecast for a location.

        Parameters
        ----------
        where: str
            The location to get the weather forecast for.
        country: str [optional]
            The country the location is in.
        """
        await ctx.response.defer()

        if where is None:
            if str(ctx.author.id) not in self.userdata or "location" not in self.userdata[str(ctx.author.id)]:
                return await ctx.edit_original_message(
                    content="You need to either specify a location, or set your location and/or country using /remember."
                )
            else:
                where = self.userdata[str(ctx.author.id)].get("location")

        if country is None:
            if str(ctx.author.id) not in self.userdata or "country" not in self.userdata[str(ctx.author.id)]:
                return await ctx.edit_original_message(
                    content="You need to specify a country, or set your location and/or country using /remember."
                )
            else:
                country = self.userdata[str(ctx.author.id)].get("country", "gb")
        else:
            if len(country) != 2:
                await ctx.edit_original_message(content="Country has to be a 2 character symbol, e.g. GB or US.")

        locations = self.weather_city_register.locations_for(where, country=country.upper())
        if len(locations) == 0:
            return await ctx.edit_original_message(content="Location not found in forecast database.")

        location, country = locations[0].name, locations[0].country
        lat, lon = locations[0].lat, locations[0].lon

        try:
            one_call = self.weather_manager.one_call(lat, lon)
        except Exception as e:
            print("weather one_call error:", e)
            return await ctx.edit_original_message(
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

        await ctx.edit_original_message(embed=embed)

    @commands.slash_command(name="help", description="get some help")
    async def help(self, ctx, command=None):
        """Display help for the bot and commands.

        Parameters
        ----------
        command: str
            The name of a command to query.
        """
        commands = self.bot.global_application_commands
        if not commands:
            return await ctx.response.send_message(f"There were no commands found.", ephemeral=True)

        commands = sorted(commands, key=lambda x: x.name)
        commands = {
            command.name: {
                "description": command.description,
                "options": command.options,
            }
            for command in commands
        }

        if command:
            if command not in commands:
                return await ctx.response.send_message(f"Command `{command}` not found.", ephemeral=True)
            name = command
            command = commands[command]
            message = f"`{name}`-- {command['description']}\nParameters:\n"
            for option in command["options"]:
                message += f"  • {option.name} - {option.description}\n"
        else:
            message = f"There are {len(commands)} commands.\n\n"
            for command in commands:
                message += f"• `{command}` - {commands[command]['description']}\n"

        await ctx.response.send_message(message, ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="roll", description="roll a dice")
    async def roll(self, ctx, n: int):
        """Roll a random number from 1 to n.

        Parameters
        ----------
        n: int
            The number of sides of the dice.
        """
        num = random.randint(1, n)
        await ctx.response.send_message(f"{ctx.author.mention} rolled a {num}.")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="news", description="get the news")
    async def news(self, ctx, source=commands.Param(default="bbc-news", choices=news_sources)):
        """Get the news headlines for the given source.

        Parameters
        ----------
        source: str
            The news source.
        """
        await ctx.response.defer()

        try:
            articles = self.news.get_top_headlines(sources=source)["articles"]
        except:
            return await ctx.edit_original_message("Reached the maximum number of news requests for the day.")

        if not len(articles):
            return await ctx.response.send_message(f"No articles were found for {source}.")

        author = articles[0]["source"]["name"]
        image = articles[0]["urlToImage"]
        embed = disnake.Embed(title=f"Top articles from {author}", color=disnake.Color.default())

        for n, article in enumerate(articles[:3]):
            title, url, description = (
                article["title"],
                article["url"],
                article["description"],
            )
            embed.add_field(
                name=f"{n + 1}. {title}",
                value=f"{description[:128]}...\n{url}",
                inline=False,
            )

        embed.set_footer(text=f"{self.generate_sentence('news')}")

        if image:
            embed.set_thumbnail(url=image)

        await ctx.edit_original_message(embed=embed)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="remember", description="set user data")
    async def remember(
        self,
        ctx,
        thing=commands.Param(choices=remember_options),
        value=commands.Param(autocomplete=autocomplete_remember_choices, converter=convert_fxtwitter_to_bool),
    ):
        """Set some user variables for a user.

        Parameters
        ----------
        thing: str
            The thing to set.
        value: str
            The value of the thing to set.
        """
        value = value.lower() if type(value) is str else value

        try:
            self.userdata[str(ctx.author.id)][thing] = value
        except KeyError:
            self.userdata[str(ctx.author.id)] = {}
            self.userdata[str(ctx.author.id)][thing] = value

        with open("data/users.json", "w") as fp:
            json.dump(self.userdata, fp)

        await ctx.response.send_message(f"{thing.capitalize()} has been set to {value}.", ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="temperature", description="get the temperature", guild_ids=config.slash_servers)
    async def temperature(
        self,
        ctx,
        where=None,
        units=commands.Param(default="metric", choices=weather_units),
    ):
        """Get the current weather for a given location.

        Parameters
        ----------
        where: str
            The location to get the weather for.
        units: str
            The unit system to use.
        """
        await ctx.response.defer()

        if where is None:
            if str(ctx.author.id) not in self.userdata or "location" not in self.userdata[str(ctx.author.id)]:
                return await ctx.edit_original_message(
                    content="You need to either specify a location, or set your location and/or country using /remember."
                )
            else:
                where = self.userdata[str(ctx.author.id)].get("location")

        try:
            observation = self.weather_manager.weather_at_place(where)
        except Exception:  # pylint: disable=broad-except
            return await ctx.edit_original_message(content=f"Could not find {where} in OpenWeatherMap.")

        if units == "imperial":
            t_units, t_units_fmt, = (
                "fahrenheit",
                "F",
            )
        else:
            t_units, t_units_fmt, = (
                "celsius",
                "C",
            )

        weather = observation.weather
        temperature = weather.temperature(t_units)

        embed = disnake.Embed(
            title=f"Temperature at {observation.location.name}, {observation.location.country}",
            color=disnake.Color.default(),
        )
        embed.add_field(
            name="Temperature",
            value=f"**{temperature['temp']:.1f} °{t_units_fmt}**",
            inline=True,
        )
        embed.add_field(
            name="Min/Max",
            value=f"**{temperature['temp_min']:.1f}/{temperature['temp_max']:.1f} °{t_units_fmt}**",
            inline=True,
        )
        embed.add_field(
            name="Feels like",
            value=f"**{temperature['feels_like']:.1f} °{t_units_fmt}**",
            inline=True,
        )
        embed.set_footer(text=f"{self.generate_sentence('temperature')}")
        embed.set_thumbnail(url=weather.weather_icon_url())

        await ctx.edit_original_message(embed=embed)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="weather", description="get the weather")
    async def weather(
        self,
        ctx,
        where=None,
        units=commands.Param(default="metric", choices=weather_units),
    ):
        """Get the current weather for a given location.

        Parameters
        ----------
        where: str
            The location to get the weather for.
        units: str
            The unit system to use.
        """
        await ctx.response.defer()

        if where is None:
            if str(ctx.author.id) not in self.userdata or "location" not in self.userdata[str(ctx.author.id)]:
                return await ctx.edit_original_message(
                    content="You need to either specify a location, or set your location and/or country using /remember."
                )
            else:
                where = self.userdata[str(ctx.author.id)].get("location")

        try:
            observation = self.weather_manager.weather_at_place(where)
        except Exception:  # pylint: disable=broad-except
            return await ctx.edit_original_message(content=f"Could not find {where} in OpenWeatherMap.")

        if units == "imperial":
            t_units, t_units_fmt, w_units, w_units_fmt = (
                "fahrenheit",
                "F",
                "miles_hour",
                "mph",
            )
        else:
            t_units, t_units_fmt, w_units, w_units_fmt = (
                "celsius",
                "C",
                "meters_sec",
                "km/h",
            )

        weather = observation.weather
        temperature = weather.temperature(t_units)
        wind = weather.wind(w_units)

        if units == "metric":
            wind["speed"] *= 3.6

        embed = disnake.Embed(
            title=f"Weather in {observation.location.name}, {observation.location.country}",
            color=disnake.Color.default(),
        )
        embed.add_field(
            name="Description",
            value=f"**{weather.detailed_status.capitalize()}**",
            inline=False,
        )
        embed.add_field(
            name="Temperature",
            value=f"**{temperature['temp']:.1f} °{t_units_fmt}**",
            inline=False,
        )
        embed.add_field(
            name="Min/Max",
            value=f"**{temperature['temp_min']:.1f}/{temperature['temp_max']:.1f} °{t_units_fmt}**",
            inline=False,
        )
        embed.add_field(
            name="Feels like",
            value=f"**{temperature['feels_like']:.1f} °{t_units_fmt}**",
            inline=False,
        )
        embed.add_field(
            name="Wind speed",
            value=f"**{wind['speed']:.1f} {w_units_fmt}**",
            inline=False,
        )
        embed.add_field(name="Humidity", value=f"**{weather.humidity:.0f}%**", inline=False)
        embed.set_footer(text=f"{self.generate_sentence('weather')}")
        embed.set_thumbnail(url=weather.weather_icon_url())

        await ctx.edit_original_message(embed=embed)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="wolfram", description="ask wolfram a question")
    async def wolfram(self, ctx, question: str, n: int = 1):
        """Submit a query to wolfram alpha.

        Parameters
        ----------
        question: str
            The question to ask.
        """
        await ctx.response.defer()
        embed = disnake.Embed(title=f"Stephen Wolfram says...", color=disnake.Color.default())
        embed.set_footer(text=f"{self.generate_sentence('wolfram')}")
        embed.set_thumbnail(
            url=r"https://upload.wikimedia.org/wikipedia/commons/4/44/Stephen_Wolfram_PR_%28cropped%29.jpg"
        )

        results = self.wolfram.query(question)

        if not results["@success"]:
            embed.add_field(
                name=f"{question}",
                value=f"You {random.choice(self.badwords)}, you asked a question Stephen Wolfram couldn't answer.",
                inline=False,
            )
            return await ctx.edit_original_message(embed=embed)

        # only go through the first N results to add to embed

        results = [result for result in results.pods]

        n += 1
        if n > len(results):
            n = len(results)

        for m, result in enumerate(results[1:n]):
            # have to check if the result is a list of results, or just a single result
            # probably a better way to do this
            if isinstance(result["subpod"], list):
                result = result["subpod"][0]["plaintext"]
            else:
                result = result["subpod"]["plaintext"]

            if m == 0:
                embed.add_field(name=f"{question}", value=result, inline=False)
            else:
                embed.add_field(name=f"Result {m}", value=result, inline=False)

        return await ctx.edit_original_message(embed=embed)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="youtube", description="search for a youtube video")
    async def youtube(self, ctx, query=None):
        """Embeds the first result on youtube for the search term.

        Parameters
        ----------
        query: str
            The term to search on YouTube.
        """
        await ctx.response.defer()
        if query is None:
            query = random.sample(self.godwords, random.randint(1, 5))

        try:
            response = self.youtube.search().list(q=query, part="snippet", maxResults=1).execute()
        except HttpError:
            await ctx.edit_original_message(content="Maximum number of daily YouTube calls has been reached.")
            return

        id = response["items"][0]["id"]["videoId"]
        request = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={id}&key={config.google_api_key}"
        response = json.loads(requests.get(request).text)
        views = int(response["items"][0]["statistics"]["viewCount"])

        await ctx.edit_original_message(content=f"https://www.youtube.com/watch?v={id}\n>>> View count: {views:,}")
