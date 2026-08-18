import base64
from dataclasses import dataclass
from enum import Enum

import httpx


class InputRole(Enum):
    """Enumerator for the possible roles in text generation."""

    user = "user"
    assistant = "assistant"


@dataclass
class TextInput:
    """Dataclass for text input."""

    text: str

    def __len__(self) -> int:
        return 1

    def __str__(self) -> str:
        return f"TextInput(text={self.text})"

    def __add__(self, v: "TextInput") -> "TextInput":
        return TextInput(self.text + v.text)


@dataclass
class ImageInput:
    """Dataclass for image input."""

    url: str
    b64image: str | None = None
    mime_type: str | None = None

    def __len__(self) -> int:
        return 1

    def __str__(self) -> str:
        return f"ImageInput(url={self.url} mime_type={self.mime_type} encoded={self.b64image is not None})"

    async def download_and_encode(self, *, httpx_timeout: int = 30) -> None:
        """Download the image and encode to a base64 string.

        Parameters
        ----------
        httpx_timeout : int
            The timeout for the HTTP request. Default is 60 seconds.

        """
        async with httpx.AsyncClient() as client:
            response = await client.get(self.url, timeout=httpx_timeout)
            response.raise_for_status()
        self.mime_type = response.headers["Content-Type"]
        self.b64image = base64.b64encode(response.content).decode("utf-8")


@dataclass
class VideoInput:
    """Dataclass for videos for LLM vision."""

    url: str
    b64video: str | None = None
    mime_type: str | None = None

    def __len__(self) -> int:
        return 1

    def __str__(self) -> str:
        return f"VideoInput(url={self.url} mime_type={self.mime_type} encoded={self.b64video is not None})"


@dataclass
class TextGenerationInput:
    """Message dataclass for an LLM conversation."""

    text: TextInput
    images: ImageInput | list[ImageInput] | None = None
    videos: VideoInput | list[VideoInput] | None = None
    role: InputRole = InputRole.user

    def __str__(self) -> str:
        num_images = len(self.images) if self.images else 0
        num_videos = len(self.videos) if self.videos else 0
        return f"TextGenerationInput(role={self.role} text={self.text} images={num_images} videos={num_videos})"

    def __post_init__(self) -> None:
        if self.images is None:
            self.images = []
        elif isinstance(self.images, ImageInput):
            self.images = [self.images]

        if self.videos is None:
            self.videos = []
        elif isinstance(self.videos, VideoInput):
            self.videos = [self.videos]

    def __add__(self, v: "TextGenerationInput") -> "TextGenerationInput":
        if self.role != v.role:
            error_message = "Cannot add TextGenerationInputs with different roles"
            raise ValueError(error_message)

        return TextGenerationInput(
            text=self.text + v.text,
            images=self.images + v.images,  # type: ignore
            videos=self.videos + v.videos,  # type: ignore
            role=self.role,
        )


@dataclass
class TextGenerationResponse:
    """Response object for text generation."""

    message: str
    tokens_used: int
    input_tokens: int
    output_tokens: int


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
