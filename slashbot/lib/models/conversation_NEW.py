from slashbot.lib.config import BotConfig
from slashbot.lib.text_generation_NEW import TextGeneratorLLM


class AIConversation(TextGeneratorLLM):
    """AI Conversation class for an LLM chatbot."""

    def __init__(self) -> None:
        """Initialise a conversation, with default values."""
        super().__init__()
        self._system_prompt = BotConfig.get_config("AI_CHAT_DEFAULT_SYSTEM_PROMPT")
        self._token_window_size = BotConfig.get_config("AI_CHAT_TOKEN_WINDOW_SIZE")
        self._context = [{"role": "system", "content": self._system_prompt}]
        self._token_size = self.count_tokens_for_message(self._system_prompt)

    # --------------------------------------------------------------------------

    def _add_user_message_to_context(self, message: str, images: list[str] | None = None) -> None:
        raise NotImplementedError

    def _add_assistant_message_to_context(self, message: str) -> None:
        raise NotImplementedError

    def _prepare_images_for_context(self) -> None:
        raise NotImplementedError

    def _prepare_audio_for_context(self) -> None:
        raise NotImplementedError

    def _remove_message_from_context(self, index: int) -> None:
        raise NotImplementedError

    def _set_system_prompt(self, prompt: str) -> None:
        raise NotImplementedError

    def _shrink_messages_to_token_window(self) -> None:
        raise NotImplementedError

    def clear_message_context(self) -> None:
        """Clear the messages in the conversation, keeping the system prompt."""
        raise NotImplementedError

    # --------------------------------------------------------------------------

    async def generate_response(self, message: str, images: list[str] | None = None) -> list[dict]:
        """Add a new message to the conversation history.

        Parameters
        ----------
        message : str
            The message to add
        images : list[str]
            Any images to add to the conversation

        """
        self._add_user_message_to_context()
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
        raise NotImplementedError
