"""Various utility functions used through slashbot."""

import json
import pathlib


def read_in_prompt_json(filepath: str | pathlib.Path) -> dict:
    """Read in a prompt and check for keys."""
    required_keys = (
        "name",
        "prompt",
    )

    with pathlib.Path(filepath).open(encoding="utf-8") as prompt_in:
        prompt = json.load(prompt_in)
        if not all(key in prompt for key in required_keys):
            msg = f"{filepath} is missing either 'name' or 'prompt' key"
            raise OSError(msg)

    return prompt


def create_prompt_dict() -> dict:
    """Create a dict of prompt_name: prompt."""
    return {
        prompt_dict["name"]: prompt_dict["prompt"]
        for prompt_dict in [
            read_in_prompt_json(file)
            for file in pathlib.Path("data/prompts").glob("*.json")
            if not file.name.startswith("_")  # prompts which start with _ are hidden prompts
        ]
    }
