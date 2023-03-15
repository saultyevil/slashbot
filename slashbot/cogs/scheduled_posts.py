#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scheduled posts cog."""

import asyncio
import logging
import calendar
import datetime
import disnake
from disnake.ext import commands, tasks

from slashbot.config import App
from slashbot.custom_cog import CustomCog
from slashbot.markov import MARKOV_MODEL
from slashbot.markov import generate_sentences_for_seed_words

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


def add_week_to_datetime(
    time: datetime.datetime, days: float, hour: int, minute: int, second: int
) -> datetime.datetime:
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


def calculate_sleep_time(day: int, hour: int, minute: int) -> int:
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
        sleep = add_week_to_datetime(when, 7, hour, minute, 0)

    return sleep


class Message:
    """A message"""

    def __init__(self, file, day, hour, minute, seed_word, message="", tagged_users=None):
        self.file = file
        self.day = day
        self.hour = hour
        self.minute = minute
        self.seed_word = seed_word
        self.message = message
        self.tagged_users = tagged_users

        self.time_until_post = calculate_sleep_time(self.day, self.hour, self.minute)

    def update_time_until_post(self):
        self.time_until_post = calculate_sleep_time(self.day, self.hour, self.minute)


class ScheduledPosts(CustomCog):
    """Schedulded messages cog."""

    def __init__(self, bot: commands.bot):
        """init function"""
        super().__init__()
        self.bot = bot

        self.scheduled_messages = [
            Message("data/videos/monday.mp4", calendar.MONDAY, 8, 30, "monday"),
            Message("data/videos/wednesday.mp4", calendar.WEDNESDAY, 8, 30, "wednesday"),
            Message(
                "data/bin.jpg",
                calendar.THURSDAY,
                23,
                54,
                "bin",
                "it's time to take the bins out!!!",
                (App.config("ID_USER_LIME")),
            ),
            Message("data/videos/friday.mp4", calendar.FRIDAY, 8, 30, "friday"),
            Message("data/videos/weekend.mp4", calendar.FRIDAY, 18, 0, "weekend"),
            Message("data/videos/sunday.mp4", calendar.SUNDAY, 8, 30, "sunday"),
        ]

        self.__order_videos_by_soonest()

        logger.info("posting messages in this order: %s", [message.file for message in self.scheduled_messages])

        self.markov_sentences = generate_sentences_for_seed_words(
            MARKOV_MODEL,
            [message.seed_word for message in self.scheduled_messages],
            1,  # these only happen once in a while, so dont need a big bank of them
        )

        self.scheduled_video_task.start()  # pylint: disable=no-member

    def __order_videos_by_soonest(self):
        """Orders self.videos to where the first entry is the video which is
        scheduled to be sent the soonest.
        """
        self.scheduled_messages.sort(key=lambda x: x.time_until_post)

    @tasks.loop(seconds=10)
    async def scheduled_video_task(self) -> None:
        """Loop"""
        await self.bot.wait_until_ready()

        for message in self.scheduled_messages:
            sleep_for = calculate_sleep_time(message.day, message.hour, message.minute)
            logger.info("Waiting %f hours until posting message with file %s", sleep_for / 3600.0, message.file)
            await asyncio.sleep(sleep_for)

            channel = await self.bot.fetch_channel(App.config("ID_CHANNEL_IDIOTS"))

            msg_to_send = ""
            if message.tagged_users:
                msg_to_send += " ".join([await self.bot.fetch_user(user).mention for user in message.tagged_users])
            if message.message:
                msg_to_send += message

            await channel.send(
                f"{msg_to_send} {self.get_generated_sentence(message.seed_word).replace(message.seed_word, f'**{message.seed_word}**')}",
                file=disnake.File(message.file),
            )

            message.update_time_until_post()

        self.__order_videos_by_soonest()
