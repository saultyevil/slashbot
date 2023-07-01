#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scheduled posts cog."""

from pathlib import Path
import asyncio
import logging
import calendar
import datetime
import random

import disnake
from disnake.ext import commands, tasks

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog

# from slashbot.markov import MARKOV_MODEL
# from slashbot.markov import generate_sentences_for_seed_words

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
    """Base class for a scheduled post.

    All arguments are required, other than message and tagged_users which are
    optional.
    """

    # pylint: disable=too-many-arguments
    def __init__(self, files, day, hour, minute, seed_word, message, tagged_users, channels):
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
        channels: _type, optional
            _description, by default None
        """
        if not isinstance(files, (set, list, dict, tuple)):
            files = (files,)

        if tagged_users is not None and not isinstance(tagged_users, (set, list, dict, tuple)):
            tagged_users = (tagged_users,)

        if not hasattr(channels, "__iter__"):
            raise ValueError("channels is not an iterable")

        self.files = files
        self.channels = channels
        self.tagged_users = () if not tagged_users else tagged_users

        self.day = day
        self.hour = hour
        self.minute = minute
        self.seed_word = seed_word
        self.message = "" if message is None else message

        # this tracks how many seconds until the message should be posted
        self.time_until_post = calculate_sleep_time(self.day, self.hour, self.minute)

    def update_time_until_post(self) -> None:
        """Updates the variable self.time_until_post."""
        self.time_until_post = calculate_sleep_time(self.day, self.hour, self.minute)


class ScheduledPosts(SlashbotCog):
    """Scheduled post cog.

    Scheduled posts should be added to self.scheduled_posts using a Post
    class.
    """

    # Special methods ----------------------------------------------------------

    def __init__(self, bot: commands.bot):
        """init function"""
        super().__init__()
        self.bot = bot

        self.scheduled_posts = [
            Post(
                "data/videos/monday.mp4",
                calendar.MONDAY,
                8,
                30,
                "monday",
                None,
                None,
                (App.config("ID_CHANNEL_IDIOTS"),),
            ),
            Post(
                "data/bin.png",
                calendar.TUESDAY,
                21,
                0,
                "bin",
                "it's time to take the bins out!!!",
                (App.config("ID_USER_SAULTYEVIL"),),
                (App.config("ID_CHANNEL_IDIOTS"),),
            ),
            Post(
                "data/videos/wednesday.mp4",
                calendar.WEDNESDAY,
                8,
                30,
                "wednesday",
                None,
                None,
                (App.config("ID_CHANNEL_IDIOTS"),),
            ),
            Post(
                "data/bin.png",
                calendar.THURSDAY,
                23,
                54,
                "bin",
                "it's time to take the bins out!!!",
                (App.config("ID_USER_LIME"),),
                (App.config("ID_CHANNEL_IDIOTS"),),
            ),
            Post(
                "data/videos/friday.mov",
                calendar.FRIDAY,
                8,
                30,
                "friday",
                None,
                None,
                (App.config("ID_CHANNEL_IDIOTS"),),
            ),
            Post(
                ("data/its_friday.gif", "data/friday_night.png", "data/videos/weekend.mp4"),
                calendar.FRIDAY,
                18,
                0,
                "weekend",
                None,
                None,
                (App.config("ID_CHANNEL_IDIOTS"),),
            ),
            Post(
                "data/videos/sunday.mp4",
                calendar.SUNDAY,
                8,
                30,
                "sunday",
                None,
                None,
                (App.config("ID_CHANNEL_IDIOTS"),),
            ),
        ]

        self.__order_videos_by_soonest()

        self.random_media_files = [
            file for file in Path(App.config("RANDOM_MEDIA_DIRECTORY")).rglob("*") if not file.is_dir()
        ]

        logger.info("%d random media files found", len(self.random_media_files))

        # self.markov_sentences = generate_sentences_for_seed_words(
        #     MARKOV_MODEL,
        #     [post.seed_word for post in self.scheduled_posts],
        #     1,  # these only happen once in a while, so dont need a big bank of them
        # )

        self.send_scheduled_posts.start()  # pylint: disable=no-member
        self.random_media_random_time.start()  # pylint: disable=no-member

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
    async def send_scheduled_posts(self) -> None:
        """Task to loop over the scheduled posts.

        Iterates over all of the scheduled posts. For each post, the bot will
        sleep for some time and then post the message, moving onto the next
        message in the list after that.

        Once all messages have been sent, the task will be complete and start
        again in 10 seconds.
        """
        await self.bot.wait_until_ready()
        self.__order_videos_by_soonest()

        for post in self.scheduled_posts:
            for file in post.files:
                if not Path(file).exists():
                    logger.error("file %s does not exist for %s", post.files, post.message)
                    continue

            sleep_for = calculate_sleep_time(post.day, post.hour, post.minute)
            logger.info(
                "Waiting %d seconds/%d minutes/%.1f hours until posting %s",
                sleep_for,
                int(sleep_for / 60),
                sleep_for / 3600.0,
                post.seed_word.upper(),
            )
            await asyncio.sleep(sleep_for)

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

            for channel in post.channels:
                channel = await self.bot.fetch_channel(channel)

                if len(post.files) > 1:
                    await channel.send(
                        f"{message} {markov_sentence}", files=[disnake.File(file) for file in post.files]
                    )
                else:
                    await channel.send(f"{message} {markov_sentence}", file=disnake.File(post.files[0]))

        self.__order_videos_by_soonest()

    @tasks.loop(seconds=1)
    async def random_media_random_time(self):
        """Posts a random piece of medium from a directory at a random
        interval.
        """
        await self.bot.wait_until_ready()
        sleep_for = random.randint(3600, 86400)  # 1 - 24 hours
        logger.info("Next random image in %.1f hours", sleep_for / 3600)
        await asyncio.sleep(sleep_for)

        if len(self.random_media_files) == 0:
            return  # return after sleep to avoid return and calling every 1 sec

        random_file = random.choice(self.random_media_files)

        for channel_id in (App.config("ID_CHANNEL_IDIOTS"), App.config("ID_CHANNEL_ENGORGED")):
            channel = await self.bot.fetch_channel(channel_id)
            await channel.send(file=disnake.File(random_file))
