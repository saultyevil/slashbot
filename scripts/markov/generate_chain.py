"""Generate a new Markov chain for use with MarkovTextGenerator.

The training data is either a text file, with one sentence per line, or the
message archive database (a .db file) written by the message archive cog.
"""

import asyncio
from argparse import ArgumentParser
from pathlib import Path

from slashbot.cogs.message_archive.cog import MessageStore
from slashbot.markov import save_chain, train_chain

DATABASE_SUFFIXES = {".db", ".sqlite"}


def load_training_data(input_data: Path) -> list[str]:
    """Load the training sentences from a text file or a message archive.

    Parameters
    ----------
    input_data : Path
        Either a text file with one sentence per line, or the message archive
        database.

    Returns
    -------
    list[str]
        The sentences to train on.

    """
    if not input_data.exists():
        msg = f"{input_data} does not exist"
        raise FileNotFoundError(msg)

    if input_data.suffix in DATABASE_SUFFIXES:
        return asyncio.run(_load_archive(input_data))
    return input_data.read_text().split("\n")


async def _load_archive(database: Path) -> list[str]:
    """Read all of the messages from a message archive."""
    store = MessageStore(database)
    try:
        await store.init()
        return await store.messages()
    finally:
        await store.close()


def train(input_data: Path, output_dir: Path, *, state_size: int = 2) -> None:
    """Train a new Markov chain.

    Parameters
    ----------
    input_data : Path
        The input data to train the model on, either a text file or a message
        archive database.
    output_dir : Path
        The directory where to write the new chain to.
    state_size : int
        The state size of the chain. By default, 2.

    """
    raw_data = load_training_data(input_data)
    chain = train_chain(raw_data, state_size=state_size)
    if chain is None:
        print("No usable training data")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "chain.pickle"
    save_chain(chain, output_file)

    print(f"New chain created at {output_file.resolve()}")


if __name__ == "__main__":
    ap = ArgumentParser(description="Train a new markov chain.")
    ap.add_argument(
        "input_data", type=Path, help="A text file of sentences, or the message archive database (.db), to train on"
    )
    ap.add_argument("output_dir", type=Path, help="The directory to write the output to")
    ap.add_argument("--state-size", default=2, type=int, help="The state size of the chain")
    args = ap.parse_args()
    train(args.input_data, args.output_dir, state_size=args.state_size)
