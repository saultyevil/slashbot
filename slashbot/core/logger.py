import logging
from logging.handlers import RotatingFileHandler
from typing import Any

from slashbot.settings import BotSettings


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
        self._cog_name = f"[{self.__cog_name__}.Cog] " if hasattr(self, "__cog_name__") else ""  # type: ignore  # noqa: PGH003

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
        self._logger.setLevel(level)


def setup_logging() -> None:
    """Set up log formatting.

    This sets up the logging for the bot's logic, and also the Disnake log.
    """
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger = logging.getLogger(BotSettings.logging.logger_name)
    logger.addHandler(console_handler)
    file_handler = RotatingFileHandler(
        filename=BotSettings.logging.log_location,
        encoding="utf-8",
        maxBytes=int(5e5),
        backupCount=5,
    )
    file_handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)8s : %(message)s (%(filename)s:%(lineno)d)",
            "%Y-%m-%d %H:%M:%S",
        ),
    )
    logger.addHandler(file_handler)

    logger = logging.getLogger("disnake")
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename="logs/disnake.log", encoding="utf-8", mode="w")
    handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
    logger.addHandler(handler)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.info("Loaded config file %s", BotSettings.config_file)


setup_logging()
