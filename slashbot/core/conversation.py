from pathlib import Path
from textwrap import dedent

from slashbot.core.text.models import VisionImage
from slashbot.core.text.text_generator import TextGeneratorLLM
from slashbot.prompts import read_in_prompt_json
from slashbot.settings import BotSettings


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
        super().__init__(BotSettings.cogs.ai_chat.default_llm_model, extra_print=extra_print)
        self.client_set_system_prompt(
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
        return self.size_messages

    # --------------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        """Get the system prompt of the conversation.

        Returns
        -------
        str
            The system prompt of the conversation.

        """
        return self._client.system_prompt

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
        self.client_set_system_prompt(self.client_system_prompt, prompt_name=self.client_system_prompt_name)

    async def send_message(self, message: str, images: VisionImage | list[VisionImage] | None = None) -> str:
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
        response = self.client_generate_response(message, images)
        self._token_size = response.tokens_used

        return response.message

    def set_system_prompt(self, new_prompt: str) -> None:
        """Set the system prompt and clear the conversation.

        Parameters
        ----------
        new_prompt : str
            The new system prompt to set.

        """
        self.client_set_system_prompt(new_prompt)
