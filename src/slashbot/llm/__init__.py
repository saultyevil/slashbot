"""Core AI module for Slashbot."""

from .client import LLM
from .models import (
    GenerationFailureError,
    ImageInput,
    InputRole,
    TextGenerationInput,
    TextGenerationResponse,
    TextInput,
    VideoInput,
)
from .prompts import Prompt, load_prompt

__all__ = [
    "LLM",
    "GenerationFailureError",
    "ImageInput",
    "InputRole",
    "Prompt",
    "TextGenerationInput",
    "TextGenerationResponse",
    "TextInput",
    "VideoInput",
    "load_prompt",
]
