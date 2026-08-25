from typing import Any

from slashbot.logger import Logger

from .clients import AbstractClient, ClaudeClient
from .models import LLMInput, LLMResponse, TextInput


class LLM(Logger):
    """LLM generator class.

    Parameters
    ----------
    model : str
        The name of the LLM to use.
    system_prompt : str | None
        The system prompt to use for generation. Optional.
    inject_prompt : str | None
        Additional prompt to inject at the start of the system prompt. Usefull
        for custom chats and etc.

    """

    SUPPORTED_MODELS = ClaudeClient.SUPPORTED_MODELS

    def __init__(
        self, model: str, system_prompt: str | None = None, hidden_prompt: str | None = None, **kwargs: Any
    ) -> None:
        """Initialise an LLM for the given model."""
        super().__init__(**kwargs)

        self.model: str = model
        self.system_prompt: str | None = system_prompt
        self.hidden_prompt: str | None = hidden_prompt

        self.prompt_tokens: int | None = None

        if model in ClaudeClient.SUPPORTED_MODELS:
            self._client: AbstractClient = ClaudeClient(**kwargs)
        else:
            error_message = f"Unknown model {model}. Supported models: {self.SUPPORTED_MODELS}"
            raise ValueError(error_message)

        self.provider: str = self._client.provider

    ## private methods

    @property
    def _combined_system_prompt(self) -> str | None:
        parts = [p for p in (self.hidden_prompt, self.system_prompt) if p]
        return "\n\n".join(parts) if parts else None

    async def _count_tokens_in_prompt(self) -> None:
        if self.prompt_tokens is None and self._combined_system_prompt:
            self.prompt_tokens = await self.count_tokens(LLMInput(TextInput(self._combined_system_prompt)))

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
        total_tokens = await self._client.count_tokens(self.model, content)

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
        await self._count_tokens_in_prompt()
        response = await self._client.generate_response(self.model, content, self._combined_system_prompt)

        return response
