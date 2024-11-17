"""Unit tests for markov.py."""

import pytest

from slashbot import markov, markovify


@pytest.fixture()
def markov_model() -> markovify.Text:
    """Load the test markov model."""
    return markov.load_markov_model("data/markov/chain.pickle")


def test_load_model(markov_model: markovify.Text) -> None:
    """Test that the markov model load."""
    assert markov_model is not None
    assert markov_model.make_sentence() is not None


def test_clean_sentences_for_cleaning() -> None:
    """Test sentence cleaning for training the markov model."""
    sentences = ["", "!test", ">test", "?test", "sentence w/ @mention", "this should be fine", "punctuation.!?"]
    cleaned = markov._clean_sentence_for_learning(sentences)
    assert len(cleaned) == 2
    assert cleaned[0] == "this should be fine"
    assert cleaned[1] == "punctuation.!?"


def test_generate_markov_sentence(markov_model: markovify.Text) -> None:
    """Test single sentence generation."""
    sentence = markov._generate_markov_sentence(markov_model)
    assert sentence is not None
    seeded_sentence = markov._generate_markov_sentence(markov_model, seed_word="hello")
    assert "hello" in seeded_sentence


def test_update_markov_chain_for_model() -> None:
    """Test that markov models can be updated."""


def test_generate_list_of_sentences_with_seed_word(markov_model: markovify.Text) -> None:
    """Test that multiple sentences can be generated for a given a seed."""
    sentences = markov.generate_list_of_sentences_with_seed_word(markov_model, "hello", 3)
    for sentence in sentences:
        assert "hello" in sentence


def test_generate_sentences_for_seed_words(markov_model: markovify.Text) -> None:
    """Tests that multiple sentences are generated for multiple seed words."""
    sentences_dict = markov.generate_sentences_for_seed_words(markov_model, ["hello", "goodbye"], 3)
    for seed, sentences in sentences_dict.items():
        for sentence in sentences:
            assert seed in sentence
