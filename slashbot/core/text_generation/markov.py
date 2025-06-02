import json
import pickle
import random
import re
import shutil
import string
from pathlib import Path
from textwrap import shorten

import markovify

from slashbot.core.logger import Logger
from slashbot.settings import BotSettings


class MarkovChain(Logger):
    """Markov Chain text generator."""

    def __init__(self, chain_path: str | Path | None = None, bank_path: str | Path | None = None) -> None:
        """Initialize the MarkovChain class.

        Parameters
        ----------
        chain_path : str | Path
            Path to the Markov chain file.
        bank_path : str | Path
            Path to the Markov bank file.

        """
        super().__init__()
        if chain_path:
            self._chain_path = Path(chain_path)
            self._chain = self._init_chain()
        elif bank_path:
            self._bank_path = Path(bank_path)
            self._bank = self._init_bank()
        else:
            msg = "Either chain_path or bank_path must be provided."
            raise ValueError(msg)

    def _init_bank(self) -> dict:
        if not self._bank_path.exists():
            msg = f"Bank file {self._bank_path} does not exist."
            raise FileNotFoundError(msg)

        with self._bank_path.open("r") as file_in:
            bank = json.load(file_in)

        self.log_info("Markov bank %s loaded", self._bank_path)

        return bank

    def _init_chain(self) -> markovify.Text:
        if not self._chain_path.exists():
            msg = f"Chain file {self._chain_path} does not exist."
            raise FileNotFoundError(msg)

        chain = markovify.Text("This is a short string, because we need one. Or maybe two.", state_size=2)
        with self._chain_path.open("rb") as file_in:
            try:
                chain.chain = pickle.load(file_in)  # noqa: S301
            except EOFError:
                shutil.copy2(str(self._chain_path) + ".bak", str(self._chain_path))
                self._init_chain()
        BotSettings.markov.current_chain_location = self._chain_path

        return chain

    def _clean_sentences_for_update(self, sentences: list[str]) -> list[str]:
        pass

    def _get_sentence_from_chain(self, seed_word: str, amount: int = 1) -> str | list[str]:
        pass

    def _get_sentence_from_bank(self, seed_word: str, amount: int = 1) -> str | list[str]:
        pass

    def update_markov_chain(self, new_messages: list[str]) -> None:
        pass

    def generate_text(self) -> str:
        pass
