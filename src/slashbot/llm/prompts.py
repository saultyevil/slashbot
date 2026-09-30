import pathlib
from textwrap import dedent

import yaml
from pydantic import BaseModel, model_validator

from slashbot.logger import Logger

LOGGER = Logger(prepend_msg="[Prompts]")


class Prompt(BaseModel):
    """Dataclass for prompt input validation using Pydantic."""

    name: str
    prompt: str
    path: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _format_prompt(cls, values: dict) -> dict:
        """Clean up the prompt string, removing newlines and indentation.

        Parameters
        ----------
        values : dict
            The dictionary of values to validate.

        """
        prompt = values.get("prompt", "")
        if not prompt:
            return values
        values["prompt"] = " ".join(dedent(prompt).splitlines()).strip()
        return values


def load_prompt(filepath: str | pathlib.Path) -> Prompt:
    """Read in a prompt from a YAML file.

    Parameters
    ----------
    filepath : str | pathlib.Path
        The path to the prompt file.

    Returns
    -------
    Prompt
        A Prompt object containing the name and prompt string.

    """
    path = pathlib.Path(filepath)
    if not path.is_file():
        msg = f"Prompt file {filepath} does not exist."
        LOGGER.log_error("Prompt file missing: %s", filepath)
        raise OSError(msg)

    try:
        with path.open(encoding="utf-8") as prompt_in:
            prompt_data = yaml.safe_load(prompt_in)
        prompt = Prompt(**prompt_data, path=str(filepath))
    except Exception:
        LOGGER.log_exception("Failed to load prompt file %s", filepath)
        raise

    LOGGER.log_debug("Loaded prompt: %s", filepath)
    return prompt
