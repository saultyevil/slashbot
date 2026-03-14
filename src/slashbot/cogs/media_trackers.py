import datetime
import re

import disnake
import feedparser
from disnake.ext import tasks
from feedparser import FeedParserDict

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.database.sql_models import WatchedMovieSQL
from slashbot.database.sql_models import LoggedGameSQL
from slashbot.logger import logger
from slashbot.settings import BotSettings


class MediaTrackers(CustomCog):
    """Cog for posting when a user has logged a new movie on Letterboxd."""

    async def _add_watched_movie_to_database(
        self, letterboxd_username: str, movie_entry: FeedParserDict
    ) -> WatchedMovieSQL:
        """Add a RSS feed movie entry into the database.

        Parameters
        ----------
        letterboxd_username : str
            The Letterboxd username.
        movie_entry : str
            An entry from the user's RSS feed to add.

        Returns
        -------
        WatchedMovie
            The movie added to the database.

        """
        user_db = await self.db.get_user("letterboxd_username", letterboxd_username)
        if not user_db:
            exc_msg = f"Letterboxd user {letterboxd_username} was not in the database"
            self.log_error("%s", exc_msg)
            raise ValueError(exc_msg)

        poster_url_regex = re.search(r'src="([^"]+)"', movie_entry["summary"])  # type: ignore
        poster_url = poster_url_regex.group(1) if poster_url_regex else None
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

    async def _get_channels_letterboxd(self) -> list[disnake.TextChannel]:
        """Get the channels for posting movie tracking to.

        Returns
        -------
        list[disnake.TextChannel]
            A list of TextChannel instances.

        """
        # If bot.reload, then we are in debug mode so return test channel
        if self.bot.reload:
            return [await self.bot.fetch_channel(1117059319230382140)]  # type: ignore

        channels = []
        for channel_id in BotSettings.cogs.media_tracker.letterboxd_channels:
            channel = await self.bot.fetch_channel(channel_id)
            if not isinstance(channel, disnake.TextChannel):
                self.log_error("Channel %d for movie tracking is not a server text channel", channel)
                continue
            channels.append(channel)

        if len(channels) == 0:
            exc_msg = "No compatible channels found for movie tracking"
            raise ValueError(exc_msg)

        return channels

    def _create_watched_movie_embed(self, watched_movie: WatchedMovieSQL) -> disnake.Embed:
        """Create an embed instance for a watched movie and user.

        Parameters
        ----------
        discord_user : disnake.User
            An instance of a User for discord.
        watched_movie : WatchedMovie
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

    async def get_most_recent_movie_watched(
        self, letterboxd_usernames: list[str] | str
    ) -> dict[str, list[WatchedMovieSQL] | list]:
        """Get the latest watched movies for some Letterboxd users.

        This will return only the latest movie for the user. Therefore if a user
        is logging multiple within the update interval, then only the most
        latest will be retrieved.

        Parameters
        ----------
        letterboxd_usernames : list[str] | str
            The user(s) to find the latest movies watched.

        Returns
        -------
        dict[str, list[WatchedMovieSQL] | list]
            A mapping of username to movies watched.

        """
        results = {}

        for letterboxd_username in letterboxd_usernames:
            user_feed = feedparser.parse(f"https://letterboxd.com/{letterboxd_username}/rss/")
            if not user_feed.entries:
                self.log_warning("%s has not logged any content in letterboxd", letterboxd_username)
                results[letterboxd_username] = []
                continue

            new_movies_watched = []
            last_movie_watched = await self.db.get_last_movie_for_letterboxd_user(letterboxd_username)
            self.log_debug(
                "Last movie watched for %s is %s",
                letterboxd_username,
                last_movie_watched.__dict__ if last_movie_watched else None,
            )
            last_movie_title = last_movie_watched.title if last_movie_watched else None

            for movie_entry in user_feed.entries:
                title = movie_entry["letterboxd_filmtitle"]
                # Early exit to avoid sending all movies watched
                if title == last_movie_title:
                    break
                # This is not a movie then, but probably a tv show
                if "tmdb_movieid" not in movie_entry:
                    continue
                try:
                    new_movies_watched.append(
                        await self._add_watched_movie_to_database(letterboxd_username, movie_entry)
                    )
                except Exception as exc:  # noqa: BLE001
                    self.log_error("Failed to add movie %s for %s: %s", title, letterboxd_username, exc)

            # If the user has just been added then there will be no last movie
            # watched. To avoid sending the last movie they watched before tracking
            # began, we'll send an empty list back
            if not last_movie_title:
                results[letterboxd_username] = []
                self.log_warning("%s has probably just been created, sending back empty watchlist", letterboxd_username)
            else:
                results[letterboxd_username] = new_movies_watched

        return results

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

        # not sure what exception is raised... but if discord is unavailable this
        # function kills the loop and it's surprisingly hard to automatically restart
        # tasks. Catching the unavailable error here should also prevent something
        # like fetch_user() from bringing the task down
        try:
            channels = await self._get_channels_letterboxd()
        except Exception as exc:
            self.log_error("Exception raised when getting channels: %s", exc)
            return

        letterboxd_to_discord_map = {user.letterboxd_username: user.discord_id for user in letterboxd_users}

        for letterboxd_username, watched_movies in new_movies_watched.items():
            if not watched_movies:
                continue
            discord_user = await self.bot.fetch_user(letterboxd_to_discord_map[letterboxd_username])
            # limit watched movies to first 10, as that is the embed limit
            embeds = [self._create_watched_movie_embed(watched_movie) for watched_movie in watched_movies[:10]]
            for channel in channels:
                in_guild = channel.guild.get_member(discord_user.id)
                if in_guild:
                    await channel.send(embeds=embeds)

    @check_for_new_watched_movies.error
    async def letterboxd_handle_uncaught_exception(self, exception: BaseException) -> None:
        """Log uncaught exceptions raised by the task.

        Parameters
        ----------
        exception : BaseException
            The exception that was raised and not caught in the loop.

        """
        self.log_error("Uncaught exception raised in task: %s", exception)

    async def _add_game_to_database(self, backloggd_username: str, game_entry: FeedParserDict) -> LoggedGameSQL:
        """Add a RSS feed movie entry into the database.

        Parameters
        ----------
        backloggd_username : str
            The Backloggd username.
        game_entry : str
            An entry from the user's RSS feed to add.

        Returns
        -------
        WatchedMovie
            The movie added to the database.

        """
        user_db = await self.db.get_user("backloggd_username", backloggd_username)
        if not user_db:
            exc_msg = f"Backloggd user {backloggd_username} was not in the database"
            self.log_error("%s", exc_msg)
            raise ValueError(exc_msg)

        m = re.match(r"^(.*?) \(\d{4}\)", str(game_entry["title"]))
        title = m.group(1) if m else None

        m = re.search(r"\((\d{4})\)", str(game_entry["title"]))
        year = m.group(1) if m else None

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


    async def _get_channels_backloggd(self) -> list[disnake.TextChannel]:
        """Get the channels for posting movie tracking to.

        Returns
        -------
        list[disnake.TextChannel]
            A list of TextChannel instances.

        """
        # If bot.reload, then we are in debug mode so return test channel
        if self.bot.reload:
            return [await self.bot.fetch_channel(1117059319230382140)]  # type: ignore

        channels = []
        for channel_id in BotSettings.cogs.media_tracker.letterboxd_channels:
            channel = await self.bot.fetch_channel(channel_id)
            if not isinstance(channel, disnake.TextChannel):
                self.log_error("Channel %d for game tracking is not a server text channel", channel)
                continue
            channels.append(channel)

        if len(channels) == 0:
            exc_msg = "No compatible channels found for game tracking"
            raise ValueError(exc_msg)

        return channels

    def _create_logged_game_embed(self, logged_game: LoggedGameSQL) -> disnake.Embed:
        """Create an embed instance for a logged game and user.

        Parameters
        ----------
        discord_user : disnake.User
            An instance of a User for discord.
        logged_game : LoggedGameSQL
            The DB instance of the movie to create the embed for.

        Returns
        -------
        disnake.Embed
            The created embed.

        """
        embed = disnake.Embed(title=f"{logged_game.username.capitalize()} logged a game", url=logged_game.url)
        embed.add_field(name="Game title", value=logged_game.title, inline=False)
        embed.add_field(name="Release year", value=logged_game.game_year, inline=False)
        embed.add_field(
            name="Published date", value=datetime.datetime.strftime(logged_game.published_date, r"%d/%m/%Y")
        )
        embed.add_field(name="User rating", value=self._convert_rating_to_stars(logged_game.user_rating), inline=False)
        embed.set_thumbnail(url=logged_game.poster_url)

        return embed

    async def get_most_recent_logged_game(
        self, backloggd_usernames: list[str] | str
    ) -> dict[str, list[LoggedGameSQL] | list]:
        """Get the latest watched movies for some Letterboxd users.

        This will return only the latest movie for the user. Therefore if a user
        is logging multiple within the update interval, then only the most
        latest will be retrieved.

        Parameters
        ----------
        backloggd_usernames : list[str] | str
            The user(s) to find the latest games logged.

        Returns
        -------
        dict[str, list[LoggedGameSQL] | list]
            A mapping of username to games logged.

        """
        results = {}

        for backloggd_username in backloggd_usernames:
            user_feed = feedparser.parse(f"https://backloggd.com/u/{backloggd_username}/reviews/rss/")
            if not user_feed.entries:
                self.log_warning("%s has not logged any content in backloggd", backloggd_username)
                results[backloggd_username] = []
                continue

            new_games_logged = []
            last_game_logged = await self.db.get_last_game_for_backloggd_user(backloggd_username)
            self.log_debug(
                "Last game logged for %s is %s",
                backloggd_username,
                last_game_logged.__dict__ if last_game_logged else None,
            )
            last_game_title = last_game_logged.title if last_game_logged else None

            for game_entry in user_feed.entries:
                m = re.match(r"^(.*?) \(\d{4}\)", str(game_entry["title"]))
                title = m.group(1) if m else None
                if not title:
                    self.log_error("Unable to parse game's title %s for %s", game_entry["title"], backloggd_username)
                    continue
                # Early exit to avoid sending all games
                if title == last_game_title:
                    break
                try:
                    new_games_logged.append(await self._add_game_to_database(backloggd_username, game_entry))
                except Exception as exc:  # noqa: BLE001
                    self.log_error("Failed to add game %s for %s: %s", title, backloggd_username, exc)

            # If the user has just been added then there will be no last movie
            # watched. To avoid sending the last movie they watched before tracking
            # began, we'll send an empty list back
            if not last_game_title:
                results[backloggd_username] = []
                self.log_warning("%s has probably just been created, sending back empty log list", backloggd_username)
            else:
                results[backloggd_username] = new_games_logged

        return results

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
            [{user: [movie.__dict__ for movie in games]} for user, games in new_games_logged.items()],
        )

        # not sure what exception is raised... but if discord is unavailable this
        # function kills the loop and it's surprisingly hard to automatically restart
        # tasks. Catching the unavailable error here should also prevent something
        # like fetch_user() from bringing the task down
        try:
            channels = await self._get_channels_backloggd()
        except Exception as exc:
            self.log_error("Exception raised when getting channels: %s", exc)
            return

        backloggd_to_discord_map = {user.backloggd_username: user.discord_id for user in backloggd_users}

        for backloggd_username, logged_games in new_games_logged.items():
            if not logged_games:
                continue
            discord_user = await self.bot.fetch_user(backloggd_to_discord_map[backloggd_username])
            # limit watched movies to first 10, as that is the embed limit
            embeds = [self._create_logged_game_embed(watched_movie) for watched_movie in logged_games[:10]]
            for channel in channels:
                in_guild = channel.guild.get_member(discord_user.id)
                if in_guild:
                    await channel.send(embeds=embeds)

    @check_for_new_logged_games.error
    async def backloggd_handle_uncaught_exception(self, exception: BaseException) -> None:
        """Log uncaught exceptions raised by the task.

        Parameters
        ----------
        exception : BaseException
            The exception that was raised and not caught in the loop.

        """
        self.log_error("Uncaught exception raised in task: %s", exception)


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.media_tracker.enabled:
        logger.log_warning("%s has been disabled in the configuration file", MediaTrackers.__cog_name__)
        return
    bot.add_cog(MediaTrackers(bot))
