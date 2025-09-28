import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class BaseCogSettings(BaseModel):
    """Base class for settings for a cog."""

    enabled: bool


class AdminCogSettings(BaseCogSettings):
    """Settings for the admin cog."""


class ChatBotCogSettings(BaseCogSettings):
    """Settings for artificial intelligence cog."""

    token_window_size: int
    max_images_in_window: int
    max_output_tokens: int
    model_temperature: float
    model_top_p: float
    model_frequency_penalty: float
    model_presence_penalty: float
    default_model: str
    default_chat_prompt: str
    random_response_chance: float
    random_response_use_n_messages: int
    response_rate_limit: int
    rate_limit_interval: int
    enable_profiling: bool
    prefer_image_urls: bool


class MarkovCogSettings(BaseCogSettings):
    """Settings for the markov cog."""


class MovieTrackerCogSettings(BaseCogSettings):
    """Settings for the movie tracker cog."""

    update_interval: float
    channels: list[int]


class RemindersCogSettings(BaseCogSettings):
    """Settings for the reminders cog."""


class ScheduledPostsCogSettings(BaseCogSettings):
    """Settings for the scheduled posts cog."""


class SpamCogSettings(BaseCogSettings):
    """Settings for the spam cog."""


class SpellcheckCogSettings(BaseCogSettings):
    """Settings for the spellcheck cog."""

    enabled: bool
    servers: dict[str, Any]
    custom_dictionary: str


class ToolsCogSettings(BaseCogSettings):
    """Settings for the tools cog."""


class UsersCogSettings(BaseCogSettings):
    """Settings for the users cog."""


class VideosCogSettings(BaseCogSettings):
    """Settings for the videos cog."""


class WeatherCogSettings(BaseCogSettings):
    """Settings for the wather cog."""


class CogSettings(BaseModel):
    """Cog settings."""

    admin: AdminCogSettings
    chatbot: ChatBotCogSettings
    markov: MarkovCogSettings
    movie_tracker: MovieTrackerCogSettings
    reminders: RemindersCogSettings
    scheduled_posts: ScheduledPostsCogSettings
    spam: SpamCogSettings
    spelling: SpellcheckCogSettings
    tools: ToolsCogSettings
    users: UsersCogSettings
    videos: VideosCogSettings
    weather: WeatherCogSettings


class CooldownSettings(BaseModel):
    """Command cooldown settings."""

    rate: int
    standard: int
    no_cooldown_users: list[int]
    no_cooldown_servers: list[int]


class DiscordUserIds(BaseModel):
    """User IDs."""

    saultyevil: int = 151378138612367360
    adam: int = 261097001301704704
    seventytwo: int = 176722208243187712


class DiscordChannelIds(BaseModel):
    """Channel IDs."""

    idiots: int = 237647756049514498


class DiscordServerIds(BaseModel):
    """Server IDs."""

    adult_children: int = 237647756049514498


class DiscordSettings(BaseModel):
    """Discord specific settings."""

    max_chars: int
    development_servers: list[int]
    users: DiscordUserIds = Field(default_factory=DiscordUserIds)
    channels: DiscordChannelIds = Field(default_factory=DiscordChannelIds)
    servers: DiscordServerIds = Field(default_factory=DiscordServerIds)


class Files(BaseModel):
    """File locations and settings."""

    database: Path
    bad_words: Path
    god_words: Path
    scheduled_posts: Path


class LoggingSettings(BaseModel):
    """Logfile settings."""

    log_location: str = "logs/slashbot.log"
    debug_log_location: str = "logs/slashbot_debug.log"
    logger_name: str = "slashbot"


class MarkovSettings(BaseModel):
    """Settings related to Markov generation."""

    enable_markov_training: bool
    enable_pregen_sentences: bool
    num_pregen_sentences: int
    pregenerate_limit: int
    current_chain_location: Path = Path("data/markov/chain.pickle")


class KeyStore(BaseModel):
    """Storage for API keys and the like."""

    run_token: str | None = os.getenv("BOT_RUN_TOKEN")
    development_token: str | None = os.getenv("BOT_DEVELOPMENT_TOKEN")
    openai: str | None = os.getenv("BOT_OPENAI_API_KEY")
    openweathermap: str | None = os.getenv("BOT_OWM_API_KEY")
    google: str | None = os.getenv("BOT_GOOGLE_API_KEY")
    wolframalpha: str | None = os.getenv("BOT_WOLFRAM_API_KEY")
    gemini: str | None = os.getenv("BOT_GEMINI_API_KEY")


class Settings(BaseModel):
    """Settings for the bot.

    Attributes
    ----------
    config_file : str
        The path to the config file.
    cogs : CogSettings
        Settings for each cog.
    cooldown : CooldownSettings
        Settings for controlling global command cooldown.
    discord : DiscordSettings
        Settings specific for the bot's interaction with Discord.
    files : Files
        Locations of important files.
    logging : LoggingSettings
        Settings which configure the logging.
    markov : MarkovSettings
        Settings for Markov chain generation.
    key : KeyStore
        API keys.

    """

    config_file: str
    cogs: CogSettings
    cooldown: CooldownSettings
    discord: DiscordSettings
    files: Files
    logging: LoggingSettings
    markov: MarkovSettings
    keys: KeyStore = Field(default_factory=KeyStore)

    @classmethod
    def from_toml(cls, config_path: str | Path) -> "Settings":
        """Load the settings from a TOML file.

        Parameters
        ----------
        config_path : str | Path
            The path to the config file to load.

        Returns
        -------
        Settings
            A populated instance of the Settings class.

        """
        config_path = Path(config_path)
        with config_path.open("rb") as f:
            data = tomllib.load(f)

        return cls(config_file=str(config_path.resolve()), **data)


def load_settings() -> Settings:
    """Load the settings from a TOML file.

    Returns
    -------
    Settings
        The settings from the TOML file, as a Settings object.

    """
    config_path = Path(os.getenv("BOT_CONFIG", "./bot-config.toml"))
    if not config_path.is_file():
        print(
            f"Failed to load config file defined in $BOT_CONFIG {config_path} or default location",
            file=sys.stderr,
        )
        sys.exit(1)

    return Settings.from_toml(config_path)


BotSettings = load_settings()
