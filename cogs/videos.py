#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import random
import re

import disnake
from disnake.ext import commands

import config

cd_user = commands.BucketType.user


class Videos(commands.Cog):
    """Send short clips to the channel."""

    def __init__(self, bot, badwords):
        self.bot = bot
        self.badwords = badwords

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="goodbye", description="goodbye")
    async def goodbye(self, inter):
        """Send a clip of Marko saying goodbye."""
        await inter.response.defer()
        await inter.edit_original_message(file=disnake.File("data/videos/goodbye.mp4"))

    @commands.cooldown(1, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="goodmorning", description="good morning people")
    async def goodmorning(self, inter):
        """Send a video of Marko saying good morning people."""
        await inter.response.defer()
        time = datetime.datetime.now()
        if time.hour >= 12:
            lee_videos = [
                "data/videos/good_morning_afternoon_1.mp4",
                "data/videos/good_morning_afternoon_2.mp4",
                "data/videos/good_morning_afternoon_3.mp4",
            ]
        else:
            lee_videos = [
                "data/videos/good_morning_vlog.mp4",
                "data/videos/good_morning_still_is.mp4",
            ]

        video_choices = (1 * len(lee_videos) * ["data/videos/good_morning_people.mp4"]) + lee_videos
        video = random.choice(video_choices)

        await inter.edit_original_message(file=disnake.File(video))

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="haha", description="haha very funny")
    async def laugh(self, inter):
        """Send a clip of Marko laughing."""
        await inter.response.defer()
        await inter.edit_original_message(file=disnake.File("data/videos/marko_laugh.mp4"))

    @commands.cooldown(1, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="spit", description="i spit in your direction")
    async def spit(self, inter, mention=None):
        """Send the GIF of the girl spitting."""
        await inter.response.defer()

        message = ""

        if mention:
            users = [user for user in re.findall(r"\<@!(.*?)\>", mention)]

            mentions = []
            for user in users:
                user = self.bot.get_user(int(user))
                if inter.author.id == config.ID_USER_ADAM:
                    mentions.append(f"{user.name}")
                else:
                    mentions.append(f"{user.mention}")
            if users:
                badword = random.choice(self.badwords)
                if len(users) == 1 and badword[-1] == "s":
                    badword = badword[:-1]
                message = "I spit at " + ", ".join(mentions) + f", the {badword}"
                if len(users) > 1:
                    message += "s"
                message += "."

        await inter.edit_original_message(content=message, file=disnake.File("data/spit.gif"))

    @commands.cooldown(1, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="what", description="what is a?")
    async def what(self, inter):
        """Send a video of Marko saying a naughty word."""
        await inter.response.defer()
        await inter.edit_original_message(file=disnake.File("data/videos/what_is_a.mp4"))
