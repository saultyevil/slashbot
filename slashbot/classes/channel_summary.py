from dataclasses import dataclass
from textwrap import dedent

import disnake

from slashbot.classes.text_generator import TextGeneratorLLM


@dataclass
class TextChannelMessage:
    """Dataclass for a message from a text channel."""

    user: str
    message: str
    tokens: int


class AIChannelSummary(TextGeneratorLLM):
    """Dataclass for generating AI summaries for text channels."""

    SUMMARY_PROMPT = " ".join(
        dedent("""
            You are a secretary for a group of people. Generate a detailed
            summary of the conversation, highlighting key points, sentiments,
            and notable exchanges to provide a comprehensive overview of the
            interaction. Provide details about specific users. You will be
            named "assistant" in any transcripts or summaries sent to you. Do
            not refer to yourself in the third person under any circumstances.
            Instead, use the first person when describing your own
            contributions. If you generate a summary where you would
            typically refer to yourself in the third person, rewrite it to
            comply with this rule before finalising your response.
    """).splitlines()
    )

    def __init__(self, *, token_window_size: int = 8096) -> None:
        """Initialise the AI channel summary."""
        super().__init__()
        self._token_size = 0
        self._token_window_size = token_window_size
        self._history_context = []

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the number of messages in the history.

        Returns
        -------
        int
            The number of messages in the history.

        """
        return len(self._history_context)

    # --------------------------------------------------------------------------

    def _remove_message_from_history_context(self, index: int) -> None:
        removed_message = self._history_context.pop(index)
        self._token_size -= removed_message.tokens

    def _shrink_history_to_token_window_size(self) -> None:
        while self._token_size > self._token_window_size and len(self) > 1:
            self._remove_message_from_history_context(1)

    # --------------------------------------------------------------------------

    def add_message_to_history(self, message: disnake.Message, *, self_message: bool = False) -> None:
        """Add a message to the history.

        Parameters
        ----------
        message : disnake.Message
            The message to add
        self_message : bool
            Whether the message was sent by the bot or not

        """
        self._shrink_history_to_token_window_size()
        self._history_context.append(
            TextChannelMessage(
                message.author.display_name if not self_message else "assistant",
                message.clean_content,
                self.count_tokens_for_message(message.clean_content),
            )
        )

    async def generate_summary(self) -> str:
        """Generate a summary of the current history."""
        history_message = "Summarise the following conversation between multiple users: " + "\n".join(
            [f"{message.user}: {message.message}" for message in self._history_context]
        )
        full_conversation = [
            {"role": "system", "content": AIChannelSummary.SUMMARY_PROMPT},
            {"role": "user", "content": history_message},
        ]

        response = await self.generate_text_from_llm(full_conversation)
        return response.message
