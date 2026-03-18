from typing import Any

import httpx

from slashbot.ai.clients.abstract_client import TextGenerationAbstractClient
from slashbot.ai.models import (
    GenerationFailureError,
    TextGenerationInput,
    TextGenerationResponse,
    VisionImage,
    VisionVideo,
)
from slashbot.settings import BotSettings


class GeminiClient(TextGenerationAbstractClient):
    """Asynchronous Gemini client."""

    SUPPORTED_MODELS = (
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    )
    # All the models support each of these inputs :)
    VISION_MODELS = SUPPORTED_MODELS
    SEARCH_MODELS = SUPPORTED_MODELS
    AUDIO_MODELS = SUPPORTED_MODELS
    VIDEO_MODELS = SUPPORTED_MODELS
    GOOGLE_MAPS_MODELS = SUPPORTED_MODELS

    # --------------------------------------------------------------------------

    def __init__(self, model_name: str, **kwargs: Any) -> None:
        """Initialise the Gemini client.

        Parameters
        ----------
        model_name : str
            The name of the model to use.
        kwargs : dict
            Additional keyword arguments to pass to the parent class.

        """
        self._count_tokens_url = ""
        super().__init__(model_name, **kwargs)

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return len(self._model_context["contents"])

    # --------------------------------------------------------------------------

    @property
    def _model_context_message_content(self) -> list[dict]:
        return self._model_context["contents"]

    @property
    def client_type(self) -> str:
        """Get the model type."""
        return "gemini"

    # --------------------------------------------------------------------------

    def _check_context_contains_images(self, contents: dict | list[dict]) -> bool:
        """Check if an image is present in the client's content.

        Parameters
        ----------
        contents : dict
            An individual message object which has been passed to LLM, e.g.
            {"role": "user", "content": [{"type": "text", "text": "hello"}]}

        Returns
        -------
        bool
            If an image, returns True. Otherwise, returns False.

        """
        if isinstance(contents, list):
            msg = f"Invalid data type {type(contents)} for contents"
            raise TypeError(msg)
        return any("inline_data" in part for part in contents.get("parts", []))

    def _content_contains_youtube_video_type(self, content: dict) -> bool:
        """Check if a youtube link or video is present in the client's content.

        Parameters
        ----------
        content : dict
            An individual message object which has been passed to LLM, e.g.
            {"role": "user", "content": [{"type": "text", "text": "hello"}]}

        Returns
        -------
        bool
            If there is a youtube link returns True. Otherwise, returns False.

        """
        for part in content.get("parts", []):
            if "file_data" in part:
                uri = part["file_data"].get("file_uri", "")
                return "youtube.com" in uri or "youtu.be" in uri
        return False

    def _add_to_model_context(self, new_content: dict) -> None:
        """Add new contents to the model context.

        This has various pre-processing steps for adding new messages, such as
        making sure there is only a certain number of images in the model
        context as too many images slows responses.

        Note that this method extends the method in the abstract client as we
        have to deal with YouTube videos as well. This is done first, then we
        call the super method.

        Parameters
        ----------
        new_content : dict
            The new content to add to the model context.

        """
        self.log_debug("Adding %s to model context", new_content)

        # Remove any existing YouTube links from the context for the same reason
        i = 0
        while i < len(self):
            content = self._model_context["contents"][i]
            if self._content_contains_youtube_video_type(content):
                self._remove_message_from_model_context(i)
            i += 1

        super()._add_to_model_context(new_content)

    def _create_assistant_response_object(self, message: str) -> dict:
        """Create a payload for the response from the LLM.

        Parameters
        ----------
        message : str
            The response message from the LLM.

        Returns
        -------
        dict
            The correctly formatted payload.

        """
        return {"role": "model", "parts": [{"text": message}]}

    def _create_image_input_object(self, images: VisionImage | list[VisionImage]) -> dict | list[dict]:
        """Create a payload for an image request.

        Parameters
        ----------
        images : VisionImage | list[VisionImage]
            The image(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """
        if self.model_name not in self.VISION_MODELS:
            return []
        if not isinstance(images, list):
            images = [images]

        return [
            {
                "inline_data": {
                    "mime_type": image.mime_type,
                    "data": image.b64image,
                }
            }
            for image in images
        ]

    def _create_text_input_object(self, text: str | list[str]) -> dict | list[dict]:
        """Create a payload for a text request.

        Parameters
        ----------
        text : str | list[str]
            The text messages(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """
        return {"text": text}

    def _create_user_input_object(
        self, text_content: dict | list[dict], image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict:
        """Create a payload for a payload, including text, images and videos.

        Parameters
        ----------
        text_content : str | list[str]
            The text messages(s) to add to the payload.
        image_content : VisionImage | list[VisionImage]
            The image(s) to add to the payload.
        video_content : VisionVideo | list[VisionVideo]
            The videos(s) to add to the  payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """
        return {"role": "user", "parts": [*video_content, *image_content, *text_content]}

    def _create_video_input_object(self, videos: VisionVideo | list[VisionVideo]) -> dict | list[dict]:
        """Create a payload for a video request.

        Parameters
        ----------
        videos : VisionVideo | list[VisionVideo]
            The videos(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """
        if self.model_name not in self.VIDEO_MODELS:
            return []
        if not isinstance(videos, list):
            videos = [videos]
        return [
            {
                "file_data": {
                    "file_uri": video.url,
                }
            }
            for video in videos
        ]

    # --------------------------------------------------------------------------

    def count_tokens(self, messages: dict | list[dict[str, str]] | str) -> int:
        """Count the number of tokens in a message.

        Parameters
        ----------
        messages : dict | list[dict[str, str]] | str
            The message to count the number of tokens. Formatted either as a
            request, or as a str or list of strings.

        """
        if not self._count_tokens_url:
            self.init_client(self.model_name)
        if isinstance(messages, str):
            messages = {"contents": [{"parts": [{"text": messages}]}]}

        with httpx.Client(timeout=self._async_timeout) as client:
            response = client.post(
                url=self._count_tokens_url,
                json=messages,
                headers={"Content-Type": "application/json"},
            )

        if response.status_code != httpx.codes.OK:
            status_code = response.status_code
            self.log_error("Request for Gemini countTokens failed. Request content: %s", messages)
            msg = f"Gemini API request failed with {response.json()['error']['message']}"
            raise GenerationFailureError(msg, code=status_code)

        response_json = response.json()

        if "totalTokens" not in response_json:
            msg = f"totalTokens not in response from countToken API: {response_json}"
            raise GenerationFailureError(msg, code=response.status_code)

        return response_json["totalTokens"]

    def create_content_payload_object(
        self, messages: TextGenerationInput | list[TextGenerationInput], *, system_prompt: str | None = None
    ) -> dict | list:
        """Create a request JSON for the current LLM model.

        Parameters
        ----------
        messages : ContextMessage | list[ContextMessage]
            Input message(s), from the user, including attached images and
            videos.
        system_prompt : str | None
            The system prompt to use. If None, the current system prompt is
            used.

        """
        content = super().create_content_payload_object(messages)
        self.log_debug("Gemini content payload before adding prompt and tools: %s", content)

        request = {
            "contents": content,
        }
        if system_prompt:
            request["system_instruction"] = {  # type: ignore
                "parts": [
                    {
                        "text": system_prompt,
                    },
                ],
            }

        if BotSettings.cogs.chatbot.enable_web_search and self.model_name in self.SEARCH_MODELS:
            request["tools"] = {  # type:ignore
                "google_search": {},
            }
            if self.model_name in self.GOOGLE_MAPS_MODELS:
                request["tools"]["googleMaps"] = {}

        self.log_debug("Final request for Gemini: %s", request)

        return request

    async def generate_response_with_context(
        self, messages: TextGenerationInput | list[TextGenerationInput]
    ) -> TextGenerationResponse:
        """Generate a text response, given new text input and previous context.

        Parameters
        ----------
        messages : ContextMessage | list[ContextMessage]
            Input message(s), from the user, including attached images and
            videos.

        """
        if not self._base_url:
            self.init_client(self.model_name)

        self._shrink_model_context_to_window_size()

        user_contents = self._create_content_payload(messages)
        if not isinstance(user_contents, dict):
            msg = f"Incorrect content payload created for Gemini, should be a dict: {user_contents}"
            raise TypeError(msg)
        self._add_to_model_context(user_contents)

        response = await self.generate_response(self._model_context)
        if not response.message:
            msg = "A valid response was not generated by the Gemini API."
            raise ValueError(msg)

        self._add_to_model_context(self._create_assistant_response_object(response.message))
        self.token_size = response.tokens_used

        return response

    def init_client(self, model_name: str) -> None:
        """Initialise the client to use a model.

        Parameters
        ----------
        model_name : str
            The name of the model to initialise the client for.

        """
        gen_ai_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.model_name = model_name
        self._base_url = f"{gen_ai_url}/{model_name}:generateContent?key={BotSettings.keys.gemini}"
        self._count_tokens_url = f"{gen_ai_url}/{model_name}:countTokens?key={BotSettings.keys.gemini}"
        self._model_context = {
            "system_instruction": {
                "parts": [
                    {
                        "text": self.system_prompt,
                    }
                ]
            },
            "contents": [],
            "generationConfig": {
                "temperature": str(BotSettings.cogs.chatbot.model_temperature),
            },
        }

        if BotSettings.cogs.chatbot.enable_web_search and self.model_name in self.SEARCH_MODELS:
            self._model_context["tools"] = {  # type:ignore
                "google_search": {},
            }
            if self.model_name in self.GOOGLE_MAPS_MODELS:
                self._model_context["tools"]["googleMaps"] = {}

        self._setup_response_logger(model_name)

    async def generate_response(self, content: list[dict] | dict) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict]
            The (correctly) formatted content to send to the API.

        """
        if not self._base_url:
            self.init_client(self.model_name)

        self.log_debug("Sending request to Gemini. Url=%s, content=%s", self._base_url, content)
        await self._log_request("%s", content)
        try:
            async with httpx.AsyncClient(timeout=self._async_timeout) as client:
                response = await client.post(
                    url=self._base_url,
                    json=content,
                    headers={"Content-Type": "application/json"},
                )
        except Exception as exc:
            msg = f"Gemini API failed to generate response due to exception: {exc}"
            self.log_error("%s", msg)
            raise GenerationFailureError(msg) from exc

        await self._log_response("%s", response.json())

        if response.status_code != httpx.codes.OK:
            error_response = response.json()
            if "error" in error_response:
                self.log_error("Gemini API request failed: %s", error_response["error"]["message"])
            else:
                self.log_error("Gemini API request failed: %s", error_response)
            status_code = response.status_code
            exc_msg = f"Gemini API request failed with {response.json()['error']['message']}"
            raise GenerationFailureError(exc_msg, code=status_code)

        response_json = response.json()

        if "parts" not in response_json["candidates"][0]["content"]:
            self.log_error("Malformed/incorrect response from Gemini API. Response: %s", response_json)
            return TextGenerationResponse(
                "Uh oh, something went wrong with the Gemini response!",
                0,
            )

        return TextGenerationResponse(
            response_json["candidates"][0]["content"]["parts"][0]["text"],
            response_json["usageMetadata"]["totalTokenCount"],
        )

    def set_system_prompt(self, prompt: str, *, prompt_name: str = "unset name") -> None:
        """Set the system prompt.

        Parameters
        ----------
        prompt : str
            The system prompt to set.
        prompt_name : str
            The name of the system prompt.

        """
        self.system_prompt = prompt
        self.system_prompt_name = prompt_name
        self._model_context = {
            "system_instruction": {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            },
            "contents": [],
        }
        self.token_size = self.count_tokens(prompt)
