#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Global configuration class."""

import copy
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def setup_logging():
    """Setup up the logger and log file."""

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger = logging.getLogger(App.get_config("LOGGER_NAME"))
    logger.addHandler(console_handler)

    if Path(App.get_config("LOGFILE_NAME")).parent.exists():
        file_handler = RotatingFileHandler(
            filename=App.get_config("LOGFILE_NAME"), encoding="utf-8", maxBytes=int(5e5), backupCount=5
        )
        file_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)8s : %(message)s (%(filename)s:%(lineno)d)", "%Y-%m-%d %H:%M:%S"
            )
        )
        logger.addHandler(file_handler)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.info("Loaded config file %s", os.getenv("SLASHBOT_CONFIG"))


class FileWatcher(FileSystemEventHandler):
    def on_modified(self, event):
        # TODO: this triggers twice on file modify...
        if event.event_type == "modified" and event.src_path == os.getenv("SLASHBOT_CONFIG"):
            original_config = copy.copy(App._config)
            new_config = App.set_config_values()
            modified_keys = {
                key for key in original_config if key in new_config and original_config[key] != new_config[key]
            }
            if modified_keys:
                logger = logging.getLogger(App.get_config("LOGGER_NAME"))
                logger.info("App config updated:")
                for key in modified_keys:
                    logger.info("  %s: %s -> %s", key, original_config[key], new_config[key])


class App:
    """The global configuration class.

    Contains shared variables or variables which control the operation
    of the bot.
    """

    # __conf is a dictionary of configuration parameters
    _config = {}

    # Private methods ----------------------------------------------------------

    @classmethod
    def set_config_values(cls):
        """Set the values of the config from the config file.

        The purpose of this script is to populate the __conf class attribute.
        """
        with open(os.getenv("SLASHBOT_CONFIG"), "r", encoding="utf-8") as file_in:
            SLASH_CONFIG = json.load(file_in)
        CURRENT_CHAIN = cls._config.get("CURRENT_MARKOV_CHAIN", None)
        _config = {
            # cooldown parameters
            "COOLDOWN_RATE": int(SLASH_CONFIG["COOLDOWN"]["RATE"]),
            "COOLDOWN_STANDARD": int(SLASH_CONFIG["COOLDOWN"]["STANDARD"]),
            "COOLDOWN_EXTENDED": int(SLASH_CONFIG["COOLDOWN"]["EXTENDED"]),
            "COOLDOWN_SERVERS": SLASH_CONFIG["COOLDOWN"]["COOLDOWN_SERVERS"],
            "NO_COOLDOWN_USERS": SLASH_CONFIG["COOLDOWN"]["NO_COOLDOWN_USERS"],
            # general things
            "MAX_CHARS": SLASH_CONFIG["DISCORD"]["MAX_CHARS"],
            "LOGGER_NAME": SLASH_CONFIG["LOGFILE"]["LOG_NAME"],
            "LOGFILE_NAME": SLASH_CONFIG["LOGFILE"]["LOG_LOCATION"],
            "DEVELOPMENT_SERVERS": SLASH_CONFIG["DISCORD"]["DEVELOPMENT_SERVERS"],
            # Define users, roles and channels
            "ID_USER_SAULTYEVIL": 151378138612367360,
            "ID_CHANNEL_IDIOTS": 237647756049514498,
            # API keys
            "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY"),
            "WOLFRAM_API_KEY": os.getenv("WOLFRAM_API_KEY"),
            "OWM_API_KEY": os.getenv("OWM_API_KEY"),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
            "MONSTER_API_KEY": os.getenv("MONSTER_API_KEY"),
            # File locations
            "DATABASE_LOCATION": Path(SLASH_CONFIG["FILES"]["DATABASE"]),
            "BAD_WORDS_FILE": Path(SLASH_CONFIG["FILES"]["BAD_WORDS"]),
            "GOD_WORDS_FILE": Path(SLASH_CONFIG["FILES"]["GOD_WORDS"]),
            "SCHEDULED_POST_FILE": Path(SLASH_CONFIG["FILES"]["SCHEDULED_POSTS"]),
            "RANDOM_MEDIA_DIRECTORY": Path(SLASH_CONFIG["FILES"]["RANDOM_MEDIA_DIRECTORY"]),
            # Markov Chain configuration
            "ENABLE_MARKOV_TRAINING": bool(SLASH_CONFIG["MARKOV"]["ENABLE_MARKOV_TRAINING"]),
            "CURRENT_MARKOV_CHAIN": CURRENT_CHAIN,
            "PREGEN_MARKOV_SENTENCES_AMOUNT": int(SLASH_CONFIG["MARKOV"]["NUM_PREGEN_SENTENCES"]),
            "PREGEN_REGENERATE_LIMIT": int(SLASH_CONFIG["MARKOV"]["PREGEN_REGENERATE_LIMIT"]),
            # Cog settings
            "SPELLCHECK_ENABLED": bool(SLASH_CONFIG["COGS"]["SPELLCHECK"]["ENABLED"]),
            "SPELLCHECK_SERVERS": SLASH_CONFIG["COGS"]["SPELLCHECK"]["SERVERS"],
            "SPELLCHECK_CUSTOM_DICTIONARY": SLASH_CONFIG["COGS"]["SPELLCHECK"]["CUSTOM_DICTIONARY"],
            "RANDOM_POST_CHANNELS": SLASH_CONFIG["COGS"]["SCHEDULED_POSTS"]["RANDOM_POST_CHANNELS"],
            "AI_CHAT_MODEL": SLASH_CONFIG["COGS"]["AI_CHAT"]["GPT_MODEL"],
            "AI_CHAT_MODEL_TEMPERATURE": SLASH_CONFIG["COGS"]["AI_CHAT"]["MODEL_TEMPERATURE"],
            "AI_CHAT_MAX_OUTPUT_TOKENS": SLASH_CONFIG["COGS"]["AI_CHAT"]["MAX_OUTPUT_TOKENS"],
            "AI_CHAT_TOKEN_WINDOW_SIZE": SLASH_CONFIG["COGS"]["AI_CHAT"]["TOKEN_WINDOW_SIZE"],
            "AI_SUMMARY_PROMPT": SLASH_CONFIG["COGS"]["AI_CHAT"]["SUMMARY_PROMPT"],
            "AI_CHAT_RANDOM_RESPONSE": SLASH_CONFIG["COGS"]["AI_CHAT"]["RANDOM_RESPONSE_CHANCE"],
            "AI_CHAT_RATE_LIMIT": SLASH_CONFIG["COGS"]["AI_CHAT"]["RESPONSE_RATE_LIMIT"],
            "AI_CHAT_RATE_INTERVAL": SLASH_CONFIG["COGS"]["AI_CHAT"]["RATE_LIMIT_INTERVAL"],
        }
        cls._config = _config

        return cls._config

    # Public methods -----------------------------------------------------------

    @staticmethod
    def get_config(name: str) -> Any:
        """Get a configuration parameter.

        Parameters
        ----------
        name: str
            The name of the parameter to get the value for.

        Returns
        -------
        Any
            The value of the parameter requested.
        """
        try:
            return App._config[name]
        except KeyError:
            return None

    @staticmethod
    def set_config(name: str, value: str) -> None:
        """Set a configuration parameter.

        Parameters
        ----------
        name : str
            The name of the parameter to set.
        value : str
            The value of the parameter.
        """
        App._config[name] = value


App.set_config_values()
setup_logging()

observer = Observer()
observer.schedule(FileWatcher(), path=Path(os.getenv("SLASHBOT_CONFIG")).parent)
observer.start()
