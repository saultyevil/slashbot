from pathlib import Path

import pytest
from spellchecker import SpellChecker

from slashbot.cogs.spelling.dictionary import add_word, load_words, remove_word, save_words
from slashbot.cogs.spelling.processing import cleanup_message, get_incorrect_words, join_list_into_csv


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("don't well-known cafe\u0301", "don't well known cafe"),
        ("https://example.com badspeling", "badspeling"),
        ("```python\nprint(`x`)\n``` tail", "tail"),
        ("<@!123> hello word_2", "hello word"),
    ],
)
def test_cleanup_message(message: str, expected: str) -> None:
    """Clean message content into words suitable for spell-checking."""
    assert cleanup_message(message) == expected


def test_get_incorrect_words_preserves_occurrences() -> None:
    """Return every occurrence of an unknown word except custom words."""
    spellchecker = SpellChecker(case_sensitive=False)

    assert get_incorrect_words(["badspeling", "badspeling", "hello"], spellchecker, {"hello"}) == [
        "badspeling",
        "badspeling",
    ]


def test_join_list_into_csv_truncates() -> None:
    """Truncate a CSV string when it reaches the configured limit."""
    assert join_list_into_csv(["one", "two", "three"], 12) == "one, two, ..."


def test_dictionary_mutations_normalize_words() -> None:
    """Add and remove dictionary words case-insensitively."""
    words = ["hello"]

    assert add_word(words, "World") == "world"
    assert add_word(words, "WORLD") is None
    assert remove_word(words, "HELLO") == "hello"
    assert remove_word(words, "missing") is None
    assert words == ["world"]


def test_dictionary_persistence(tmp_path: Path) -> None:
    """Persist and load normalized dictionary words."""
    path = tmp_path / "words.txt"
    save_words(path, ["Hello", "world", "hello", ""])

    assert load_words(path) == ["hello", "world"]
