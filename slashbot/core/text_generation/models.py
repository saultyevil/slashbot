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


class GenerationFailureError(Exception):
    """Exception for generation failures."""

    def __init__(self, message: str, code: int = 0) -> None:
        """Initialize a GenerationFailureError.

        Parameters
        ----------
        message : str
            The error message describing the failure.
        code : int
            An optional error code. Defaults to 0.

        """
        super().__init__(message)
        self.code = code
