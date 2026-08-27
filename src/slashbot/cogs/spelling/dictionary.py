from pathlib import Path


def load_words(path: Path) -> list[str]:
    """Load normalized custom dictionary words from a file.

    Parameters
    ----------
    path : pathlib.Path
        The file containing one word per line.

    Returns
    -------
    list[str]
        The unique, normalized words in the dictionary.

    Raises
    ------
    OSError
        If the dictionary file cannot be read.

    """
    with path.open(encoding="utf-8") as file_in:
        return sorted({line.strip().lower() for line in file_in if line.strip()})


def save_words(path: Path, words: list[str]) -> None:
    """Save custom dictionary words to a file.

    Parameters
    ----------
    path : pathlib.Path
        The file to write.
    words : list[str]
        The words to write, one per line.

    """
    path.write_text("\n".join(words), encoding="utf-8")


def add_word(words: list[str], word: str) -> str | None:
    """Add a word to a custom dictionary in place.

    Parameters
    ----------
    words : list[str]
        The dictionary to update.
    word : str
        The word to add.

    Returns
    -------
    str or None
        The normalized word when added, or ``None`` when it already exists.

    """
    normalized_word = word.lower()
    if normalized_word in words:
        return None
    words.append(normalized_word)
    return normalized_word


def remove_word(words: list[str], word: str) -> str | None:
    """Remove a word from a custom dictionary in place.

    Parameters
    ----------
    words : list[str]
        The dictionary to update.
    word : str
        The word to remove.

    Returns
    -------
    str or None
        The normalized word when removed, or ``None`` when it does not exist.

    """
    normalized_word = word.lower()
    if normalized_word not in words:
        return None
    words.remove(normalized_word)
    return normalized_word
