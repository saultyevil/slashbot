#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for posting tweets from a local archive."""

import re
import ast
import csv
import random
import logging
import datetime
from pathlib import Path

import disnake
from disnake.ext import commands
from sqlalchemy.orm import Session

from slashbot.config import App
from slashbot.custom_cog import CustomCog
from slashbot.db import connect_to_database_engine
from slashbot.db import Tweet
from slashbot.db import Image

cd_user = commands.BucketType.user
logger = logging.getLogger(App.config("LOGGER_NAME"))


class ArchiveCommands(CustomCog):
    """Admin tools for the bot."""

    def __init__(self, bot: commands.InteractionBot):
        """Initialize the class."""
        super().__init__()
        self.bot = bot

        self.__initialise_database()

    # Private functions --------------------------------------------------------

    def __initialise_database(self) -> None:
        """Fill in any missing images or tweets."""
        if not (path := Path(App.config("IMAGE_DIRECTORY"))).exists():
            return logger.info("No tweet image directory found at %s", App.config("IMAGE_DIRECTORY"))

        with Session(connect_to_database_engine()) as session:
            for image_path in path.glob("*.jpg"):
                path = str(image_path.resolve())

                query = session.query(Image).filter(Image.file_path == path)
                if query.count() > 0:
                    continue

                session.add(
                    Image(
                        file_path=path,
                    )
                )

            session.commit()

        if not (path := Path(App.config("TWEET_FILE"))).exists():
            return logger.info("No tweets CSV file at %s", App.config("TWEET_FILE"))

        with Session(connect_to_database_engine()) as session:
            with open(path, "r", encoding="utf-8") as file_in:
                for tweet_line in csv.DictReader(file_in, quotechar='"', delimiter=","):
                    user = tweet_line.get("UserName", None)
                    if not user:
                        continue

                    tweet = tweet_line["Embedded_text"]
                    date = datetime.datetime.fromisoformat(tweet_line.get("Timestamp"))

                    query = session.query(Tweet).filter(Tweet.date == date and Tweet.user == user)
                    if query.count() > 0:
                        continue

                    # images can either be URLs in tweet or
                    image_url = ast.literal_eval(tweet_line.get("Image link", None))
                    if not image_url:
                        search = re.search(r"(?P<url>https?://[^\s]+)", tweet)
                        image_url = search.group("url") if search else None
                        tweet = tweet.replace(f"{image_url}", "").strip(" -")
                    else:
                        image_url = random.choice(image_url)

                    session.add(
                        Tweet(
                            user=user,
                            tweet=tweet,
                            date=date,
                            image_url=image_url,
                        )
                    )

            session.commit()

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="tweet", description="send a tweet to the chat")
    async def tweet(self, inter: disnake.ApplicationCommandInteraction):
        """Send a tweet to chat."""
        await inter.response.defer()
        with Session(connect_to_database_engine()) as session:
            while True:
                tweet = random.choice(session.query(Tweet).all())
                if len(tweet.tweet) < 256:
                    break

        print(tweet.id, tweet.tweet)

        embed = disnake.Embed(title=tweet.tweet, description="", color=disnake.Colour.yellow())
        embed.set_image(url=tweet.image_url)
        embed.set_footer(text=f"{tweet.user} - {datetime.datetime.strftime(tweet.date, r'%-d %B %Y')}")

        await inter.edit_original_message(embed=embed)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="picture", description="send a picture to the chat")
    async def picture(self, inter: disnake.ApplicationCommandInteraction):
        """Send a picture to chat."""
        await inter.response.defer()

        with Session(connect_to_database_engine()) as session:
            image_file_path = random.choice(session.query(Image).all()).file_path

        await inter.edit_original_message(file=disnake.File(image_file_path))
