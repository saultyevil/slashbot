import datetime
import re
from collections.abc import Callable

import disnake
from feedparser import FeedParserDict

from slashbot.database.sql_database import DatabaseSQL
from slashbot.database.sql_models import WatchedMovieSQL

from .tracker import MediaTracker, convert_rating_to_stars


class LetterboxdTracker:
    """Letterboxd feed, database, and embed adapter."""

    def __init__(self, db: DatabaseSQL, log_error: Callable[..., None], log_debug: Callable[..., None]) -> None:
        """Initialize the Letterboxd adapter.

        Parameters
        ----------
        db : DatabaseSQL
            Database used to read and persist movies.
        log_error : Callable
            Error logging callback.
        log_debug : Callable
            Debug logging callback.

        """
        self.db = db
        self.log_error = log_error
        self.log_debug = log_debug

    def config(self) -> MediaTracker[WatchedMovieSQL]:
        """Return the Letterboxd tracker configuration.

        Returns
        -------
        MediaTracker[WatchedMovieSQL]
            Configured Letterboxd feed and persistence operations.

        """
        return MediaTracker(
            service_label="letterboxd",
            feed_url_template="https://letterboxd.com/{}/rss/",
            get_last_entry=self.db.get_last_movie_for_letterboxd_user,
            get_title=self.get_title,
            upsert_entry=self.add_to_database,
            empty_log_label="watchlist",
            entry_label="movie",
        )

    @staticmethod
    def get_title(entry: FeedParserDict) -> str | None:
        """Extract a supported movie title from an RSS entry.

        Parameters
        ----------
        entry : FeedParserDict
            Raw Letterboxd RSS entry.

        Returns
        -------
        str or None
            Movie title when the entry has a supported TMDB identifier.

        """
        if "tmdb_movieid" in entry or "tmdb_tvid" in entry:
            title = entry.get("letterboxd_filmtitle")
            return title if isinstance(title, str) else None
        return None

    async def add_to_database(self, username: str, movie_entry: FeedParserDict) -> WatchedMovieSQL:
        """Persist a Letterboxd RSS entry.

        Parameters
        ----------
        username : str
            Letterboxd username owning the entry.
        movie_entry : FeedParserDict
            Raw Letterboxd RSS entry.

        Returns
        -------
        WatchedMovieSQL
            Persisted movie row.

        Raises
        ------
        ValueError
            If the Letterboxd user is not in the database.

        """
        user_db = await self.db.get_user("letterboxd_username", username)
        if not user_db:
            exc_msg = f"Letterboxd user {username} was not in the database"
            self.log_error("%s", exc_msg)
            raise ValueError(exc_msg)

        poster_url_match = re.search(r'src="([^"]+)"', movie_entry["summary"])  # type: ignore
        poster_url = poster_url_match.group(1) if poster_url_match else None
        watched_date_str = movie_entry.get("letterboxd_watcheddate")
        watched_date = datetime.datetime.strptime(watched_date_str, r"%Y-%m-%d") if watched_date_str else None  # type: ignore # noqa: DTZ007

        movie = WatchedMovieSQL(
            user_id=user_db.id,
            username=username,
            title=movie_entry["letterboxd_filmtitle"],
            film_year=movie_entry["letterboxd_filmyear"],
            user_rating=movie_entry.get("letterboxd_memberrating"),
            published_date=datetime.datetime.strptime(movie_entry["published"], "%a, %d %b %Y %H:%M:%S %z"),  # type: ignore
            watched_date=watched_date,
            tmdb_id=movie_entry.get("tmdb_movieid", movie_entry.get("tmdb_tvid")),
            url=str(movie_entry["link"]).replace(f"{username}/", ""),
            poster_url=poster_url,
        )
        new_movie = await self.db.upsert_row(movie)
        self.log_debug("Added new movie %s (%s) for %s", movie.title, movie.watched_date, username)
        return new_movie

    @staticmethod
    def create_embed(movie: WatchedMovieSQL) -> disnake.Embed:
        """Create a Discord embed for a watched movie.

        Parameters
        ----------
        movie : WatchedMovieSQL
            Movie row to render.

        Returns
        -------
        disnake.Embed
            Discord embed containing the movie details.

        """
        embed = disnake.Embed(title=f"{movie.username.capitalize()} added a film", url=movie.url)
        embed.add_field(name="Film title", value=movie.title, inline=False)
        embed.add_field(name="Release year", value=movie.film_year, inline=False)
        if movie.watched_date:
            embed.add_field(name="Watched date", value=movie.watched_date.strftime(r"%d/%m/%Y"))
        embed.add_field(name="User rating", value=convert_rating_to_stars(movie.user_rating), inline=False)
        embed.set_thumbnail(url=movie.poster_url)
        return embed
