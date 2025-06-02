from typing import Any

import httpx

from slashbot.core.text_generation.clients.abstract_client import TextGenerationAbstractClient
from slashbot.core.text_generation.models import (
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
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash-preview-04-17",
        "gemini-2.5-pro-preview-03-25",
    )
    VISION_MODELS = (
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash-preview-04-17",
        "gemini-2.5-pro-preview-03-25",
    )
    SEARCH_MODELS = ()
    AUDIO_MODELS = (
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash-preview-04-17",
        "gemini-2.5-pro-preview-03-25",
    )
    VIDEO_MODELS = (
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-flash-preview-04-17",
        "gemini-2.5-pro-preview-03-25",
    )

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

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return len(self._context["contents"])

    def _content_contains_youtube_video_type(self, content: dict) -> bool:
        for part in content.get("parts", []):
            if "file_data" in part:
                uri = part["file_data"].get("file_uri", "")
                return "youtube.com" in uri or "youtu.be" in uri
        return False

    def _add_to_contents(self, new_content: dict) -> None:
        # Remove youtube links (the only supported video understanding) from
        # the context, as it drastically increases the latency of responses
        i = 0
        while i < len(self._context["contents"]):
            content = self._context["contents"][i]
            if self._content_contains_youtube_video_type(content):
                self._remove_message(i)
            else:
                i += 1

        # But we still include new video request here, we are only removing OLD
        # youtube links. The one added to the context here will be removed
        # before the next request is sent
        self._context["contents"].append(new_content)

    def _create_assistant_text_payload(self, message: str) -> dict:
        return {"role": "model", "parts": [{"text": message}]}

    def _create_image_payload(self, images: VisionImage | list[VisionImage]) -> dict | list[dict]:
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

    def _create_text_payload(self, text: str | list[str]) -> dict | list[dict]:
        return {"text": text}

    def _create_user_payload(
        self, text_content: dict | list[dict], image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict:
        return {"role": "user", "parts": [*video_content, *image_content, *text_content]}

    def _create_video_payload(self, videos: VisionVideo | list[VisionVideo]) -> dict | list[dict]:
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

    def _remove_message(self, index: int) -> dict:
        if index < 0:
            msg = "Cannot remove message at negative index"
            raise IndexError(msg)
        if index >= len(self._context["contents"]):
            msg = "Cannot remove message at index greater than number of messages"
            raise IndexError(msg)
        self.token_size -= self.count_tokens_for_message(
            {"contents": [{"parts": self._context["contents"][index]["parts"]}]}
        )

        return self._context["contents"].pop(index)

    # --------------------------------------------------------------------------

    @property
    def context(self) -> list[dict]:
        """Get the context, minus the system prompt."""
        return self._context["contents"]

    def count_tokens_for_message(self, messages: dict | list[dict[str, str]] | str) -> int:
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

    def create_request_json(
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
        if not isinstance(messages, list):
            messages = [messages]
        content = []
        for message in messages:
            if message.role == "user":
                part = self._create_content_payload(message)
            else:
                part = self._create_assistant_text_payload(message.text)
            content.append(part)

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

        self._shrink_messages_to_token_window()

        user_contents = self._create_content_payload(messages)
        if isinstance(user_contents, list):
            for content in user_contents:
                self._add_to_contents(content)
        else:
            self._add_to_contents(user_contents)

        response = await self.send_response_request(self._context)
        if not response.message:
            msg = "A valid response was not generated by the Gemini API."
            raise ValueError(msg)

        self._add_to_contents(self._create_assistant_text_payload(response.message))
        self.token_size = response.tokens_used

        return response

    def init_client(self, model_name: str) -> None:
        """Initialise the client to use a model.

        Parameters
        ----------
        model_name : str
            The name of the model to initialise the client for.

        """
        self.model_name = model_name
        gen_ai_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self._base_url = f"{gen_ai_url}/{model_name}:generateContent?key={BotSettings.keys.gemini}"
        self._count_tokens_url = f"{gen_ai_url}/{model_name}:countTokens?key={BotSettings.keys.gemini}"
        self._context = {
            "system_instruction": {
                "parts": [
                    {
                        "text": self.system_prompt,
                    }
                ]
            },
            "contents": [],
        }

        self._setup_response_logger(model_name)

    async def send_response_request(self, content: list[dict] | dict) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict]
            The (correctly) formatted content to send to the API.

        """
        if not self._base_url:
            self.init_client(self.model_name)

        await self._log_request("%s", content)
        async with httpx.AsyncClient(timeout=self._async_timeout) as client:
            response = await client.post(
                url=self._base_url,
                json=content,
                headers={"Content-Type": "application/json"},
            )
        await self._log_response("%s", response.json())

        if response.status_code != httpx.codes.OK:
            error_response = response.json()
            if "error" in error_response:
                self.log_error("Gemini API request failed: %s", error_response["error"]["message"])
            else:
                self.log_error("Gemini API request failed: %s", error_response)
            status_code = response.status_code
            msg = f"Gemini API request failed with {response.json()['error']['message']}"
            raise GenerationFailureError(msg, code=status_code)

        response_json = response.json()

        return TextGenerationResponse(
            response_json["candidates"][0]["content"]["parts"][0]["text"],
            response_json["usageMetadata"]["totalTokenCount"],
        )

    def set_system_prompt(self, prompt: str, *, prompt_name: str = "unset") -> None:
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
        self._context = {
            "system_instruction": {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            },
            "contents": [],
        }
        self.token_size = self.count_tokens_for_message(prompt)
