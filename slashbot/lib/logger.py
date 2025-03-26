import logging

from slashbot.lib.config import BotConfig


class Logger:
    """Logger object for classes."""

    def __init__(self) -> None:
        """Initialise the logger."""
        self.logger = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))

    def log_debug(self, msg: str, *args: any) -> None:
        """Log a debug message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        self.logger.debug("%s", msg % args)

    def log_error(self, msg: str, *args: any) -> None:
        """Log an error message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        self.logger.error("%s", msg % args)

    def log_exception(self, msg: str, *args: any) -> None:
        """Log a exception message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        self.logger.exception("%s", msg % args)

    def log_info(self, msg: str, *args: any) -> None:
        """Log an info message.

        Parameters
        ----------
        msg : str
            The message to log.
        args : any
            The arguments to pass to the message.

        """
        self.logger.info("%s", msg % args)
