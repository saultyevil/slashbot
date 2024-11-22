"""Scheduled posts cog."""

import asyncio
import json
import logging
import threading
from pathlib import Path

import disnake
from disnake.ext import commands, tasks
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from bot.custom_bot import SlashbotInterationBot
from bot.custom_cog import SlashbotCog
from slashbot.config import Bot
from slashbot.markov import generate_markov_sentences
from slashbot.util import calculate_seconds_until

logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


def check_post_has_keys(post: dict, keys: list) -> bool:
    """Check if all the given keys are present in the given dictionary.

    Parameters
    ----------
    post : dict
        The dictionary to check.
    keys : list
        The list of keys to check for.

    Returns
    -------
    bool
        True if all keys are present, False otherwise.

    """
    return all(key in post for key in keys)


def check_post_has_iterable(post: dict, key: str) -> bool:
    """Check if the given key has an iterable value.

    Parameters
    ----------
    post : dict
        The dictionary to check.
    key : str
        The key to check for.

    Returns
    -------
    bool
        True if the key has an iterable value, False otherwise.

    """
    return hasattr(post[key], "__iter__")


class ScheduledPosts(SlashbotCog):
    """Scheduled post cog.

    Scheduled posts should be added to self.scheduled_posts using a Post
    class.
    """

    # Special methods ----------------------------------------------------------

    def __init__(self, bot: SlashbotInterationBot) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The bot object.

        """
        super().__init__(bot)

        self.scheduled_posts = None
        self.get_scheduled_posts()
        self.post_loop.start()  # pylint: disable=no-member

        self.watch_thread = threading.Thread(target=self.update_posts_on_modify)
        self.watch_thread.start()

    # Private methods ----------------------------------------------------------

    def calculate_time_until_post(self) -> None:
        """Calculate the length until a post is to be posted.

        This function doesn't return anything. It modifies self.scheduled_posts
        in place.
        """
        for post in self.scheduled_posts:
            post["time_until_post"] = calculate_seconds_until(
                int(post["day"]),
                int(post["hour"]),
                int(post["minute"]),
                7,
            )

    def order_scheduled_posts_by_soonest(self) -> None:
        """Order the schedulded posts by the soonest post."""
        self.calculate_time_until_post()
        self.scheduled_posts.sort(key=lambda x: x["time_until_post"])

    def get_scheduled_posts(self) -> None:
        """Read in the scheduled posts Json file."""
        with Path.open(Bot.get_config("SCHEDULED_POST_FILE"), encoding="utf-8") as file_in:
            posts_json = json.load(file_in)

        self.scheduled_posts = posts_json["SCHEDULED_POSTS"]

        # Before we return from this function, we should first check to make
        # sure each post has the correct fields in the correct format
        for post in self.scheduled_posts:
            if not check_post_has_keys(
                post,
                ("title", "files", "channels", "users", "day", "hour", "minute", "seed_word", "message"),
            ):
                logger.warning("Post '%s' is missing some keys", post.get("title", "unknown"))
            if not check_post_has_iterable(post, "files"):
                logger.warning("Post '%s' has non-iterable files", post["title"])
            if not check_post_has_iterable(post, "users"):
                logger.warning("Post '%s' has non-iterable users", post["title"])
            if not check_post_has_iterable(post, "channels"):
                logger.warning("Post '%s' has non-iterable channels", post["title"])

        logger.info(
            "%d scheduled posts loaded from %s",
            len(self.scheduled_posts),
            Bot.get_config("SCHEDULED_POST_FILE"),
        )
        self.order_scheduled_posts_by_soonest()

    def update_posts_on_modify(self) -> None:
        """Reload the posts on file modify."""

        class PostWatcher(FileSystemEventHandler):
            """File watcher to watch for changes to scheduled posts file."""

            def __init__(self, parent: ScheduledPosts) -> None:
                """Initialise the watcher."""
                super().__init__()
                self.parent = parent

            def on_modified(self, event: FileSystemEventHandler) -> None:
                """Reload the posts on file modify.

                Parameters
                ----------
                event : FileSystemEventHandler
                    The event to check.

                """
                if event.src_path == str(Bot.get_config("SCHEDULED_POST_FILE").absolute()):
                    self.parent.get_scheduled_posts()
                    # If the loop is running, we'll restart the task otherwise
                    # start the task. The post should *never* not be running,
                    # but better safe than sorry as it can sometimes raise an
                    # exception and stop
                    if self.parent.post_loop.is_running():
                        self.parent.post_loop.restart()
                    else:
                        self.parent.post_loop.start()

        observer = Observer()
        observer.schedule(PostWatcher(self), path=str(Bot.get_config("SCHEDULED_POST_FILE").parent.absolute()))
        observer.start()

    # Task ---------------------------------------------------------------------

    @tasks.loop(seconds=1)
    async def post_loop(self) -> None:
        """Task to loop over the scheduled posts.

        Iterates over all the scheduled posts. For each post, the bot will
        sleep for some time and then post the message, moving onto the next
        message in the list after that.

        Once all messages have been sent, the task will be complete and start
        again in 10 seconds.
        """
        self.order_scheduled_posts_by_soonest()

        for post in self.scheduled_posts:
            # we first should update sleep_for, as the original value calculated
            # when read in is no longer valid as it is a static, and not
            # dynamic, value
            sleep_for = calculate_seconds_until(int(post["day"]), int(post["hour"]), int(post["minute"]), 7)
            logger.info(
                "Waiting %d seconds/%d minutes/%.1f hours until posting %s",
                sleep_for,
                int(sleep_for / 60),
                sleep_for / 3600.0,
                post["title"],
            )
            await asyncio.sleep(sleep_for)

            markov_sentence = generate_markov_sentences(None, post["seed_word"], 1)
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
                channel = await self.bot.fetch_channel(channel)  # noqa: PLW2901
                # Check in this case, just to be safe as I don't want
                # disnake.File to complain if it gets nothing
                if len(post["files"]) > 0:
                    await channel.send(
                        f"{message} {markov_sentence}",
                        files=[disnake.File(file) for file in post["files"]],
                    )
                else:
                    await channel.send(f"{message} {markov_sentence}")

    @post_loop.before_loop
    async def wait(self) -> None:
        """Wait for bot to be ready."""
        await self.bot.wait_until_ready()


def setup(bot: commands.InteractionBot) -> None:
    """Set up the cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(ScheduledPosts(bot))
