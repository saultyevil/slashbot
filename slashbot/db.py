#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This module contains functions for modifying the slashbot database."""

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
    """Create a database engine.

    Creates an Engine object which is used to create a database session.

    Parameters
    ----------
    location : str
        The location of the SQLite database to load, default is None where the
        value is then taken from App.config.
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


def create_new_user(database: dict, user: disnake.User | disnake.Member) -> dict:
    """Create a new user row.

    Creates a new user row, populating only the user ID and user name. The
    new row is returned.

    Parameters
    ----------
    database : dict
        _description_
    user : disnake.User | disnake.Member
        _description_

    Returns
    -------
    dict
        The updated database.
    """
    new_user = {
        "user_name": user.name,
        "city": "",
        "country_code": "",
        "bad_word": "",
        "convert_twitter_url": False,
    }
    database["USERS"][user.id] = new_user
    database = save_database(database)

    return database


def get_users(database: dict) -> dict:
    """_summary_

    Parameters
    ----------
    database : dict
        _description_

    Returns
    -------
    dict
        _description_
    """
    return database["USERS"]


def get_reminders(database: dict) -> list:
    """_summary_

    Parameters
    ----------
    database : dict
        _description_

    Returns
    -------
    list
        _description_
    """
    return database["REMINDERS"]


def get_user(database: dict, user: disnake.User | disnake.Member) -> dict:
    """_summary_

    Parameters
    ----------
    database : dict
        _description_
    user_id : int
        _description_

    Returns
    -------
    dict
        _description_
    """
    if user.id not in database:
        database = create_new_user(database, user)

    return database["USERS"][user.id]


def get_user_location(database: dict, user: disnake.User | disnake.Member) -> str:
    """_summary_

    Parameters
    ----------
    database : dict
        _description_
    user : disnake.User | disnake.Member
        _description_

    Returns
    -------
    str
        _description_
    """
    user = get_user(database, user.id)
    return f"{user['city'].capitalize()}, {user['country_code'].upper() if user['country_code'] else ''}"


def get_twitter_convert_users(database: dict) -> List[int]:
    """Returns a list of users who are opted out from having their tweets
    converted to fxtwitter.

    Returns
    -------
    List[disnake.User]
        The list of users.
    """
    return [
        user_id for user_id, user_settings in database["USERS"].items() if user_settings["convert_twitter_url"] is True
    ]
