from typing import Any

import anthropic
from anthropic import Anthropic, AsyncAnthropic, Omit

from slashbot.llm.models import (
    GenerationFailureError,
    ImageInput,
    InputRole,
    TextGenerationInput,
    TextGenerationResponse,
    TextInput,
    VideoInput,
)
from slashbot.settings import BotSettings

from .abstract_client import AbstractClient


class ClaudeClient(AbstractClient):
    """Claude client for text generation."""

    ## class variables

    VISION_MODELS = ("claude-haiku-4-5", "claude-sonnet-5")
    SEARCH_MODELS = ()
    AUDIO_MODELS = ()
    VIDEO_MODELS = ()

    SUPPORTED_MODELS = ("claude-haiku-4-5", "claude-sonnet-5")

    ## magic methods

    def __init__(self, **kwargs: dict[str, Any]) -> None:
        """Initialise a Claude client with the given arguments."""
        super().__init__(**kwargs)

        self.provider = "anthropic"
        self._client = AsyncAnthropic(api_key=BotSettings.keys.claude)

    ## private member functions

    def _create_image_input_object(self, model: str, images: ImageInput | list[ImageInput]) -> dict | list[dict]:
        """Create a payload for an image request.

        Parameters
        ----------
        model : str
            The name of the model.
        images : VisionImage | list[VisionImage]
            The image(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload for image inputs.

        """
        if model not in self.VISION_MODELS:
            return []
        if not isinstance(images, list):
            images = [images]
        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": f"{image.mime_type}",
                    "data": f"{image.b64image}",
                },
            }
            for image in images
        ]

    def _create_text_input_object(self, text: TextInput) -> dict:
        """Create a payload for a text request.

        Parameters
        ----------
        text : str | list[str]
            The text messages(s) to format into a payload.

        Returns
        -------
        dict
            The correctly formatted payload for text input.

        """
        return {"type": "text", "text": text.text}

    def _construct_final_payload(
        self, role: InputRole, text_content: dict, image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict:
        """Create a payload for a payload, including text, images and videos.

        Parameters
        ----------
        role : InputRole
            The role of the input, e.g. user or assistant
        text_content : str | list[str]
            The text messages(s) to add to the payload.
        image_content : VisionImage | list[VisionImage]
            The image(s) to add to the payload.
        video_content : VisionVideo | list[VisionVideo]
            The videos(s) to add to the  payload.

        Returns
        -------
        dict
            The correctly formatted payload for all inputs.

        """
        return {"role": role.value, "content": [text_content, *image_content, *video_content]}

    def _create_video_input_object(self, model: str, videos: VideoInput | list[VideoInput]) -> dict | list[dict]:
        """Create a payload for a video request.

        Parameters
        ----------
        model : str
            The name of the model.
        videos : VisionVideo | list[VisionVideo]
            The videos(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload for video inputs.

        """
        if model not in self.VIDEO_MODELS:
            return []
        return []

    async def _send_request(
        self, model: str, content: dict | list[dict], system_prompt: str | None = None, inject_prompt: str | None = None
    ) -> TextGenerationResponse:
        """Send a request to the uderlying API client.

        Parameters
        ----------
        model : str
            The model to use.
        content : dict | list[dict]
            The payload to send to the API client.
        system_prompt : str | None
            The optional system prompt to use.
        inject_prompt : str | None
            Additional prompt to inject at the start of the system prompt. Usefull
            for custom chats and etc.


        Returns
        -------
        TextGenerationResponse
            The response returned from the API client.

        """
        parts = [p for p in (inject_prompt, system_prompt) if p]
        system = "\n\n".join(parts) if parts else Omit()

        self.log_debug("system_prompt '%s", system_prompt)
        self.log_debug("inject_prommpt '%s'", inject_prompt)
        self.log_debug("Using system prompt '%s'", system)

        try:
            response = await self._client.messages.create(
                model=model,
                messages=content,  # type: ignore
                max_tokens=BotSettings.cogs.chatbot.max_output_tokens,
                system=system,
            )
        except Exception as exc:
            error_message = f"Claude API failed to generate response due to exception: {exc}"
            self.log_error("%s", error_message)
            raise GenerationFailureError(error_message) from exc

        if not response.content:
            error_message = "A valid response was not generated by the Anthropic client."
            raise GenerationFailureError(error_message)

        text_response = next(
            (block for block in response.content if isinstance(block, anthropic.types.TextBlock)), None
        )
        if not text_response:
            error_message = "A text response was not generated"
            raise GenerationFailureError(error_message)

        return TextGenerationResponse(
            text_response.text,
            response.usage.input_tokens + response.usage.output_tokens,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

    ## public interface

    async def count_tokens(self, model: str, content: TextGenerationInput | list[TextGenerationInput]) -> int:
        """Get the token count for a given message for the current LLM model.

        The synchronous client must be used for token counting.

        Parameters
        ----------
        model : str
            The name of the model to generate a response with.
        content : TextGenerationInput | list[TextGenerationInput]
            The (correctly) formatted content to send to the API.

        Returns
        -------
        int
            The count of tokens in the given message for the current model.

        """
        client = Anthropic(api_key=self._client.api_key, base_url=self._client.base_url)
        response = client.messages.count_tokens(model=model, messages=self.transform_input_to_payload(model, content))  # type: ignore

        return response.input_tokens

    async def generate_response(
        self,
        model: str,
        content: TextGenerationInput | list[TextGenerationInput],
        system_prompt: str | None = None,
        inject_prompt: str | None = None,
    ) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        model : str
            The name of the model to generate a response with.
        content : TextGenerationInput | list[TextGenerationInput]
            The (correctly) formatted content to send to the API.
        system_prompt : str
            The system prompt to use to generate the response with.
        inject_prompt : str | None
            Additional prompt to inject at the start of the system prompt. Usefull
            for custom chats and etc.


        Returns
        -------
        TextGenerationResponse
            The response from the LLM.

        """
        text_generation_response = await self._send_request(
            model, self.transform_input_to_payload(model, content), system_prompt, inject_prompt
        )

        return text_generation_response
