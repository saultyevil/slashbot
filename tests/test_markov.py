"""Unit tests for markov.py."""

import pytest

from lib import markov


def test_load_model() -> None:
    """Test loading a markov model."""
    model = markov.load_markov_model("data/markov/chain.pickle")
    assert model is not None
    assert model.make_sentence() is not None
