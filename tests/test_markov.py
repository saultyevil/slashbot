from slashbot.markov_class import MarkovTextGenerator


def test_markov_generate(markov_model: MarkovTextGenerator) -> None:
    """Test that Markov generation works."""
    response = markov_model.generate_response()
    assert len(response) == 1
    response = markov_model.generate_response(2)
    assert len(response) == 2
