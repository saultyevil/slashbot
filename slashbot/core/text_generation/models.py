from dataclasses import dataclass


@dataclass
class VisionImage:
    """Dataclass for images for LLM vision."""

    url: str
    b64image: str | None = None
    mime_type: str | None = None


@dataclass
class VisionVideo:
    """Dataclass for videos for LLM vision."""

    url: str
    b64video: str | None = None
    mime_type: str | None = None


@dataclass
class TextGenerationInput:
    """Message dataclass for an LLM conversation."""

    text: str
    images: VisionImage | list[VisionImage] | None = None
    videos: VisionVideo | list[VisionVideo] | None = None
    role: str = "user"


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
