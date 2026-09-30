import contextlib
import time
from typing import Any

from slashbot.logger import Logger

from .clients import AbstractClient, ClaudeClient
from .models import LLMGenerationFailureError, LLMInput, LLMResponse, TextInput


class LLM(Logger):
    """LLM generator class.

    Parameters
    ----------
    model : str
        The name of the LLM to use.
    system_prompt : str | None
        The system prompt to use for generation. Optional.

    """

    SUPPORTED_MODELS = ClaudeClient.SUPPORTED_MODELS

    def __init__(self, model: str, system_prompt: str | None = None, **kwargs: Any) -> None:
        """Initialise an LLM for the given model."""
        super().__init__(**kwargs)

        self.model: str = model
        self.system_prompt: str | None = system_prompt

        self.prompt_tokens: int | None = None

        if model in ClaudeClient.SUPPORTED_MODELS:
            self._client: AbstractClient = ClaudeClient(**kwargs)
        else:
            error_message = f"Unknown model {model}. Supported models: {self.SUPPORTED_MODELS}"
            raise ValueError(error_message)

        self.provider: str = self._client.provider

    ## private methods

    async def _count_tokens_in_prompt(self) -> None:
        if self.prompt_tokens is None and self.system_prompt:
            self.prompt_tokens = await self.count_tokens(LLMInput(TextInput(self.system_prompt)))

    ## public interface

    async def assemble_input_payload(self, content: LLMInput | list[LLMInput]) -> dict | list:
        """Create a payload object for the LLM.

        Parameters
        ----------
        content : LLMInput | list[LLMInput]
            Input message(s), from the user, including attached images and
            videos.

        """
        payload = self._client.transform_input_to_payload(self.model, content)

        return payload

    async def count_tokens(self, content: LLMInput | list[LLMInput]) -> int:
        """Get the token count for a given message for the current LLM model.

        Parameters
        ----------
        content : LLMInput | list[LLMInput]
            The (correctly) formatted content to send to the API.

        Returns
        -------
        int
            The count of tokens in the given message for the current model.

        """
        started = time.perf_counter()
        total_tokens = await self._client.count_tokens(self.model, content)
        self.log_debug(
            "Counted tokens: model=%s tokens=%d duration=%.2fs",
            self.model,
            total_tokens,
            time.perf_counter() - started,
        )

        return total_tokens

    async def generate_response(self, content: LLMInput | list[LLMInput]) -> LLMResponse:
        """Genereate a response from the LLM for the provided input.

        Parameters
        ----------
        content : LLMInput | list[LLMInput]
            The (correctly) formatted content to send to the API.

        Returns
        -------
        LLMResponse
            The response from the LLM.

        """
        with contextlib.suppress(LLMGenerationFailureError):
            await self._count_tokens_in_prompt()

        started = time.perf_counter()
        response = await self._client.generate_response(self.model, content, self.system_prompt)
        self.log_debug("Generated response: model=%s duration=%.2fs", self.model, time.perf_counter() - started)

        return response
