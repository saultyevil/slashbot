import json
import logging
import os
import shutil
from pathlib import Path

import aiofiles
import git
from lib.config import BotConfig

logger = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))


def _open_config_file() -> dict:
    """Open the config file and return its contents.

    Returns
    -------
    dict
        The contents of the config file.

    """
    with Path(BotConfig.get_config("CONFIG_FILE")).open(encoding="utf-8") as file_in:
        return json.load(file_in)


def _save_modified_config(updated_config: dict) -> None:
    """Save the updated config file.

    Parameters
    ----------
    updated_config : dict
        The updated config file.

    """
    file = Path(BotConfig.get_config("CONFIG_FILE"))
    shutil.copy(file, file.with_suffix(".bak"))
    try:
        with file.open("w", encoding="utf-8") as file_out:
            json.dump(updated_config, file_out, indent=4)
    except:
        shutil.move(file.with_suffix(".bak"), file)
        raise


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
        if num_chars > BotConfig.get_config("MAX_CHARS"):
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
        logger.error("Could not find the poetry executable")
        return
    command = [poetry_executable, "run", *arguments]
    logger.info("Restarting with command %s", command)
    os.execv(command[0], command)  # noqa: S606


def get_modifiable_config_keys() -> tuple[str]:
    """Get the keys that can be modified for the config file.

    Returns
    -------
    tuple[str]
        A list of the keys that can be modified.

    """
    return (
        "TOKEN_WINDOW_SIZE",
        "MAX_OUTPUT_TOKENS",
        "MODEL_TEMPERATURE",
        "MODEL_TOP_P",
        "MODEL_FREQUENCY_PENALTY",
        "MODEL_PRESENCE_PENALTY",
        "CHAT_MODEL",
        "API_BASE_URL",
        "RANDOM_RESPONSE_CHANCE",
        "ENABLE_PROFILING",
        "USE_HISTORIC_REPLIES",
        "PREFER_IMAGE_URLS",
        "PROMPT_PREPEND",
        "PROMPT_APPEND",
    )


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


def set_config_value(key: str, value: str) -> None:  # noqa: C901
    """Set the value of a config key.

    Parameters
    ----------
    key : str
        The key to set.
    value : str
        The value to set.

    Returns
    -------
    str | None
        The old value of the key, or None if the key was not found.

    """
    config = _open_config_file()

    def _set_value(d: dict) -> str | None:
        for k, v in d.items():
            if k == key:
                old_value = d[k]
                d[k] = value
                return old_value
            if isinstance(v, dict):
                result = _set_value(v)
                if result is not None:
                    return result
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        result = _set_value(item)
                        if result is not None:
                            return result
        return None

    old_value = _set_value(config)
    if old_value is None:
        msg = f"Key {key} not found in config file"
        raise KeyError(msg)
    _save_modified_config(config)

    return old_value
