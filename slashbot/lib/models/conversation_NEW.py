from dataclasses import dataclass
from pathlib import Path

from slashbot.lib.config import BotConfig
from slashbot.lib.text_generation_NEW import TextGeneratorLLM
from slashbot.lib.util import read_in_prompt_json


@dataclass
class Message:
    """Message dataclass for an LLM conversation."""

    role: str
    text: str
    tokens: int
    images: list[str]


class AIConversation(TextGeneratorLLM):
    """AI Conversation class for an LLM chatbot."""

    def __init__(self) -> None:
        """Initialise a conversation, with default values."""
        super().__init__()
        self._system_prompt = ""
        self._token_size = 0
        self._token_window_size = BotConfig.get_config("AI_CHAT_TOKEN_WINDOW_SIZE")
        self._context = [{"role": "system", "content": self._system_prompt}]
        self.set_system_message(
            self._load_system_prompt("data/prompts/soulless.json")
        )  # TODO(EP): Make this configurable

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

    def _add_user_message_to_context(self, message: str, images: list[str] | None = None) -> None:
        if images:
            # images = self._prepare_images_for_context(images)
            self._conext.append(
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

    def _prepare_images_for_context(self) -> None:
        raise NotImplementedError

    def _prepare_video_for_context(self) -> None:
        raise NotImplementedError

    def _load_system_prompt(self, filepath: str | Path) -> str:
        if not isinstance(filepath, Path):
            filepath = Path(filepath)
        if not filepath.exists():
            msg = f"Prompt file does not exist at {filepath}"
            raise FileNotFoundError(msg)
        if filepath.suffix != ".json":
            msg = "Prompt file must be a JSON file"
            raise ValueError(msg)
        return read_in_prompt_json(filepath)["prompt"]

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

    def _set_system_prompt_and_clear_context(self, prompt: str) -> None:
        self.log_debug("Setting system prompt to %s", prompt)
        self._context = [{"role": "system", "content": prompt}]
        self._token_size = self.count_tokens_for_message(prompt)

    def _shrink_messages_to_token_window(self) -> None:
        min_messages_to_keep = 2
        token_start = self.tokens
        messages_start = len(self)

        while self.tokens > self._token_window_size and len(self) > min_messages_to_keep:
            self._remove_message_from_context(1)
            self._remove_message_from_context(1)

        if self.tokens != token_start:
            self.log_info(
                "Removed %d tokens and %d messages from conversation",
                token_start - self.tokens,
                messages_start - len(self),
            )

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

    async def send_message(self, message: str, images: list[str] | None = None) -> list[dict]:
        """Add a new message to the conversation history.

        Parameters
        ----------
        message : str
            The message to add
        images : list[str]
            Any images to add to the conversation

        """
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


if __name__ == "__main__":
    import asyncio

    async def _main() -> None:
        conversation = AIConversation()
        message = await conversation.send_message("What is the capital of the United Kingdom? And why does it smell?")
        conversation.reset_history()
        print(message)
        conversation.set_system_message("You are zombie, only respond in a series of moans.")
        message = await conversation.send_message("What is the capital of the United Kingdom? And why does it smell?")
        print(message)
        history = conversation.get_history()
        print(history)

    asyncio.run(_main())
