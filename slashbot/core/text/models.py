from dataclasses import dataclass


@dataclass
class ContextMessage:
    """Message dataclass for an LLM conversation."""

    role: str
    text: str
    tokens: int
    images: list[str]


@dataclass
class VisionImage:
    """Dataclass for images for LLM vision."""

    url: str
    b64image: str | None = None
    mime_type: str | None = None


@dataclass
class TextGenerationResponse:
    """Response object for text generation."""

    message: str
    tokens_used: int
