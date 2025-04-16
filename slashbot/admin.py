import os
import shutil
from pathlib import Path

import aiofiles
import git

from slashbot.core.logger import Logger
from slashbot.settings import BotSettings

logger = Logger()


async def get_logfile_tail(logfile_path: Path, num_lines: int) -> str:
    """Get the last `num_lines` lines of the Slashbot logfile.

    Parameters
    ----------
    logfile_path : Path
        The path to the log file.
    num_lines : int
        The number of lines to retrieve.

    Returns
    -------
    str
        The last `num_lines` lines of the log file.

    """
    async with aiofiles.open(logfile_path, encoding="utf-8") as file_in:
        log_file = await file_in.read()
    log_lines = log_file.splitlines()

    tail = []
    num_chars = 0
    for i in range(1, num_lines + 1):
        try:
            num_chars += len(log_lines[-i])
        except IndexError:
            break
        if num_chars > BotSettings.discord.max_chars:
            break
        tail.append(log_lines[-i])

    return "\n".join(tail[::-1])


def restart_bot(arguments: list[str]) -> None:
    """Restart the current process with the given arguments.

    Parameters
    ----------
    arguments : list[str]
        Additional arguments to pass to the new process.

    """
    poetry_executable = shutil.which("poetry")
    if poetry_executable is None:
        logger.log_error("Could not find the poetry executable")
        return
    command = [poetry_executable, "run", *arguments]
    logger.log_info("Restarting with command %s", command)
    os.execv(command[0], command)  # noqa: S606


def update_local_repository(branch: str) -> None:
    """Update the local git repository to `branch` and pull in changes.

    Parameters
    ----------
    branch : str
        The branch to switch to.

    """
    repo = git.Repo(".", search_parent_directories=True)
    if repo.active_branch != branch:
        target_branch = repo.heads[branch]
        target_branch.checkout()
    repo.remotes.origin.pull()
