import openai
import tiktoken

from slashbot.core.text_generation import TextGenerationInput, TextGenerationResponse, VisionImage, VisionVideo
from slashbot.core.text_generation.clients.abstract_client import TextGenerationAbstractClient
from slashbot.settings import BotSettings


class OpenAIClient(TextGenerationAbstractClient):
    """Synchronous OpenAI client."""

    OPENAI_LOW_DETAIL_IMAGE_TOKENS = 85
    SUPPORTED_MODELS = (
        "gpt-3.5-turbo",
        "gpt-4o-mini",
        "gpt-4.1-nano",
        "gpt-4.1-mini",
    )
    VISION_MODELS = ("gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano")
    SEARCH_MODELS = ()
    AUDIO_MODELS = ()
    VIDEO_MODELS = ()

    # --------------------------------------------------------------------------

    def _make_assistant_text_content(self, message: str) -> dict:
        return {"role": "assistant", "content": message}

    def _make_image_content(self, images: VisionImage | list[VisionImage]) -> list[dict]:
        if self.model_name not in self.VISION_MODELS:
            return []
        if not isinstance(images, list):
            images = [images]
        return [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{image.mime_type};base64,{image.b64image}" if image.b64image else image.url,
                    "detail": "low",
                },
            }
            for image in images
        ]

    def _make_text_content(self, message: str) -> dict:
        return {"type": "text", "text": message}

    def _make_user_content(
        self, text_content: dict, image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict | list[dict]:
        return {"role": "user", "content": [*text_content, *image_content, *video_content]}

    def _make_video_content(self, videos: VisionVideo | list[VisionVideo]) -> list[dict]:  # noqa: ARG002
        if self.model_name not in self.VIDEO_MODELS:
            return []
        return []

    # --------------------------------------------------------------------------

    @property
    def context(self) -> list[dict]:
        """Get the context, minus the system prompt."""
        return self._context[1:]

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
        try:
            encoding = tiktoken.encoding_for_model(self.model_name)
        except KeyError:
            encoding = tiktoken.get_encoding("o200k_base")  # Fallback to this base

        if isinstance(messages, list):
            num_tokens = 0
            # Handle case where there are images and messages. Images are a fixed
            # cost of something like 85 tokens so we don't need to encode those
            # using tiktoken.
            for content in messages:
                if content["type"] == "text":
                    num_tokens += len(encoding.encode(content["text"]))
                else:
                    num_tokens += self.OPENAI_LOW_DETAIL_IMAGE_TOKENS if content["type"] == "image_url" else 0
        elif isinstance(messages, str):
            num_tokens = len(encoding.encode(messages))
        else:
            msg = f"Expected a string or list of strings for encoding, got {type(messages)}"
            raise TypeError(msg)

        return num_tokens

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
                _content = self._create_user_contents(message)
            else:
                _content = self._make_assistant_text_content(message.text)
            content.append(_content)
        return [{"role": "system", "content": system_prompt if system_prompt else ""}, *content]

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
        self._context.append(self._create_user_contents(messages))  # type: ignore  # noqa: PGH003

        response = await self.send_response_request(self._context)
        if not response.message:
            msg = "A valid response was not generated by the OpenAI client."
            raise ValueError(msg)

        self._context.append(self._make_assistant_text_content(response.message))
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
        self._base_url = "https://api.openai.com/v1"
        self._client = openai.AsyncClient(api_key=BotSettings.keys.openai)
        self._context = [{"role": "system", "content": self.system_prompt}]

    async def send_response_request(self, content: list[dict] | dict) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict]
            The (correctly) formatted content to send to the API.

        """
        if not self._client:
            self.init_client(self.model_name)
        self.log_debug("Sending request to OpenAI client: %s", content)

        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=content,  # type: ignore  # noqa: PGH003
            max_completion_tokens=self._max_completion_tokens,
        )

        assistant_response = response.choices[0].message.content
        if not assistant_response:
            msg = "A valid response was not generated by the OpenAI client."
            raise ValueError(msg)
        token_usage = response.usage.total_tokens if response.usage else self.token_size
        self.log_debug("Response usage: %s", response.usage)

        return TextGenerationResponse(assistant_response, token_usage)

    def set_system_prompt(self, prompt: str, *, prompt_name: str = "unknown") -> None:
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
        self._context = [{"role": "system", "content": prompt}]
        self.token_size = self.count_tokens_for_message(prompt)
