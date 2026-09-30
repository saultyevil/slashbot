import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass

from spellchecker import SpellChecker


@dataclass
class UserSpellCheck:
    """Store the checked word count and incorrect spellings for a user."""

    total: int
    incorrect: list[str]


def cleanup_message(text: str) -> str:
    """Remove non-prose content and normalize words for spell-checking.

    Parameters
    ----------
    text : str
        The message content to clean.

    Returns
    -------
    str
        The normalized, space-separated words to check.

    """
    clean_text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.IGNORECASE)
    clean_text = re.sub(r"```.*?```", " ", clean_text, flags=re.DOTALL)
    clean_text = re.sub(r"`[^`\n]*`", " ", clean_text)
    clean_text = re.sub(r"<@!?\d+>|<@&\d+>|<#\d+>", " ", clean_text)
    normalized_text = unicodedata.normalize("NFKD", clean_text.lower())
    normalized_text = "".join(char for char in normalized_text if not unicodedata.combining(char))
    words = re.findall(r"[^\W\d_]+(?:['\u2019][^\W\d_]+)*", normalized_text, flags=re.UNICODE)
    return " ".join(words)


def get_incorrect_words(words: list[str], spellchecker: SpellChecker, custom_words: Collection[str]) -> list[str]:
    """Return each checked word that is not in the spelling dictionaries.

    Parameters
    ----------
    words : list[str]
        The normalized words to check.
    spellchecker : SpellChecker
        The spellchecker used to identify unknown words.
    custom_words : Collection[str]
        Words that should be treated as correctly spelled.

    Returns
    -------
    list[str]
        The incorrect words, including repeated occurrences.

    """
    unknown_words = spellchecker.unknown(words).difference(custom_words)
    return [word for word in words if word in unknown_words]


def join_list_into_csv(words: list[str], max_chars: int) -> str:
    """Join words into a comma-separated string within a character limit.

    Parameters
    ----------
    words : list[str]
        The words to join.
    max_chars : int
        The maximum length of the returned string.

    Returns
    -------
    str
        The joined words, with an ellipsis if the character limit is reached.

    """
    result = ""
    current_length = 0

    for word in words:
        if current_length + len(word) > max_chars - 3:
            if result:
                result += "..."
            break
        result += word + ", "
        current_length += len(word)

    return result.removesuffix(", ")
