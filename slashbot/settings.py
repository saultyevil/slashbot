import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class BaseCogSettings(BaseModel):
    """Base class for settings for a cog.

    Attributes
    ----------
    enabled : bool
        Whether the cog is enabled.

    """

    enabled: bool


class AdminCogSettings(BaseCogSettings):
    """Settings for the admin cog.

    Attributes
    ----------
    enabled : bool
        Whether the admin cog is enabled.

    """


class ChatBotCogSettings(BaseCogSettings):
    """Settings for chatbot cog.

    Attributes
    ----------
    enabled : bool
        Whether the chatbot cog is enabled.
    token_window_size : int
        Number of tokens to keep in context window.
    max_images_in_window : int
        Maximum number of images allowed in context window.
    max_output_tokens : int
        Maximum number of tokens in model output.
    model_temperature : float
        Sampling temperature for model generation.
    model_top_p : float
        Nucleus sampling parameter for model generation.
    model_frequency_penalty : float
        Penalty for frequent tokens in model output.
    model_presence_penalty : float
        Penalty for new tokens in model output.
    default_model : str
        Name of the default chat model to use.
    default_chat_prompt : str
        Default prompt for chat.
    random_response_chance : float
        Chance to send a random response.
    random_response_use_n_messages : int
        Number of messages to consider for random response.
    response_rate_limit : int
        Maximum responses to a user allowed per interval.
    rate_limit_interval : int
        Time interval for rate limiting (seconds).
    enable_profiling : bool
        Whether to enable profiling for chat response time.
    prefer_image_urls : bool
        Prefer using image URLs in request to chat API.

    """

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
    """Settings for the markov cog.

    Attributes
    ----------
    enabled : bool
        Whether the markov cog is enabled.

    """


class MovieTrackerCogSettings(BaseCogSettings):
    """Settings for the movie tracker cog.

    Attributes
    ----------
    enabled : bool
        Whether the movie tracker cog is enabled.
    update_interval : float
        Interval (minutes) between updates.
    channels : list[int]
        List of channel IDs to post updates to.

    """

    update_interval: float
    channels: list[int]


class RemindersCogSettings(BaseCogSettings):
    """Settings for the reminders cog.

    Attributes
    ----------
    enabled : bool
        Whether the reminders cog is enabled.

    """


class ScheduledPostsCogSettings(BaseCogSettings):
    """Settings for the scheduled posts cog.

    Attributes
    ----------
    enabled : bool
        Whether the scheduled posts cog is enabled.

    """


class SpamCogSettings(BaseCogSettings):
    """Settings for the spam cog.

    Attributes
    ----------
    enabled : bool
        Whether the spam cog is enabled.

    """


class SpellcheckCogSettings(BaseCogSettings):
    """Settings for the spellcheck cog.

    Attributes
    ----------
    enabled : bool
        Whether the spellcheck cog is enabled.
    servers : dict[str, Any]
        Dictionary of spellcheck servers and users in that server enabled for.
    custom_dictionary : str
        Path to custom dictionary file.

    """

    servers: dict[str, Any]
    custom_dictionary: str


class ToolsCogSettings(BaseCogSettings):
    """Settings for the tools cog.

    Attributes
    ----------
    enabled : bool
        Whether the tools cog is enabled.

    """


class UsersCogSettings(BaseCogSettings):
    """Settings for the users cog.

    Attributes
    ----------
    enabled : bool
        Whether the users cog is enabled.

    """


class VideosCogSettings(BaseCogSettings):
    """Settings for the videos cog.

    Attributes
    ----------
    enabled : bool
        Whether the videos cog is enabled.

    """


class WeatherCogSettings(BaseCogSettings):
    """Settings for the weather cog.

    Attributes
    ----------
    enabled : bool
        Whether the weather cog is enabled.

    """


