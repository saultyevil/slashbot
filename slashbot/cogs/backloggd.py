import datetime
import re

import disnake
import feedparser
from disnake.ext import tasks
from feedparser import FeedParserDict

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.database.sql_models import LoggedGameSQL
from slashbot.logger import logger
from slashbot.settings import BotSettings


class BackloggdTracker(CustomCog):
    """Cog for posting when a user has logged a new movie on Letterboxd."""

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

    async def _get_channels(self) -> list[disnake.TextChannel]:
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
        for channel_id in BotSettings.cogs.letterboxd.channels:
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

    @tasks.loop(minutes=BotSettings.cogs.backloggd.update_interval)
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
        channels = await self._get_channels()
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


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.backloggd.enabled:
        logger.log_warning("%s has been disabled in the configuration file", BackloggdTracker.__cog_name__)
        return
    bot.add_cog(BackloggdTracker(bot))
