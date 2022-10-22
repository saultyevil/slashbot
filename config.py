#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Global variables used throughout the bot."""

import json
import logging
import os
from pathlib import Path

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

# Constants defined for controlling cooldowns

COOLDOWN_RATE = 3
COOLDOWN_STANDARD = 60
COOLDOWN_ONE_HOUR = 3600
COOLDOWN_TEN_MINUTES = 600
HOURS_IN_WEEK = 168

# Constants for general discord things

SYMBOL = "%"
MAX_CHARS = 1994
LOGGER_NAME = "slashbot"
LOGFILE_NAME = Path("./slashbot.log")

__logger = logging.getLogger(LOGGER_NAME)

# Constants to define users, roles and channels. Note that users are supposed
# to be set as environment variables for privacy reasons.

ID_BOT = 815234903251091456
ID_USER_ADAM = 261097001301704704
ID_USER_ZADETH = 737239706214858783
ID_USER_LIME = 121310675132743680
ID_USER_SAULTYEVIL = 151378138612367360
ID_USER_HYPNOTIZED = 176726054256377867
ID_SERVER_ADULT_CHILDREN = 237647756049514498
ID_SERVER_FREEDOM = 815237689775357992
ID_SERVER_BUMPAPER = 710120382144839691
ID_CHANNEL_IDIOTS = 237647756049514498
ID_CHANNEL_SPAM = 627234669791805450

SLASH_SERVERS = [ID_SERVER_ADULT_CHILDREN, ID_SERVER_FREEDOM, ID_SERVER_BUMPAPER]

NO_COOL_DOWN_USERS = [ID_USER_SAULTYEVIL]

# API keys and specific settings

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
WOLFRAM_API_KEY = os.getenv("WOLFRAM_API_KEY")
OWN_API_KEY = os.getenv("OWM_API_KEY")
TWITTER_BEARER_KEY = os.getenv("TWITTER_BEARER_KEY")

# File locations for staring data

USERS_FILE = Path("data/users.json").resolve()
REMINDERS_FILE = Path("data/reminders.json").resolve()
BANK_FILE = Path("data/bank.json").resolve()
ALL_FILES = [USERS_FILE, REMINDERS_FILE, BANK_FILE]

# Check for files which don't exist, and create empty files if they dont

for file in ALL_FILES:
    if not os.path.exists(file):
        with open(file, "w", encoding="utf-8") as file_out:
            file_out.write("{}")

# Create global file streams, so they can be watched in here

with open(USERS_FILE, "r", encoding="utf-8") as gl_file_in:
    USER_FILE_STREAM = json.load(gl_file_in)

with open(REMINDERS_FILE, "r", encoding="utf-8") as gl_file_in:
    REMINDERS_FILE_STREAM = json.load(gl_file_in)

with open(BANK_FILE, "r", encoding="utf-8") as gl_file_in:
    BANK_FILE_STREAM = json.load(gl_file_in)


def on_directory_change(_):
    """On changes to the directory, reload all the data files."""
    global USER_FILE_STREAM  # pylint: disable=global-statement
    global REMINDERS_FILE_STREAM  # pylint: disable=global-statement
    global BANK_FILE_STREAM  # pylint: disable=global-statement

    with open(USERS_FILE, "r", encoding="utf-8") as file_in:
        USER_FILE_STREAM = json.load(file_in)
        __logger.info("reloaded user file")

    with open(REMINDERS_FILE, "r", encoding="utf-8") as file_in:
        REMINDERS_FILE_STREAM = json.load(file_in)
        __logger.info("reloaded reminders")

    with open(BANK_FILE, "r", encoding="utf-8") as file_in:
        BANK_FILE_STREAM = json.load(file_in)
        __logger.info("reloaded bank file")


# Set up an observer so when something in the data directory changes, then
# we read in the different files in again

observer = Observer()
event_handler = PatternMatchingEventHandler(["*"], None, False, True)
event_handler.on_modified = on_directory_change
observer.schedule(event_handler, "./data", False)
observer.start()


# Special files

BAD_WORDS_FILE = "data/badwords.txt"
GOD_WORDS_FILE = "data/godwords.txt"
