import datetime
import re

import disnake
import feedparser
from disnake.ext import tasks
from feedparser import FeedParserDict

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.core.database.models import WatchedMovie
from slashbot.settings import BotSettings


class MovieTracker(CustomCog):
    """Cog for posting when a user has logged a new movie on Letterboxd."""

    async def _add_movie_to_database(self, letterboxd_username: str, movie_entry: FeedParserDict) -> WatchedMovie:
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
        user_db = await self.db.get_user_by_letterboxd_username(letterboxd_username)
        if not user_db:
            exc_msg = f"Letterboxd user {letterboxd_username} was not in the database"
            self.log_error("%s", exc_msg)
            raise ValueError(exc_msg)

        poster_url_regex = re.search(r'src="([^"]+)"', movie_entry["summary"])  # type: ignore
        poster_url = poster_url_regex.group(1) if poster_url_regex else None
        watched_date_str = movie_entry.get("letterboxd_watcheddate", None)
        watched_date = datetime.datetime.strptime(watched_date_str, r"%Y-%m-%d") if watched_date_str else None  # noqa: DTZ007

        movie = WatchedMovie(
            user_id=user_db.id,
            username=letterboxd_username,
            title=movie_entry["letterboxd_filmtitle"],
            film_year=movie_entry["letterboxd_filmyear"],
            user_rating=movie_entry.get("letterboxd_memberrating", None),
            watched_date=watched_date,
            tmdb_id=movie_entry["tmdb_movieid"],
            url=movie_entry["link"],
            poster_url=poster_url,
        )
        new_movie = await self.db.add_watched_movie(movie)

        return new_movie  # noqa: RET504

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

    async def get_latest_movies_watched(self, letterboxd_usernames: list[str] | str) -> dict[str, WatchedMovie]:
        """Get the latest watched movies for some Letterboxd users.

        Parameters
        ----------
        letterboxd_usernames : list[str] | str
            The user(s) to find the latest movies watched.

        Returns
        -------
        dict[str, list]
            A mapping of username to movies watched.

        """
        results = {}

        for letterboxd_username in letterboxd_usernames:
            feed = feedparser.parse(f"https://letterboxd.com/{letterboxd_username}/rss/")
            if not feed.entries:
                results[letterboxd_username] = []
                continue

            new_movies = []
            last_movie = await self.db.get_last_movie_for_user(letterboxd_username)
            last_movie_title = last_movie.title if last_movie else None
            self.log_debug("Latest movie for %s: %s", letterboxd_username, last_movie_title)

            for movie_entry in feed.entries:
                title = movie_entry["letterboxd_filmtitle"]
                # Early exit to avoid sending all movies watched
                if title == last_movie_title:
                    break
                # This is not a movie then, but probably a tv show
                if "tmdb_movieid" not in movie_entry:
                    continue
                new_movies.append(await self._add_movie_to_database(letterboxd_username, movie_entry))
            results[letterboxd_username] = (
                new_movies[0] if len(new_movies) > 0 else []
            )  # Just return the latest one for now...

        return results

    @tasks.loop(minutes=1)
    async def check_for_new_watches(self) -> None:
        """Periodically check for new logged movies."""
        letterboxd_users = await self.db.get_letterboxd_users()
        letterboxd_to_discord = {user.letterboxd_user: user.discord_id for user in letterboxd_users}
        new_movies_watched = await self.get_latest_movies_watched([user.letterboxd_user for user in letterboxd_users])
        self.log_debug("New movies to post: %s", new_movies_watched)

        # post to test channel if bot.reload, as this only happens in debug mode
        channel = await self.bot.fetch_channel(
            1117059319230382140 if self.bot.reload else BotSettings.cogs.movie_tracker.channel
        )

        if not isinstance(channel, disnake.TextChannel):
            exc_msg = "Movie tracker channel is not a guild channel"
            self.log_error("%s", exc_msg)
            raise TypeError(exc_msg)

        for username, movie in new_movies_watched.items():
            if not movie:
                continue
            discord_id = letterboxd_to_discord[username]
            discord_user = await self.bot.fetch_user(discord_id)
            embed = disnake.Embed(title=f"{movie.username.capitalize()} watched a film", url=movie.url)
            embed.add_field(name="Film title", value=movie.title, inline=False)
            embed.add_field(name="Release year", value=movie.film_year, inline=False)
            if movie.watched_date:
                embed.add_field(name="Watched date", value=datetime.datetime.strftime(movie.watched_date, r"%d/%m/%Y"))
            embed.add_field(name="User rating", value=self._convert_rating_to_stars(movie.user_rating), inline=False)
            embed.set_image(movie.poster_url)
            embed.set_thumbnail(url=discord_user.display_avatar.url)

            await channel.send(embed=embed)


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(MovieTracker(bot))
