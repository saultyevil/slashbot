"""Markov sentence generation functions.

This module contains functions for loading and updating Markov chains and
generating sentences using the Markov chain. There is a synchronous and
asynchronous version of sentence generation functions.
"""

import json
import pickle
import random
import re
import shutil
import string
from pathlib import Path
from textwrap import shorten

import markovify

from slashbot.bot.custom_types import ApplicationCommandInteraction
from slashbot.core.logger import Logger
from slashbot.errors import deferred_error_message
from slashbot.settings import BotSettings

LOGGER = Logger()
MARKOV_MODEL = None
MARKOV_BANK = {}


def _search_for_seed_in_markov_bank(seed_word: str) -> str:
    """Search for a sentence in the markov bank for a given seed word.

    Parameters
    ----------
    seed_word : str
        The seed word to search for.

    Returns
    -------
    str
        The markov sentence.

    """
    if seed_word not in MARKOV_BANK:
        LOGGER.log_error("Seed word '%s' not found in markov bank", seed_word)
        sentences = MARKOV_BANK.get(
            "error", ["An error occurred with the markov sentence generation [a seed word is probably missing]"]
        )
        return random.choice(sentences)

    return random.choice(MARKOV_BANK[seed_word])


def _generate_markov_sentence(
    model: markovify.Text | None = None, seed_word: str | None = None, attempts: int = 5
) -> str:
    """Generate a sentence using a markov chain.

    Parameters
    ----------
    model : markovify.Text
        The model to generate the sentence from, by default None
    seed_word : str, optional
        A seed word to include in the sentence, by default None
    attempts : int, optional
        The number of attempts to generate a sentence with a seed word, by
        default 5

    Returns
    -------
    str
        The generated sentence

    """
    sentence = "My Markov Chain sentence generator isn't working!"

    if not model:
        model = MARKOV_MODEL
    if not model or not isinstance(model, markovify.Text):
        LOGGER.log_error("An invalid Markov model was passed to sentence generation")
        return sentence

    for _ in range(attempts):
        if seed_word:
            try:
                if len(seed_word.split()) > 1:
                    sentence = model.make_sentence_with_start(seed_word)
                else:
                    sentence = model.make_sentence_that_contains(seed_word)
            except (IndexError, KeyError, markovify.text.ParamError):
                sentence = model.make_sentence()
        else:
            sentence = model.make_sentence()

        # fallback case, usually when the chain is too sparse for a seed word
        if not sentence:
            sentence = "My Markov chain isn't work properly!"

        # No matter what, don't allow @here and @everyone mentions, but
        # allow user mentions, if mentions == True

        if "@" not in sentence:
            break

    if not sentence:
        sentence = "My Markov chain isn't work properly!"

    return shorten(sentence.strip(), 1024)


def _get_sentence_from_bank(seed_word: str | None, amount: int = 1) -> str | list[str]:
    """Get a sentence from the markov bank.

    Parameters
    ----------
    seed_word : str
        The seed word for the sentence.
    amount : int, optional
        The number of sentences to generate, by default 1

    Returns
    -------
    str | list[str]
        The generated sentence(s).

    """
    if not seed_word:
        seed_word = "?random"
    if amount == 1:
        return _search_for_seed_in_markov_bank(seed_word)
    return [_search_for_seed_in_markov_bank(seed_word) for _ in range(amount)]


def _get_sentence_from_model(model: markovify.Text, seed_word: str | None, amount: int = 1) -> str | list[str]:
    """Get a sentence from the markov model.

    Parameters
    ----------
    model : markovify.Text
        The model to generate the sentence from.
    seed_word : str
        The seed word for the sentence.
    amount : int, optional
        The number of sentences to generate, by default 1

    Returns
    -------
    str | list[str]
        The generated sentence(s).

    """
    if not model or not isinstance(model, markovify.Text):
        msg = "The provided markov model is not valid"
        raise ValueError(msg)
    if amount == 1:
        return _generate_markov_sentence(model, seed_word)
    return [_generate_markov_sentence(model, seed_word) for _ in range(amount)]


def _clean_sentence_for_learning(sentences: list[str]) -> list[str]:
    """Clean up a list of sentences for learning.

    This will remove empty strings, messages which start with punctuation
    and any sentences with @ oi them.

    Parameters
    ----------
    sentences : List[str]
        A list of sentences to clean up for learning.

    Returns
    -------
    List[str]
        The cleaned up list of sentences.

    """
    clean_sentences = []

    for sentence in sentences:
        # ignore empty strings
        if not sentence:
            continue
        # ignore commands, which usually start with punctuation
        if sentence[0] in string.punctuation:
            continue
        # don't want to learn how to mention :)
        if "@" in sentence:
            continue

        clean_sentences.append(sentence)

    return clean_sentences


