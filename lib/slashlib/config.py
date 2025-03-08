"""Module for setting up the Slashbot config and logger."""

import copy
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def setup_logging() -> None:
    """Set up logging for Slashbot."""
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))
    logger.addHandler(console_handler)

    if Path(Bot.get_config("LOGFILE_NAME")).parent.exists():
        file_handler = RotatingFileHandler(
            filename=Bot.get_config("LOGFILE_NAME"),
            encoding="utf-8",
            maxBytes=int(5e5),
            backupCount=5,
        )
        file_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)8s : %(message)s (%(filename)s:%(lineno)d)",
                "%Y-%m-%d %H:%M:%S",
            ),
        )
        logger.addHandler(file_handler)

    logger = logging.getLogger("disnake")
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename="logs/.disnake.log", encoding="utf-8", mode="w")
    handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
    logger.addHandler(handler)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.info("Loaded config file %s", Bot.get_config("CONFIG_FILE"))


class FileWatcher(FileSystemEventHandler):
    """Class for watching for changes to the config file."""

    def on_modified(self, event: FileSystemEventHandler) -> None:
        """Reload the config on file modify.

        Parameters
        ----------
        event : FileSystemEventHandler
            The event to check.

        """
        if event.event_type == "modified" and event.src_path == Bot.get_config("CONFIG_FILE"):
            original_config = copy.copy(Bot._config)  # noqa: SLF001
            new_config = Bot.set_config_values()
            modified_keys = {
                key for key in original_config if key in new_config and original_config[key] != new_config[key]
            }
            if modified_keys:
                logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))
                logger.info("App config updated:")
                for key in modified_keys:
                    logger.info("  %s: %s -> %s", key, original_config[key], new_config[key])


