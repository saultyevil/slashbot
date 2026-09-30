import os
from unittest.mock import AsyncMock

import pytest

from slashbot.cogs.chatbot.chat import Chat
from slashbot.llm import InputRole, LLMInput, TextInput
from slashbot.settings import BotSettings

BotSettings.keys.claude = os.getenv("BOT_ANTHROPIC_API_KEY")
model = "claude-haiku-4-5"


@pytest.fixture(autouse=True)
def disable_chat_file_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent chat tests from writing transcript files."""
    monkeypatch.setattr(Chat, "_write_chat_log", AsyncMock())


@pytest.mark.asyncio
async def test_chat_responds_for_new_input() -> None:
    """Test that a Chat will return a response for a given input."""
    chat = Chat("1", model)

    assert chat.model == model
    assert chat.provider == "anthropic"
    assert len(chat) == 0

    confirmation_text = "Loud and clear!"
    text_input = TextInput(
        f"Confirm that this text was successfully received by responding **only** with '{confirmation_text}'."
    )
    response = await chat.chat("test-user", LLMInput(text_input))

    assert response.message == confirmation_text
    assert len(chat) == 2

    assert chat.messages[0].role == InputRole.user
    assert chat.messages[1].role == InputRole.assistant


@pytest.mark.asyncio
async def test_chat_shrinks() -> None:
    """Test that the chat shrinks when exceeding the context window."""
    chat = Chat("2", model)

    # start conversation
    BotSettings.cogs.chatbot.chat_token_window_size = 1000
    await chat.chat("test-user", LLMInput(TextInput("Hello! Say something funny :-).")))
    assert len(chat) == 2

    # set window to be small, only the two new messages should be left
    BotSettings.cogs.chatbot.chat_token_window_size = 10
    await chat.chat("test-user", LLMInput(TextInput("Hello again! What was your previous joke?")))
    assert len(chat) == 2

    # set window to be big again so there should be 4 mesasages now
    BotSettings.cogs.chatbot.chat_token_window_size = 2048
    await chat.chat("test-user", LLMInput(TextInput("What's the capital of France?")))
    assert len(chat) == 4
