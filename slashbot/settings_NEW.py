import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# --- Dataclass Definitions ---
@dataclass
class SpellcheckSettings:
    enabled: bool
    servers: dict[str, Any]
    custom_dictionary: str


@dataclass
class ScheduledPostsSettings:
    random_post_channels: list[int]


@dataclass
class AIChatSettings:
    summary_prompt: str
    random_response_prompt: str
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
    prompt_prepend: str
    prompt_append: str
    use_historic_replies: bool
    enable_profiling: bool
    prefer_image_urls: bool


@dataclass
class CogSettings:
    spellcheck: SpellcheckSettings
    scheduled_posts: ScheduledPostsSettings
    ai_chat: AIChatSettings


@dataclass
class CooldownSettings:
    rate: int
    standard: int
    extended: int
    no_cooldown_users: list[int]
    no_cooldown_servers: list[int]


@dataclass
class DiscordSettings:
    max_chars: int
    development_servers: list[int]


@dataclass
class FilesSettings:
    database: str
    bad_words: str
    god_words: str
    scheduled_posts: str


@dataclass
class LogfileSettings:
    log_name: str
    log_location: str


@dataclass
class MarkovSettings:
    enable_markov_training: bool
    enable_pregen_sentences: bool
    num_pregen_sentences: int
    pregenerate_limit: int


@dataclass
class Settings:
    cogs: CogSettings
    cooldown: CooldownSettings
    discord: DiscordSettings
    files: FilesSettings
    logfile: LogfileSettings
    markov: MarkovSettings

    @classmethod
    def from_toml(cls, path: str | Path) -> "Settings":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        # Build each section using the lower-case keys from the TOML.
        spellcheck = SpellcheckSettings(
            enabled=data["cogs"]["spellcheck"]["enabled"],
            servers=data["cogs"]["spellcheck"]["servers"],
            custom_dictionary=data["cogs"]["spellcheck"]["custom_dictionary"],
        )
        scheduled_posts = ScheduledPostsSettings(
            random_post_channels=data["cogs"]["scheduled_posts"]["random_post_channels"]
        )
        ai_chat = AIChatSettings(
            summary_prompt=data["cogs"]["ai_chat"]["summary_prompt"],
            random_response_prompt=data["cogs"]["ai_chat"]["random_response_prompt"],
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
            prompt_prepend=data["cogs"]["ai_chat"]["prompt_prepend"],
            prompt_append=data["cogs"]["ai_chat"]["prompt_append"],
            use_historic_replies=data["cogs"]["ai_chat"]["use_historic_replies"],
            enable_profiling=data["cogs"]["ai_chat"]["enable_profiling"],
            prefer_image_urls=data["cogs"]["ai_chat"]["prefer_image_urls"],
        )
        cogs = CogSettings(spellcheck=spellcheck, scheduled_posts=scheduled_posts, ai_chat=ai_chat)
        cooldown = CooldownSettings(
            rate=data["cooldown"]["rate"],
            standard=data["cooldown"]["standard"],
            extended=data["cooldown"]["extended"],
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
        logfile = LogfileSettings(
            log_name=data["logfile"]["log_name"],
            log_location=data["logfile"]["log_location"],
        )
        markov = MarkovSettings(
            enable_markov_training=data["markov"]["enable_markov_training"],
            enable_pregen_sentences=data["markov"]["enable_pregen_sentences"],
            num_pregen_sentences=data["markov"]["num_pregen_sentences"],
            pregenerate_limit=data["markov"]["pregenerate_limit"],
        )
        return cls(
            cogs=cogs,
            cooldown=cooldown,
            discord=discord,
            files=files,
            logfile=logfile,
            markov=markov,
        )


def load_settings() -> Settings:
    config_path = "bot-config.toml"
    return Settings.from_toml(config_path)


settings = load_settings()
print(settings)
