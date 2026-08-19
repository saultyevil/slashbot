import time

from watchdog.events import FileSystemEvent, FileSystemEventHandler

from slashbot.settings import BotSettings


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
