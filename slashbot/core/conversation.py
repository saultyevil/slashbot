from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from slashbot.core.text_generator import TextGeneratorLLM
from slashbot.prompts import read_in_prompt_json


@dataclass
class ContextMessage:
    """Message dataclass for an LLM conversation."""

    role: str
    text: str
    tokens: int
    images: list[str]


@dataclass
class VisionImage:
    """Dataclass for images for LLM vision."""

    url: str
    b64image: str | None = None
    mime_type: str | None = None


class AIConversation(TextGeneratorLLM):
    """AI Conversation class for an LLM chatbot."""

    DEFAULT_SYSTEM_PROMPT = " ".join(
        dedent("""
        Be a useful assistant, don't be patronising or write anything that can
        be portrayed as being patronising. Be extremely concise. One sentence
        responses are best where possible. Do not try to be friendly or
        personable, just useful and soulless.
    """).splitlines()
    )

    def __init__(self, *, system_prompt: str = DEFAULT_SYSTEM_PROMPT, token_window_size: int = 2048) -> None:
        """Initialise a conversation, with default values.

        Parameters
        ----------
        system_prompt : str, optional
            The system prompt of the conversation. If not provided, the default
            system prompt is used.
        token_window_size : int, optional
            The maximum number of tokens to store in the conversation history.

        """
        super().__init__()
        self._system_prompt = ""
        self._system_prompt_name = ""
        self._context = []
        self._token_size = 0
        self._token_window_size = token_window_size
        self._set_system_prompt_and_clear_context(
            system_prompt,
            prompt_name="default prompt" if system_prompt == AIConversation.DEFAULT_SYSTEM_PROMPT else "custom prompt",
        )

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

    @staticmethod
    def _load_system_prompt(self, filepath: str | Path) -> tuple[str, str]:
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

    def _add_user_message_to_context(self, message: str, images: VisionImage | list[VisionImage] | None = None) -> None:
        if images:
            images = self._prepare_images_for_context(images)
            self._context.append(
                {"role": "user", "content": [{"type": "text", "content": message}, *images]},
            )
        else:
            self._context.append({"role": "user", "content": message})

    def _add_assistant_message_to_context(self, message: str) -> None:
        self._context.append({"role": "assistant", "content": message})

    def _clear_message_context(self) -> None:
        self._context = [{"role": "system", "content": self._system_prompt}]
        self._token_size = self.count_tokens_for_message(self._system_prompt)

    def _prepare_audio_for_context(self) -> None:
        raise NotImplementedError

    def _prepare_images_for_context(self, images: VisionImage | list[VisionImage]) -> list[dict]:
        if not isinstance(images, list):
            images = [images]
        return [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image.mime_type};base64,{image.b64image}" if image.b64image else image.url,
                    "detail": "low",
                },
            }
            for image in images
        ]

    def _prepare_video_for_context(self) -> None:
        raise NotImplementedError

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

    def _set_system_prompt_and_clear_context(self, prompt: str, *, prompt_name: str = "unknown") -> None:
        self.log_debug("Setting system prompt to %s", prompt)
        self._system_prompt = prompt
        self._system_prompt_name = prompt_name
        self._context = [{"role": "system", "content": prompt}]
        self._token_size = self.count_tokens_for_message(prompt)

    def _shrink_messages_to_token_window(self) -> None:
        min_messages_to_keep = 2
        while self._token_size > self._token_window_size and len(self) > min_messages_to_keep:
            self._remove_message_from_context(1)
            self._remove_message_from_context(1)

    # --------------------------------------------------------------------------

    @property
    def tokens(self) -> int:
        """The number of tokens in the context window."""
        return int(self._token_size)

    # --------------------------------------------------------------------------

    def get_history(self) -> list[dict]:
        """Get the conversation context history.

        Returns
        -------
        list[dict]
            The conversation history, formatted for the LLM API.

        """
        return self._context

    def reset_history(self) -> None:
        """Reset the conversation history back to the system prompt."""
        self._clear_message_context()

    async def send_message(self, message: str, images: list[str] | None = None) -> str:
        """Add a new message to the conversation history.

        Parameters
        ----------
        message : str
            The message to add
        images : list[str]
            Any images to add to the conversation

        Returns
        -------
        str
            The message response from the AI.

        """
        self._shrink_messages_to_token_window()
        self._add_user_message_to_context(message, images)
        response = await self.generate_text_from_llm(self._context)
        self._add_assistant_message_to_context(response.message)
        self._token_size = response.tokens_used
        return response.message

    def set_system_message(self, new_prompt: str) -> None:
        """Set the system prompt and clear the conversation.

        Parameters
        ----------
        new_prompt : str
            The new system prompt to set.

        """
        self._set_system_prompt_and_clear_context(new_prompt)
