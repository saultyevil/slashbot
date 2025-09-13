import os
import shutil

import git

from slashbot.core.logger import Logger

logger = Logger()


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
