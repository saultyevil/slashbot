import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from slashbot.prompts import create_prompt_dict, read_in_prompt_json
from slashbot.settings import BotSettings, reload_settings

AVAILABLE_LLM_PROMPTS = create_prompt_dict()
LOGGER = logging.getLogger(BotSettings.logging.logger_name)


class PromptFileWatcher(FileSystemEventHandler):
    """File watched for prompt files for LLM purposes."""

    def __init__(self) -> None:
        """Initialise the watcher."""
        super().__init__()

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle any file system event.

        This method is called when any file system event occurs.
        It updates the `PROMPT_CHOICES` dictionary based on the event type and
        source path.
        """
        global AVAILABLE_LLM_PROMPTS  # noqa: PLW0603
        if event.is_directory and not event.src_path.endswith(".json"):
            return
        try:
            if event.event_type in ["created", "modified"]:
                prompt = read_in_prompt_json(event.src_path)
                AVAILABLE_LLM_PROMPTS[prompt["name"]] = prompt["prompt"]
            if event.event_type == "deleted":
                AVAILABLE_LLM_PROMPTS = create_prompt_dict()
            LOGGER.debug("%s prompt %s", event.event_type.capitalize(), event.src_path)
        except json.decoder.JSONDecodeError:
            LOGGER.exception("Error reading in prompt file %s", event.src_path)


class ConfigFileWatcher(FileSystemEventHandler):
    """Watches for changes to the configuration file and reloads BotSettings.

    ####
    THIS IS NOT IMPLEMENTED YET
    ###

    """

    def on_modified(self, event: FileSystemEventHandler) -> None:
        """Reload the config on file modify.

        Parameters
        ----------
        event : FileSystemEventHandler
            The event to check.

        """
        src_path = str(Path(event.src_path).resolve())
        if event.event_type == "modified" and src_path == BotSettings.config_file:
            old_settings = asdict(BotSettings)
            new_settings = asdict(reload_settings())
            changes = {
                key: (old_settings[key], new_settings[key])
                for key in old_settings
                if old_settings[key] != new_settings[key]
            }
            if changes:
                LOGGER.info("Bot settings updated:")
                for key, (old_val, new_val) in changes.items():
                    LOGGER.info("  %s: %s -> %s", key, old_val, new_val)

            LOGGER.info("%s", BotSettings.markov.pregenerate_limit)


class ScheduledPostWatcher(FileSystemEventHandler):
    """File watcher to watch for changes to scheduled posts file.

    Note that the ScheduledPostWatcher is scheduled to a different thread inside
    the ScheduledPosts cog.
    """

    def __init__(self, parent_class) -> None:  # noqa: ANN001
        """Initialise the watcher."""
        super().__init__()
        self.parent = parent_class
        self.last_restart_time = 0

    def on_modified(self, event: FileSystemEventHandler) -> None:
        """Reload the posts on file modify.

        Parameters
        ----------
        event : FileSystemEventHandler
            The event to check.

        """
        if time.time() - self.last_restart_time < 2:  # Prevent multiple triggers within 2s
            return
        self.last_restart_time = time.time()

        if event.src_path == str(BotSettings.files.scheduled_posts):
            self.parent.get_scheduled_posts()
            if self.parent.post_loop.is_running():
                self.parent.post_loop.cancel()
                while self.parent.post_loop.is_running():
                    time.sleep(0.5)
            self.parent.post_loop.start()


FILE_OBSERVER = Observer()
FILE_OBSERVER.schedule(PromptFileWatcher(), "data/prompts", recursive=True)
# FILE_OBSERVER.schedule(ConfigFileWatcher(), path=Path(BotSettings.config_file).parent)
FILE_OBSERVER.start()
