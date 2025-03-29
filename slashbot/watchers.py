import copy
import json
import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from slashbot.prompts import create_prompt_dict, read_in_prompt_json
from slashbot.settings import BotConfig

AVAILABLE_LLM_PROMPTS = create_prompt_dict()
LOGGER = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))


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
                LOGGER.info("App config updated:")
                for key in modified_keys:
                    LOGGER.info("  %s: %s -> %s", key, original_config[key], new_config[key])


class ScheduledPostWatcher(FileSystemEventHandler):
    """File watcher to watch for changes to scheduled posts file."""

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

        if event.src_path == str(BotConfig.get_config("SCHEDULED_POST_FILE").absolute()):
            self.parent.get_scheduled_posts()
            if self.parent.post_loop.is_running():
                self.parent.post_loop.cancel()
                while self.parent.post_loop.is_running():
                    time.sleep(0.5)
            self.parent.post_loop.start()


FILE_OBSERVER = Observer()
FILE_OBSERVER.schedule(PromptFileWatcher(), "data/prompts", recursive=True)
FILE_OBSERVER.schedule(ConfigFileWatcher(), path=Path(BotConfig.get_config("CONFIG_FILE")).parent)
FILE_OBSERVER.start()
