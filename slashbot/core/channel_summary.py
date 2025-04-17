from dataclasses import dataclass
from textwrap import dedent

from slashbot.core.text.text_generator import TextGenerator


@dataclass
class SummaryMessage:
    """Dataclass for a message from a text channel."""

    user: str
    content: str
    tokens: int = 0


class AIChannelSummary(TextGenerator):
    """Dataclass for generating AI summaries for text channels."""

    SUMMARY_PROMPT = " ".join(
        dedent("""
            You are a secretary for a group of people. Generate a detailed
            summary of the conversation, highlighting key points, sentiments,
            and notable exchanges to provide a comprehensive overview of the
            interaction. Provide details about specific users. You will be
            named "me" in any transcripts or summaries sent to you. Do
            not refer to yourself in the third person under any circumstances.
            Instead, use the first person when describing your own
            contributions. If you generate a summary where you would
            typically refer to yourself in the third person, rewrite it to
            comply with this rule before finalising your response.
    """).splitlines()
    )

    def __init__(self, *, token_window_size: int = 8096, extra_print: str = "") -> None:
        """Initialise the AI channel summary."""
        extra_print = f"[AIChannelSummary:{extra_print}] " if extra_print else ""
        super().__init__(extra_print=extra_print)
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
        self.log_debug("Removed %d tokens with message: %s", removed_message.tokens, removed_message.message)

    def _shrink_history_to_token_window_size(self) -> None:
        while self._token_size > self._token_window_size and len(self) > 1:
            self._remove_message_from_history_context(1)

    # --------------------------------------------------------------------------

    def add_message_to_history(self, message: SummaryMessage) -> None:
        """Add a message to the history.

        Parameters
        ----------
        message : disnake.Message
            The message to add

        """
        self._shrink_history_to_token_window_size()
        if message.tokens == 0:
            message.tokens = self.client_count_tokens_for_message(message.content)
        self._history_context.append(message)
        self.log_debug("Adding message: %s", message.content)

    def get_history(self, *, amount: int = 0) -> list[SummaryMessage]:
        """Get the current history.

        Parameters
        ----------
        amount : int
            The number of messages to return, starting from the end. If <= 0,
            return all messages.

        Returns
        -------
        list[SummaryMessage]
            The current history.

        """
        if amount > 0:
            return self._history_context[-amount:]

        return self._history_context

    async def generate_summary(self, *, requesting_user: str | None = None) -> str:
        """Generate a summary of the current history.

        Parameters
        ----------
        requesting_user : str | None
            The user requesting the summary, to referred to in the summary as
            "you".

        """
        history_message = "Summarise the following conversation between multiple users:\n" + "\n".join(
            [f"{message.user}: {message.content}" for message in self._history_context]
        )
        full_conversation = [
            {"role": "system", "content": AIChannelSummary.SUMMARY_PROMPT},
            {"role": "user", "content": history_message},
        ]
        if requesting_user:
            full_conversation[-1]["content"] += (
                f".\nPlease refer to me, {requesting_user}, as 'you' in the summary like we were having a conversation."
            )

        self.log_debug("Context for summary: %s", full_conversation[1:])
        response = await self.generate_text_from_llm(full_conversation)
        self.log_debug("Generated summary: %s", response.message)

        return response.message
