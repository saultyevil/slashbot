import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SpellcheckSettings:
    """Settings for the spellcheck cog."""

    enabled: bool
    servers: dict[str, Any]
    custom_dictionary: str


@dataclass
class AIChatSettings:
    """Settings for LLM text generation."""

    token_window_size: int
    max_output_tokens: int
    model_temperature: float
    model_top_p: float
    model_frequency_penalty: float
    model_presence_penalty: float
    chat_model: str
    api_base_url: str
    random_response_chance: float
    response_rate_limit: int
    rate_limit_interval: int
    enable_profiling: bool
    prefer_image_urls: bool


@dataclass
class CogSettings:
    """Cog settings."""

    spellcheck: SpellcheckSettings
    ai_chat: AIChatSettings


@dataclass
class CommandCooldownSettings:
    """Command cooldown settings."""

    rate: int
    standard: int
    no_cooldown_users: list[int]
    no_cooldown_servers: list[int]


@dataclass
class DiscordSettings:
    """Discord specific settings."""

    max_chars: int
    development_servers: list[int]


@dataclass
class FilesSettings:
    """File locations and settings."""

    database: str
    bad_words: str
    god_words: str
    scheduled_posts: str


@dataclass
class LoggingSettings:
    """Logfile settings."""

    logger_name: str
    log_location: str


@dataclass
class MarkovSettings:
    """Settings related to Markov generation."""

    enable_markov_training: bool
    enable_pregen_sentences: bool
    num_pregen_sentences: int
    pregenerate_limit: int


@dataclass
class Settings:
    """Global settings dataclass."""

    config_file: str
    cogs: CogSettings
    cooldown: CommandCooldownSettings
    discord: DiscordSettings
    files: FilesSettings
    logging: LoggingSettings
    markov: MarkovSettings

    @classmethod
    def from_toml(cls, config_path: str | Path) -> "Settings":
        """Load the settings from a TOML file."""
        config_path = Path(config_path)
        with config_path.open("rb") as f:
            data = tomllib.load(f)

        spellcheck = SpellcheckSettings(
            enabled=data["cogs"]["spellcheck"]["enabled"],
            servers=data["cogs"]["spellcheck"]["servers"],
            custom_dictionary=data["cogs"]["spellcheck"]["custom_dictionary"],
        )
        ai_chat = AIChatSettings(
            token_window_size=data["cogs"]["ai_chat"]["token_window_size"],
            max_output_tokens=data["cogs"]["ai_chat"]["max_output_tokens"],
            model_temperature=data["cogs"]["ai_chat"]["model_temperature"],
            model_top_p=data["cogs"]["ai_chat"]["model_top_p"],
            model_frequency_penalty=data["cogs"]["ai_chat"]["model_frequency_penalty"],
            model_presence_penalty=data["cogs"]["ai_chat"]["model_presence_penalty"],
            chat_model=data["cogs"]["ai_chat"]["chat_model"],
            api_base_url=data["cogs"]["ai_chat"]["api_base_url"],
            random_response_chance=data["cogs"]["ai_chat"]["random_response_chance"],
            response_rate_limit=data["cogs"]["ai_chat"]["response_rate_limit"],
            rate_limit_interval=data["cogs"]["ai_chat"]["rate_limit_interval"],
            enable_profiling=data["cogs"]["ai_chat"]["enable_profiling"],
            prefer_image_urls=data["cogs"]["ai_chat"]["prefer_image_urls"],
        )
        cogs = CogSettings(spellcheck=spellcheck, ai_chat=ai_chat)
        cooldown = CommandCooldownSettings(
            rate=data["cooldown"]["rate"],
            standard=data["cooldown"]["standard"],
            no_cooldown_users=data["cooldown"]["no_cooldown_users"],
            no_cooldown_servers=data["cooldown"]["no_cooldown_servers"],
        )
        discord = DiscordSettings(
            max_chars=data["discord"]["max_chars"],
            development_servers=data["discord"]["development_servers"],
        )
        files = FilesSettings(
            database=data["files"]["database"],
            bad_words=data["files"]["bad_words"],
            god_words=data["files"]["god_words"],
            scheduled_posts=data["files"]["scheduled_posts"],
        )
        logging = LoggingSettings(
            logger_name=data["logfile"]["log_name"],
            log_location=data["logfile"]["log_location"],
        )
        markov = MarkovSettings(
            enable_markov_training=data["markov"]["enable_markov_training"],
            enable_pregen_sentences=data["markov"]["enable_pregen_sentences"],
            num_pregen_sentences=data["markov"]["num_pregen_sentences"],
            pregenerate_limit=data["markov"]["pregenerate_limit"],
        )
        return cls(
            config_file=str(config_path.resolve()),
            cogs=cogs,
            cooldown=cooldown,
            discord=discord,
            files=files,
            logging=logging,
            markov=markov,
        )


def load_settings() -> Settings:
    """Load the settings from a TOML file.

    Returns
    -------
    Settings
        The settings from the TOML file, as a Settings dataclass.

    """
    config_path = Path(os.getenv("BOT_CONFIG_TOML", "./bot-config.toml"))
    if not config_path.is_file():
        print(f"Failed to load config file defined in $BOT_CONFIG {config_path} or default location")  # noqa: T201
        sys.exit(1)

    return Settings.from_toml(config_path)


BotSettings = load_settings()
a = 1


def reload_settings() -> None:
    """Reload the global BotSettings."""
    global BotSettings  # noqa: PLW0603
    BotSettings = load_settings()
    return BotSettings
