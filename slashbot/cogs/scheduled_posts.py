#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Scheduled posts cog."""

import asyncio
import json
import logging
import random
import threading
from pathlib import Path

import disnake
from disnake.ext import commands, tasks
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.util import calculate_sleep_time

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


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

        self.random_channels = App.config("RANDOM_POST_CHANNELS")
        self.scheduled_posts = None
        self.get_scheduled_posts()
        self.random_media_files = [
            file for file in Path(App.config("RANDOM_MEDIA_DIRECTORY")).rglob("*") if not file.is_dir()
        ]
        logger.info("Random post channels: %s", self.random_channels)
        logger.info("%d random media files found", len(self.random_media_files))

        self.post_scheduled_post_loop.start()  # pylint: disable=no-member
        self.post_random_media_file_loop.start()  # pylint: disable=no-member
        self.post_evil_wii_loop.start()  # pylint: disable=no-member

        self.watch_thread = threading.Thread(target=self.__update_posts_on_modify)
        self.watch_thread.start()

    # Private methods ----------------------------------------------------------

    def __update_posts_on_modify(self):
        """Reload the posts on file modify."""

        class MyHandler(FileSystemEventHandler):
            def __init__(self, parent):
                super().__init__()
                self.parent = parent

            def on_modified(self, event):
                if event.src_path == str(App.config("SCHEDULED_POST_FILE").absolute()):
                    self.parent.get_scheduled_posts()
                    self.parent.post_scheduled_post_loop.restart()

        observer = Observer()
        observer.schedule(MyHandler(self), path=str(App.config("SCHEDULED_POST_FILE").parent.absolute()))
        observer.start()

    def __calculate_time_until_post(self):
        """Calculates how long until a post is to be posted."""
        for post in self.scheduled_posts:
            post["time_until_post"] = calculate_sleep_time(post["day"], post["hour"], post["minute"])

    def __order_scheduled_posts_by_soonest(self):
        """Orders self.scheduled_posts to where the first entry is the video
        which is scheduled to be sent the soonest.
        """
        self.__calculate_time_until_post()
        self.scheduled_posts.sort(key=lambda x: x["time_until_post"])

    def get_scheduled_posts(self):
        """Read in the scheduled posts Json file."""
        with open(App.config("SCHEDULED_POST_FILE"), "r", encoding="utf-8") as file_in:
            posts_json = json.load(file_in)

        self.scheduled_posts = posts_json["SCHEDULED_POSTS"]

        # Before we return from this function, we should first check to make
        # sure each post has the correct fields in the correct format
        for post in self.scheduled_posts:
            assert all(
                key in post
                for key in ("title", "files", "channels", "users", "day", "hour", "minute", "seed_word", "message")
            ), f"{post.get('title', 'unknown')} post is missing some keys"
            assert hasattr(post["files"], "__iter__"), f"{post['title']} has non-iterable files"
            assert hasattr(post["users"], "__iter__"), f"{post['title']} has non-iterable users"
            assert hasattr(post["channels"], "__iter__"), f"{post['title']} has non-iterable channels"

        logger.info("%d scheduled posts loaded from %s", len(self.scheduled_posts), App.config("SCHEDULED_POST_FILE"))
        self.__order_scheduled_posts_by_soonest()

    # Task ---------------------------------------------------------------------

    @tasks.loop(seconds=1)
    async def post_scheduled_post_loop(self) -> None:
        """Task to loop over the scheduled posts.

        Iterates over all the scheduled posts. For each post, the bot will
        sleep for some time and then post the message, moving onto the next
        message in the list after that.

        Once all messages have been sent, the task will be complete and start
        again in 10 seconds.
        """
        await self.bot.wait_until_ready()
        self.__order_scheduled_posts_by_soonest()

        for post in self.scheduled_posts:
            # we first should update sleep_for, as the original value calculated
            # when read in is no longer valid as it is a static, and not
            # dynamic, value
            sleep_for = calculate_sleep_time(post["day"], post["hour"], post["minute"])
            logger.info(
                "Waiting %d seconds/%d minutes/%.1f hours until posting %s",
                sleep_for,
                int(sleep_for / 60),
                sleep_for / 3600.0,
                post["title"],
            )
            await asyncio.sleep(sleep_for)

            markov_sentence = await self.get_generated_sentence(post["seed_word"])
            markov_sentence = markov_sentence.replace(
                post["seed_word"],
                f"**{post['seed_word']}**",
            )

            message = ""
            if post["users"]:
                message += " ".join([(await self.bot.fetch_user(user)).mention for user in post["users"]])
            if post["message"]:
                message += f" {post['message']}"

            for channel in post["channels"]:
                channel = await self.bot.fetch_channel(channel)
                if len(post["files"]) > 1:
                    await channel.send(
                        f"{message} {markov_sentence}", files=[disnake.File(file) for file in post["files"]]
                    )
                else:
                    await channel.send(f"{message} {markov_sentence}", file=disnake.File(post["files"][0]))

    @tasks.loop(minutes=1)
    async def post_random_media_file_loop(self):
        """Posts a random piece of medium from a directory at a random
        interval.
        """
        await self.bot.wait_until_ready()

        sleep_for = random.randint(12 * 3600, 48 * 3600)
        logger.info("Next random image in %.1f hours", sleep_for / 3600)
        await asyncio.sleep(sleep_for)

        # return after sleep to avoid return and calling every 1 sec
        if len(self.random_media_files) == 0 or len(self.random_channels) == 0:
            return

        for channel_id in self.random_channels:
            channel = await self.bot.fetch_channel(int(channel_id))
            await channel.send(file=disnake.File(random.choice(self.random_media_files)))

    @tasks.loop(minutes=1)
    async def post_evil_wii_loop(self):
        """Posts a random piece of medium from a directory at a random
        interval.
        """
        await self.bot.wait_until_ready()

        sleep_for = random.randint(24 * 3600, 72 * 3600)
        logger.info("Next random evil wii in %.1f hours", sleep_for / 3600)
        await asyncio.sleep(sleep_for)

        file = disnake.File("data/images/evil_wii.png")
        file.filename = f"SPOILER_{file.filename}"
        channel = await self.bot.fetch_channel(App.config("ID_CHANNEL_IDIOTS"))
        await channel.send(file=file)


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.
    """
    bot.add_cog(ScheduledPosts(bot))
