#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This module contains functions for accessing and modifying the slashbot
database.

The functions in here are basically just wrappers around a dictionary and JSON.
The database is saved to disk as a JSON. This should be performant enough, as
the database will likely remain small.
"""

import json
import logging
import pathlib
from typing import List

import disnake
from slashbot.config import App

# Functions --------------------------------------------------------------------

logger = logging.getLogger(App.config("LOGGER_NAME"))


def create_empty_database(location: str):
    """_summary_

    Parameters
    ----------
    location : str
        _description_
    """
    with open(location, "w", encoding="utf-8") as file_out:
        json.dump({"USERS": {}, "REMINDERS": []}, file_out)


def check_database_exists(location: str):
    """_summary_

    Parameters
    ----------
    location : str
        _description_
    """
    location = pathlib.Path(location)
    if not location.exists():
        create_empty_database(location)


def load_database(location: str = None) -> dict:
    """_summary_

    Parameters
    ----------
    location : str, optional
        _description_, by default None

    Returns
    -------
    dict
        _description_
    """
    if not location:
        location = App.config("DATABASE_LOCATION")

    check_database_exists(location)

    with open(location, "r", encoding="utf-8") as file_in:
        database = json.load(file_in)

    return database


def save_database(database: dict, location: str = None):
    """_summary_

    Parameters
    ----------
    database : dict
        _description_
    location : str, optional
        _description_, by default None
    """
    if not location:
        location = App.config("DATABASE_LOCATION")

    with open(location, "w", encoding="utf-8") as file_out:
        json.dump(database, file_out)

    return database


def create_new_user(user: disnake.User | disnake.Member) -> dict:
    """_summary_

    Parameters
    ----------
    user : disnake.User | disnake.Member
        _description_

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
    database = save_database(database)

    return database


def get_users() -> dict:
    """_summary_

    Returns
    -------
    dict
        _description_
    """
    database = load_database()
    return database["USERS"]


def get_all_reminders() -> List[dict]:
    """_summary_

    Returns
    -------
    List[dict]
        _description_
    """
    database = load_database()
    return database["REMINDERS"]


def get_all_reminders_for_user(user_id: int) -> List[dict]:
    """_summary_

    Parameters
    ----------
    user_id : int
        _description_

    Returns
    -------
    List[dict]
        _description_
    """
    return filter(lambda r: r["user_id"] == user_id, get_all_reminders())


def add_reminder(reminder: dict) -> None:
    """_summary_

    Parameters
    ----------
    reminder : dict
        _description_
    """
    database = load_database()
    reminders = database["REMINDERS"]
    reminders.append(reminder)
    database = save_database(database)


def remove_reminder(index: int) -> None:
    """_summary_

    Parameters
    ----------
    index : int
        _description_
    """
    database = load_database()
    reminders = database["REMINDERS"]
    reminders.pop(index)
    database = save_database(database)


def get_user(user: disnake.User | disnake.Member) -> dict:
    """_summary_

    Parameters
    ----------
    user_id : int
        _description_

    Returns
    -------
    dict
        _description_
    """
    database = load_database()

    if str(user.id) not in database["USERS"]:
        database = create_new_user(user)

    return database["USERS"][str(user.id)]


def get_user_location(user: disnake.User | disnake.Member) -> str:
    """_summary_

    Parameters
    ----------
    user : disnake.User | disnake.Member
        _description_

    Returns
    -------
    str
        _description_
    """
    user = get_user(user)
    if not user["city"]:
        return None

    return f"{user['city'].capitalize()}{', ' + user['country_code'].upper() if user['country_code'] else ''}"


def get_twitter_convert_users() -> List[int]:
    """_summary_

    Parameters
    ----------
    database : dict
        _description_

    Returns
    -------
    List[int]
        _description_
    """
    database = load_database()
    return [
        user_id for user_id, user_settings in database["USERS"].items() if user_settings["convert_twitter_url"] is True
    ]


def update_user(user_id: int, update: dict) -> None:
    """_summary_

    Parameters
    ----------
    user_id : int
        _description_
    update : dict
        _description_
    """
    database = load_database()
    users = database["USERS"]
    users[str(user_id)] = update
    database = save_database(database)
