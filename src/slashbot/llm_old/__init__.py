"""Core AI module for Slashbot."""

from .models import GenerationFailureError, TextGenerationInput, TextGenerationResponse, VisionImage, VisionVideo
from .prompts import Prompt, read_in_prompt
from .text_generator import TextGenerator

SUPPORTED_MODELS = TextGenerator.SUPPORTED_MODELS


__all__ = [
    "SUPPORTED_MODELS",
    "GenerationFailureError",
    "Prompt",
    "TextGenerationInput",
    "TextGenerationResponse",
    "TextGenerator",
    "VisionImage",
    "VisionVideo",
    "read_in_prompt",
]
