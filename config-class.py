#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Global configuration class."""


import json
import os
from pathlib import Path
from typing import Any

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer


class App:
    """The global configuration class.

    Contains shared variables or variables which control the operation
    of the bot.

    TODO: __conf may be better coming from a YAML file.
    """

    # __conf is a dictionary of configuration parameters
    __conf = {
        # cooldown parameters
        "COOLDOWN_RATE": 3,
        "COOLDOWN_STANDARD": 60,
        "COOLDOWN_ONE_HOUR": 3600,
        "HOURS_IN_WEEK": 168,
        # general discord things
        "MAX_CHARS": 1994,
        "LOGGER_NAME": "slashbot",
        "LOGFILE_NAME": Path("./slashbot.log"),
        # Define users, roles and channels
        "ID_BOT": 815234903251091456,
        "ID_USER_ADAM": 261097001301704704,
        "ID_USER_ZADETH": 737239706214858783,
        "ID_USER_LIME": 121310675132743680,
        "ID_USER_SAULTYEVIL": 151378138612367360,
        "ID_USER_HYPNOTIZED": 176726054256377867,
        "ID_SERVER_ADULT_CHILDREN": 237647756049514498,
        "ID_SERVER_FREEDOM": 815237689775357992,
        "ID_SERVER_BUMPAPER": 710120382144839691,
        "ID_CHANNEL_IDIOTS": 237647756049514498,
        "ID_CHANNEL_SPAM": 627234669791805450,
        # API keys
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY"),
        "WOLFRAM_API_KEY": os.getenv("WOLFRAM_API_KEY"),
        "OWM_API_KEY": os.getenv("OWM_API_KEY"),
        "TWITTER_BEARER_KEY": os.getenv("TWITTER_BEARER_KEY"),
        # File locations
        "USERS_FILE": Path("data/users.json"),
        "REMINDERS_FILE": Path("data/reminders.json"),
        "BANK_FILE": Path("data/bank.json"),
        "BAD_WORDS_FILE": Path("data/badwords.txt"),
        "GOD_WORDS_FILE": Path("data/godwords.txt"),
        # File streams
        "USER_FILE_STREAM": None,
        "REMINDERS_FILE_STREAM": None,
        "BANK_FILE_STREAM": None,
    }

    __conf["SLASH_SERVERS"] = [
        __conf["ID_SERVER_ADULT_CHILDREN"],
        __conf["ID_SERVER_FREEDOM"],
        __conf["ID_SERVER_BUMPAPER"],
    ]
    __conf["NO_COOL_DOWN_USERS"] = [__conf["ID_USER_SAULTYEVIL"]]
    __conf["ALL_FILES"] = [__conf["USERS_FILE"], __conf["REMINDERS_FILE"], __conf["BANK_FILE"]]

    @staticmethod
    def __read_in_json_file(filepath: Path, conf_key: str) -> None:
        """Read in a JSON file and set it to a __conf key.

        Parameters
        ----------
        filepath: Path
            The filepath to the file.
        conf_key: str
            The key for the file in the App.__conf dict.
        """
        with open(filepath, "r", encoding="utf-8") as file_in:
            App.__conf[conf_key] = json.load(file_in)

    __read_in_json_file(__conf["USERS_FILE"], "USERS_FILE_STREAM")
    __read_in_json_file(__conf["REMINDERS_FILE"], "REMINDERs_FILE_STREAM")
    __read_in_json_file(__conf["BANK_FILE"], "BANK_FILE_STREAM")

    @staticmethod
    def __on_directory_change(_):
        App.__read_in_json_file(App.__conf["USERS_FILE"], "USERS_FILE_STREAM")
        App.__read_in_json_file(App.__conf["REMINDERS_FILE"], "REMINDERs_FILE_STREAM")
        App.__read_in_json_file(App.__conf["BANK_FILE"], "BANK_FILE_STREAM")

    __observer = Observer()
    __event_handler = PatternMatchingEventHandler(["*.json"], None, False, True)
    __event_handler.on_modified = __on_directory_change
    __observer.schedule(__event_handler, "./data", False)
    __observer.start()

    # __setters is a tuple of parameters which can be set
    __setters = ()

    # Public methods -----------------------------------------------------------

    @staticmethod
    def config(name: str) -> Any:
        """Get a configuration parameter.

        Parameters
        ----------
        name: str
            The name of the parameter to get the value for.
        """
        return App.__conf[name]

    @staticmethod
    def set(name: str, value: Any) -> None:
        """Set the value of a configuration parameter.

        Parameters
        ----------
        name: str
            The name of the parameter to set a value for.
        value: Any
            The new value of the parameter.
        """
        if name in App.__setters:
            App.__conf[name] = value
        else:
            raise NameError("Name not accepted in set() method")
