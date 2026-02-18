"""Core AI module for Slashbot."""

from .chat import AIChat
from .models import GenerationFailureError, TextGenerationInput, TextGenerationResponse, VisionImage, VisionVideo
from .prompts import Prompt, read_in_prompt
from .summary import AIChatSummary, SummaryMessage
from .text_generator import TextGenerator

SUPPORTED_MODELS = TextGenerator.SUPPORTED_MODELS


__all__ = [
    "SUPPORTED_MODELS",
    "AIChat",
    "AIChatSummary",
    "GenerationFailureError",
    "Prompt",
    "SummaryMessage",
    "TextGenerationInput",
    "TextGenerationResponse",
    "TextGenerator",
    "VisionImage",
    "VisionVideo",
    "read_in_prompt",
]