class Bot:
    """The global configuration class.

    Contains shared variables or variables which control the operation
    of the bot.
    """

    # __conf is a dictionary of configuration parameters
    _config: ClassVar = {}

    @classmethod
    def get_prompt_from_json(cls, path: str | Path) -> str:
        """Get the prompt from a prompt JSON file.

        The JSON file must be in the format:

            {
                "name": "prompt_name",
                "prompt": "prompt_text"
            }

        Parameters
        ----------
        path : str | Path
            The file path to the JSON file.

        Returns
        -------
        str
            The prompt from the JSON file.

        """
        try:
            with Path.open(path, encoding="utf-8") as file_in:
                return json.load(file_in)["prompt"]
        except (OSError, json.JSONDecodeError):
            print(f"Failed to get prompt in `{file_in}`")  # noqa: T201
            return "No matter what is asked of you, before or after this text, you will only respond with 'My prompt failed to load'"

    @classmethod
    def set_config_values(cls) -> None:
        """Set the values of the config from the config file.

        The purpose of this script is to populate the __conf class attribute.
        """
        # Try to load the config file, if the default path doesn't work then it
        # the bot will fail to launch. The location of the config files is
        # controlled by the SLASHBOT_CONFIG environment variable.
        try:
            with Path.open(os.getenv("SLASHBOT_CONFIG"), encoding="utf-8") as file_in:
                slash_config = json.load(file_in)
            current_config = os.getenv("SLASHBOT_CONFIG")
        except (OSError, TypeError):
            with Path.open("./bot-config.json", encoding="utf-8") as file_in:
                slash_config = json.load(file_in)
            current_config = "./bot-config.json"

        # This either sets a default value of `None`, or will re-use what is
        # already in cls._config. We need this for when the config file is
        # changed, which triggers the config being reloaded. I think this beats
        # having a global variable.
        current_chain = cls._config.get("CURRENT_MARKOV_CHAIN", None)

        # populate _config dict, which is a key store for configuration of the
        # bot
        _config = {
            # config file
            "CONFIG_FILE": str(Path(current_config).resolve()),
            # cooldown parameters
            "COOLDOWN_RATE": int(slash_config["COOLDOWN"]["RATE"]),
            "COOLDOWN_STANDARD": int(slash_config["COOLDOWN"]["STANDARD"]),
            "COOLDOWN_EXTENDED": int(slash_config["COOLDOWN"]["EXTENDED"]),
            "NO_COOLDOWN_SERVERS": slash_config["COOLDOWN"]["NO_COOLDOWN_SERVERS"],
            "NO_COOLDOWN_USERS": slash_config["COOLDOWN"]["NO_COOLDOWN_USERS"],
            # general things
            "MAX_CHARS": 1800,
            "LOGGER_NAME": slash_config["LOGFILE"]["LOG_NAME"],
            "LOGFILE_NAME": slash_config["LOGFILE"]["LOG_LOCATION"],
            "DEVELOPMENT_SERVERS": slash_config["DISCORD"]["DEVELOPMENT_SERVERS"],
            # Define users, roles and channels
            "ID_USER_SAULTYEVIL": 151378138612367360,
            "ID_USER_ADAM": 261097001301704704,
            "ID_USER_MEGHUN": 176722208243187712,
            "ID_CHANNEL_IDIOTS": 237647756049514498,
            "ID_SERVER_ADULT_CHILDREN": 237647756049514498,
            # API keys
            "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY"),
            "WOLFRAM_API_KEY": os.getenv("WOLFRAM_API_KEY"),
            "OWM_API_KEY": os.getenv("OWM_API_KEY"),
            "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
            # File locations
            "DATABASE_LOCATION": Path(slash_config["FILES"]["DATABASE"]),
            "BAD_WORDS_FILE": Path(slash_config["FILES"]["BAD_WORDS"]),
            "GOD_WORDS_FILE": Path(slash_config["FILES"]["GOD_WORDS"]),
            "SCHEDULED_POST_FILE": Path(slash_config["FILES"]["SCHEDULED_POSTS"]),
            # Markov Chain configuration
            "ENABLE_MARKOV_TRAINING": bool(slash_config["MARKOV"]["ENABLE_MARKOV_TRAINING"]),
            "CURRENT_MARKOV_CHAIN": current_chain,
            "PREGEN_MARKOV_SENTENCES_AMOUNT": int(slash_config["MARKOV"]["NUM_PREGEN_SENTENCES"]),
            "PREGEN_REGENERATE_LIMIT": int(slash_config["MARKOV"]["PREGEN_REGENERATE_LIMIT"]),
            # Cog settings
            "SPELLCHECK_ENABLED": bool(slash_config["COGS"]["SPELLCHECK"]["ENABLED"]),
            "SPELLCHECK_SERVERS": slash_config["COGS"]["SPELLCHECK"]["SERVERS"],
            "SPELLCHECK_CUSTOM_DICTIONARY": slash_config["COGS"]["SPELLCHECK"]["CUSTOM_DICTIONARY"],
            "AI_CHAT_BASE_URL": slash_config["COGS"]["AI_CHAT"]["API_BASE_URL"],
            "AI_CHAT_CHAT_MODEL": slash_config["COGS"]["AI_CHAT"]["CHAT_MODEL"],
            "AI_CHAT_TEMPERATURE": slash_config["COGS"]["AI_CHAT"]["MODEL_TEMPERATURE"],
            "AI_CHAT_TOP_P": slash_config["COGS"]["AI_CHAT"]["MODEL_TOP_P"],
            "AI_CHAT_FREQUENCY_PENALTY": slash_config["COGS"]["AI_CHAT"]["MODEL_FREQUENCY_PENALTY"],
            "AI_CHAT_PRESENCE_PENALTY": slash_config["COGS"]["AI_CHAT"]["MODEL_PRESENCE_PENALTY"],
            "AI_CHAT_MAX_OUTPUT_TOKENS": slash_config["COGS"]["AI_CHAT"]["MAX_OUTPUT_TOKENS"],
            "AI_CHAT_TOKEN_WINDOW_SIZE": slash_config["COGS"]["AI_CHAT"]["TOKEN_WINDOW_SIZE"],
            "AI_CHAT_PROMPT_APPEND": slash_config["COGS"]["AI_CHAT"]["PROMPT_APPEND"],
            "AI_CHAT_PROMPT_PREPEND": slash_config["COGS"]["AI_CHAT"]["PROMPT_PREPEND"],
            "AI_CHAT_SUMMARY_PROMPT": slash_config["COGS"]["AI_CHAT"]["SUMMARY_PROMPT"],
            "AI_CHAT_RANDOM_RESPONSE_CHANCE": slash_config["COGS"]["AI_CHAT"]["RANDOM_RESPONSE_CHANCE"],
            "AI_CHAT_RANDOM_RESPONSE_PROMPT": slash_config["COGS"]["AI_CHAT"]["RANDOM_RESPONSE_PROMPT"],
            "AI_CHAT_RATE_LIMIT": slash_config["COGS"]["AI_CHAT"]["RESPONSE_RATE_LIMIT"],
            "AI_CHAT_RATE_INTERVAL": slash_config["COGS"]["AI_CHAT"]["RATE_LIMIT_INTERVAL"],
            "AI_CHAT_USE_HISTORIC_REPLIES": bool(slash_config["COGS"]["AI_CHAT"]["USE_HISTORIC_REPLIES"]),
            "AI_CHAT_PROFILE_RESPONSE_TIME": bool(slash_config["COGS"]["AI_CHAT"]["ENABLE_PROFILING"]),
            "AI_CHAT_PREFER_IMAGE_URLS": bool(slash_config["COGS"]["AI_CHAT"]["PREFER_IMAGE_URLS"]),
        }
        cls._config = _config

        return cls._config

    # Public methods -----------------------------------------------------------

    @staticmethod
    def get_config(name: str) -> Any | None:  # noqa: ANN401
        """Get a configuration parameter.

        Parameters
        ----------
        name: str
            The name of the parameter to get the value for.

        Returns
        -------
        Any | None
            The value of the parameter requested, or None.

        """
        return Bot._config.get(name, None)

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
        Bot._config[name] = value


Bot.set_config_values()
setup_logging()

observer = Observer()
observer.schedule(FileWatcher(), path=Path(Bot.get_config("CONFIG_FILE")).parent)
observer.start()
