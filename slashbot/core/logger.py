import logging
import pathlib
from logging import FileHandler
from logging.handlers import RotatingFileHandler
from typing import Any

from slashbot.settings import BotSettings

USER_FACING_LOGGER = "user-facing-log"


class ConditionalFormatter(logging.Formatter):
    """Custom log formatter that adjusts format based on log level.

    For log records with level WARNING or higher, the output includes the log
    level name. For lower levels (e.g. DEBUG, INFO), the log level is omitted
    from the output.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the specified log record.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to be formatted.

        Returns
        -------
        str
            The formatted log message.

        """
        if record.levelno >= logging.WARNING:
            self._style._fmt = "%(asctime)s | %(levelname)s | %(message)s"  # noqa: SLF001
        else:
            self._style._fmt = "%(asctime)s | %(message)s"  # noqa: SLF001
        return super().format(record)


def setup_logging() -> None:
    """Set up log formatting.

    This sets up the logging for the bot's logic, and also the Disnake log. Not
    part of the Logger class below because you end up with multiple handlers on
    one logger and this was the cleaner way to do it.
    """
    logger = logging.getLogger(BotSettings.logging.logger_name)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)8s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    debug_console_handler = logging.StreamHandler()
    debug_console_handler.setFormatter(formatter)
    debug_console_handler.setLevel(logging.DEBUG)
    debug_console_handler.set_name("debug-console")
    logger.addHandler(debug_console_handler)

    debug_file_handler = RotatingFileHandler(
        filename=BotSettings.logging.debug_log_location,
        encoding="utf-8",
        maxBytes=int(10 * 1e6),  # 10 MB
        backupCount=2,
    )
    debug_file_handler.setFormatter(formatter)
    debug_file_handler.setLevel(logging.DEBUG)
    debug_file_handler.set_name("debug-file-handler")
    logger.addHandler(debug_file_handler)

    file_handler = FileHandler(
        filename=BotSettings.logging.log_location,
        mode="w",
        encoding="utf-8",
    )
    file_handler.setFormatter(
        ConditionalFormatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            "%Y-%m-%d %H:%M:%S",
        ),
    )
    file_handler.setLevel(logging.INFO)
    file_handler.set_name(USER_FACING_LOGGER)
    logger.addHandler(file_handler)

    logger.info("Loaded config file %s", BotSettings.config_file)


class Logger:
    """Logger object for classes."""

    def __init__(self, *, prepend_msg: str = "", append_msg: str = "") -> None:
        """Initialise the logger.

        Parameters
        ----------
        prepend_msg : str
            The message to prepend to the message.
        append_msg : str
            The message to append to the message.

        """
        self._logger = logging.getLogger(BotSettings.logging.logger_name)
        self._prepend = prepend_msg.strip()
        self._append = append_msg.strip()
        self._cog_name = f"[{self.__cog_name__}.Cog] " if hasattr(self, "__cog_name__") else ""  # type: ignore

    def _log_impl(self, level: int, msg: str, *args: Any, exc_info: bool = False) -> None:
        formatted_msg = msg % args
        stripped_msg = formatted_msg.strip()

        if self._prepend:
            stripped_msg = " " + stripped_msg
        if self._append:
            stripped_msg = stripped_msg + " "

        self._logger.log(
            level,
            "%s%s%s%s",
            self._cog_name,
            self._prepend,
            stripped_msg,
            self._append,
            exc_info=exc_info,
        )

    def log_exception(self, msg: str, *args: Any) -> None:
        """Log a exception message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        self._log_impl(logging.ERROR, msg, *args, exc_info=True)

    def log_debug(self, msg: str, *args: Any) -> None:
        """Log a debug message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        self._log_impl(logging.DEBUG, msg, *args)

    def log_error(self, msg: str, *args: Any) -> None:
        """Log an error message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        self._log_impl(logging.ERROR, msg, *args)

    def log_warning(self, msg: str, *args: Any) -> None:
        """Log a warning message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        self._log_impl(logging.WARNING, msg, *args)

    def log_info(self, msg: str, *args: Any) -> None:
        """Log an info message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        self._log_impl(logging.INFO, msg, *args)

    def set_log_level(self, level: int) -> None:
        """Set the logging output level.

        Parameters
        ----------
        level : int
            The logging output level.

        """
        for handler in self._logger.handlers:
            if handler.name != USER_FACING_LOGGER:
                handler.setLevel(level)

    @property
    def last_error(self) -> str:
        """Get the last error message.

        Returns
        -------
        str
            The last error message.

        """
        handler = next((x for x in self._logger.handlers if x.name == USER_FACING_LOGGER), None)
        if handler is None:
            msg = f"Unable to find `{USER_FACING_LOGGER}` in logger"
            raise ValueError(msg)
        if not isinstance(handler, logging.FileHandler):
            msg = f"The logging handler named `{USER_FACING_LOGGER}` is not a file handler"
            raise TypeError(msg)

        path = pathlib.Path(handler.baseFilename)

        with path.open(encoding="utf-8") as file_in:
            lines = file_in.readlines()

        latest_error = ""
        for line in reversed(lines):
            if "ERROR" in line:
                latest_error = line
                break

        return latest_error
