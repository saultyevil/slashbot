#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Global variables used throughout the bot."""

import os
from pathlib import Path

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

USERS_FILES = Path("data/users.json").resolve()
REMINDERS_FILE = Path("data/reminders.json").resolve()
BANK_FILE = Path("data/bank.json").resolve()
ALL_FILES = [USERS_FILES, REMINDERS_FILE, BANK_FILE]

# Special files

BAD_WORDS_FILE = "data/badwords.txt"
GOD_WORDS_FILE = "data/godwords.txt"
