#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import random

import disnake
import magic8ball
import requests
import wolframalpha
from disnake.ext import commands
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

import config

logger = logging.getLogger(config.LOGGER_NAME)
cd_user = commands.BucketType.user


class Info(commands.Cog):
    """Query information from the internet."""

    def __init__(self, bot, generate_sentence, bad_words, god_words, attempts=10):
        self.bot = bot
        self.generate_sentence = generate_sentence
        self.attempts = attempts
        self.bad_words = bad_words
        self.god_words = god_words
        with open(config.USERS_FILES, "r", encoding="utf-8") as fp:
            self.user_data = json.load(fp)

        def on_modify(_):
            with open(config.USERS_FILES, "r", encoding="utf-8") as fp:
                self.user_data = json.load(fp)
            logger.info("Reloaded userdata")

        observer = Observer()
        event_handler = PatternMatchingEventHandler(["*"], None, False, True)
        event_handler.on_modified = on_modify
        observer.schedule(event_handler, config.USERS_FILES, False)
        observer.start()

        self.wolfram_api = wolframalpha.Client(config.WOLFRAM_API_KEY)
        self.youtube_api = build("youtube", "v3", developerKey=config.GOOGLE_API_KEY)

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, inter):
        """Reset the cooldown for some users and servers."""
        if inter.guild and inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOL_DOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="8ball", description="ask the magicall ball a question")
    async def ball(self, inter, question):
        """Ask the magical ball a question.

        Parameters
        ----------
        question : str
            The question to ask.
        """
        question = question.capitalize()
        if question[-1] != "?":
            question += "?"
        await inter.response.send_message(f"*{question}* {random.choice(magic8ball.list)}")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="roll", description="roll a dice")
    async def roll(self, inter, n):
        """Roll a random number from 1 to n.

        Parameters
        ----------
        n: int
            The number of sides of the dice.
        """
        await inter.response.send_message(f"{inter.author.name} rolled a {random.randint(1, int(n))}.")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="wolfram", description="ask wolfram a question")
    async def wolfram(self, inter, question: str, n_sols: int = 1):
        """Submit a query to wolfram alpha.

        Parameters
        ----------
        question: str
            The question to ask.
        n_sols: int
            The number of solutions to return.
        """
        await inter.response.defer()
        embed = disnake.Embed(title="Stephen Wolfram says...", color=disnake.Color.default())
        embed.set_footer(text=f"{self.generate_sentence('wolfram')}")
        embed.set_thumbnail(
            url=r"https://upload.wikimedia.org/wikipedia/commons/4/44/Stephen_Wolfram_PR_%28cropped%29.jpg"
        )

        results = self.wolfram_api.query(question)

        if not results["@success"]:
            embed.add_field(
                name=f"{question}",
                value=f"You {random.choice(self.bad_words)}, you asked a question Stephen Wolfram couldn't answer.",
                inline=False,
            )
            return await inter.edit_original_message(embed=embed)

        # only go through the first N results to add to embed

        results = [result for result in results.pods]

        n_sols += 1
        if n_sols > len(results):
            n_sols = len(results)

        for n_sol, result in enumerate(results[1:n_sols]):
            # have to check if the result is a list of results, or just a single result
            # probably a better way to do this
            if isinstance(result["subpod"], list):
                result = result["subpod"][0]["plaintext"]
            else:
                result = result["subpod"]["plaintext"]

            if n_sol == 0:
                embed.add_field(name=f"{question}", value=result, inline=False)
            else:
                embed.add_field(name=f"Result {n_sol}", value=result, inline=False)

        return await inter.edit_original_message(embed=embed)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="youtube", description="search for a youtube video")
    async def youtube(self, inter, query=None):
        """Embeds the first result on youtube for the search term.

        Parameters
        ----------
        query: str
            The term to search on YouTube.
        """
        await inter.response.defer()
        if query is None:
            query = random.sample(self.god_words, random.randint(1, 5))

        try:
            # pylint: disable=no-member
            response = self.youtube_api.search().list(q=query, part="snippet", maxResults=1).execute()
        except HttpError:
            await inter.edit_original_message(content="Maximum number of daily YouTube calls has been reached.")
            return

        video_id = response["items"][0]["id"]["videoId"]
        request = (
            f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={video_id}&key={config.GOOGLE_API_KEY}"
        )
        response = json.loads(requests.get(request).text)
        views = int(response["items"][0]["statistics"]["viewCount"])

        await inter.edit_original_message(
            content=f"https://www.youtube.com/watch?v={video_id}\n>>> View count: {views:,}"
        )
