from pathlib import Path
from textwrap import dedent

from slashbot.core.text_generation import TextGenerator
from slashbot.core.text_generation.models import VisionImage, VisionVideo
from slashbot.prompts import read_in_prompt_json


class AIChat(TextGenerator):
    """AI Conversation class for an LLM chatbot."""

    DEFAULT_SYSTEM_PROMPT = " ".join(
        dedent("""
        Be a useful assistant, don't be patronising or write anything that can
        be portrayed as being patronising. Be extremely concise. One sentence
        responses are best where possible. Do not try to be friendly or
        personable, just useful and soulless.
    """).splitlines()
    )

    def __init__(self, *, system_prompt: str = DEFAULT_SYSTEM_PROMPT, extra_print: str = "") -> None:
        """Initialise a conversation, with default values.

        Parameters
        ----------
        system_prompt : str, optional
            The system prompt of the conversation. If not provided, the default
            system prompt is used.
        extra_print : str, optional
            Additional information to print at the start of the log message.

        """
        extra_print = f"[AIConversation:{extra_print}] " if extra_print else ""
        super().__init__(extra_print=extra_print)
        self._chat_system_prompt = system_prompt
        self.set_system_prompt(
            system_prompt,
            prompt_name="default prompt" if system_prompt == self.DEFAULT_SYSTEM_PROMPT else "custom prompt",
        )

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return self.size_messages

    # --------------------------------------------------------------------------

    @staticmethod
    def _load_system_prompt(filepath: str | Path) -> tuple[str, str]:
        if not isinstance(filepath, Path):
            filepath = Path(filepath)
        if not filepath.exists():
            msg = f"Prompt file does not exist at {filepath}"
            raise FileNotFoundError(msg)
        if filepath.suffix != ".json":
            msg = "Prompt file must be a JSON file"
            raise ValueError(msg)
        prompt = read_in_prompt_json(filepath)
        return prompt["name"], prompt["prompt"]

    # --------------------------------------------------------------------------

    def get_history(self) -> list[dict]:
        """Get the conversation context history.

        Returns
        -------
        list[dict]
            The conversation history, formatted for the LLM API.

        """
        return self._client.context

    def reset_history(self) -> None:
        """Reset the conversation history back to the system prompt."""
        self.set_system_prompt(self._chat_system_prompt, prompt_name=self.system_prompt_name)

    def send_message(
        self,
        message: str,
        images: VisionImage | list[VisionImage] | None = None,
        videos: VisionVideo | list[VisionVideo] | None = None,
    ) -> str:
        """Add a new message to the conversation history.

        Parameters
        ----------
        message : str
            The message to add
        images : VisionImage | list[VisionVideo] | None
            Any images to add to the conversation
        videos : VisionVideo | list[VisionVideo] | None
            Any videos to add to the conversation

        Returns
        -------
        str
            The message response from the AI.

        """
        response = self.generate_response_including_context(message, images, videos)
        self._token_size = response.tokens_used

        return response.message

    def send_raw_request(self, content: list[dict]) -> str:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict]
            The (correctly) formatted content to send to the API.

        """
        response = self.send_response_request(content)

        return response.message

    def set_chat_prompt(self, new_prompt: str) -> None:
        """Set the system prompt and clear the conversation.

        Parameters
        ----------
        new_prompt : str
            The new system prompt to set.

        """
        self.set_system_prompt(new_prompt)
