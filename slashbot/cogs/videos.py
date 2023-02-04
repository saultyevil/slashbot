#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for sending videos, and scheduled videos."""

import asyncio
import calendar
import datetime
import random
from types import coroutine
from typing import List

import disnake
from slashbot.config import App
from disnake.ext import commands, tasks

cd_user = commands.BucketType.user


class Videos(commands.Cog):
    """Send short clips to the channel."""

    def __init__(self, bot: commands.InteractionBot, bad_words: List[str], generate_sentence: callable):
        """Initialize the cog.

        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.
        bad_words: List[str]
            A list of bad words.
        generate_sentence: callable
            A function to generate a sentence given a seed word.
        """
        self.bot = bot
        self.bad_words = bad_words
        self.generate_sentence = generate_sentence

        self.monday_morning.start()  # pylint: disable=no-member
        self.wednesday_morning.start()  # pylint: disable=no-member
        self.friday_morning.start()  # pylint: disable=no-member
        self.friday_evening.start()  # pylint: disable=no-member
        self.sunday_morning.start()  # pylint: disable=no-member
        self.jack_bin_day.start()  # pylint: disable=no-member

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
    @commands.slash_command(name="admin_abuse", description="admin abuse!!! you're the worst admin ever!!!")
    async def admin_abuse(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a clip of someone shouting admin abuse.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        await inter.response.defer()
        seed = random.choice(["admin", "abuse", "admin abuse"])
        return await inter.edit_original_message(
            content=f"{self.generate_sentence(seed)}", file=disnake.File("data/videos/admin_abuse.mp4")
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="goodbye", description="goodbye")
    async def goodbye(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a clip of Marko saying goodbye.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        await inter.response.defer()
        return await inter.edit_original_message(file=disnake.File("data/videos/goodbye.mp4"))

    @commands.cooldown(1, App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="good_morning", description="good morning people")
    async def good_morning(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a video of Marko saying good morning people.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
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

        return await inter.edit_original_message(file=disnake.File(video))

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="haha", description="haha very funny")
    async def laugh(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a clip of Marko laughing.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        await inter.response.defer()
        return await inter.edit_original_message(file=disnake.File("data/videos/marko_laugh.mp4"))

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="naughty_marko", description="Marko Vanhanen says a naughty word")
    async def marko_gamer_word(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a clip of Marko saying the gamer word.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        await inter.response.defer()
        return await inter.edit_original_message(file=disnake.File("data/videos/what_is_a.mp4"))

    # Utility functions --------------------------------------------------------

    @staticmethod
    def add_time(time: datetime.datetime, days: float, hour: int, minute: int, second: int) -> datetime.datetime:
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

        Returns
        -------
        A datetime object a week after the given one.
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

    # Scheduled videos ---------------------------------------------------------

    @tasks.loop(hours=App.config("HOURS_IN_WEEK"))
    async def monday_morning(self) -> None:
        """Send a message on Monday morning."""
        server = self.bot.get_guild(App.config("ID_SERVER_ADULT_CHILDREN"))
        channel = server.get_channel(App.config("ID_CHANNEL_IDIOTS"))
        await channel.send(
            self.generate_sentence("monday").replace("monday", "**monday**"),
            file=disnake.File("data/videos/monday.mp4"),
        )

    @tasks.loop(hours=App.config("HOURS_IN_WEEK"))
    async def wednesday_morning(self) -> None:
        """Send a message on Wednesday morning."""
        server = self.bot.get_guild(App.config("ID_SERVER_ADULT_CHILDREN"))
        channel = server.get_channel(App.config("ID_CHANNEL_IDIOTS"))
        await channel.send(
            self.generate_sentence("wednesday").replace("wednesday", "**wednesday**"),
            file=disnake.File("data/videos/wednesday.mp4"),
        )

    @tasks.loop(hours=App.config("HOURS_IN_WEEK"))
    async def friday_evening(self) -> None:
        """Send a message on Friday evening."""
        server = self.bot.get_guild(App.config("ID_SERVER_ADULT_CHILDREN"))
        channel = server.get_channel(App.config("ID_CHANNEL_IDIOTS"))
        await channel.send(
            self.generate_sentence("weekend").replace("weekend", "**weekend**"),
            file=disnake.File("data/videos/weekend.mp4"),
        )

    @tasks.loop(hours=App.config("HOURS_IN_WEEK"))
    async def friday_morning(self) -> None:
        """Send a message on Friday morning."""
        server = self.bot.get_guild(App.config("ID_SERVER_ADULT_CHILDREN"))
        channel = server.get_channel(App.config("ID_CHANNEL_IDIOTS"))
        await channel.send(
            self.generate_sentence("friday").replace("friday", "**friday**"),
            file=disnake.File("data/videos/friday.mov"),
        )

    @tasks.loop(hours=App.config("HOURS_IN_WEEK"))
    async def sunday_morning(self) -> None:
        """Send a message on Sunday morning."""
        server = self.bot.get_guild(App.config("ID_SERVER_ADULT_CHILDREN"))
        channel = server.get_channel(App.config("ID_CHANNEL_IDIOTS"))
        await channel.send(
            self.generate_sentence("sunday").replace("sunday", "**sunday**"),
            file=disnake.File("data/videos/sunday.mp4"),
        )

    @tasks.loop(hours=App.config("HOURS_IN_WEEK"))
    async def jack_bin_day(self) -> None:
        """Send a bin reminder for Jack."""
        server = self.bot.get_guild(App.config("ID_SERVER_ADULT_CHILDREN"))
        channel = server.get_channel(App.config("ID_CHANNEL_IDIOTS"))
        user = self.bot.get_user(App.config("ID_USER_LIME"))
        await channel.send(
            f"{user.mention} it's time to take the bins out!!! " + self.generate_sentence("bin"),
            file=disnake.File("data/bin.png"),
        )

    # Sleep tasks --------------------------------------------------------------

    def calc_sleep_time(self, day: int, hour: int, minute: int) -> int:
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
    async def sleep_monday_morning(self) -> None:
        """Sleep until Monday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.MONDAY, 8, 30))
        await self.bot.wait_until_ready()

    @wednesday_morning.before_loop
    async def sleep_wednesday_morning(self) -> None:
        """Sleep until Wednesday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.WEDNESDAY, 8, 30))
        await self.bot.wait_until_ready()

    @friday_morning.before_loop
    async def sleep_friday_morning(self) -> None:
        """Sleep until Friday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.FRIDAY, 8, 30))
        await self.bot.wait_until_ready()

    @friday_evening.before_loop
    async def sleep_friday_evening(self) -> None:
        """Sleep until Friday evening."""
        await asyncio.sleep(self.calc_sleep_time(calendar.FRIDAY, 18, 0))
        await self.bot.wait_until_ready()

    @sunday_morning.before_loop
    async def sleep_sunday_morning(self) -> None:
        """Sleep until Sunday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.SUNDAY, 10, 0))
        await self.bot.wait_until_ready()

    @jack_bin_day.before_loop
    async def sleep_jack_bin_day(self) -> None:
        """Sleep until Thursday  11:54 pm."""
        await asyncio.sleep(self.calc_sleep_time(calendar.THURSDAY, 23, 54))
        await self.bot.wait_until_ready()
