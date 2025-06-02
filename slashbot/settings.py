import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SpellcheckSettings:
    """Settings for the spellcheck cog."""

    enabled: bool
    guilds: dict[str, Any]
    custom_dictionary: str


@dataclass
class ArtificialIntelligenceSettings:
    """Settings for LLM text generation."""

    token_window_size: int
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


@dataclass
class CogSettings:
    """Cog settings."""

    spellcheck: SpellcheckSettings
    artificial_intelligence: ArtificialIntelligenceSettings


@dataclass
class CommandCooldownSettings:
    """Command cooldown settings."""

    rate: int
    standard: int
    no_cooldown_users: list[int]
    no_cooldown_servers: list[int]


@dataclass
class UserIDs:
    """User IDs."""

    saultyevil: int = 151378138612367360
    adam: int = 261097001301704704
    seventytwo: int = 176722208243187712


@dataclass
class ChannelIDs:
    """Channel IDs."""

    idiots: int = 237647756049514498


@dataclass
class ServerIDs:
    """Server IDs."""

    adult_children: int = 237647756049514498


@dataclass
class DiscordSettings:
    """Discord specific settings."""

    max_chars: int
    development_servers: list[int]
    users: UserIDs = field(default_factory=UserIDs)
    channels: ChannelIDs = field(default_factory=ChannelIDs)
    servers: ServerIDs = field(default_factory=ServerIDs)


@dataclass
class FileLocations:
    """File locations and settings."""

    database: Path
    bad_words: Path
    god_words: Path
    scheduled_posts: Path


@dataclass
class LoggingSettings:
    """Logfile settings."""

    log_location: str = "logs/slashbot.log"
    debug_log_location: str = "logs/slashbot_debug.log"
    logger_name: str = "slashbot"


@dataclass
class MarkovSettings:
    """Settings related to Markov generation."""

    enable_markov_training: bool
    enable_pregen_sentences: bool
    num_pregen_sentences: int
    pregenerate_limit: int
    current_chain_location: str | Path = Path("data/markov/chain.pickle")


@dataclass
class KeyStore:
    """Storage for API keys and the like."""

    run_token = os.getenv("BOT_RUN_TOKEN")
    development_token = os.getenv("BOT_DEVELOPMENT_TOKEN")
    openai = os.getenv("BOT_OPENAI_API_KEY")
    openweathermap = os.getenv("BOT_OWM_API_KEY")
    google = os.getenv("BOT_GOOGLE_API_KEY")
    wolframalpha = os.getenv("BOT_WOLFRAM_API_KEY")
    gemini = os.getenv("BOT_GEMINI_API_KEY")


@dataclass
class Settings:
    """Global settings dataclass."""

    config_file: str
    cogs: CogSettings
    cooldown: CommandCooldownSettings
    discord: DiscordSettings
    file_locations: FileLocations
    logging: LoggingSettings
    markov: MarkovSettings
    keys: KeyStore

    @classmethod
    def from_toml(cls, config_path: str | Path) -> "Settings":
        """Load the settings from a TOML file."""
        config_path = Path(config_path)
        with config_path.open("rb") as f:
            data = tomllib.load(f)

        spellcheck = SpellcheckSettings(
            enabled=data["cogs"]["spellcheck"]["enabled"],
            guilds=data["cogs"]["spellcheck"]["servers"],
            custom_dictionary=data["cogs"]["spellcheck"]["custom_dictionary"],
        )
        artificial_intelligence = ArtificialIntelligenceSettings(
            token_window_size=data["cogs"]["artificial_intelligence"]["token_window_size"],
            max_output_tokens=data["cogs"]["artificial_intelligence"]["max_output_tokens"],
            model_temperature=data["cogs"]["artificial_intelligence"]["model_temperature"],
            model_top_p=data["cogs"]["artificial_intelligence"]["model_top_p"],
            model_frequency_penalty=data["cogs"]["artificial_intelligence"]["model_frequency_penalty"],
            model_presence_penalty=data["cogs"]["artificial_intelligence"]["model_presence_penalty"],
            default_model=data["cogs"]["artificial_intelligence"]["default_model"],
            default_chat_prompt=data["cogs"]["artificial_intelligence"]["default_chat_prompt"],
            random_response_chance=data["cogs"]["artificial_intelligence"]["random_response_chance"],
            response_rate_limit=data["cogs"]["artificial_intelligence"]["response_rate_limit"],
            random_response_use_n_messages=data["cogs"]["artificial_intelligence"]["random_response_use_n_messages"],
            rate_limit_interval=data["cogs"]["artificial_intelligence"]["rate_limit_interval"],
            enable_profiling=data["cogs"]["artificial_intelligence"]["enable_profiling"],
            prefer_image_urls=data["cogs"]["artificial_intelligence"]["prefer_image_urls"],
        )
        cogs = CogSettings(spellcheck=spellcheck, artificial_intelligence=artificial_intelligence)
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
        files = FileLocations(
            database=Path(data["files"]["database"]).absolute(),
            bad_words=Path(data["files"]["bad_words"]).absolute(),
            god_words=Path(data["files"]["god_words"]).absolute(),
            scheduled_posts=Path(data["files"]["scheduled_posts"]).absolute(),
        )
        logging = LoggingSettings(
            log_location=data["logfile"]["log_location"],
        )
        markov = MarkovSettings(
            enable_markov_training=data["markov"]["enable_markov_training"],
            enable_pregen_sentences=data["markov"]["enable_pregen_sentences"],
            num_pregen_sentences=data["markov"]["num_pregen_sentences"],
            pregenerate_limit=data["markov"]["pregenerate_limit"],
        )
        keys = KeyStore()
        return cls(
            config_file=str(config_path.resolve()),
            cogs=cogs,
            cooldown=cooldown,
            discord=discord,
            file_locations=files,
            logging=logging,
            markov=markov,
            keys=keys,
        )


def load_settings() -> Settings:
    """Load the settings from a TOML file.

    Returns
    -------
    Settings
        The settings from the TOML file, as a Settings dataclass.

    """
    config_path = Path(os.getenv("BOT_CONFIG", "./bot-config.toml"))
    if not config_path.is_file():
        print(f"Failed to load config file defined in $BOT_CONFIG {config_path} or default location")  # noqa: T201
        sys.exit(1)

    return Settings.from_toml(config_path)


BotSettings = load_settings()
