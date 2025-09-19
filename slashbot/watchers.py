import time

import pydantic
import yaml
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from slashbot.ai.prompts import create_prompt_dict, read_in_prompt
from slashbot.logger import Logger
from slashbot.settings import BotSettings

AVAILABLE_LLM_PROMPTS = create_prompt_dict()
LOGGER = Logger()


class PromptFileWatcher(FileSystemEventHandler):
    """File watched for prompt files for LLM purposes."""

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle any file system event.

        This method is called when any file system event occurs.
        It updates the `PROMPT_CHOICES` dictionary based on the event type and
        source path.
        """
        global AVAILABLE_LLM_PROMPTS  # noqa: PLW0603
        if event.is_directory and not event.src_path.endswith(".yaml"):
            return
        try:
            if event.event_type in ["created", "modified"]:
                prompt = read_in_prompt(event.src_path)
                AVAILABLE_LLM_PROMPTS[prompt.name] = prompt.prompt
                LOGGER.log_debug("%s prompt %s", event.event_type.capitalize(), event.src_path)
            if event.event_type == "deleted":
                AVAILABLE_LLM_PROMPTS = create_prompt_dict()
                LOGGER.log_debug("%s prompt %s", event.event_type.capitalize(), event.src_path)
        except (yaml.YAMLError, pydantic.ValidationError):
            LOGGER.log_exception("Error reading in prompt file %s", event.src_path)


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

    def on_modified(self, event: FileSystemEvent) -> None:
        """Reload the posts on file modify.

        Parameters
        ----------
        event : FileSystemEventHandler
            The event to check.

        """
        if time.time() - self.last_restart_time < 2:  # Prevent multiple triggers within 2s  # noqa: PLR2004
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
FILE_OBSERVER.start()
