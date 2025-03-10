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
    logger = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))
    logger.addHandler(console_handler)
    file_handler = RotatingFileHandler(
        filename=BotConfig.get_config("LOGFILE_NAME"),
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
    logger.info("Loaded config file %s", BotConfig.get_config("CONFIG_FILE"))


class FileWatcher(FileSystemEventHandler):
    """Class for watching for changes to the config file."""

    def on_modified(self, event: FileSystemEventHandler) -> None:
        """Reload the config on file modify.

        Parameters
        ----------
        event : FileSystemEventHandler
            The event to check.

        """
        if event.event_type == "modified" and event.src_path == BotConfig.get_config("CONFIG_FILE"):
            original_config = copy.copy(BotConfig._config)  # noqa: SLF001
            new_config = BotConfig.set_config_values()
            modified_keys = {
                key for key in original_config if key in new_config and original_config[key] != new_config[key]
            }
            if modified_keys:
                logger = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))
                logger.info("App config updated:")
                for key in modified_keys:
                    logger.info("  %s: %s -> %s", key, original_config[key], new_config[key])


class BotConfig:
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
        # controlled by the BOT_CONFIG environment variable.
        try:
            with Path.open(os.getenv("BOT_CONFIG"), encoding="utf-8") as file_in:
                config_json = json.load(file_in)
            current_config = os.getenv("BOT_CONFIG")
        except (OSError, TypeError):
            print(f"Failed to load config file defined in $BOT_CONFIG: {os.getenv('BOT_CONFIG')}")  # noqa: T201
            print("Trying to load default config file: ./bot-config.json")  # noqa: T201
            with Path.open("./bot-config.json", encoding="utf-8") as file_in:
                config_json = json.load(file_in)
            current_config = "./bot-config.json"

        # This either sets a default value of `None`, or will re-use what is
        # already in cls._config. We need this for when the config file is
        # changed, which triggers the config being reloaded. I think this beats
        # having a global variable.
        current_chain = cls._config.get("CURRENT_MARKOV_CHAIN", None)

        # populate _config dict, which is a key store for configuration of the
        # bot
        _config = {
            # tokens
            "DEVELOPMENT_TOKEN": os.getenv("BOT_DEVELOPMENT_TOKEN"),
            "RUN_TOKEN": os.getenv("BOT_RUN_TOKEN"),
            # config file
            "CONFIG_FILE": str(Path(current_config).resolve()),
            # cooldown parameters
            "COOLDOWN_RATE": int(config_json["COOLDOWN"]["RATE"]),
            "COOLDOWN_STANDARD": int(config_json["COOLDOWN"]["STANDARD"]),
            "COOLDOWN_EXTENDED": int(config_json["COOLDOWN"]["EXTENDED"]),
            "NO_COOLDOWN_SERVERS": config_json["COOLDOWN"]["NO_COOLDOWN_SERVERS"],
            "NO_COOLDOWN_USERS": config_json["COOLDOWN"]["NO_COOLDOWN_USERS"],
            # general things
            "MAX_CHARS": 1800,
            "LOGGER_NAME": config_json["LOGFILE"]["LOG_NAME"],
            "LOGFILE_NAME": config_json["LOGFILE"]["LOG_LOCATION"],
            "DEVELOPMENT_SERVERS": config_json["DISCORD"]["DEVELOPMENT_SERVERS"],
            # Define users, roles and channels
            "ID_USER_SAULTYEVIL": 151378138612367360,
            "ID_USER_ADAM": 261097001301704704,
            "ID_USER_MEGHUN": 176722208243187712,
            "ID_CHANNEL_IDIOTS": 237647756049514498,
            "ID_SERVER_ADULT_CHILDREN": 237647756049514498,
            # API keys
            "GOOGLE_API_KEY": os.getenv("BOT_GOOGLE_API_KEY"),
            "WOLFRAM_API_KEY": os.getenv("BOT_WOLFRAM_API_KEY"),
            "OWM_API_KEY": os.getenv("BOT_OWM_API_KEY"),
            "DEEPSEEK_API_KEY": os.getenv("BOT_DEEPSEEK_API_KEY"),
            "OPENAI_API_KEY": os.getenv("BOT_OPENAI_API_KEY"),
            # File locations
            "DATABASE_LOCATION": Path(config_json["FILES"]["DATABASE"]),
            "BAD_WORDS_FILE": Path(config_json["FILES"]["BAD_WORDS"]),
            "GOD_WORDS_FILE": Path(config_json["FILES"]["GOD_WORDS"]),
            "SCHEDULED_POST_FILE": Path(config_json["FILES"]["SCHEDULED_POSTS"]),
            # Markov Chain configuration
            "ENABLE_MARKOV_TRAINING": bool(config_json["MARKOV"]["ENABLE_MARKOV_TRAINING"]),
            "CURRENT_MARKOV_CHAIN": current_chain,
            "PREGEN_MARKOV_SENTENCES_AMOUNT": int(config_json["MARKOV"]["NUM_PREGEN_SENTENCES"]),
            "PREGEN_REGENERATE_LIMIT": int(config_json["MARKOV"]["PREGEN_REGENERATE_LIMIT"]),
            # Cog settings
            "SPELLCHECK_ENABLED": bool(config_json["COGS"]["SPELLCHECK"]["ENABLED"]),
            "SPELLCHECK_SERVERS": config_json["COGS"]["SPELLCHECK"]["SERVERS"],
            "SPELLCHECK_CUSTOM_DICTIONARY": config_json["COGS"]["SPELLCHECK"]["CUSTOM_DICTIONARY"],
            "AI_CHAT_BASE_URL": config_json["COGS"]["AI_CHAT"]["API_BASE_URL"],
            "AI_CHAT_CHAT_MODEL": config_json["COGS"]["AI_CHAT"]["CHAT_MODEL"],
            "AI_CHAT_TEMPERATURE": config_json["COGS"]["AI_CHAT"]["MODEL_TEMPERATURE"],
            "AI_CHAT_TOP_P": config_json["COGS"]["AI_CHAT"]["MODEL_TOP_P"],
            "AI_CHAT_FREQUENCY_PENALTY": config_json["COGS"]["AI_CHAT"]["MODEL_FREQUENCY_PENALTY"],
            "AI_CHAT_PRESENCE_PENALTY": config_json["COGS"]["AI_CHAT"]["MODEL_PRESENCE_PENALTY"],
            "AI_CHAT_MAX_OUTPUT_TOKENS": config_json["COGS"]["AI_CHAT"]["MAX_OUTPUT_TOKENS"],
            "AI_CHAT_TOKEN_WINDOW_SIZE": config_json["COGS"]["AI_CHAT"]["TOKEN_WINDOW_SIZE"],
            "AI_CHAT_PROMPT_APPEND": config_json["COGS"]["AI_CHAT"]["PROMPT_APPEND"],
            "AI_CHAT_PROMPT_PREPEND": config_json["COGS"]["AI_CHAT"]["PROMPT_PREPEND"],
            "AI_CHAT_SUMMARY_PROMPT": config_json["COGS"]["AI_CHAT"]["SUMMARY_PROMPT"],
            "AI_CHAT_RANDOM_RESPONSE_CHANCE": config_json["COGS"]["AI_CHAT"]["RANDOM_RESPONSE_CHANCE"],
            "AI_CHAT_RANDOM_RESPONSE_PROMPT": config_json["COGS"]["AI_CHAT"]["RANDOM_RESPONSE_PROMPT"],
            "AI_CHAT_RATE_LIMIT": config_json["COGS"]["AI_CHAT"]["RESPONSE_RATE_LIMIT"],
            "AI_CHAT_RATE_INTERVAL": config_json["COGS"]["AI_CHAT"]["RATE_LIMIT_INTERVAL"],
            "AI_CHAT_USE_HISTORIC_REPLIES": bool(config_json["COGS"]["AI_CHAT"]["USE_HISTORIC_REPLIES"]),
            "AI_CHAT_PROFILE_RESPONSE_TIME": bool(config_json["COGS"]["AI_CHAT"]["ENABLE_PROFILING"]),
            "AI_CHAT_PREFER_IMAGE_URLS": bool(config_json["COGS"]["AI_CHAT"]["PREFER_IMAGE_URLS"]),
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
        return BotConfig._config.get(name, None)

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
        BotConfig._config[name] = value


BotConfig.set_config_values()
setup_logging()

observer = Observer()
observer.schedule(FileWatcher(), path=Path(BotConfig.get_config("CONFIG_FILE")).parent)
observer.start()
