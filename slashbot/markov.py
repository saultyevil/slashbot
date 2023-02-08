#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Markov chain module
"""

import pickle
import logging
import shutil
from pathlib import Path
from typing import Coroutine
from typing import List
from typing import Dict
import string

import disnake

from slashbot import markovify
from slashbot.config import App
from slashbot.error import deferred_error_message

logger = logging.getLogger(App.config("LOGGER_NAME"))


# Private functions ------------------------------------------------------------


def __clean_sentences_for_learning(sentences: List[str]) -> List[str]:
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
        if len(sentence) == 0:
            continue
        # ignore commands, which usually start with punctuation
        if sentence.startswith(string.punctuation):
            continue
        # don't want to learn how to mention :)
        if "@" in sentence:
            continue
        clean_sentences.append(sentence)

    return clean_sentences


# Public functions -------------------------------------------------------------


def load_markov_model(chain_location: str | Path) -> markovify.Text:
    """Load a Markovify model.

    If a chain exists at chain_location, this is read in and applied. Otherwise
    a new model is created which is practically empty.

    Parameters
    ----------
    chain_location : str | Path
        The location of the markov chain to load. Must be a pickle.

    Returns
    -------
    markovify.Text
        The Markov Chain model loaded.
    """
    if not isinstance(str, Path):
        chain_location = Path(chain_location)

    model = markovify.Text("Jack is a naughty boy. Edward is a good boy.")
    if chain_location.exists():
        with open(chain_location, "rb") as file_in:
            model.chain = pickle.load(file_in)

    return model


MARKOV_MODEL = load_markov_model(App.config("MARKOV_CHAIN_FILE"))


def generate_sentence(model: markovify.Text = None, seed_word: str = None, attempts: int = 5) -> str:
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
    if not model:
        model = MARKOV_MODEL

    sentence = "My Markov chain isn't working properly!"

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
        sentence = model.make_sentence()

    return sentence.strip()[:1024]


async def update_markov_chain_for_model(
    inter: disnake.ApplicationCommandInteraction,
    model: markovify.Text,
    new_messages: List[str],
    save_location: str | Path,
) -> Coroutine | None | markovify.Text:
    """Update a Markov chain model.

    Can be used either with a command interaction, or by itself.

    Parameters
    ----------
    inter : disnake.ApplicationCommandInteraction
        A Discord interaction with a deferred response.
    model : markovify.Text
        The model to update with new messages.
    new_messages : List[str]
        A list of strings to update the chain with.
    save_location : str | Path
        The location the save the chain.

    Returns
    -------
    Coroutine | None
        Either the updated model, a co-routine for a interaction, or None
        when no interaction is passed and a model could not be updated.
    """
    if not isinstance(save_location, Path):
        save_location = Path(save_location)

    if len(new_messages) == 0:
        if inter:
            return await deferred_error_message(inter, "No new messages to update chain with.")
        return

    messages = __clean_sentences_for_learning(new_messages)
    if len(messages) == 0:
        if inter:
            return await deferred_error_message(inter, "No new messages to update chain with.")
        return

    shutil.copy2(save_location, str(save_location) + ".bak")
    try:
        new_model = markovify.NewlineText(messages)
    except KeyError:  # I can't remember what causes this... but it can happen when indexing new words
        return await deferred_error_message(inter, "The interim model failed to train.")

    combined_chain = markovify.combine([model.chain, new_model.chain])
    with open(save_location, "wb") as file_out:
        pickle.dump(combined_chain, file_out)
    model.chain = combined_chain

    if inter:
        await inter.edit_original_message(content=f"Markov chain updated with {len(messages)} new messages.")

    return model


def generate_list_of_sentences_with_seed_word(model: markovify.Text, seed_word: str, amount: int) -> List[str]:
    """_summary_

    Parameters
    ----------
    model : markovify.Text
        _description_
    seed_word : str
        _description_
    amount : int, optional
        _description_

    Returns
    -------
    List[str]
        _description_
    """
    logger.debug("Generating %d sentences for seed word %d", amount, seed_word)
    return [generate_sentence(model, seed_word) for _ in range(amount)]


def generate_sentences_for_seed_words(
    model: markovify.Text, seed_words: List[str], amount: int
) -> Dict[str, List[str]]:
    """_summary_

    Parameters
    ----------
    model : markovify.Text
        _description_
    seed_words : List[str]
        _description_
    amount : int
        _description_

    Returns
    -------
    Dict[List[str]]
        _description_
    """
    return {seed_word: generate_list_of_sentences_with_seed_word(model, seed_word, amount) for seed_word in seed_words}
