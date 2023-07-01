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
import string

import disnake
from disnake.ext import commands
from sqlalchemy.orm import Session

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.db import connect_to_database_engine
from slashbot.db import Tweet
from slashbot.db import Image
from slashbot.error import deferred_error_message

cd_user = commands.BucketType.user
logger = logging.getLogger(App.config("LOGGER_NAME"))


class Archive(SlashbotCog):
    """Admin tools for the bot."""

    def __init__(self, bot: commands.InteractionBot):
        """Initialize the class."""
        super().__init__()
        self.bot = bot

        self.__initialise_database()

    # Private functions --------------------------------------------------------

    def __initialise_database(self) -> None:
        """Fill in any missing images or tweets."""

        if not (path := Path(App.config("TWEET_FILE"))).exists():
            logger.error("No tweets CSV file at %s", App.config("TWEET_FILE"))
            return

        with Session(connect_to_database_engine()) as session:
            with open(path, "r", encoding="utf-8") as file_in:
                for tweet_line in csv.DictReader(file_in, quotechar='"', delimiter=","):
                    user = tweet_line.get("UserName", None)
                    if not user:
                        continue

                    tweet = tweet_line["Embedded_text"].rstrip(string.digits)
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

                    tweet_url = tweet_line.get("Tweet URL", None)

                    session.add(
                        Tweet(
                            user=user,
                            tweet=tweet,
                            date=date,
                            image_url=image_url,
                            tweet_url=tweet_url,
                        )
                    )

                    image_query = session.query(Image).filter(Image.image_url == image_url)
                    if image_url and image_query.count() == 0:
                        if "twitpic.com" in image_url:
                            continue
                        session.add(
                            Image(
                                image_url=image_url.replace("&name=small", "&name=orig")
                                .replace("&name=900x900", "&name=orig")
                                .replace("&name=360x360", "&name=orig"),
                            )
                        )

            session.commit()

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="tweet", description="send a tweet to the chat")
    async def tweet(
        self,
        inter: disnake.ApplicationCommandInteraction,
        search_term: str = commands.Param(description="A term for search for in tweets", default=None),
    ):
        """Send a tweet to chat."""
        await inter.response.defer()
        with Session(connect_to_database_engine()) as session:
            while True:
                if search_term:
                    tweets_with_term = session.query(Tweet).filter(Tweet.tweet.contains(search_term))
                    if tweets_with_term.count() == 0:
                        return await deferred_error_message(inter, f"No tweets found containing term {search_term}")
                    tweet = random.choice(tweets_with_term.all())
                else:
                    tweet = random.choice(session.query(Tweet).all())

                if len(tweet.tweet) < 256:
                    break

        embed = disnake.Embed(title=tweet.tweet, description=f"{tweet.tweet_url}", color=disnake.Colour.yellow())
        embed.set_image(url=tweet.image_url)
        embed.set_footer(text=f"{tweet.user} - {datetime.datetime.strftime(tweet.date, r'%-d %B %Y')}")

        await inter.edit_original_message(embed=embed)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="picture", description="send a picture to the chat")
    async def picture(self, inter: disnake.ApplicationCommandInteraction):
        """Send a picture to chat."""
        with Session(connect_to_database_engine()) as session:
            image_file_path = random.choice(session.query(Image).all()).image_url

        await inter.response.send_message(f"{image_file_path}")
