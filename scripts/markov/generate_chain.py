"""Generate a new Markov chain for use with MarkovTextGenerator."""

import pickle
from argparse import ArgumentParser
from pathlib import Path

from markovify import Text


def clean(text: str) -> str:
    """Clean up a sentence ready for training.

    Parameters
    ----------
    text : str
        Text to be cleaned up for training.

    Returns
    -------
    str
        The cleaned up text.

    """
    clean = text
    # Put rules and stuff here to clean up the sentence

    return clean


def prepare_training_data(input_data: list[str]) -> str:
    """Prepare the input data for training.

    Parameters
    ----------
    input_data : list[str]
        A list of strings to train the model on.


    Returns
    -------
    str
        The cleaned up text ready for training.

    """
    return ". ".join([clean(sentence) for sentence in input_data])


def train(input_data: Path, output_dir: Path, *, state_size: int = 2) -> None:
    """Train a new Markov chain.

    Parameters
    ----------
    input_data : Path
        The input data to train the model on.
    output_dir : Path
        The directory where to write the new chain to.
    state_size : int
        The state size of the chain. By default, 2.

    """
    raw_data = input_data.read_text().split("\n")
    training_data = prepare_training_data(raw_data)

    model = Text(training_data, state_size=state_size)

    output_file = output_dir / "chain.pickle"
    with output_file.open("wb") as file_out:
        pickle.dump(model.chain, file_out)

    print(f"New chain created at {output_file.resolve()}")


if __name__ == "__main__":
    ap = ArgumentParser(description="Train a new markov chain.")
    ap.add_argument("input_data", type=Path, help="The text file containing sentences to train on")
    ap.add_argument("output_dir", type=Path, help="The directory to write the output to")
    ap.add_argument("--state-size", default=2, type=int, help="The state size of the chain")
    args = ap.parse_args()
    train(args.input_data, args.output_dir)
