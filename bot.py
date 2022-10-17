#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slashbot is another discord bot, using slash command.

The sole purpose of this bot is now to annoy Gareth.
"""

import logging
import os
import pickle
import time
from pathlib import Path

import disnake
from disnake.ext import commands
import aiohttp
import requests

import cogs.content
import cogs.info
import cogs.music
import cogs.remind
import cogs.spam
import cogs.users
import cogs.videos
import cogs.weather
import cogs.admin

import config

from markovify import markovify  # pylint: disable=import-error

# Set up logger ----------------------------------------------------------------

logger = logging.getLogger("slashbot")
formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)8s : %(message)s (%(filename)s:%(lineno)d)", "%Y-%m-%d %H:%M:%S"
)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
log_path = Path("./slashbot.log")
file_handler = logging.handlers.RotatingFileHandler(
    filename=log_path, encoding="utf-8", maxBytes=int(1e6), backupCount=5
)
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.propagate = False
logger.setLevel(logging.INFO)


def create_and_run_bot():  # pylint: disable=too-many-locals too-many-statements
    """Create the bot and run it."""
    start = time.time()

    class Bot(commands.InteractionBot):
        """Bot class, with changes for clean up on close."""

        def __init__(self, **kwargs):
            """Initialize the class."""
            super().__init__(**kwargs)
            self.cleanup_functions = []

        def add_to_cleanup(self, name, function, args):
            """Add a function to the cleanup list.

            Parameters
            ----------
            function: function
                The function to add to the clean up routine.
            args: tuple
                The arguments to pass to the function.
            """
            self.cleanup_functions.append({"name": name, "function": function, "args": args})

        async def close(self):
            """Clean up things on close."""
            for function in self.cleanup_functions:
                print(f"{function['name']}")
                if function["args"]:
                    await function["function"](*function["args"])
                else:
                    await function["function"]()
            await super().close()

    # Load in the markov chain and various other data --------------------------

    markovchain = markovify.Text("Jack is a naughty boy.", state_size=2)
    if os.path.exists("data/chain.pickle"):
        with open("data/chain.pickle", "rb") as file_in:
            markovchain.chain = pickle.load(file_in)

    with open(config.BADWORDS_FILE, "r", encoding="utf-8") as file_in:
        badwords = file_in.readlines()[0].split()

    with open(config.GODWORDS_FILE, "r", encoding="utf-8") as file_in:
        godwords = file_in.read().splitlines()

    for file in config.ALL_FILES:
        if not os.path.exists(file):
            with open(file, "w", encoding="utf-8") as file_in:
                file_in.write("{}")

    # Set up the bot and cogs --------------------------------------------------

    intents = disnake
    intents = disnake.Intents.default()
    intents.members = True  # pylint: disable=assigning-non-slot
    intents.invites = True  # pylint: disable=assigning-non-slot

    bot = Bot(intents=intents)
    spam = cogs.spam.Spam(bot, markovchain, badwords, godwords)
    info = cogs.info.Info(bot, spam.generate_sentence, badwords, godwords)
    reminder = cogs.remind.Reminder(bot, spam.generate_sentence)
    # music = cogs.music.Music(bot)
    content = cogs.content.Content(bot, spam.generate_sentence)
    weather = cogs.weather.Weather(bot, spam.generate_sentence)
    videos = cogs.videos.Videos(bot, badwords, spam.generate_sentence)
    users = cogs.users.Users(bot)
    admin = cogs.admin.Admin(bot, log_path)

    # bot.add_cog(music)
    bot.add_cog(spam)
    bot.add_cog(info)
    bot.add_cog(reminder)
    bot.add_cog(content)
    bot.add_cog(weather)
    bot.add_cog(videos)
    bot.add_cog(users)
    bot.add_cog(admin)
    bot.add_to_cleanup("Updating markov chains on close", spam.learn, [None])

    # Functions ------------------------------------------------------------

    @bot.event
    async def on_ready():
        """Information to print on bot launch."""
        logger.info("Logged in as %s in the current servers:", bot.user)
        for n_server, server in enumerate(bot.guilds):
            logger.info("\t%d). %s (%d)", n_server, server.name, server.id)
        logger.info("Started in %.2f seconds", time.time() - start)

    @bot.event
    async def on_slash_command_error(ctx, error):
        """Handle different types of errors.

        Parameters
        ----------
        error: Exception
            The error that occurred.
        """

        logger.info("%s for %s failed with error:", ctx.application_command.name, ctx.author.name)
        logger.info(error)

        if isinstance(error, commands.errors.CommandOnCooldown):
            return await ctx.response.send_message("This command is on cooldown for you.", ephemeral=True)

    bot.run(os.environ["BOT_TOKEN"])


# Run the bot ------------------------------------------------------------------
# Do it in a loop like this, as on connection lost to the internet we'll keep
# re-trying to start the bot until eventually a connection is established

if __name__ == "__main__":
    while True:
        try:
            create_and_run_bot()
            break  # exit for other errors
        except (ConnectionError, aiohttp.ClientConnectorError, requests.exceptions.ConnectionError):
            logger.error("Attempting to restart bot in 10s")  # pylint: disable=logging-fstring-interpolation
            time.sleep(10)
