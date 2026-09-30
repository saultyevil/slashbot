import datetime
import re
from collections.abc import Callable

import disnake
from feedparser import FeedParserDict

from slashbot.database.sql_database import DatabaseSQL
from slashbot.database.sql_models import LoggedGameSQL

from .tracker import MediaTracker, convert_rating_to_stars


class BackloggdTracker:
    """Backloggd feed, database, and embed adapter."""

    def __init__(self, db: DatabaseSQL, log_error: Callable[..., None], log_debug: Callable[..., None]) -> None:
        """Initialize the Backloggd adapter.

        Parameters
        ----------
        db : DatabaseSQL
            Database used to read and persist games.
        log_error : Callable
            Error logging callback.
        log_debug : Callable
            Debug logging callback.

        """
        self.db = db
        self.log_error = log_error
        self.log_debug = log_debug

    def config(self) -> MediaTracker[LoggedGameSQL]:
        """Return the Backloggd tracker configuration.

        Returns
        -------
        MediaTracker[LoggedGameSQL]
            Configured Backloggd feed and persistence operations.

        """
        return MediaTracker(
            service_label="backloggd",
            feed_url_template="https://backloggd.com/u/{}/reviews/rss/",
            get_last_entry=self.db.get_last_game_for_backloggd_user,
            get_title=self.get_title,
            upsert_entry=self.add_to_database,
            empty_log_label="log list",
            entry_label="game",
        )

    @staticmethod
    def get_title(entry: FeedParserDict) -> str | None:
        """Extract a game title from an RSS entry.

        Parameters
        ----------
        entry : FeedParserDict
            Raw Backloggd RSS entry.

        Returns
        -------
        str or None
            Game title when the entry contains a four-digit release year.

        """
        match = re.match(r"^(.*?) \(\d{4}\)", str(entry["title"]))
        return match.group(1) if match else None

    async def add_to_database(self, username: str, game_entry: FeedParserDict) -> LoggedGameSQL:
        """Persist a Backloggd RSS entry.

        Parameters
        ----------
        username : str
            Backloggd username owning the entry.
        game_entry : FeedParserDict
            Raw Backloggd RSS entry.

        Returns
        -------
        LoggedGameSQL
            Persisted game row.

        Raises
        ------
        ValueError
            If the Backloggd user is not in the database.

        """
        user_db = await self.db.get_user("backloggd_username", username)
        if not user_db:
            exc_msg = f"Backloggd user {username} was not in the database"
            self.log_error("%s", exc_msg)
            raise ValueError(exc_msg)

        title_match = re.match(r"^(.*?) \(\d{4}\)", str(game_entry["title"]))
        year_match = re.search(r"\((\d{4})\)", str(game_entry["title"]))
        date_str = game_entry.get("published")
        date = datetime.datetime.strptime(date_str, r"%a, %d %b %Y %H:%M:%S %z") if date_str else None  # type: ignore

        game = LoggedGameSQL(
            user_id=user_db.id,
            username=username,
            title=title_match.group(1) if title_match else None,
            game_year=year_match.group(1) if year_match else None,
            published_date=date,
            user_rating=float(str(game_entry["backloggd_user_rating"])) / 2,
            url=game_entry["link"],
            poster_url=game_entry["href"],
        )
        new_game = await self.db.upsert_row(game)
        self.log_debug("Added new game %s (%s) for %s", game.title, game.published_date, username)
        return new_game

    @staticmethod
    def create_embed(game: LoggedGameSQL) -> disnake.Embed:
        """Create a Discord embed for a logged game.

        Parameters
        ----------
        game : LoggedGameSQL
            Game row to render.

        Returns
        -------
        disnake.Embed
            Discord embed containing the game details.

        """
        embed = disnake.Embed(title=f"{game.username.capitalize()} logged a game", url=game.url)
        embed.add_field(name="Game title", value=game.title, inline=False)
        embed.add_field(name="Release year", value=game.game_year, inline=False)
        if game.published_date:
            embed.add_field(name="Published date", value=game.published_date.strftime(r"%d/%m/%Y"))
        embed.add_field(name="User rating", value=convert_rating_to_stars(game.user_rating), inline=False)
        embed.set_thumbnail(url=game.poster_url)
        return embed
