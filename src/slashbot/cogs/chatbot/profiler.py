import functools
import logging
from collections.abc import Callable
from typing import Any

from pyinstrument import Profiler

from slashbot.settings import BotSettings

file_handler = logging.FileHandler("logs/profile.log")
file_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
_profiler_logger = logging.getLogger("ProfilerLogger")
_profiler_logger.handlers.clear()
_profiler_logger.addHandler(file_handler)
_profiler_logger.setLevel(logging.INFO)


_MIN_LOGGED_DURATION_SECONDS = 0.05


def profile(func: Callable) -> Callable:
    """Profile function execution using pyinstrument.

    Creates a fresh Profiler instance for each call, so overlapping or
    concurrent invocations of the decorated function do not interfere
    with one another. Has no effect when
    BotSettings.cogs.chatbot.enable_profiling is False.
    """

    @functools.wraps(func)
    async def _profile(*args: Any, **kwargs: dict[str, Any]) -> Any:
        if not BotSettings.cogs.chatbot.enable_profiling:
            return await func(*args, **kwargs)

        profiler = Profiler(async_mode="enabled")
        profiler.start()
        try:
            return await func(*args, **kwargs)
        finally:
            profiler.stop()
            if profiler.last_session and profiler.last_session.duration >= _MIN_LOGGED_DURATION_SECONDS:
                _profiler_logger.info("\n%s", profiler.output_text())

    return _profile
