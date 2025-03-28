import logging

from slashbot.settings import BotConfig


class Logger:
    """Logger object for classes."""

    def __init__(self) -> None:
        """Initialise the logger."""
        self.logger = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))

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
