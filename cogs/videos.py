#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import calendar
import datetime
import random
import re

import disnake
from disnake.ext import commands, tasks

import config

cd_user = commands.BucketType.user


class Videos(commands.Cog):
    """Send short clips to the channel."""

    def __init__(self, bot, badwords, generate_sentence):
        self.bot = bot
        self.badwords = badwords
        self.generate_sentence = generate_sentence

        self.monday_morning.start()  # pylint: disable=no-member
        self.wednesday_morning.start()  # pylint: disable=no-member
        self.friday_morning.start()  # pylint: disable=no-member
        self.friday_evening.start()  # pylint: disable=no-member
        self.sunday_morning.start()  # pylint: disable=no-member
        self.jack_bin_day.start()  # pylint: disable=no-member

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, inter):
        """Reset the cooldown for some users and servers."""
        if inter.guild and inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOLDOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Commands -----------------------------------------------------------------

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

    # Utility functions --------------------------------------------------------

    @staticmethod
    def add_time(time, days, hour, minute, second):
        """Add a week to a datetime object.

        Parameters
        ----------
        time: datetime.datetime
            The datetime to calculate from.
        days: float
            The number of additional days to sleep for
        hour: int
            The scheduled hour
        minute: int
            The scheduled minute
        second: int
            The scheduled second
        """
        next_date = time + datetime.timedelta(days=days)
        when = datetime.datetime(
            year=next_date.year,
            month=next_date.month,
            day=next_date.day,
            hour=hour,
            minute=minute,
            second=second,
        )
        next_date = when - time

        return next_date.days * 86400 + next_date.seconds

    # Sheduled videos ----------------------------------------------------------

    @tasks.loop(hours=config.HOURS_IN_WEEK)
    async def monday_morning(self):
        """Send a message on Monday morning."""
        server = self.bot.get_guild(config.ID_SERVER_ADULT_CHILDREN)
        channel = server.get_channel(config.ID_CHANNEL_IDIOTS)
        await channel.send(
            self.generate_sentence("monday").replace("monday", "**monday**"),
            file=disnake.File("data/videos/monday.mp4"),
        )

    @tasks.loop(hours=config.HOURS_IN_WEEK)
    async def wednesday_morning(self):
        """Send a message on Wednesday morning."""
        server = self.bot.get_guild(config.ID_SERVER_ADULT_CHILDREN)
        channel = server.get_channel(config.ID_CHANNEL_IDIOTS)
        await channel.send(
            self.generate_sentence("wednesday").replace("wednesday", "**wednesday**"),
            file=disnake.File("data/videos/wednesday.mp4"),
        )

    @tasks.loop(hours=config.HOURS_IN_WEEK)
    async def friday_evening(self):
        """Send a message on Friday evening."""
        server = self.bot.get_guild(config.ID_SERVER_ADULT_CHILDREN)
        channel = server.get_channel(config.ID_CHANNEL_IDIOTS)
        await channel.send(
            self.generate_sentence("weekend").replace("weekend", "**weekend**"),
            file=disnake.File("data/videos/weekend.mp4"),
        )

    @tasks.loop(hours=config.HOURS_IN_WEEK)
    async def friday_morning(self):
        """Send a message on Friday morning."""
        server = self.bot.get_guild(config.ID_SERVER_ADULT_CHILDREN)
        channel = server.get_channel(config.ID_CHANNEL_IDIOTS)
        await channel.send(
            self.generate_sentence("friday").replace("friday", "**friday**"),
            file=disnake.File("data/videos/friday.mov"),
        )

    @tasks.loop(hours=config.HOURS_IN_WEEK)
    async def sunday_morning(self):
        """Send a message on Sunday morning."""
        server = self.bot.get_guild(config.ID_SERVER_ADULT_CHILDREN)
        channel = server.get_channel(config.ID_CHANNEL_IDIOTS)
        await channel.send(
            self.generate_sentence("sunday").replace("sunday", "**sunday**"),
            file=disnake.File("data/videos/sunday.mp4"),
        )

    @tasks.loop(hours=config.HOURS_IN_WEEK)
    async def jack_bin_day(self):
        """Send a bin reminder for Jack."""
        server = self.bot.get_guild(config.ID_SERVER_ADULT_CHILDREN)
        channel = server.get_channel(config.ID_CHANNEL_IDIOTS)
        user = self.bot.get_user(config.ID_USER_LIME)
        await channel.send(
            f"{user.mention} it's time to take the bins out!!! " + self.generate_sentence("bin"),
            file = disnake.File("data/bin.png")
        )

    # Sleep tasks --------------------------------------------------------------

    def calc_sleep_time(self, day, hour, minute):
        """Calculate the time to sleep until the next specified week day.

        Parameters
        ----------
        day: int
            The day of the week to wake up, i.e. calender.MONDAY
        hour: int
            The hour to wake up.
        minute: int
            The minute to wake up.

        Returns
        -------
        sleep: int
            The time to sleep in seconds.
        """
        now = datetime.datetime.now()
        next_date = now + datetime.timedelta(days=(day - now.weekday()) % 7)
        when = datetime.datetime(
            year=next_date.year,
            month=next_date.month,
            day=next_date.day,
            hour=hour,
            minute=minute,
            second=0,
        )
        next_date = when - now
        sleep = next_date.days * 86400 + next_date.seconds
        if sleep < 0:
            sleep = self.add_time(when, 7, hour, minute, 0)

        return sleep

    @monday_morning.before_loop
    async def sleep_monday_morning(self):
        """Sleep until Monday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.MONDAY, 8, 30))
        await self.bot.wait_until_ready()

    @wednesday_morning.before_loop
    async def sleep_wednesday_morning(self):
        """Sleep until Wednesday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.WEDNESDAY, 8, 30))
        await self.bot.wait_until_ready()

    @friday_morning.before_loop
    async def sleep_friday_morning(self):
        """Sleep until Friday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.FRIDAY, 8, 30))
        await self.bot.wait_until_ready()

    @friday_evening.before_loop
    async def sleep_friday_evening(self):
        """Sleep until Friday evening."""
        await asyncio.sleep(self.calc_sleep_time(calendar.FRIDAY, 18, 0))
        await self.bot.wait_until_ready()

    @sunday_morning.before_loop
    async def sleep_sunday_morning(self):
        """Sleep until Sunday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.SUNDAY, 10, 0))
        await self.bot.wait_until_ready()

    @jack_bin_day.before_loop
    async def sleep_jack_bin_day(self):
        """Sleep until Friday 5:45 am"""
        await asyncio.sleep(self.calc_sleep_time(calendar.FRIDAY, 5, 45))
        await self.bot.wait_until_ready()
