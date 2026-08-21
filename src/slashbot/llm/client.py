from typing import Any

from slashbot.logger import Logger

from .clients import ClaudeClient
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
        self, model: str, system_prompt: str | None = None, inject_prompt: str | None = None, **kwargs: Any
    ) -> None:
        """Initialise an LLM for the given model."""
        super().__init__(**kwargs)

        self.model = model
        self.system_prompt = system_prompt
        self.inject_prompt = inject_prompt

        self.prompt_tokens = 0

        if model in ClaudeClient.SUPPORTED_MODELS:
            self._client = ClaudeClient(**kwargs)
        else:
            supported_models = ClaudeClient.SUPPORTED_MODELS
            error_message = f"Unknown model {model}. Supported models: {supported_models}"
            raise ValueError(error_message)

        self.provider = self._client.provider

    ## private methods

    async def _count_tokens_in_prompt(self) -> None:
        if self.prompt_tokens == 0 and (self.system_prompt or self.inject_prompt):
            prompt_parts = [p for p in (self.inject_prompt, self.system_prompt) if p]
            if prompt_parts:
                self.prompt_tokens = await self.count_tokens(LLMInput(TextInput("\n\n".join(prompt_parts))))

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
        response = await self._client.generate_response(self.model, content, self.system_prompt, self.inject_prompt)

        return response