def load_markov_model(chain_location: str | Path, state_size: int = 2) -> markovify.Text:
    """Load a Markovify markov chain.

    If a chain exists at chain_location, this is read in and applied. Otherwise
    a new model is created which is practically empty.

    Parameters
    ----------
    chain_location : str | Path
        The location of the markov chain to load. Must be a pickle.
    state_size : int
        The state size of the model, defaults to 2.

    Returns
    -------
    markovify.Text
        The Markov Chain model loaded.

    """
    chain_location = Path(chain_location)
    model = markovify.Text(
        "This is an empty markov model. I think you may need two sentences.",
        state_size=state_size if state_size != 0 else 2,
    )

    if chain_location.exists():
        with chain_location.open("rb") as file_in:
            try:
                model.chain = pickle.load(file_in)  # noqa: S301
                LOGGER.log_info("Model %s has been loaded", str(chain_location))
            except EOFError:
                shutil.copy2(str(chain_location) + ".bak", chain_location)
                model = load_markov_model(chain_location, state_size)  # the recursion might be a bit spicy here
    else:
        msg = f"No chain at {chain_location}"
        raise OSError(msg)

    BotSettings.markov.current_chain_location = chain_location

    return model


def load_markov_bank(bank_location: str | Path) -> dict:
    """Load a pre-generated bank of Markov sentences.

    This file should be a JSON file with the following format:

        {
            "seed_word": [sentence1, sentence2, ...]
        }

    Parameters
    ----------
    bank_location : str | Path
        The file path to the bank file.

    Returns
    -------
    dict
        The bank of Markov sentences, as a dict.

    """
    path = Path(bank_location)
    if not path.exists():
        msg = f"No bank at {bank_location}"
        raise OSError(msg)

    with path.open("r") as file_in:
        bank = json.load(file_in)

    LOGGER.log_info("Markov bank %s has been loaded", bank_location)

    return bank


async def update_markov_chain_for_model(  # noqa: PLR0911
    inter: ApplicationCommandInteraction | None,
    model: markovify.Text,
    new_messages: list[str],
    save_location: str | Path,
) -> markovify.Text | None:
    """Update a Markov chain model.

    Can be used either with a command interaction, or by itself.

    Parameters
    ----------
    inter : ApplicationCommandInteraction
        A Discord interaction with a deferred response.
    model : markovify.Text
        The model to update with new messages.
    new_messages : List[str]
        A list of strings to update the chain with.
    save_location : str | Path
        The location the save the chain.

    Returns
    -------
    markovify.Text | None
        Either the updated model, a co-routine for a interaction, or None
        when no interaction is passed and a model could not be updated.

    """
    if not model or not isinstance(model, markovify.Text):
        msg = "The provided markov model is not valid"
        raise ValueError(msg)

    if not isinstance(save_location, Path):
        save_location = Path(save_location)

    state_size = int(re.findall(r"\d+", save_location.name)[0])

    if len(new_messages) == 0:
        if inter:
            await deferred_error_message(inter, "No new messages to update chain with.")
            return None
        LOGGER.log_info("No sentences to update chain with")
        return None

    messages = _clean_sentence_for_learning(new_messages)
    num_messages = len(messages)

    if num_messages == 0:
        if inter:
            await deferred_error_message(inter, "No new messages to update chain with.")
            return None
        LOGGER.log_info("No sentences to update chain with")
        return None

    shutil.copy2(save_location, str(save_location) + ".bak")
    try:
        new_model = markovify.NewlineText("\n".join(messages), state_size=state_size if state_size != 0 else 2)
    except KeyError:  # I can't remember what causes this... but it can happen when indexing new words
        if inter:
            await deferred_error_message(inter, "The interim model failed to train.")
            return None
        LOGGER.log_exception("The interim model failed to train.")
        return None

    combined_chain = markovify.combine([model.chain, new_model.chain])
    with Path.open(save_location, "wb") as file_out:
        pickle.dump(combined_chain, file_out)
    model.chain = combined_chain

    if inter:
        await inter.edit_original_message(content=f"Markov chain updated with {num_messages} new messages.")

    # num_messages should already but an int, but sometimes it isn't...
    LOGGER.log_info(
        "Markov chain (%s) updated with %d new messages",
        str(save_location),
        int(num_messages),
    )

    return model


def generate_text_from_markov_chain(model: markovify.Text, seed_word: str | None, amount: int) -> str | list[str]:
    """Generate a list of markov generated sentences for a specific key word.

    Parameters
    ----------
    model : markovify.Text
        The markov model to use to generate sentences.
    seed_word : str | None
        The seed word to use.
    amount : int, optional
        The number of sentences to generate.

    Returns
    -------
    str | list[str]
        The generated sentence(s), as a str or a list of str.

    """
    if model and isinstance(model, markovify.Text):
        return _get_sentence_from_model(model, seed_word, amount)
    if MARKOV_MODEL:
        return _get_sentence_from_model(MARKOV_MODEL, seed_word, amount)
    return _get_sentence_from_bank(seed_word, amount)
