import base64
import re
import time
from typing import Any

from google import genai
from google.genai import types

from slashbot.llm.models import (
    ImageInput,
    InputRole,
    LLMGenerationFailureError,
    LLMInput,
    LLMResponse,
    TextInput,
    VideoInput,
)
from slashbot.settings import BotSettings

from .abstract_client import AbstractClient


class GeminiClient(AbstractClient):
    """Gemini client for text generation."""

    ## class variables

    VISION_MODELS = ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite")
    SEARCH_MODELS = VISION_MODELS
    AUDIO_MODELS = ()
    VIDEO_MODELS = VISION_MODELS

    YOUTUBE_URL_RE = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/", re.IGNORECASE)

    SUPPORTED_MODELS = VISION_MODELS

    # Lowest thinking level each model supports; 3.8 Flash has no "minimal"
    THINKING_LEVELS = {
        "gemini-3.8-flash": "low",
        "gemini-3.6-flash": "minimal",
        "gemini-3.5-flash-lite": "minimal",
    }

    ## magic methods

    def __init__(self, **kwargs: dict[str, Any]) -> None:
        """Initialise a Gemini client with the given arguments."""
        super().__init__(**kwargs)

        self.provider = "google"
        self._client = genai.Client(api_key=BotSettings.keys.gemini)

    ## private member functions

    def _create_image_input_object(self, model: str, images: ImageInput | list[ImageInput]) -> dict | list[dict]:
        """Create a payload for an image request.

        Parameters
        ----------
        model : str
            The name of the model.
        images : ImageInput | list[ImageInput]
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
            {"inline_data": {"mime_type": image.mime_type, "data": base64.b64decode(image.b64image)}}
            for image in images
            if image.b64image
        ]

    def _create_text_input_object(self, text: TextInput) -> dict:
        """Create a payload for a text request.

        Parameters
        ----------
        text : TextInput
            The text message to format into a payload.

        Returns
        -------
        dict
            The correctly formatted payload for text input.

        """
        return {"text": text.text}

    def _construct_final_payload(
        self, role: InputRole, text_content: dict, image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict:
        """Create a payload, including text, images and videos.

        Parameters
        ----------
        role : InputRole
            The role of the input, e.g. user or assistant
        text_content : dict
            The text message to add to the payload.
        image_content : dict | list[dict]
            The image(s) to add to the payload.
        video_content : dict | list[dict]
            The videos(s) to add to the payload.

        Returns
        -------
        dict
            The correctly formatted payload for all inputs.

        """
        # Gemini calls the assistant role "model"
        gemini_role = "model" if role == InputRole.assistant else "user"
        return {"role": gemini_role, "parts": [text_content, *image_content, *video_content]}

    def _create_video_input_object(self, model: str, videos: VideoInput | list[VideoInput]) -> dict | list[dict]:
        """Create a payload for a video request.

        Parameters
        ----------
        model : str
            The name of the model.
        videos : VideoInput | list[VideoInput]
            The videos(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload for video inputs.

        """
        if model not in self.VIDEO_MODELS:
            return []
        if not isinstance(videos, list):
            videos = [videos]
        # Gemini fetches public YouTube videos itself, so only the URL is sent
        return [{"file_data": {"file_uri": video.url}} for video in videos if self.YOUTUBE_URL_RE.match(video.url)]

    async def _send_request(
        self,
        model: str,
        content: dict | list[dict],
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Send a request to the underlying API client.

        Parameters
        ----------
        model : str
            The model to use.
        content : dict | list[dict]
            The payload to send to the API client.
        system_prompt : str | None
            The optional system prompt to use.

        Returns
        -------
        LLMResponse
            The response returned from the API client.

        """
        request_started = time.perf_counter()
        content_count = len(content) if isinstance(content, list) else 1
        self.log_debug("Sending Gemini request: model=%s messages=%d", model, content_count)

        use_search = BotSettings.cogs.chatbot.enable_web_search and model in self.SEARCH_MODELS

        try:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=content,  # type: ignore
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt if system_prompt else None,
                    max_output_tokens=BotSettings.cogs.chatbot.max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_level=self.THINKING_LEVELS[model]),  # type: ignore
                    tools=[types.Tool(google_search=types.GoogleSearch())] if use_search else None,
                ),
            )
        except Exception as exc:
            error_message = f"Gemini API failed to generate response due to exception: {exc}"
            self.log_exception("%s", error_message)
            raise LLMGenerationFailureError(error_message) from exc

        if not response.candidates:
            error_message = "A valid response was not generated by the Gemini client."
            self.log_warning("Gemini returned no candidates for model %s", model)
            raise LLMGenerationFailureError(error_message)

        text_response = response.text
        if not text_response:
            error_message = "A text response was not generated"
            self.log_warning("Gemini returned no text content for model %s", model)
            raise LLMGenerationFailureError(error_message)

        metadata = response.candidates[0].grounding_metadata
        if metadata and metadata.web_search_queries:
            self.log_debug("Gemini searched the web: queries=%s", metadata.web_search_queries)

        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count or 0) if usage else 0
        output_tokens = (usage.candidates_token_count or 0) if usage else 0

        self.log_info(
            "Gemini request completed: model=%s duration=%.2fs input_tokens=%d output_tokens=%d",
            model,
            time.perf_counter() - request_started,
            input_tokens,
            output_tokens,
        )

        return LLMResponse(
            message=text_response,
            tokens_used=input_tokens + output_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            _original_response=response,
        )

    ## public interface

    async def count_tokens(self, model: str, content: LLMInput | list[LLMInput]) -> int:
        """Get the token count for a given message for the current LLM model.

        Parameters
        ----------
        model : str
            The name of the model to count tokens with.
        content : LLMInput | list[LLMInput]
            The content to count tokens for.

        Returns
        -------
        int
            The count of tokens in the given message for the current model.

        """
        try:
            response = await self._client.aio.models.count_tokens(
                model=model,
                contents=self.transform_input_to_payload(model, content),  # type: ignore
            )
        except Exception as exc:
            error_message = f"Gemini API failed to count tokens due to exception: {exc}"
            self.log_exception("%s", error_message)
            raise LLMGenerationFailureError(error_message) from exc

        total_tokens = response.total_tokens or 0
        self.log_debug("Counted Gemini input tokens: model=%s tokens=%d", model, total_tokens)
        return total_tokens

    async def generate_response(
        self,
        model: str,
        content: LLMInput | list[LLMInput],
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Send a request to the API client.

        Parameters
        ----------
        model : str
            The name of the model to generate a response with.
        content : LLMInput | list[LLMInput]
            The content to send to the API.
        system_prompt : str | None
            The system prompt to use to generate the response with.

        Returns
        -------
        LLMResponse
            The response from the LLM.

        """
        return await self._send_request(model, self.transform_input_to_payload(model, content), system_prompt)
