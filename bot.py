#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Badderbot is another discord bot.

The sole purpose of this bot is to annoy Gareth.
"""

import os
import disnake
from disnake.ext import commands
import config
import os
from markovify import markovify
import pickle

import cogs.spam
import cogs.info
import cogs.music
import cogs.remind

# Load in the markov chain and various other data ------------------------------

markovchain = markovify.Text("Jack is a naughty boy.")
if os.path.exists("data/chain.pickle"):
    with open("data/chain.pickle", "rb") as fp:
        markovchain.chain = pickle.load(fp)
with open("data/badwords.txt", "r") as fp:
    badwords = fp.readlines()[0].split()
with open("data/godwords.txt", "r") as fp:
    godwords = fp.read().splitlines()

for file in ["data/users.json", "data/reminders.json"]:
    if not os.path.exists(file):
        fp = open(file, "w").write("{}").close()

# Set up the bot and cogs ------------------------------------------------------

intents = disnake
intents = disnake.Intents.default()
intents.members = True
intents.invites = True

bot = commands.Bot(command_prefix=config.symbol, intents=intents)
spam = cogs.spam.Spam(bot, markovchain, badwords, godwords)
info = cogs.info.Info(bot, spam.generate_sentence, badwords, godwords)
reminder = cogs.remind.Reminder(bot, spam.generate_sentence)
music = cogs.music.Music(bot)

bot.add_cog(spam)
bot.add_cog(info)
bot.add_cog(reminder)
bot.add_cog(music)

# Functions --------------------------------------------------------------------

@bot.event
async def on_ready():
    """Information to print on bot launch.
    """
    message = f"Logged in as {bot.user} in the current servers:"
    for n, server in enumerate(bot.guilds):
        message += "\n  {0}). {1.name} ({1.id})".format(n, server)
    print(message)


@bot.event
async def on_slash_command_error(ctx, error):
    """Handle different types of errors.
    """
    if isinstance(error, commands.errors.CommandOnCooldown):
        await ctx.response.send_message("This command is on cooldown for you.", ephemeral=True)
    else:
        print(f"A command failed with error:\n{error}\n", "-" * 80)

# Run the bot ------------------------------------------------------------------

bot.run(os.environ["BOT_TOKEN"])
