"""Contains functions for accessing and modifying the slashbot database.

The functions in here are basically just wrappers around a dictionary and JSON.
The database is saved to disk as a JSON. This should be performant enough, as
the database will likely remain small.
"""

import json
import logging
import pathlib

from slashbot.custom_types import Member, User
from slashbot.settings import BotConfig

logger = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))


# Database functions -----------------------------------------------------------


def create_empty_database(location: str) -> None:
    """Create an empty database.

    The keys and their types are in the database are:
        - USERS: dict
        - REMINDERS: list

    Parameters
    ----------
    location : str
        The file location to save the database.

    """
    with open(location, "w", encoding="utf-8") as file_out:
        json.dump({"USERS": {}, "REMINDERS": []}, file_out)


def check_database_exists(location: str) -> None:
    """Check if a database exists at the given location, and create one it not.

    Parameters
    ----------
    location : str
        The file location to check.

    """
    location = pathlib.Path(location)
    if not location.exists():
        create_empty_database(location)


def load_database(location: str | None = None) -> dict:
    """Load a database.

    If no location is provided, the location defined in the config file will be
    used.

    Parameters
    ----------
    location : str, optional
        The file location of the database, by default None where the value from
        the config file will be used.

    Returns
    -------
    dict
        The database as a dict.

    """
    if not location:
        location = BotConfig.get_config("DATABASE_LOCATION")

    check_database_exists(location)

    with open(location, encoding="utf-8") as file_in:
        database = json.load(file_in)

    return database


def save_database(database: dict, location: str = None) -> dict:
    """Dump the provided database to disk.

    The database is not modified by this function.

    If no location is provided, the location defined in the config fill will be
    used.

    Parameters
    ----------
    database : dict
        The database to dump to disk.
    location : str, optional
        The file location of the database, by default None where the value from
        the config file will be used.

    Returns
    -------
    dict
        The database written to disk.

    """
    if not location:
        location = BotConfig.get_config("DATABASE_LOCATION")

    with open(location, "w", encoding="utf-8") as file_out:
        json.dump(database, file_out)

    return database


def create_new_user(user: User | Member) -> dict:
    """Create an empty user in the database.

    Adds a user to the USERS key. All fields other than the user_name are either
    unpopulated or given a default value.

    The database is dumped to disk when the new user is added.

    Parameters
    ----------
    user : User | Member
        The disnake user to add.

    Returns
    -------
    dict
        _description_

    """
    new_user = {
        "user_name": user.name,
        "city": "",
        "country_code": "",
        "bad_word": "",
        "convert_twitter_url": False,
    }

    database = load_database()
    database["USERS"][str(user.id)] = new_user
    save_database(database)

    return database


# User functions ---------------------------------------------------------------


def get_users() -> dict:
    """Get all the users in the database.

    Returns
    -------
    dict
        A dict of users. The keys of the dict are user ids.

    """
    database = load_database()
    return database["USERS"]


def get_user(user: User | Member) -> dict:
    """Get a user from the database.

    If the user does not exist, it is created first with empty/default values.

    Parameters
    ----------
    user : User | Member
        The Disnake class for the user to get.

    Returns
    -------
    dict
        The information set by the user.

    """
    database = load_database()

    if str(user.id) not in database["USERS"]:
        database = create_new_user(user)

    return database["USERS"][str(user.id)]


def get_user_location(user: User | Member) -> None | str:
    """Get the location set by a user.

    Parameters
    ----------
    user : User | Member
        The Disnake class for the user to get.

    Returns
    -------
    None | str
        If no location is set None. Otherwise a string 'city, county_code'.

    """
    user = get_user(user)
    if not user["city"]:
        return None

    return f"{user['city'].capitalize()}{', ' + user['country_code'].upper() if user['country_code'] else ''}"


def get_twitter_convert_users() -> list[int]:
    """Return a list of Discord user IDs where `convert_twitter_url` == True.

    Returns
    -------
    List[int]
        The list of user IDs where `convert_twitter_url` = True.

    """
    database = load_database()
    return [
        int(user_id)
        for user_id, user_settings in database["USERS"].items()
        if user_settings["convert_twitter_url"] == True  # pylint: disable=C0121  # noqa: E712
    ]


def update_user(user: Member | User, updated_fields: dict) -> None:
    """Update a user in the database.

    This function will update the entire dict for a user, instead of an
    individual field.

    Parameters
    ----------
    user : Member | User
        The user to update.
    updated_fields : dict
        A dict containing all the fields with the updated field.

    """
    database = load_database()
    users = database["USERS"]
    users[str(user.id)] = updated_fields
    save_database(database)


# Reminder functions -----------------------------------------------------------


def get_all_reminders() -> list[dict]:
    """Get all the remidners in a database.

    Returns
    -------
    List[dict]
        A list of all the reminders.

    """
    database = load_database()
    return database["REMINDERS"]


def get_all_reminders_for_user(user_id: int) -> list[dict]:
    """Get all reminders set for a given user.

    Parameters
    ----------
    user_id : int
        The Discord ID for the user to get reminders for.

    Returns
    -------
    List[dict]
        A list of the reminders for this user.

    """
    return filter(lambda r: r["user_id"] == user_id, get_all_reminders())


def add_reminder(reminder: dict) -> None:
    """Add a reminder to the database.

    Parameters
    ----------
    reminder : dict
        The reminder dict to add.

    """
    database = load_database()
    database["REMINDERS"].append(reminder)
    save_database(database)


def remove_reminder(reminder: dict) -> None:
    """Remove a reminder from the database.

    Parameters
    ----------
    reminder : dict
        The reminder to remove from the database.

    """
    database = load_database()
    index = database["REMINDERS"].index(reminder)
    database["REMINDERS"].pop(index)
    save_database(database)
