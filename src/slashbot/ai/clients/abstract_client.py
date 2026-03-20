import asyncio
import logging
import logging.handlers
from abc import ABCMeta, abstractmethod
from typing import Any

from slashbot.ai.models import (
    TextGenerationInput,
    TextGenerationResponse,
    VisionImage,
    VisionVideo,
)
from slashbot.ai.prompts import read_in_prompt
from slashbot.logger import Logger
from slashbot.settings import BotSettings


class TextGenerationAbstractClient(Logger, metaclass=ABCMeta):
    """Abstract class for a TextGenerationClient."""

    DEFAULT_SYSTEM_PROMPT = read_in_prompt(BotSettings.cogs.chatbot.default_chat_prompt)

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
        self.system_prompt = kwargs.get("system_prompt", self.DEFAULT_SYSTEM_PROMPT.prompt)
        self.system_prompt_name = kwargs.get("system_prompt_name", self.DEFAULT_SYSTEM_PROMPT.name)

        self._model_context = []
        self._client = None
        self._base_url = None
        self._async_timeout = 240  # seconds
        self._token_window_size = BotSettings.cogs.chatbot.token_window_size
        self._max_completion_tokens = BotSettings.cogs.chatbot.max_output_tokens

        self._response_logger = logging.getLogger(f"TextGenerationAbstractClient-{model_name}")
        self._logger_lock = asyncio.Lock()

        self.init_client(self.model_name)
        self.token_size = self.count_tokens(self.system_prompt)
        self._setup_response_logger(self.model_name)

    def _add_to_model_context(self, new_content: dict) -> None:
        """Add new contents to the model context.

        This has various pre-processing steps for adding new messages, such as
        making sure there is only a certain number of images in the model
        context as too many images slows responses.

        Parameters
        ----------
        new_content : dict
            The new content to add to the model context.

        """
        # Keep some variable amount of images in the request. If we have too
        # many images, then the latency is too high
        i = 0
        num_images = 0
        while i < len(self._model_context_message_content):
            contents = self._model_context_message_content[i]
            # can only be an image of contents is a dict or a list
            if not isinstance(contents, str):
                if self._check_context_contains_images(contents):
                    num_images += 1
                if num_images > BotSettings.cogs.chatbot.max_images_in_window:
                    self.log_debug("Removing an image from model context")
                    self._remove_message_from_model_context(i)
                    continue  # don't increment as the lift has been shifted
            i += 1

        # But we still include new video request here, we are only removing OLD
        # youtube links. The one added to the context here will be removed
        # before the next request is sent
        self.log_debug("Model context before append: %s", self._model_context)
        self._model_context_message_content.append(new_content)
        self.log_debug("Updated model context: %s", self._model_context)

    def _create_content_payload(self, messages: TextGenerationInput | list[TextGenerationInput]) -> dict | list[dict]:
        """Create the contents payload for a request.

        The input object(s), TextGenerationInput, can contain text, image and
        video (url) data to add to the contents payload. The methods inside this
        method are all abstract and must be implemented by the current client.

        Parameters
        ----------
        messages : TextGenerationInput | list[TextGenerationInput]
            The input message(s) to create a contents payload.

        Returns
        -------
        dict | list [dict]
            An appropriately formatted dict or list of dict's for the current
            active client.

        """
        if isinstance(messages, TextGenerationInput):
            messages = [messages]

        self.log_debug("Creating request payload for %s using %s", self.model_name, messages)

        text_content = []
        image_content = []
        video_content = []

        for message in messages:
            text_content.append(self._create_text_input_object(message.text))
            if message.images:
                image_content.extend(self._create_image_input_object(message.images))
            if message.videos:
                video_content.extend(self._create_video_input_object(message.videos))

        user_request_object = self._create_user_input_object(text_content, image_content, video_content)
        self.log_debug("Created request object %s", user_request_object)

        return user_request_object

    def _shrink_model_context_to_window_size(self) -> None:
        """Shrink the context of the conversation within a token limit.

        This method uses an abstract method to remove messages from the context
        (typically the contents payload) which must be implemented by the
        client.
        """
        min_messages_to_keep = 2
        while self.token_size > self._token_window_size and len(self) > min_messages_to_keep:
            msg1 = self._remove_message_from_model_context(0)
            msg2 = self._remove_message_from_model_context(0)
            self.log_debug("Removed messages\n\t[1] %s\n\t[2] %s", msg1, msg2)

    def _remove_message_from_model_context(self, index: int) -> dict:
        """Remove an image from the conversation context.

        Parameters
        ----------
        index : int
            The index of the message to remove.

        Returns
        -------
        dict
            The removed message, including all content (text, image, video).

        """
        if index < 0:
            msg = "Cannot remove message at negative index"
            raise IndexError(msg)
        if index >= len(self):
            msg = "Cannot remove message at index greater than number of messages"
            raise IndexError(msg)

        message = self._model_context_message_content[index]
        removed_message_tokens = self.count_tokens(message)
        self.token_size -= removed_message_tokens
        self.log_debug("Removed %s tokens with message %s", removed_message_tokens, message)

        return self._model_context_message_content.pop(index)

    def _setup_response_logger(self, model_name: str) -> None:
        """Set up a debug logger for logging responses and requests.

        Parameters
        ----------
        model_name : str
            The name of the model.

        Returns
        -------
        logging.Logger
            The initialised logger.

        """
        logger = logging.getLogger(f"TextGenerationAbstractClient-{model_name}")

        if not logger.handlers:
            handler = logging.handlers.RotatingFileHandler(
                f"logs/{model_name}-requests.log", mode="a", maxBytes=int(5 * 1e6), backupCount=1
            )
            formatter = logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")
            handler.setFormatter(formatter)
            logger.setLevel(logging.INFO)
            logger.addHandler(handler)
            logger.propagate = False

        self._response_logger = logger

    async def _log_request(self, message: str, *args: Any) -> None:
        """Log a request to an LLM API.

        Parameters
        ----------
        message : str
            The message string to love.
        *args : Any
            Additional arguments, typically used for string interpolation.

        """
        async with self._logger_lock:
            self._response_logger.info("Request  | %s", message % args)

    async def _log_response(self, message: str, *args: Any) -> None:
        """Log a response for a LLM API.

        Parameters
        ----------
        message : str
            The message string to love.
        *args : Any
            Additional arguments, typically used for string interpolation.

        """
        async with self._logger_lock:
            self._response_logger.info("Response | %s", message % args)

    def create_content_payload_object(self, messages: TextGenerationInput | list[TextGenerationInput]) -> dict | list:
        """Create a request JSON for the current LLM model.

        Parameters
        ----------
        messages : ContextMessage | list[ContextMessage]
            Input message(s), from the user, including attached images and
            videos.

        """
        if not isinstance(messages, list):
            messages = [messages]
        content = []
        for message in messages:
            if message.role == "user":
                part = self._create_content_payload(message)
            else:
                part = self._create_assistant_response_object(message.text)
            content.append(part)

        self.log_debug("create_content_payload_object: current payload to be returned %s", content)

        return content

    # --------------------------------------------------------------------------
    # ABSTRACT METHODS WHICH REQUIRE IMPLEMENTATION
    # --------------------------------------------------------------------------

    @property
    @abstractmethod
    def _model_context_message_content(self) -> list[dict]:
        """Return a reference to the contents of the context.

        This reference exists because the request objects are different for
        each LLM.

        Returns
        -------
        list[dict]
            The contents of the context.

        """

    @abstractmethod
    def __len__(self) -> int:
        """Get the length of the conversation."""

    @abstractmethod
    def _check_context_contains_images(self, contents: dict) -> bool:
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
    def _create_user_input_object(
        self, text_content: dict | list[dict], image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict | list[dict]:
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

    @abstractmethod
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

    @abstractmethod
    def count_tokens(self, messages: dict | list[dict[str, str]] | str) -> int:
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
    async def generate_response(self, content: dict | list[dict]) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict] | dict
            The (correctly) formatted content to send to the API.

        """

    @abstractmethod
    def set_system_prompt(self, prompt: str, *, prompt_name: str = "unset name") -> None:
        """Set the system prompt.

        Parameters
        ----------
        prompt : str
            The system prompt to set.
        prompt_name : str
            The name of the system prompt.

        """
