import os

import pytest

from slashbot.llm import ClaudeClient, TextGenerationInput, TextInput
from slashbot.settings import BotSettings

BotSettings.keys.claude = os.getenv("BOT_ANTHROPIC_API_KEY")


@pytest.mark.asyncio
async def test_claude_generation() -> None:
    """Test that text generation works for the Claude client."""
    client = ClaudeClient()

    confirmation_text = "I have received your message"
    text_input = TextInput(
        f"Confirm that this text was successfully received by responding **only** with '{confirmation_text}'."
    )

    response = await client.generate_response("claude-haiku-4-5", TextGenerationInput(text_input))
    assert response.message == confirmation_text
