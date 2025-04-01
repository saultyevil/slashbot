import logging
from logging.handlers import RotatingFileHandler

from slashbot.settings import BotSettings


class Logger:
    """Logger object for classes."""

    def __init__(self) -> None:
        """Initialise the logger."""
        self.logger = logging.getLogger(BotSettings.logging.logger_name)

    def _get_extra_logging(self) -> str:
        return f"[Cog:{self.__cog_name__}] " if hasattr(self, "__cog_name__") else ""

    def log_debug(self, msg: str, *args: any) -> None:
        """Log a debug message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        extra = self._get_extra_logging()
        self.logger.debug("%s%s", extra, msg % args)

    def log_error(self, msg: str, *args: any) -> None:
        """Log an error message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        extra = self._get_extra_logging()
        self.logger.error("%s%s", extra, msg % args)

    def log_exception(self, msg: str, *args: any) -> None:
        """Log a exception message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        extra = self._get_extra_logging()
        self.logger.exception("%s%s", extra, msg % args)

    def log_info(self, msg: str, *args: any) -> None:
        """Log an info message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        extra = self._get_extra_logging()
        self.logger.info("%s%s", extra, msg % args)


def setup_logging() -> None:
    """Set up logging for Slashbot."""
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
    handler = logging.FileHandler(filename="logs/.disnake.log", encoding="utf-8", mode="w")
    handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
    logger.addHandler(handler)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.info("Loaded config file %s", BotSettings.config_file)


setup_logging()
