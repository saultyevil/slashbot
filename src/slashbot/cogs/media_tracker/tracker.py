from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import disnake
from feedparser import FeedParserDict

# Type alias for the per-entry upsert callables passed to MediaTracker.
type UpsertCallable[T] = Callable[[str, FeedParserDict], Awaitable[T]]


@dataclass(frozen=True)
class MediaTracker[T]:
    """Service-specific feed and persistence operations.

    Attributes
    ----------
    service_label : str
        Name used in log messages.
    feed_url_template : str
        URL template containing one username placeholder.
    get_last_entry : Callable
        Async function returning the latest stored entry for a username.
    get_title : Callable
        Function extracting a comparable title from a feed entry.
    upsert_entry : UpsertCallable
        Async function persisting a feed entry.
    empty_log_label : str
        Label used when a newly configured user is skipped.
    entry_label : str
        Singular label used in summary logs.

    """

    service_label: str
    feed_url_template: str
    get_last_entry: Callable[[str], Awaitable[T | None]]
    get_title: Callable[[FeedParserDict], str | None]
    upsert_entry: UpsertCallable[T]
    empty_log_label: str
    entry_label: str


@dataclass
class PollResult[T]:
    """New feed entries grouped by service username.

    Parameters
    ----------
    entries_by_user : dict[str, list[T]]
        New entries keyed by service username.

    """

    entries_by_user: dict[str, list[T]]

    @property
    def entries(self) -> list[T]:
        """Return all new entries in username order.

        Returns
        -------
        list[T]
            Flattened entries from all users.

        """
        return [entry for entries in self.entries_by_user.values() for entry in entries]

    @property
    def has_new_entries(self) -> bool:
        """Return whether at least one new entry was found.

        Returns
        -------
        bool
            Whether the result contains an entry.

        """
        return bool(self.entries)


@dataclass(frozen=True)
class TrackerRun[T]:
    """Inputs needed to poll and notify one media service.

    Attributes
    ----------
    usernames : list[str]
        Service usernames to poll.
    username_to_discord_id : dict[str, int]
        Mapping from service username to Discord user ID.
    channel_ids : list[int]
        Channels where entries may be posted.
    channel_label : str
        Human-readable channel purpose for error messages.
    tracker : MediaTracker
        Service-specific feed and persistence adapter.
    create_embed : Callable
        Function creating a Discord embed for an entry.

    """

    usernames: list[str]
    username_to_discord_id: dict[str, int]
    channel_ids: list[int]
    channel_label: str
    tracker: MediaTracker[T]
    create_embed: Callable[[T], disnake.Embed]


def convert_rating_to_stars(rating: float) -> str:
    """Convert a rating out of five to a string of stars.

    Parameters
    ----------
    rating : float
        Rating on a five-point scale. Zero represents no rating.

    Returns
    -------
    str
        Star representation of the rating, or ``"Unrated"``.

    """
    if not rating:
        return "Unrated"
    full_stars = int(rating)
    half_star = rating - full_stars >= 0.5  # noqa: PLR2004
    stars = "★" * full_stars
    if half_star:
        stars += "½"
    return stars
