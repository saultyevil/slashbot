import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from slashbot.llm import LLM


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
class LLMInput:
    """Message dataclass for an LLM conversation."""

    text: TextInput
    images: ImageInput | list[ImageInput] = field(default_factory=list)
    videos: VideoInput | list[VideoInput] = field(default_factory=list)
    role: InputRole = InputRole.user

    tokens = 0

    def __str__(self) -> str:
        num_images = len(self.images) if self.images else 0
        num_videos = len(self.videos) if self.videos else 0
        return f"LLMInput(role={self.role} text={self.text} images={num_images} videos={num_videos})"

    def __post_init__(self) -> None:
        if isinstance(self.images, ImageInput):
            self.images = [self.images]
        if isinstance(self.videos, VideoInput):
            self.videos = [self.videos]
        if not self.text.text and (self.videos or self.images):
            self.text = TextInput("Please describe the following attached item(s)")

    def __add__(self, v: "LLMInput") -> "LLMInput":
        if self.role != v.role:
            error_message = "Cannot add LLMInputs with different roles"
            raise ValueError(error_message)

        return LLMInput(
            text=self.text + v.text,
            images=self.images + v.images,  # type: ignore
            videos=self.videos + v.videos,  # type: ignore
            role=self.role,
        )

    async def count_tokens(self, llm: "LLM") -> None:
        """Get the size of the input in tokens.

        Parameters
        ----------
        llm : LLM
            The LLM client to use to count tokens.

        """
        self.tokens = await llm.count_tokens(self)


@dataclass
class LLMResponse:
    """Response object for text generation."""

    message: str
    tokens_used: int
    input_tokens: int
    output_tokens: int


class LLMGenerationFailureError(Exception):
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
