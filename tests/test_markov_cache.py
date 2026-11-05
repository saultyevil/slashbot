import asyncio
from collections import deque
from types import SimpleNamespace

import pytest

from slashbot.bot.custom_cog import CustomCog
from slashbot.settings import BotSettings


class FakeGenerator:
    """A generator which counts how many sentences were computed."""

    def __init__(self) -> None:
        self.computed = 0

    def generate_response(self, amount: int = 1, seed_word: str | None = None) -> list[str]:
        sentences = [f"{seed_word} sentence {self.computed + i}" for i in range(amount)]
        self.computed += amount
        return sentences


def _cog(*, use_cache: bool = True) -> SimpleNamespace:
    cog = SimpleNamespace(
        bot=SimpleNamespace(use_markov_cache=use_cache, markov_generator=FakeGenerator()),
        markov_seed_words=["weather"],
        _markov_sentences={},
        _markov_refill_task=None,
        log_debug=lambda *_a, **_k: None,
        log_exception=lambda *_a, **_k: None,
    )
    for name in [
        "_get_random_markov_sentence",
        "_generate_markov_sentences",
        "_populate_markov_cache",
        "_request_markov_cache_refill",
        "_refill_markov_cache",
    ]:
        setattr(cog, name, getattr(CustomCog, name).__get__(cog))
    return cog


@pytest.mark.asyncio
async def test_populate_fills_cache() -> None:
    cog = _cog()
    await cog._populate_markov_cache()  # noqa: SLF001
    assert len(cog._markov_sentences["weather"]) == BotSettings.markov.num_pregen_sentences  # noqa: SLF001
    # topping up a full cache computes nothing new
    computed = cog.bot.markov_generator.computed
    await cog._populate_markov_cache()  # noqa: SLF001
    assert cog.bot.markov_generator.computed == computed


@pytest.mark.asyncio
async def test_cached_sentence_is_served_without_computing_and_refilled() -> None:
    cog = _cog()
    await cog._populate_markov_cache()  # noqa: SLF001
    generator = cog.bot.markov_generator
    computed = generator.computed

    sentence = cog._get_random_markov_sentence("weather", 1)  # noqa: SLF001
    assert sentence == "weather sentence 0"
    assert generator.computed == computed  # served straight from the cache

    # drain below the limit, then wait for the background refill
    while len(cog._markov_sentences["weather"]) >= BotSettings.markov.pregenerate_limit:  # noqa: SLF001
        cog._get_random_markov_sentence("weather", 1)  # noqa: SLF001
    await cog._markov_refill_task  # noqa: SLF001
    assert len(cog._markov_sentences["weather"]) == BotSettings.markov.num_pregen_sentences  # noqa: SLF001


@pytest.mark.asyncio
async def test_partial_cache_is_topped_up_with_generated_sentences() -> None:
    cog = _cog()
    cog._markov_sentences["weather"] = deque(["cached"])  # noqa: SLF001
    result = cog._get_random_markov_sentence("weather", 3)  # noqa: SLF001
    assert result[0] == "cached"
    assert len(result) == 3  # noqa: PLR2004
    await cog._markov_refill_task  # noqa: SLF001


def test_uncached_seed_and_disabled_cache_generate_directly() -> None:
    cog = _cog()
    assert cog._get_random_markov_sentence("other", 1).startswith("other")  # noqa: SLF001
    assert cog._get_random_markov_sentence(None, 2) == ["None sentence 1", "None sentence 2"]  # noqa: SLF001
    assert cog._markov_refill_task is None  # noqa: SLF001

    disabled = _cog(use_cache=False)
    disabled._markov_sentences["weather"] = deque(["cached"])  # noqa: SLF001
    assert disabled._get_random_markov_sentence("weather", 1) != "cached"  # noqa: SLF001


def test_no_generator_gives_message() -> None:
    cog = _cog(use_cache=False)
    cog.bot.markov_generator = None
    assert cog._get_random_markov_sentence("x", 2) == ["Markov generation is not available."] * 2  # noqa: SLF001


@pytest.mark.asyncio
async def test_refill_runs_off_the_event_loop() -> None:
    """Generation happens in a worker thread so the loop stays responsive."""
    import threading  # noqa: PLC0415

    cog = _cog()
    threads = []
    original = cog.bot.markov_generator.generate_response

    def spy(amount: int = 1, seed_word: str | None = None) -> list[str]:
        threads.append(threading.current_thread())
        return original(amount, seed_word)

    cog.bot.markov_generator.generate_response = spy
    await cog._populate_markov_cache()  # noqa: SLF001
    assert threads
    assert all(t is not threading.main_thread() for t in threads)
    await asyncio.sleep(0)
