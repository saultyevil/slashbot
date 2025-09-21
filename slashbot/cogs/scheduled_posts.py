"""Scheduled posts cog."""

import asyncio
import threading
from pathlib import Path

import disnake
import yaml
from disnake.ext import tasks
from pydantic import BaseModel, Field, field_validator

import slashbot.watchers
from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.clock import calculate_seconds_until
from slashbot.markov import generate_text_from_markov_chain
from slashbot.settings import BotSettings
from slashbot.watchers import ScheduledPostWatcher


class ScheduledPost(BaseModel):
    """Pydantic model for scheduled posts."""

    title: str
    channels: list[int]
    files: list[str] | None = Field(default_factory=list)
    users: list[int] | None = Field(default_factory=list)
    day: int
    hour: int
    minute: int
    markov_seed_word: str | None = None
    message: str | None = None
    time_until_post: float | int | None = None

    @field_validator("day")
    @classmethod
    def _validate_day(cls, value: int) -> int:
        if not (0 <= value <= 6):  # noqa: PLR2004
            msg = "day must be between 0 and 6"
            raise ValueError(msg)
        return value

    @field_validator("hour")
    @classmethod
    def _validate_hour(cls, value: int) -> int:
        if not (0 <= value <= 23):  # noqa: PLR2004
            msg = "hour must be between 0 and 23"
            raise ValueError(msg)
        return value

    @field_validator("minute")
    @classmethod
    def _validate_minute(cls, value: int) -> int:
        if not (0 <= value <= 59):  # noqa: PLR2004
            msg = "minute must be between 0 and 59"
            raise ValueError(msg)
        return value

    @field_validator("channels")
    @classmethod
    def _validate_channels(cls, value: int | list[int]) -> int | list[int]:
        if isinstance(value, int):
            value = [value]
        elif isinstance(value, list):
            if not all(isinstance(item, int) for item in value):
                msg = "all items in channels must be integers"
                raise ValueError(msg)
        elif not isinstance(value, int):
            msg = "channels must be an integer or a list of integers"
            raise TypeError(msg)
        return value

    @field_validator("files", mode="before")
    @classmethod
    def _validate_files(cls, value: str | list[str] | None) -> str | list[str] | None:
        if value is None:
            return value
        if isinstance(value, str):
            return [value]
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        msg = "files must be a string or a list of strings"
        raise ValueError(msg)


class ScheduledPosts(CustomCog):
    """Scheduled post cog.

    Scheduled posts should be added to self.scheduled_posts using a Post
    class.
    """

    # Special methods ----------------------------------------------------------

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The bot object.

        """
        super().__init__(bot)

        self.scheduled_posts: list[ScheduledPost] = []
        self.watch_thread = threading.Thread(target=self.update_posts_on_modify)
        self.watch_thread.start()

    # Private methods ----------------------------------------------------------

    def calculate_time_until_post(self) -> None:
        """Calculate the length until a post is to be posted.

        This function doesn't return anything. It modifies self.scheduled_posts
        in place.
        """
        for post in self.scheduled_posts:
            post.time_until_post = calculate_seconds_until(
                post.day,
                post.hour,
                post.minute,
                7,
            )

    def order_scheduled_posts_by_soonest(self) -> None:
        """Order the schedulded posts by the soonest post."""
        self.calculate_time_until_post()
        self.scheduled_posts.sort(key=lambda x: x.time_until_post)  # type: ignore

    def get_scheduled_posts(self) -> None:
        """Read in the scheduled posts Json file."""
        with Path.open(BotSettings.files.scheduled_posts, encoding="utf-8") as file_in:
            posts_data = yaml.safe_load(file_in)
        for post in posts_data:
            try:
                self.scheduled_posts.append(ScheduledPost(**post))
            except TypeError as e:
                self.log_warning("Post '%s' is not valid: %s", post.get("title", "unknown"), e)
                continue
        self.log_info("%d scheduled posts loaded from %s", len(self.scheduled_posts), BotSettings.files.scheduled_posts)
        self.order_scheduled_posts_by_soonest()

    def update_posts_on_modify(self) -> None:
        """Reload the posts on file modify."""
        slashbot.watchers.FILE_OBSERVER.schedule(
            ScheduledPostWatcher(self), path=str(BotSettings.files.scheduled_posts.parent.absolute())
        )

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
        await self.bot.wait_until_ready()

        if not self.scheduled_posts:
            self.get_scheduled_posts()

        self.order_scheduled_posts_by_soonest()

        for post in self.scheduled_posts:
            # we first should update sleep_for, as the original value calculated
            # when read in is no longer valid as it is a static, and not
            # dynamic, value
            sleep_for = calculate_seconds_until(int(post.day), int(post.hour), int(post.minute), 7)
            self.log_info(
                "Waiting %d seconds/%d minutes/%.1f hours until posting %s",
                sleep_for,
                int(sleep_for / 60),
                sleep_for / 3600.0,
                post.title,
            )
            await asyncio.sleep(sleep_for)

            if post.markov_seed_word:
                markov_sentence = generate_text_from_markov_chain(None, post.markov_seed_word, 1)
                markov_sentence = markov_sentence.replace(  # type: ignore
                    post.markov_seed_word,
                    f"**{post.markov_seed_word}**",
                )
            else:
                markov_sentence = ""

            message = ""
            if post.users:
                message += " ".join([(await self.bot.fetch_user(user)).mention for user in post.users])
            if post.message:
                message += f" {post.message}"

            for channel in post.channels:
                channel = await self.bot.fetch_channel(channel)  # noqa: PLW2901
                if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
                    self.log_warning("Scheduled post '%s' has invalid channel %s", post.title, channel)
                    continue
                # Check in this case, just to be safe as I don't want
                # disnake.File to complain if it gets nothing
                if post.files:
                    await channel.send(
                        f"{message} {markov_sentence}",
                        files=[disnake.File(file) for file in post.files],
                    )
                else:
                    await channel.send(f"{message} {markov_sentence}")

    @post_loop.before_loop
    async def wait(self) -> None:
        """Wait for bot to be ready."""
        await self.bot.wait_until_ready()


def setup(bot: CustomInteractionBot) -> None:
    """Set up the cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.enabled.scheduled_posts:
        return
    bot.add_cog(ScheduledPosts(bot))
