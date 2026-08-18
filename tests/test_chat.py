import os

import pytest

from slashbot.cogs.chatbot.chat import Chat
from slashbot.llm import InputRole, TextGenerationInput, TextInput
from slashbot.settings import BotSettings

BotSettings.keys.claude = os.getenv("BOT_ANTHROPIC_API_KEY")
model = "claude-haiku-4-5"


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
    response = await chat.respond_to_message(TextGenerationInput(text_input))

    assert response.message == confirmation_text
    assert len(chat) == 2

    assert chat.messages[0].role == InputRole.user
    assert chat.messages[1].role == InputRole.assistant
