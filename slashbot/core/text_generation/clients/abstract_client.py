import logging
from abc import ABCMeta, abstractmethod
from textwrap import dedent
from typing import Any

from slashbot.core.logger import Logger
from slashbot.core.text_generation import TextGenerationInput, TextGenerationResponse, VisionImage, VisionVideo
from slashbot.settings import BotSettings


class TextGenerationAbstractClient(Logger, metaclass=ABCMeta):
    """Abstract class for a TextGenerationClient."""

    DEFAULT_SYSTEM_PROMPT = " ".join(
        dedent("""
        Be a useful assistant, don't be patronising or write anything that can
        be portrayed as being patronising. Be extremely concise. One sentence
        responses are best where possible. Do not try to be friendly or
        personable, just useful and soulless.
    """).splitlines()
    )

    def __init__(self, model_name: str, **kwargs: Any) -> None:
        """Initialise the text generation class.

        Parameters
        ----------
        model_name : str
            The name of the model.
        **kwargs : Any
            A list of key word arguments to use for the model.

        """
        super().__init__(**kwargs)
        self.model_name = model_name
        self._context = []
        self._client = None
        self._base_url = None
        self._async_timeout = 240  # seconds
        self.system_prompt = kwargs.get("system_prompt", self.DEFAULT_SYSTEM_PROMPT)
        self.system_prompt_name = kwargs.get("system_prompt_name", "default")
        self.token_size = self.count_tokens_for_message(self.system_prompt)
        self._token_window_size = BotSettings.cogs.text_generation.token_window_size
        self._max_completion_tokens = BotSettings.cogs.text_generation.max_output_tokens
        self.init_client(self.model_name)

        handler = logging.FileHandler(f"logs/{model_name}_requests.log", mode="w")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        self.debug_logger = logging.getLogger(f"{model_name}")
        self.debug_logger.addHandler(handler)
        self.debug_logger.setLevel(logging.INFO)

    @abstractmethod
    def __len__(self) -> int:
        """Get the length of the conversation."""

    # --------------------------------------------------------------------------

    def _create_user_contents(self, messages: TextGenerationInput | list[TextGenerationInput]) -> dict | list[dict]:
        if isinstance(messages, TextGenerationInput):
            messages = [messages]

        text_content = []
        image_content = []
        video_content = []

        for message in messages:
            text_content.append(self._make_text_content(message.text))
            if message.images:
                image_content.extend(self._make_image_content(message.images))
            if message.videos:
                video_content.extend(self._make_video_content(message.videos))

        return self._make_user_content(text_content, image_content, video_content)

    def _shrink_messages_to_token_window(self) -> None:
        min_messages_to_keep = 2
        while self.token_size > self._token_window_size and len(self) > min_messages_to_keep:
            self._remove_message_from_context(1)
            self._remove_message_from_context(1)

    def _log_request(self, message: str, *args: Any) -> None:
        self.debug_logger.info("Request  | %s", message % args)

    def _log_response(self, message: str, *args: Any) -> None:
        self.debug_logger.info("Response | %s", message % args)

    # --------------------------------------------------------------------------

    @abstractmethod
    def _make_assistant_text_content(self, message: str) -> dict:
        pass

    @abstractmethod
    def _make_image_content(self, images: VisionImage | list[VisionImage]) -> dict | list[dict]:
        pass

    @abstractmethod
    def _make_text_content(self, text: str | list[str]) -> dict | list[dict]:
        pass

    @abstractmethod
    def _make_user_content(
        self, text_content: dict | list[dict], image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict | list[dict]:
        pass

    @abstractmethod
    def _make_video_content(self, videos: VisionVideo | list[VisionVideo]) -> dict | list[dict]:
        pass

    @abstractmethod
    def _remove_message_from_context(self, index: int) -> dict:
        pass

    # --------------------------------------------------------------------------

    @property
    @abstractmethod
    def context(self) -> list[dict]:
        """Get the context, minus the system prompt."""

    # --------------------------------------------------------------------------

    @abstractmethod
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

    @abstractmethod
    def count_tokens_for_message(self, messages: dict | list[dict[str, str]] | str) -> int:
        """Count the number of tokens in a message.

        Parameters
        ----------
        messages : dict | list[dict[str, str]] | str
            The message to count the number of tokens.

        """

    @abstractmethod
    async def generate_response_with_context(
        self, messages: TextGenerationInput | list[TextGenerationInput]
    ) -> TextGenerationResponse:
        """Generate a text response, given new text input and previous context.

        Text generation includes the entire context history, and not just the
        most recent inputs.

        Parameters
        ----------
        messages : ContextMessage | list[ContextMessage]
            Input message(s), from the user, including attached images and
            videos.

        """

    @abstractmethod
    def init_client(self, model_name: str) -> None:
        """Initialise the client to use a model.

        Parameters
        ----------
        model_name : str
            The name of the model to initialise the client for.

        """

    @abstractmethod
    async def send_response_request(self, content: dict | list[dict]) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict] | dict
            The (correctly) formatted content to send to the API.

        """

    @abstractmethod
    def set_system_prompt(self, prompt: str, *, prompt_name: str = "unknown") -> None:
        """Set the system prompt.

        Parameters
        ----------
        prompt : str
            The system prompt to set.
        prompt_name : str
            The name of the system prompt.

        """
