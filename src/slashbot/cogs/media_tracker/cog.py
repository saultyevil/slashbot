import datetime
import re
from collections.abc import Awaitable, Callable

import disnake
import feedparser
from disnake.ext import tasks
from feedparser import FeedParserDict

from slashbot.bot.custom_cog import CustomCog
from slashbot.database.sql_models import LoggedGameSQL, WatchedMovieSQL
from slashbot.settings import BotSettings

# Type alias for the per-entry upsert callables passed to _get_new_feed_entries
type UpsertCallable[T] = Callable[[str, FeedParserDict], Awaitable[T]]


class MediaTrackers(CustomCog):
    """Cog for posting when a user has logged media on Letterboxd or Backloggd."""

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_rating_to_stars(rating: float) -> str:
        """Convert a float rating to a string of stars.

        Parameters
        ----------
        rating : float
            The rating, out of 5.

        Returns
        -------
        str
            The rating depicted as a number of stars.

        """
        if not rating:
            return "Unrated"
        full_stars = int(rating)
        half_star = rating - full_stars >= 0.5  # noqa: PLR2004
        stars = "★" * full_stars
        if half_star:
            stars += "½"
        return stars

    async def _get_channels(self, channel_ids: list[int], label: str) -> list[disnake.TextChannel]:
        """Get a list of text channels for posting tracking updates to.

        Parameters
        ----------
        channel_ids : list[int]
            The channel IDs to fetch, as configured in settings.
        label : str
            A human-readable label for the tracker (e.g. "movie", "game"),
            used in log messages.

        Returns
        -------
        list[disnake.TextChannel]
            A list of TextChannel instances.

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

    async def _get_new_feed_entries[T](
        self,
        usernames: list[str],
        feed_url_template: str,
        get_last_entry: Callable[[str], Awaitable[T | None]],
        get_title: Callable[[FeedParserDict], str | None],
        upsert_entry: UpsertCallable[T],
        service_label: str,
        empty_log_label: str,
    ) -> dict[str, list[T]]:
        """Fetch new RSS feed entries for a list of users, relative to the last known entry.

        This is the shared core for both Letterboxd and Backloggd polling. For
        each username it parses the RSS feed, walks entries until it reaches the
        last known one, and upserts any new ones via the provided callable.

        Parameters
        ----------
        usernames : list[str]
            The usernames to poll.
        feed_url_template : str
            A format string with a single ``{}`` placeholder for the username.
        get_last_entry : Callable[[str], Awaitable[T | None]]
            Async callable that returns the most recently stored entry for a
            username, or ``None`` if none exists.
        get_title : Callable[[FeedParserDict], str | None]
            Extracts the title string from a raw feed entry. May return ``None``
            if the entry should be skipped (e.g. unparseable title).
        upsert_entry : UpsertCallable[T]
            Async callable that persists a feed entry and returns the stored row.
        service_label : str
            Human-readable service name used in log messages (e.g. "letterboxd").
        empty_log_label : str
            Label used in the "empty watchlist" warning (e.g. "watchlist", "log list").

        Returns
        -------
        dict[str, list[T]]
            A mapping of username to newly logged entries.

        """
        if isinstance(usernames, str):
            usernames = [usernames]

        results: dict[str, list[T]] = {}

        for username in usernames:
            user_feed = feedparser.parse(feed_url_template.format(username))
            if not user_feed.entries:
                self.log_warning("%s has not logged any content in %s", username, service_label)
                results[username] = []
                continue

            last_entry = await get_last_entry(username)
            self.log_debug(
                "Last entry for %s is %s",
                username,
                last_entry.__dict__ if last_entry else None,
            )
            last_title = last_entry.title if last_entry else None

            new_entries: list[T] = []
            for feed_entry in user_feed.entries:
                title = get_title(feed_entry)
                if not title:
                    self.log_error("Unable to parse entry title %s for %s", feed_entry.get("title"), username)
                    continue
                if title == last_title:
                    break
                try:
                    new_entries.append(await upsert_entry(username, feed_entry))
                except Exception as exc:  # noqa: BLE001
                    self.log_error("Failed to add entry %s for %s: %s", title, username, exc)

            # If there was no prior entry the user was just added; return an
            # empty list to avoid re-posting historical content.
            if not last_title:
                results[username] = []
                self.log_warning("%s has probably just been created, sending back empty %s", username, empty_log_label)
            else:
                results[username] = new_entries

        return results

    async def _post_new_entries[T](
        self,
        new_entries: dict[str, list[T]],
        username_to_discord_id: dict[str, int],
        channels: list[disnake.TextChannel],
        create_embed: Callable[[T], disnake.Embed],
    ) -> None:
        """Post embeds for newly logged entries to all relevant channels.

        Parameters
        ----------
        new_entries : dict[str, list[T]]
            Mapping of username to new entries to post.
        username_to_discord_id : dict[str, int]
            Mapping of service username to Discord user ID.
        channels : list[disnake.TextChannel]
            The channels to post to.
        create_embed : Callable[[T], disnake.Embed]
            Callable that builds an embed for a single entry.

        """
        for username, entries in new_entries.items():
            if not entries:
                continue
            discord_user = await self.bot.fetch_user(username_to_discord_id[username])
            # Discord caps embeds per message at 10
            embeds = [create_embed(entry) for entry in entries[:10]]
            for channel in channels:
                if channel.guild.get_member(discord_user.id):
                    await channel.send(embeds=embeds)

    def _handle_task_error(self, exception: BaseException) -> None:
        """Log uncaught exceptions raised by a task loop.

        Parameters
        ----------
        exception : BaseException
            The exception that was raised and not caught in the loop.

        """
        self.log_error("Uncaught exception raised in task: %s", exception)

    # ------------------------------------------------------------------
    # Letterboxd
    # ------------------------------------------------------------------

    async def _add_watched_movie_to_database(
        self, letterboxd_username: str, movie_entry: FeedParserDict
    ) -> WatchedMovieSQL:
        """Add an RSS feed movie entry into the database.

        Parameters
        ----------
        letterboxd_username : str
            The Letterboxd username.
        movie_entry : FeedParserDict
            An entry from the user's RSS feed to add.

        Returns
        -------
        WatchedMovieSQL
            The movie added to the database.

        """
        user_db = await self.db.get_user("letterboxd_username", letterboxd_username)
        if not user_db:
            exc_msg = f"Letterboxd user {letterboxd_username} was not in the database"
            self.log_error("%s", exc_msg)
            raise ValueError(exc_msg)

        poster_url_match = re.search(r'src="([^"]+)"', movie_entry["summary"])  # type: ignore
        poster_url = poster_url_match.group(1) if poster_url_match else None
        watched_date_str = movie_entry.get("letterboxd_watcheddate", None)
        watched_date = datetime.datetime.strptime(watched_date_str, r"%Y-%m-%d") if watched_date_str else None  # type: ignore # noqa: DTZ007

        movie = WatchedMovieSQL(
            user_id=user_db.id,
            username=letterboxd_username,
            title=movie_entry["letterboxd_filmtitle"],
            film_year=movie_entry["letterboxd_filmyear"],
            user_rating=movie_entry.get("letterboxd_memberrating", None),
            published_date=datetime.datetime.strptime(movie_entry["published"], "%a, %d %b %Y %H:%M:%S %z"),  # type: ignore
            watched_date=watched_date,
            tmdb_id=movie_entry["tmdb_movieid"],
            url=str(movie_entry["link"]).replace(f"{letterboxd_username}/", ""),
            poster_url=poster_url,
        )
        new_movie = await self.db.upsert_row(movie)
        self.log_debug("Added new movie %s (%s) for %s", movie.title, movie.watched_date, letterboxd_username)

        return new_movie

    def _create_watched_movie_embed(self, watched_movie: WatchedMovieSQL) -> disnake.Embed:
        """Create an embed instance for a watched movie.

        Parameters
        ----------
        watched_movie : WatchedMovieSQL
            The DB instance of the movie to create the embed for.

        Returns
        -------
        disnake.Embed
            The created embed.

        """
        embed = disnake.Embed(title=f"{watched_movie.username.capitalize()} added a film", url=watched_movie.url)
        embed.add_field(name="Film title", value=watched_movie.title, inline=False)
        embed.add_field(name="Release year", value=watched_movie.film_year, inline=False)
        if watched_movie.watched_date:
            embed.add_field(
                name="Watched date", value=datetime.datetime.strftime(watched_movie.watched_date, r"%d/%m/%Y")
            )
        embed.add_field(
            name="User rating", value=self._convert_rating_to_stars(watched_movie.user_rating), inline=False
        )
        embed.set_thumbnail(url=watched_movie.poster_url)

        return embed

    async def get_most_recent_movie_watched(self, letterboxd_usernames: list[str]) -> dict[str, list[WatchedMovieSQL]]:
        """Get newly watched movies for a list of Letterboxd users.

        Only entries logged since the last known entry are returned. If a user
        has no prior entries (i.e. they were just added), an empty list is
        returned to avoid replaying their full history.

        Parameters
        ----------
        letterboxd_usernames : list[str]
            The Letterboxd usernames to poll.

        Returns
        -------
        dict[str, list[WatchedMovieSQL]]
            A mapping of username to newly watched movies.

        """

        def get_title(entry: FeedParserDict) -> str | None:
            # Skip non-movie entries (e.g. TV shows lack a tmdb_movieid)
            if "tmdb_movieid" not in entry:
                return None
            return entry.get("letterboxd_filmtitle")

        return await self._get_new_feed_entries(
            usernames=letterboxd_usernames,
            feed_url_template="https://letterboxd.com/{}/rss/",
            get_last_entry=self.db.get_last_movie_for_letterboxd_user,
            get_title=get_title,
            upsert_entry=self._add_watched_movie_to_database,
            service_label="letterboxd",
            empty_log_label="watchlist",
        )

    @tasks.loop(minutes=BotSettings.cogs.media_tracker.update_interval)
    async def check_for_new_watched_movies(self) -> None:
        """Periodically check for new logged movies."""
        letterboxd_users = await self.db.get_letterboxd_usernames()
        new_movies_watched = await self.get_most_recent_movie_watched(
            [user.letterboxd_username for user in letterboxd_users]
        )
        if not new_movies_watched:
            return
        self.log_debug(
            "New movies watched: %s",
            [{user: [movie.__dict__ for movie in movies]} for user, movies in new_movies_watched.items()],
        )

        # Catch Discord unavailability broadly — if this kills the loop it is
        # surprisingly difficult to automatically restart tasks.
        try:
            channels = await self._get_channels(BotSettings.cogs.media_tracker.letterboxd_channels, label="movie")
        except Exception as exc:
            self.log_error("Exception raised when getting channels: %s", exc)
            return

        await self._post_new_entries(
            new_entries=new_movies_watched,
            username_to_discord_id={user.letterboxd_username: user.discord_id for user in letterboxd_users},
            channels=channels,
            create_embed=self._create_watched_movie_embed,
        )

    @check_for_new_watched_movies.error
    async def letterboxd_handle_uncaught_exception(self, exception: BaseException) -> None:
        """Log uncaught exceptions raised by the Letterboxd task."""
        self._handle_task_error(exception)

    # ------------------------------------------------------------------
    # Backloggd
    # ------------------------------------------------------------------

    async def _add_game_to_database(self, backloggd_username: str, game_entry: FeedParserDict) -> LoggedGameSQL:
        """Add an RSS feed game entry into the database.

        Parameters
        ----------
        backloggd_username : str
            The Backloggd username.
        game_entry : FeedParserDict
            An entry from the user's RSS feed to add.

        Returns
        -------
        LoggedGameSQL
            The game added to the database.

        """
        user_db = await self.db.get_user("backloggd_username", backloggd_username)
        if not user_db:
            exc_msg = f"Backloggd user {backloggd_username} was not in the database"
            self.log_error("%s", exc_msg)
            raise ValueError(exc_msg)

        title_match = re.match(r"^(.*?) \(\d{4}\)", str(game_entry["title"]))
        title = title_match.group(1) if title_match else None

        year_match = re.search(r"\((\d{4})\)", str(game_entry["title"]))
        year = year_match.group(1) if year_match else None

        date_str = game_entry.get("published", None)
        date = datetime.datetime.strptime(date_str, r"%a, %d %b %Y %H:%M:%S %z") if date_str else None  # type: ignore

        game_row = LoggedGameSQL(
            user_id=user_db.id,
            username=backloggd_username,
            title=title,
            game_year=year,
            published_date=date,
            user_rating=float(str(game_entry["backloggd_user_rating"])) / 2,
            url=game_entry["link"],
            poster_url=game_entry["href"],
        )
        new_game = await self.db.upsert_row(game_row)
        self.log_debug("Added new game %s (%s) for %s", game_row.title, game_row.published_date, backloggd_username)

        return new_game

    def _create_logged_game_embed(self, logged_game: LoggedGameSQL) -> disnake.Embed:
        """Create an embed instance for a logged game.

        Parameters
        ----------
        logged_game : LoggedGameSQL
            The DB instance of the game to create the embed for.

        Returns
        -------
        disnake.Embed
            The created embed.

        """
        embed = disnake.Embed(title=f"{logged_game.username.capitalize()} logged a game", url=logged_game.url)
        embed.add_field(name="Game title", value=logged_game.title, inline=False)
        embed.add_field(name="Release year", value=logged_game.game_year, inline=False)
        if logged_game.published_date:
            embed.add_field(
                name="Published date", value=datetime.datetime.strftime(logged_game.published_date, r"%d/%m/%Y")
            )
        embed.add_field(name="User rating", value=self._convert_rating_to_stars(logged_game.user_rating), inline=False)
        embed.set_thumbnail(url=logged_game.poster_url)

        return embed

    async def get_most_recent_logged_game(self, backloggd_usernames: list[str]) -> dict[str, list[LoggedGameSQL]]:
        """Get newly logged games for a list of Backloggd users.

        Only entries logged since the last known entry are returned. If a user
        has no prior entries (i.e. they were just added), an empty list is
        returned to avoid replaying their full history.

        Parameters
        ----------
        backloggd_usernames : list[str]
            The Backloggd usernames to poll.

        Returns
        -------
        dict[str, list[LoggedGameSQL]]
            A mapping of username to newly logged games.

        """

        def get_title(entry: FeedParserDict) -> str | None:
            m = re.match(r"^(.*?) \(\d{4}\)", str(entry["title"]))
            return m.group(1) if m else None

        return await self._get_new_feed_entries(
            usernames=backloggd_usernames,
            feed_url_template="https://backloggd.com/u/{}/reviews/rss/",
            get_last_entry=self.db.get_last_game_for_backloggd_user,
            get_title=get_title,
            upsert_entry=self._add_game_to_database,
            service_label="backloggd",
            empty_log_label="log list",
        )

    @tasks.loop(minutes=BotSettings.cogs.media_tracker.update_interval)
    async def check_for_new_logged_games(self) -> None:
        """Periodically check for new logged games."""
        backloggd_users = await self.db.get_backloggd_usernames()
        if not backloggd_users:
            return
        new_games_logged = await self.get_most_recent_logged_game([user.backloggd_username for user in backloggd_users])
        if not new_games_logged:
            return
        self.log_debug(
            "New games logged: %s",
            [{user: [game.__dict__ for game in games]} for user, games in new_games_logged.items()],
        )

        # Catch Discord unavailability broadly — if this kills the loop it is
        # surprisingly difficult to automatically restart tasks.
        try:
            channels = await self._get_channels(BotSettings.cogs.media_tracker.backloggd_channels, label="game")
        except Exception as exc:
            self.log_error("Exception raised when getting channels: %s", exc)
            return

        await self._post_new_entries(
            new_entries=new_games_logged,
            username_to_discord_id={user.backloggd_username: user.discord_id for user in backloggd_users},
            channels=channels,
            create_embed=self._create_logged_game_embed,
        )

    @check_for_new_logged_games.error
    async def backloggd_handle_uncaught_exception(self, exception: BaseException) -> None:
        """Log uncaught exceptions raised by the Backloggd task."""
        self._handle_task_error(exception)
