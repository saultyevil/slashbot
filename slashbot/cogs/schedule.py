#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scheduled posts cog."""

from pathlib import Path
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


# pylint: disable=too-few-public-methods
class Post:
    """Base class for a scheulded post.

    All arguments are required, other than message and tagged_users which are
    optional.
    """

    # pylint: disable=too-many-arguments
    def __init__(self, file, day, hour, minute, seed_word, message="", tagged_users=None):
        """_summary_

        Parameters
        ----------
        file : _type_
            _description_
        day : _type_
            _description_
        hour : _type_
            _description_
        minute : _type_
            _description_
        seed_word : _type_
            _description_
        message : str, optional
            _description_, by default ""
        tagged_users : _type_, optional
            _description_, by default None
        """
        self.file = file
        self.day = day
        self.hour = hour
        self.minute = minute
        self.seed_word = seed_word
        self.message = message
        self.tagged_users = tagged_users
        # this tracks how many seconds until the message should be posted
        self.time_until_post = calculate_sleep_time(self.day, self.hour, self.minute)

    def update_time_until_post(self) -> None:
        """Updates the variable self.time_until_post."""
        self.time_until_post = calculate_sleep_time(self.day, self.hour, self.minute)


class ScheduledPosts(CustomCog):
    """Schedulded post cog.

    Schedulded posts shouldd be added to self.scheduled_posts using a Post
    class.
    """

    # Special methods ----------------------------------------------------------

    def __init__(self, bot: commands.bot):
        """init function"""
        super().__init__()
        self.bot = bot

        self.scheduled_posts = [
            Post("data/videos/monday.mp4", calendar.MONDAY, 8, 30, "monday"),
            Post("data/videos/wednesday.mp4", calendar.WEDNESDAY, 8, 30, "wednesday"),
            Post(
                "data/bin.png",
                calendar.THURSDAY,
                23,
                54,
                "bin",
                "it's time to take the bins out!!!",
                (App.config("ID_USER_LIME"),),
            ),
            Post("data/videos/friday.mov", calendar.FRIDAY, 8, 30, "friday"),
            Post("data/videos/weekend.mp4", calendar.FRIDAY, 18, 0, "weekend"),
            Post("data/videos/sunday.mp4", calendar.SUNDAY, 8, 30, "sunday"),
        ]

        self.__order_videos_by_soonest()

        logger.info("posting messages in this order: %s", [message.file for message in self.scheduled_posts])

        self.markov_sentences = generate_sentences_for_seed_words(
            MARKOV_MODEL,
            [post.seed_word for post in self.scheduled_posts],
            1,  # these only happen once in a while, so dont need a big bank of them
        )

        self.send_schedulded_posts.start()  # pylint: disable=no-member

    # Private methods ----------------------------------------------------------

    def __order_videos_by_soonest(self):
        """Orders self.videos to where the first entry is the video which is
        scheduled to be sent the soonest. Time until post is updated when
        this function is called.
        """
        for post in self.scheduled_posts:
            post.update_time_until_post()

        self.scheduled_posts.sort(key=lambda x: x.time_until_post)

    # Task ---------------------------------------------------------------------

    @tasks.loop(seconds=10)
    async def send_schedulded_posts(self) -> None:
        """Task to loop over the scheduled posts.

        Iterates over all of the schedulded posts. For each post, the bot will
        sleep for some time and then post the message, moving onto the next
        message in the list after that.

        Once all messages have been sent, the task will be complete and start
        again in 10 seconds.
        """
        await self.bot.wait_until_ready()
        self.__order_videos_by_soonest()

        for post in self.scheduled_posts:
            if not Path(post.file).exists():
                logger.error("file %s does not exist for %s", post.file, post.message)
                continue

            sleep_for = calculate_sleep_time(post.day, post.hour, post.minute)
            logger.info(
                "Waiting %d seconds (or %d minutes or %.1f hours) until posting message with file %s",
                sleep_for,
                int(sleep_for / 60),
                sleep_for / 3600.0,
                post.file,
            )
            await asyncio.sleep(sleep_for)

            channel = await self.bot.fetch_channel(App.config("ID_CHANNEL_IDIOTS"))

            markov_sentence = self.get_generated_sentence(post.seed_word).replace(
                post.seed_word, f"**{post.seed_word}**"
            )

            message = ""
            if post.tagged_users:
                if not hasattr(post.tagged_users, "__iter__"):
                    logger.error("%s has invalid tagged users %s", post.message, post.tagged_users)
                else:
                    message += " ".join([(await self.bot.fetch_user(user)).mention for user in post.tagged_users])
            if post.message:
                message += f" {post.message}"

            await channel.send(f"{message} {markov_sentence}", file=disnake.File(post.file))

        self.__order_videos_by_soonest()