class CogSettings(BaseModel):
    """Cog settings.

    Attributes
    ----------
    admin : AdminCogSettings
        Settings for the admin cog.
    chatbot : ChatBotCogSettings
        Settings for the chatbot cog.
    markov : MarkovCogSettings
        Settings for the markov cog.
    movie_tracker : MovieTrackerCogSettings
        Settings for the movie tracker cog.
    reminders : RemindersCogSettings
        Settings for the reminders cog.
    scheduled_posts : ScheduledPostsCogSettings
        Settings for the scheduled posts cog.
    spam : SpamCogSettings
        Settings for the spam cog.
    spelling : SpellcheckCogSettings
        Settings for the spellcheck cog.
    tools : ToolsCogSettings
        Settings for the tools cog.
    users : UsersCogSettings
        Settings for the users cog.
    videos : VideosCogSettings
        Settings for the videos cog.
    weather : WeatherCogSettings
        Settings for the weather cog.

    """

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
    """Command cooldown settings.

    Attributes
    ----------
    rate : int
        Number of allowed commands per interval.
    standard : int
        Standard cooldown time (seconds).
    no_cooldown_users : list[int]
        List of user IDs exempt from cooldown.
    no_cooldown_servers : list[int]
        List of server IDs exempt from cooldown.

    """

    rate: int
    standard: int
    no_cooldown_users: list[int]
    no_cooldown_servers: list[int]


class DiscordUserIds(BaseModel):
    """User IDs.

    Attributes
    ----------
    saultyevil : int
        Discord user ID for saultyevil.
    adam : int
        Discord user ID for adam.
    seventytwo : int
        Discord user ID for seventytwo.

    """

    saultyevil: int = 151378138612367360
    adam: int = 261097001301704704
    seventytwo: int = 176722208243187712


class DiscordChannelIds(BaseModel):
    """Channel IDs.

    Attributes
    ----------
    idiots : int
        Discord channel ID for idiots channel.

    """

    idiots: int = 237647756049514498


class DiscordServerIds(BaseModel):
    """Server IDs.

    Attributes
    ----------
    adult_children : int
        Discord server ID for adult_children server.

    """

    adult_children: int = 237647756049514498


class DiscordSettings(BaseModel):
    """Discord specific settings.

    Attributes
    ----------
    max_chars : int
        Maximum number of characters allowed in a message.
    development_servers : list[int]
        List of server IDs for development.
    users : DiscordUserIds
        User IDs for Discord users.
    channels : DiscordChannelIds
        Channel IDs for Discord channels.
    servers : DiscordServerIds
        Server IDs for Discord servers.

    """

    max_chars: int
    development_servers: list[int]
    users: DiscordUserIds = Field(default_factory=DiscordUserIds)
    channels: DiscordChannelIds = Field(default_factory=DiscordChannelIds)
    servers: DiscordServerIds = Field(default_factory=DiscordServerIds)


class Files(BaseModel):
    """File locations and settings.

    Attributes
    ----------
    database : Path
        Path to the database file.
    bad_words : Path
        Path to the bad words file.
    god_words : Path
        Path to the god words file.
    scheduled_posts : Path
        Path to the scheduled posts file.

    """

    database: Path
    bad_words: Path
    god_words: Path
    scheduled_posts: Path


class LoggingSettings(BaseModel):
    """Logfile settings.

    Attributes
    ----------
    log_location : str
        Path to the main log file.
    debug_log_location : str
        Path to the debug log file.
    logger_name : str
        Name of the logger.

    """

    log_location: str = "logs/slashbot.log"
    debug_log_location: str = "logs/slashbot_debug.log"
    logger_name: str = "slashbot"


class MarkovSettings(BaseModel):
    """Settings related to Markov generation.

    Attributes
    ----------
    enable_markov_training : bool
        Whether Markov training is enabled.
    enable_pregen_sentences : bool
        Whether pregeneration of sentences is enabled.
    num_pregen_sentences : int
        Number of pregenerated sentences to generate.
    pregenerate_limit : int
        Minimum number of sentences allowed before pre-generating more.
    current_chain_location : Path
        Path to the current Markov chain file.

    """

    enable_markov_training: bool
    enable_pregen_sentences: bool
    num_pregen_sentences: int
    pregenerate_limit: int
    current_chain_location: Path = Path("data/markov/chain.pickle")


class KeyStore(BaseModel):
    """Storage for API keys and the like.

    Attributes
    ----------
    run_token : str | None
        Token for running the bot.
    development_token : str | None
        Token for development environment.
    openai : str | None
        OpenAI API key.
    openweathermap : str | None
        OpenWeatherMap API key.
    google : str | None
        Google API key.
    wolframalpha : str | None
        WolframAlpha API key.
    gemini : str | None
        Gemini API key.

    """

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
        print(  # noqa: T201
            f"Failed to load config file defined in $BOT_CONFIG {config_path} or default location",
            file=sys.stderr,
        )
        sys.exit(1)

    return Settings.from_toml(config_path)


BotSettings = load_settings()
