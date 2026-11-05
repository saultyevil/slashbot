"""Generate a new Markov chain for use with MarkovTextGenerator."""

from argparse import ArgumentParser
from pathlib import Path

from slashbot.markov import save_chain, train_chain


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
    chain = train_chain(raw_data, state_size=state_size)
    if chain is None:
        print("No usable training data")
        return

    output_file = output_dir / "chain.pickle"
    save_chain(chain, output_file)

    print(f"New chain created at {output_file.resolve()}")


if __name__ == "__main__":
    ap = ArgumentParser(description="Train a new markov chain.")
    ap.add_argument("input_data", type=Path, help="The text file containing sentences to train on")
    ap.add_argument("output_dir", type=Path, help="The directory to write the output to")
    ap.add_argument("--state-size", default=2, type=int, help="The state size of the chain")
    args = ap.parse_args()
    train(args.input_data, args.output_dir, state_size=args.state_size)
