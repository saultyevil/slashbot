from typing import Any

from slashbot.logger import Logger

from .clients import ClaudeClient
from .models import TextGenerationInput, TextGenerationResponse


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

        self.model = model
        self.system_prompt = system_prompt

        if model in ClaudeClient.SUPPORTED_MODELS:
            self._client = ClaudeClient(**kwargs)
        else:
            supported_models = ClaudeClient.SUPPORTED_MODELS
            error_message = f"Unknown model {model}. Supported models: {supported_models}"
            raise ValueError(error_message)

        self.provider = self._client.provider

    ## public interface

    async def assemble_input_payload(self, content: TextGenerationInput | list[TextGenerationInput]) -> dict | list:
        """Create a payload object for the LLM.

        Parameters
        ----------
        content : TextGenerationInput | list[TextGenerationInput]
            Input message(s), from the user, including attached images and
            videos.

        """
        payload = self._client.transform_input_to_payload(self.model, content)

        return payload

    async def count_tokens(self, content: TextGenerationInput | list[TextGenerationInput]) -> int:
        """Get the token count for a given message for the current LLM model.

        Parameters
        ----------
        content : TextGenerationInput | list[TextGenerationInput]
            The (correctly) formatted content to send to the API.

        Returns
        -------
        int
            The count of tokens in the given message for the current model.

        """
        total_tokens = await self._client.count_tokens(self.model, content)

        return total_tokens

    async def generate_response(
        self, content: TextGenerationInput | list[TextGenerationInput]
    ) -> TextGenerationResponse:
        """Genereate a response from the LLM for the provided input.

        Parameters
        ----------
        content : TextGenerationInput | list[TextGenerationInput]
            The (correctly) formatted content to send to the API.

        Returns
        -------
        TextGenerationResponse
            The response from the LLM.

        """
        response = await self._client.generate_response(self.model, content, self.system_prompt)

        return response
