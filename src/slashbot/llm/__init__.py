"""Core AI module for Slashbot."""

from .client import LLM
from .models import (
    ImageInput,
    InputRole,
    LLMGenerationFailureError,
    LLMInput,
    LLMResponse,
    TextInput,
    VideoInput,
)
from .prompts import Prompt, load_prompt

__all__ = [
    "LLM",
    "ImageInput",
    "InputRole",
    "LLMGenerationFailureError",
    "LLMInput",
    "LLMResponse",
    "Prompt",
    "TextInput",
    "VideoInput",
    "load_prompt",
]
