"""Markov text generator.

This module contains a class for text generation using a trained Markov Chain.
"""

import json
import pickle
import random
from enum import Enum, auto
from pathlib import Path
from textwrap import shorten
from typing import Any

import markovify

from slashbot.logger import Logger


class MarkovGeneratorType(Enum):
    """Enumerator for different type of Markov generator.

    The MarkovTextGenerator can either used a pre-generated json file of seed
    words and sentences, or use a Markovify Text class to generate on-the-fly
    responses.
    """

    UNKNOWN = auto()
    PREGEN = auto()
    ON_THE_FLY = auto()


class Pregen(Logger):
    """Markov generation using pre-generated sentences."""

    def __init__(self, markov_data: Path) -> None:
        """Initialise the class.

        Parameters
        ----------
        markov_data : Path
            The file path to the .json file containing seed words and sentences.

        """
        super().__init__()

        if not markov_data.exists():
            exc_msg = f"Unable to open {markov_data}. Does it exist?"
            raise FileNotFoundError(exc_msg)

        with markov_data.open("r") as file_in:
            self.model = json.load(file_in)

    def generate(self, seed_word: str | None = None) -> str:
        """Generate a sentence, optionally containing a given seed word.

        Parameters
        ----------
        seed_word : str | None
            An optional seed word to include in the generated sentence.

        Returns
        -------
        str
            The generated sentence.

        """
        seed = seed_word if seed_word else "?random"

        if seed not in self.model:
            seed = "?random"

        return random.choice(self.model.get(seed))


class OnTheFly(Logger):
    """On-the-fly markov sentence generation."""

    def __init__(self, markov_data: Path, *, state_size: int = 2, attempts: int = 5) -> None:
        """Initialise the class.

        Parameters
        ----------
        markov_data : Path
            The file path to the .chain or .pickle file containing the Markovify
            markov chain.
        state_size : int
            The state size of the Markov chain, by default 2. This controls the
            number of words which the probability of the next generated word
            depends on. For example, a state size of 2 uses two words. A state
            size of 1 will only use the last word and create very interesting
            sentences.
        attempts : int
            The number of attempts to try and generate a sentence containing
            the seed word.

        """
        super().__init__()
        if not isinstance(state_size, int) or state_size < 1:
            exc_msg = "state_size should be a non-negative and non-zero integer"
            raise TypeError(exc_msg)

        if not markov_data.exists():
            exc_msg = f"Unable to open {markov_data}. Does it exist?"
            raise FileNotFoundError(exc_msg)

        self._state_size = state_size
        self._attempts = attempts

        self._model = markovify.Text(
            "This is an empty model. You need at least two sentences, I think.",
            state_size=self._state_size,
        )

        with markov_data.open("rb") as file_in:
            self._model.chain = pickle.load(file_in)  # noqa: S301

    def generate(self, seed_word: str | None) -> str:
        """Generate a sentence, optionally containing a given seed word.

        Parameters
        ----------
        seed_word : str | None
            An optional seed word to include in the generated sentence.

        Returns
        -------
        str
            The generated sentence.

        """
        attempts = self._attempts if seed_word else 1
        sentence = "My Markov Chain is not working :-("

        for _ in range(attempts):
            if seed_word:
                try:
                    sentence = self._model.make_sentence_that_contains(seed_word)
                except (IndexError, KeyError, markovify.text.ParamError):
                    sentence = self._model.make_sentence()
                if not sentence:
                    sentence = "My Markov Chain is not working :-("
                if seed_word in sentence:
                    break
            else:
                sentence = self._model.make_sentence()

        if not sentence:
            sentence = "My Markov Chain is not working :-("

        return shorten(sentence.strip(), 1024)


class MarkovTextGenerator(Logger):
    """Generate text using a pre-trained Markov chain.

    The MarkovTextGenerator can either used a pre-generated json file of seed
    words and sentences, or use a Markovify Text class to generate on-the-fly
    responses.
    """

    def __init__(self, markov_data: Path, **kwargs: dict[Any, Any]) -> None:
        """Initisliation method.

        Parameters
        ----------
        markov_data : Path
            A file path to a file containing markov chain data to load.
        kwargs : dict[Any, Any]
            Additional keyword arguments to pass.

        """
        super().__init__(*kwargs, prepend_msg="[MarkovTextGenerator]")

        if markov_data.suffix not in [".json", ".chain", ".pickle"]:
            exc_msg = f"Unable to open {markov_data.suffix} file for Markov data. Expected .json, .chain or .pickle."
            raise TypeError(exc_msg)

        self.type = MarkovGeneratorType.UNKNOWN
        self._model = self._load_markov_data(markov_data)
        self.log_info("MarkovTextGenerator type %s loaded using %s", self.type, markov_data.resolve())

    # Private API --------------------------------------------------------------

    def _load_markov_bank(self, markov_data: Path) -> Pregen:
        return Pregen(markov_data)

    def _load_markov_chain(self, markov_data: Path) -> OnTheFly:
        return OnTheFly(markov_data)

    def _load_markov_data(self, markov_data: Path) -> Pregen | OnTheFly:
        self.type = MarkovGeneratorType.PREGEN if markov_data.suffix == ".json" else MarkovGeneratorType.ON_THE_FLY
        return (
            self._load_markov_bank(markov_data)
            if self.type == MarkovGeneratorType.PREGEN
            else self._load_markov_chain(markov_data)
        )

    # Public API ---------------------------------------------------------------

    def generate_response(self, amount: int = 1, seed_word: str | None = None) -> list[str]:
        """Generate a response from the Markov chain.

        Parameters
        ----------
        amount : int
            The number of sentences to generate. By default one sentence is
            generated.
        seed_word : str | None
            An optional seed word to include in the generated response.

        Returns
        -------
        str
            The generated response.

        """
        return [self._model.generate(seed_word) for _ in range(amount)]
