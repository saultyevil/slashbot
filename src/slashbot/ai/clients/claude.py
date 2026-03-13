from anthropic import Anthropic, AsyncAnthropic

from slashbot.ai.clients.abstract_client import TextGenerationAbstractClient
from slashbot.ai.models import TextGenerationInput, TextGenerationResponse, VisionImage, VisionVideo
from slashbot.settings import BotSettings


class ClaudeClient(TextGenerationAbstractClient):
    """Asynchronous Claude client."""

    SUPPORTED_MODELS = (
        "claude-haiku-4-5",
        "claude-sonnet-4-6",
    )
    VISION_MODELS = (
        "claude-haiku-4-5",
        "claude-sonnet-4-6",
    )
    SEARCH_MODELS = ()
    AUDIO_MODELS = ()
    VIDEO_MODELS = ()

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return len(self._context)

    # --------------------------------------------------------------------------

    def _content_contains_image_type(self, contents: list[dict]) -> bool:
        return any(content["type"] == "image" for content in contents)

    def _add_to_contents(self, new_content: dict) -> None:
        # Keep some variable amount of images in the request. If we have too
        # many images, then the latency is too high
        i = 0
        num_images = 0
        while i < len(self._context):
            contents = self._context[i]["content"]
            # can only be an image of contents is a dict or a list
            if not isinstance(contents, str):
                if self._content_contains_image_type(contents):
                    num_images += 1
                if num_images > BotSettings.cogs.chatbot.max_images_in_window:
                    self._remove_message(i)
                    continue  # don't increment as the lift has been shifted
            i += 1

        # But we still include new video request here, we are only removing OLD
        # youtube links. The one added to the context here will be removed
        # before the next request is sent
        self._context.append(new_content)

    def _create_assistant_text_payload(self, message: str) -> dict:
        return {"role": "assistant", "content": message}

    def _create_image_payload(self, images: VisionImage | list[VisionImage]) -> list[dict]:
        if self.model_name not in self.VISION_MODELS:
            return []
        if not isinstance(images, list):
            images = [images]
        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": f"image/{image.mime_type}",
                    "data": f"{image.b64image}",
                },
            }
            for image in images
        ]

    def _create_text_payload(self, text: str | list[str]) -> dict | list[dict]:
        return {"type": "text", "text": text}

    def _create_user_payload(
        self, text_content: dict | list[dict], image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict | list[dict]:
        return {"role": "user", "content": [*text_content, *image_content, *video_content]}

    def _create_video_payload(self, videos: VisionVideo | list[VisionVideo]) -> list[dict]:  # noqa: ARG002
        if self.model_name not in self.VIDEO_MODELS:
            return []
        return []

    def _remove_message(self, index: int) -> dict:
        if index < 0:
            msg = "Cannot remove message at negative index"
            raise IndexError(msg)
        if index >= len(self._context):
            msg = "Cannot remove message at index greater than number of messages"
            raise IndexError(msg)
        self.token_size -= self.count_tokens_for_message(self._context[index]["content"])
        return self._context.pop(index)

    # --------------------------------------------------------------------------

    @property
    def context(self) -> list[dict]:
        """Get the context, minus the system prompt."""
        return self._context

    @property
    def client_type(self) -> str:
        """Get the model type."""
        return "claude"

    # --------------------------------------------------------------------------

    def count_tokens_for_message(self, messages: dict | list[dict[str, str]] | str) -> int:
        """Get the token count for a given message for the current LLM model.

        Parameters
        ----------
        messages : dict | list[str] | str
            The message for which the token count needs to be computed.

        Returns
        -------
        int
            The count of tokens in the given message for the current model.

        """
        if not self._client:
            msg = "No API client is available to query the tokens endpoint"
            raise ValueError(msg)
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        client = Anthropic(api_key=self._client.api_key, base_url=self._client.base_url)
        response = client.messages.count_tokens(model=self.model_name, messages=messages)
        self.log_debug("Count token response %s for messages %s", response, messages)

        return response.input_tokens

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

        return content

    async def generate_response_with_context(
        self, messages: TextGenerationInput | list[TextGenerationInput]
    ) -> TextGenerationResponse:
        """Generate a text response, gievn a message and image inputs.

        Text generation includes the entire context history, and not just the
        most recent inputs.

        Parameters
        ----------
        messages : ContextMessage | list[ContextMessage]
            Input message(s), from the user, including attached images and
            videos.

        """
        if not self._client:
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
            msg = "A valid response was not generated by the Anthropic client."
            raise ValueError(msg)

        self._context.append(self._create_assistant_text_payload(response.message))
        self.token_size = response.tokens_used

        return response

    def init_client(self, model_name: str, *, base_url: str | None = None) -> None:
        """Initialise the client to use a model.

        Parameters
        ----------
        model_name : str
            The name of the model to initialise the client for.
        base_url : str | None
            The base URL of the API service. By default None, which means the
            default URL of the relevant SDK is used.

        """
        self.model_name = model_name
        if base_url is None:
            self._base_url = "https://api.anthropic.com/v1/"
        else:
            self._base_url = base_url
        self._client = AsyncAnthropic(api_key=BotSettings.keys.claude)
        self._context = []
        self._setup_response_logger(model_name)

    async def send_response_request(self, content: list[dict] | dict) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict]
            The (correctly) formatted content to send to the API.

        """
        if not self._client:
            self.init_client(self.model_name)

        await self._log_request("%s", content)
        response = await self._client.messages.create(
            model=self.model_name,
            messages=content,  # type: ignore
            max_tokens=self._max_completion_tokens,
            temperature=BotSettings.cogs.chatbot.model_temperature,
            system=self.system_prompt,
        )
        await self._log_response("%s", response)

        if not response.content:
            msg = "A valid response was not generated by the Anthropic client."
            raise ValueError(msg)

        assistant_response = response.content[0].text
        token_usage = response.usage.input_tokens + response.usage.output_tokens if response.usage else self.token_size

        return TextGenerationResponse(assistant_response, token_usage)

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
        self._context = []
        self.token_size = self.count_tokens_for_message(prompt)
