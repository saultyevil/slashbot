from collections.abc import Callable

import disnake
import feedparser
from disnake.ext import tasks

from slashbot.bot.custom_cog import CustomCog
from slashbot.settings import BotSettings

from .backloggd import BackloggdTracker
from .letterboxd import LetterboxdTracker
from .tracker import MediaTracker, PollResult, TrackerRun


class MediaTrackers(CustomCog):
    """Cog for posting when a user has logged media on Letterboxd or Backloggd."""

    async def _get_channels(self, channel_ids: list[int], label: str) -> list[disnake.TextChannel]:
        """Get compatible text channels for a tracker.

        Parameters
        ----------
        channel_ids : list[int]
            Discord channel IDs to fetch.
        label : str
            Tracker label used in error messages.

        Returns
        -------
        list[disnake.TextChannel]
            Compatible channels.

        Raises
        ------
        ValueError
            If no configured channel is a server text channel.

        """
        if self.bot.reload:
            return [await self.bot.fetch_channel(1117059319230382140)]  # type: ignore

        channels = []
        for channel_id in channel_ids:
            channel = await self.bot.fetch_channel(channel_id)
            if not isinstance(channel, disnake.TextChannel):
                self.log_error("Channel %d for %s tracking is not a server text channel", channel_id, label)
                continue
            channels.append(channel)

        if not channels:
            exc_msg = f"No compatible channels found for {label} tracking"
            raise ValueError(exc_msg)
        return channels

    async def _poll_tracker[T](self, usernames: list[str], tracker: MediaTracker[T]) -> PollResult[T]:
        """Fetch, persist, and return entries newer than the last stored entry.

        Parameters
        ----------
        usernames : list[str]
            Service usernames to poll.
        tracker : MediaTracker[T]
            Service-specific feed and persistence operations.

        Returns
        -------
        PollResult[T]
            New entries grouped by username.

        """
        results: dict[str, list[T]] = {}
        for username in usernames:
            user_feed = feedparser.parse(tracker.feed_url_template.format(username))
            if user_feed.bozo:
                self.log_warning("Malformed %s feed: username=%s", tracker.service_label, username)
            self.log_debug(
                "Fetched %s feed: username=%s entries=%d", tracker.service_label, username, len(user_feed.entries)
            )
            if not user_feed.entries:
                self.log_warning("%s has not logged any content in %s", username, tracker.service_label)
                results[username] = []
                continue

            last_entry = await tracker.get_last_entry(username)
            self.log_debug(
                "Checked last %s entry: username=%s found=%s",
                tracker.service_label,
                username,
                last_entry is not None,
            )
            last_title = getattr(last_entry, "title", None)
            new_entries: list[T] = []
            for feed_entry in user_feed.entries:
                title = tracker.get_title(feed_entry)
                if not title:
                    self.log_error("Unable to parse entry title %s for %s", feed_entry.get("title"), username)
                    continue
                if title == last_title:
                    break
                try:
                    new_entries.append(await tracker.upsert_entry(username, feed_entry))
                except Exception as exc:  # noqa: BLE001
                    self.log_error("Failed to add entry %s for %s: %s", title, username, exc)

            if not last_title:
                results[username] = []
                self.log_warning(
                    "%s has probably just been created, sending back empty %s",
                    username,
                    tracker.empty_log_label,
                )
            else:
                results[username] = new_entries

        return PollResult(results)

    async def _post_new_entries[T](
        self,
        poll_result: PollResult[T],
        username_to_discord_id: dict[str, int],
        channels: list[disnake.TextChannel],
        create_embed: Callable[[T], disnake.Embed],
    ) -> None:
        """Post newly found entries to channels where the user is a member.

        Parameters
        ----------
        poll_result : PollResult[T]
            Entries to post, grouped by username.
        username_to_discord_id : dict[str, int]
            Mapping from service username to Discord user ID.
        channels : list[disnake.TextChannel]
            Channels where entries may be posted.
        create_embed : Callable
            Function creating an embed for an entry.

        """
        for username, entries in poll_result.entries_by_user.items():
            if not entries:
                continue
            discord_user = await self.bot.fetch_user(username_to_discord_id[username])
            embeds = [create_embed(entry) for entry in entries[:10]]
            for channel in channels:
                if channel.guild.get_member(discord_user.id):
                    await channel.send(embeds=embeds)

    async def _run_tracker[T](self, run: TrackerRun[T]) -> None:
        """Poll one tracker and notify Discord when new entries are found.

        Parameters
        ----------
        run : TrackerRun[T]
            Tracker, users, channels, and embed factory for this run.

        """
        poll_result = await self._poll_tracker(run.usernames, run.tracker)
        if not poll_result.has_new_entries:
            return

        self.log_info(
            "New %ss found: users=%d entries=%d",
            run.tracker.entry_label,
            len(poll_result.entries_by_user),
            len(poll_result.entries),
        )
        try:
            channels = await self._get_channels(run.channel_ids, label=run.channel_label)
        except Exception as exc:  # noqa: BLE001
            self.log_error("Exception raised when getting channels: %s", exc)
            return

        await self._post_new_entries(
            poll_result=poll_result,
            username_to_discord_id=run.username_to_discord_id,
            channels=channels,
            create_embed=run.create_embed,
        )
        self.log_info(
            "Posted new %s entries: users=%d channels=%d",
            run.tracker.entry_label,
            len(poll_result.entries_by_user),
            len(channels),
        )

    async def get_most_recent_movie_watched(self, usernames: list[str]) -> PollResult:
        """Return newly watched Letterboxd movies grouped by username.

        Parameters
        ----------
        usernames : list[str]
            Letterboxd usernames to poll.

        Returns
        -------
        PollResult
            Newly watched movies grouped by username.

        """
        adapter = LetterboxdTracker(self.db, self.log_error, self.log_debug)
        return await self._poll_tracker(usernames, adapter.config())

    @tasks.loop(minutes=BotSettings.cogs.media_tracker.update_interval)
    async def check_for_new_watched_movies(self) -> None:
        """Periodically check for new logged movies."""
        users = await self.db.get_letterboxd_usernames()
        adapter = LetterboxdTracker(self.db, self.log_error, self.log_debug)
        await self._run_tracker(
            TrackerRun(
                usernames=[user.letterboxd_username for user in users],
                username_to_discord_id={user.letterboxd_username: user.discord_id for user in users},
                channel_ids=BotSettings.cogs.media_tracker.letterboxd_channels,
                channel_label="movie",
                tracker=adapter.config(),
                create_embed=adapter.create_embed,
            )
        )

    @check_for_new_watched_movies.error
    async def letterboxd_handle_uncaught_exception(self, exception: BaseException) -> None:
        """Log uncaught exceptions raised by the Letterboxd task."""
        self.log_error("Uncaught exception raised in task: %s", exception)

    async def get_most_recent_logged_game(self, usernames: list[str]) -> PollResult:
        """Return newly logged Backloggd games grouped by username.

        Parameters
        ----------
        usernames : list[str]
            Backloggd usernames to poll.

        Returns
        -------
        PollResult
            Newly logged games grouped by username.

        """
        adapter = BackloggdTracker(self.db, self.log_error, self.log_debug)
        return await self._poll_tracker(usernames, adapter.config())

    @tasks.loop(minutes=BotSettings.cogs.media_tracker.update_interval)
    async def check_for_new_logged_games(self) -> None:
        """Periodically check for new logged games."""
        users = await self.db.get_backloggd_usernames()
        if not users:
            return
        adapter = BackloggdTracker(self.db, self.log_error, self.log_debug)
        await self._run_tracker(
            TrackerRun(
                usernames=[user.backloggd_username for user in users],
                username_to_discord_id={user.backloggd_username: user.discord_id for user in users},
                channel_ids=BotSettings.cogs.media_tracker.backloggd_channels,
                channel_label="game",
                tracker=adapter.config(),
                create_embed=adapter.create_embed,
            )
        )

    @check_for_new_logged_games.error
    async def backloggd_handle_uncaught_exception(self, exception: BaseException) -> None:
        """Log uncaught exceptions raised by the Backloggd task."""
        self.log_error("Uncaught exception raised in task: %s", exception)
