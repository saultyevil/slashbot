import os

import pytest

from slashbot.llm import LLM, LLMInput, TextInput
from slashbot.settings import BotSettings

BotSettings.keys.claude = os.getenv("BOT_ANTHROPIC_API_KEY")


@pytest.mark.asyncio
async def test_claude_generation() -> None:
    """Test that text generation works for the Claude client."""
    client = LLM("claude-haiku-4-5")

    assert client.provider == "anthropic"

    confirmation_text = "Loud and clear!"
    text_input = TextInput(
        f"Confirm that this text was successfully received by responding **only** with '{confirmation_text}'."
    )

    response = await client.generate_response(LLMInput(text_input))
    assert response.message == confirmation_text


@pytest.mark.asyncio
async def test_claude_count_tokens() -> None:
    """Tests whether the count tokens API is working."""
    client = LLM("claude-haiku-4-5")

    confirmation_text = "Loud and clear!"
    text_input = TextInput(
        f"Confirm that this text was successfully received by responding **only** with '{confirmation_text}'."
    )
    expected_tokens = 29  # taken from another source

    tokens = await client.count_tokens(LLMInput(text_input))
    assert tokens == expected_tokens
