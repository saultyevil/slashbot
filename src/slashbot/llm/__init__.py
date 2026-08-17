"""Core AI module for Slashbot."""

from .client import LLM
from .models import (
    GenerationFailureError,
    ImageInput,
    TextGenerationInput,
    TextGenerationResponse,
    TextInput,
    VideoInput,
)
from .prompts import Prompt, read_in_prompt

__all__ = [
    "LLM",
    "GenerationFailureError",
    "ImageInput",
    "Prompt",
    "TextGenerationInput",
    "TextGenerationResponse",
    "TextInput",
    "VideoInput",
    "read_in_prompt",
]
