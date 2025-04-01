from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import openai
import tiktoken

from slashbot.core.logger import Logger
from slashbot.settings import BotConfig


@dataclass
class TextGenerationResponse:
    """Response object for text generation."""

    message: str
    tokens_used: int


class TextGeneratorLLM(Logger):
    """Base class for text generation using LLMs."""

    OPENAI_LOW_DETAIL_IMAGE_TOKENS = 85
    SUPPORTED_OPENAI_MODELS = (
        "gpt-3.5-turbo",
        "gpt-4o-mini",
        "gpt-4o-mini-search-preview",
        "gpt-4o-mini-audio-preview",
        "o1-mini",
        "o3-mini",
    )
    SUPPORTED_CLAUDE_MODELS = ()
    SUPPORTED_GOOGLE_MODELS = ()
    SUPPORTED_MODELS = SUPPORTED_OPENAI_MODELS + SUPPORTED_CLAUDE_MODELS + SUPPORTED_GOOGLE_MODELS
    VISION_MODELS = ("gpt-4o-mini",)
    SEARCH_MODELS = ("gpt-4o-mini-search-preview",)
    AUDIO_MODELS = ("gpt-4o-mini-audio-preview",)

    def __init__(self, *, extra_print: str = "") -> None:
        """Initialise a TextGeneratorLLM with default values.

        Parameters
        ----------
        extra_print : str, optional
            Additional information to print at the start of the log message.

        """
        super().__init__()
        self._model_name = "gpt-4o-mini"
        self._client = None
        self._base_url = None
        self._text_generator = None
        self._extra_print = extra_print

    def _init_for_model(self, model: str) -> None:
        if model not in self.SUPPORTED_MODELS:
            msg = f"Model {model} is not supported."
            raise ValueError(msg)

        self._model_name = model
        self._base_url = self._get_base_url_for_model(model)
        self._client = self._get_client()
        self._text_generator = self._get_generator_function()
        self.log_info("%sModel set to %s with base url %s", self._extra_print, self._model_name, self._base_url)

    def _get_base_url_for_model(self, model: str) -> str:
        if model in TextGeneratorLLM.SUPPORTED_OPENAI_MODELS:
            return "https://api.openai.com/v1"

        msg = f"Model {model} is not supported."
        raise ValueError(msg)

    def _get_client(self) -> openai.AsyncClient:
        if self._client:
            return self._client
        api_key = BotConfig.get_config("OPENAI_API_KEY")

        return openai.AsyncOpenAI(api_key=api_key, base_url=self._base_url)

    def _get_generator_function(self) -> Callable[..., Any]:
        return self._client.chat.completions.create

    # --------------------------------------------------------------------------

    @property
    def model(self) -> str:
        """The name of the model."""
        return self._model_name

    # --------------------------------------------------------------------------

    def count_tokens_for_message(self, message: list[str] | str) -> int:
        """Get the token count for a given message for the current LLM model.

        Parameters
        ----------
        message : list[str] | str
            The message for which the token count needs to be computed.

        Returns
        -------
        int
            The count of tokens in the given message for the current model.

        """
        try:
            encoding = tiktoken.encoding_for_model(self._model_name)
        except KeyError:
            encoding = tiktoken.get_encoding("o200k_base")  # Fallback to this base

        if isinstance(message, list):
            num_tokens = 0
            # Handle case where there are images and messages. Images are a fixed
            # cost of something like 85 tokens so we don't need to encode those
            # using tiktoken.
            for content in message:
                if content["type"] == "text":
                    num_tokens += len(encoding.encode(content["text"]))
                else:
                    num_tokens += (
                        TextGeneratorLLM.OPENAI_LOW_DETAIL_IMAGE_TOKENS if content["type"] == "image_url" else 0
                    )
        elif isinstance(message, str):
            num_tokens = len(encoding.encode(message))
        else:
            msg = f"Expected a string or list of strings for encoding, got {type(message)}"
            raise TypeError(msg)

        return num_tokens

    def set_model(self, model: str) -> None:
        """Set the current LLM model.

        Parameters
        ----------
        model : str
            The name of the model to use.

        """
        self._init_for_model(model)

    async def generate_text_from_llm(self, messages: list[dict]) -> TextGenerationResponse:
        """Generate text from the current LLM model.

        Parameters
        ----------
        messages: list[dict]
            A list of messages to provide to the LLM, in the format similar to
            the following:
                [
                    {"role": "user", "content": "Hello world"},
                ]

        """
        if not self._client:
            self._init_for_model(self._model_name)

        # TODO(EP): handle and/or raise custom exception on failure
        response = await self._text_generator(
            messages=messages,
            model=self._model_name,
            max_completion_tokens=2048,  # TODO(EP): Make this configurable
        )
        message = response.choices[0].message.content
        token_usage = response.usage.total_tokens
        return TextGenerationResponse(message, token_usage)
