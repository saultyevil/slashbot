#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Badderbot is another discord bot.

The sole purpose of this bot is to annoy Gareth.
"""

import logging
import os
import pickle
import time
import requests

import disnake
from disnake.ext import commands

import cogs.content
import cogs.info
import cogs.music
import cogs.remind
import cogs.spam
import cogs.users
import cogs.videos
import cogs.weather
import config
from markovify import markovify  # pylint: disable=import-error

# Check that there is an internet connection, or wait for one ------------------

n = 0
while True:
    try:
        request = requests.get("https://www.google.co.uk", timeout=5)
        if n > 0:
            print(" connected!")
        break
    except requests.ConnectTimeout:
        if n == 0:
            print("Trying to connect to the internet", endl="")
        else:
            print(".", endl="")
        n += 1

# Set up logger ----------------------------------------------------------------

logger = logging.getLogger("disnake")
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename="slashbot_disnake.log", encoding="utf-8", mode="a")
handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
logger.addHandler(handler)


# Run the bot ------------------------------------------------------------------
# Do it in a loop like this, as on connection lost to the internet we'll keep
# re-trying to start the bot until eventually a connection is established

while True:
    try:
        start = time.time()

        # Create the bot class, with extra clean up functionality --------------

        class Bot(commands.Bot):
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

        # Load in the markov chain and various other data ----------------------

        markovchain = markovify.Text("Jack is a naughty boy.", state_size=2)
        if os.path.exists("data/chain.pickle"):
            with open("data/chain.pickle", "rb") as fp:
                markovchain.chain = pickle.load(fp)

        with open(config.BADWORDS_FILE, "r", encoding="utf-8") as fp:
            badwords = fp.readlines()[0].split()

        with open(config.GODWORDS_FILE, "r", encoding="utf-8") as fp:
            godwords = fp.read().splitlines()

        for file in config.ALL_FILES:
            if not os.path.exists(file):
                with open(file, "w", encoding="utf-8") as fp:
                    fp.write("{}")

        # Set up the bot and cogs ----------------------------------------------

        intents = disnake
        intents = disnake.Intents.default()
        intents.members = True  # pylint: disable=assigning-non-slot
        intents.invites = True  # pylint: disable=assigning-non-slot

        bot = Bot(command_prefix=config.SYMBOL, intents=intents)
        spam = cogs.spam.Spam(bot, markovchain, badwords, godwords)
        info = cogs.info.Info(bot, spam.generate_sentence, badwords, godwords)
        reminder = cogs.remind.Reminder(bot, spam.generate_sentence)
        music = cogs.music.Music(bot)
        content = cogs.content.Content(bot, spam.generate_sentence)
        weather = cogs.weather.Weather(bot, spam.generate_sentence)
        videos = cogs.videos.Videos(bot, badwords, spam.generate_sentence)
        users = cogs.users.Users(bot)

        # bot.add_cog(music)
        bot.add_cog(spam)
        bot.add_cog(info)
        bot.add_cog(reminder)
        bot.add_cog(content)
        bot.add_cog(weather)
        bot.add_cog(videos)
        bot.add_cog(users)
        bot.add_to_cleanup("Updating markov chains on close", spam.learn, [None])

        # Functions ------------------------------------------------------------

        @bot.event
        async def on_ready():
            """Information to print on bot launch."""
            message = f"Logged in as {bot.user} in the current servers:"
            for n_server, server in enumerate(bot.guilds):
                message += f"\n  {n_server}). {server.name} ({server.id})"
            print(message)
            print(f"Started in {time.time() - start:.2f} seconds.\n")

        @bot.event
        async def on_slash_command_error(ctx, error):
            """Handle different types of errors.

            Parameters
            ----------
            error: Exception
                The error that occurred.
            """

            print(f"{ctx.application_command.name} for {ctx.author.name} failed with error:")
            print(error)

            if isinstance(error, commands.errors.CommandOnCooldown):
                return await ctx.response.send_message("This command is on cooldown for you.", ephemeral=True)

        bot.run(os.environ["BOT_TOKEN"])
    except Exception as e:
        print(f"Attempting to restart bot in 10s\n {e}")
        time.sleep(10)
