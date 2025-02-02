import json
import logging
import os
import sys
from pathlib import Path

import aiofiles
import disnake
import git

from slashbot.config import Bot

logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))


async def get_logfile_tail(logfile_path: Path, num_lines: int) -> list[str]:
    """Get the last `num_lines` lines of the Slashbot logfile.

    Parameters
    ----------
    logfile_path : Path
        The path to the log file.
    num_lines : int
        The number of lines to retrieve.

    Returns
    -------
    list[str]
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
        if num_chars > Bot.get_config("MAX_CHARS"):
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
    logger.info("Restarting with new process with arguments %s", arguments)
    os.execv(sys.executable, ["python", *arguments])  # noqa: S606


def update_local_repository(branch: str) -> None:
    """Update the local git repository to `branch` and pull in changes.

    Parameters
    ----------
    branch : str
        The branch to switch to.

    """
    repo = git.Repo(".", search_parent_directories=True)
    if repo.active_branch != branch:
        branch = repo.branches[branch]
        branch.checkout()
    repo.remotes.origin.pull()


def _open_config_file() -> dict:
    with Path(Bot.get_config("CONFIG_FILE")).open(encoding="utf-8") as file_in:
        return json.load(file_in)


def _save_modified_config(updated_config: dict) -> None:
    with Path(Bot.get_config("CONFIG_FILE")).open("w", encoding="utf-8") as file_out:
        json.dump(file_out, updated_config, indent=4)


def _get_config_keys() -> list[str]:
    config = _open_config_file()
    keys = []

    def _iterate_dict(d: dict) -> None:
        for key, value in d.items():
            keys.append(key)
            if isinstance(value, dict):
                _iterate_dict(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        _iterate_dict(item)

    _iterate_dict(config)
    return keys


def config_key_autocomplete(_inter: disnake.ApplicationCommandInteraction, key: str) -> list[str]:
    return [k for k in _get_config_keys() if k.startswith(key)]


def set_config_value(key: str, value: str) -> None:
    config = _open_config_file()

    def _set_value(d: dict) -> None:
        for k, v in d.items():
            if k == key:
                old_value = d[k]
                d[k] = value
                return old_value
            if isinstance(v, dict):
                _set_value(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        _set_value(item)

        msg = f"Key {key} not found in config file"
        raise KeyError(msg)

    _set_value(config)
    _save_modified_config(config)
