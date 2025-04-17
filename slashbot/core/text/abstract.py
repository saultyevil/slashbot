from abc import abstractmethod
from textwrap import dedent
from typing import Any

from slashbot.core.logger import Logger
from slashbot.core.text.models import TextGenerationResponse, VisionImage
from slashbot.settings import BotSettings


class TextGenerationAbstractClient(Logger):
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
        self._context = [
            {
                "role": "system",
                "content": kwargs["system_prompt"] if kwargs.get("system_prompt") else self.DEFAULT_SYSTEM_PROMPT,
            }
        ]
        self._client = None
        self._base_url = None
        self._token_size = 0
        self._system_prompt = None
        self._system_prompt_name = None
        self._token_window_size = BotSettings.cogs.ai_chat.token_window_size
        self._max_completion_tokens = BotSettings.cogs.ai_chat.max_output_tokens
        self.init_model(self.model_name)

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return len(self._context[1:])

    # --------------------------------------------------------------------------

    @abstractmethod
    def _add_assistant_message_to_context(self, message: str) -> None:
        pass

    @abstractmethod
    def _add_images_to_context(self, images: VisionImage | list[VisionImage]) -> None:
        pass

    @abstractmethod
    def _add_user_message_to_context(self, message: str) -> None:
        pass

    @abstractmethod
    def _set_system_prompt_and_clear_context(self, prompt: str, *, prompt_name: str = "unknown") -> None:
        pass

    @abstractmethod
    def _send_request(self) -> None:
        pass

    # --------------------------------------------------------------------------

    def _remove_message_from_context(self, index: int) -> dict:
        if index == 0:
            msg = "Cannot remove system prompt at index 0"
            raise IndexError(msg)
        if index < 0:
            msg = "Cannot remove message at negative index"
            raise IndexError(msg)
        if index >= len(self._context):
            msg = "Cannot remove message at index greater than number of messages"
            raise IndexError(msg)
        self._token_size -= self.count_tokens_for_message(self._context[index]["content"])
        return self._context.pop(index)

    def _shrink_messages_to_token_window(self) -> None:
        min_messages_to_keep = 2
        while self._token_size > self._token_window_size and len(self) > min_messages_to_keep:
            self._remove_message_from_context(1)
            self._remove_message_from_context(1)

    # --------------------------------------------------------------------------

    @property
    @abstractmethod
    def context(self) -> list[dict]:
        """Get the context, minus the system prompt."""

    @abstractmethod
    def count_tokens_for_message(self, messages: list[dict[str, str]] | str) -> int:
        """Count the number of tokens in a message.

        Parameters
        ----------
        messages : list[dict[str, str]] | str
            The message to count the number of tokens.

        """

    @abstractmethod
    def generate_response(
        self, message: str, images: VisionImage | list[VisionImage] | None = None
    ) -> TextGenerationResponse:
        """Generate a text response, gievn a message and image inputs.

        Text generation includes the entire context history, and not just the
        most recent inputs.

        Parameters
        ----------
        message : str
            An input message, from the user.
        images : VisionImage | list[VisionImage] | None
            Input image(s), from the user.

        """

    @abstractmethod
    def init_model(self, model_name: str) -> None:
        """Initialise the client to use a model.

        Parameters
        ----------
        model_name : str
            The name of the model to initialise the client for.

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
