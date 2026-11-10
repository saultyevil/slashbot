"""Train separate Markov chains from the bot's message archive database."""

import asyncio
from argparse import ArgumentParser
from pathlib import Path

from slashbot.cogs.message_archive.cog import MessageStore
from slashbot.markov import save_chain, train_chain


def load_training_data(database: Path) -> tuple[list[str], list[str]]:
    """Load individual and grouped messages from the archive database.

    Parameters
    ----------
    database : Path
        The bot's message archive database.

    Returns
    -------
    tuple[list[str], list[str]]
        Individual messages followed by grouped messages.

    """
    if not database.exists():
        msg = f"{database} does not exist"
        raise FileNotFoundError(msg)
    return asyncio.run(_load_archive(database))


async def _load_archive(database: Path) -> tuple[list[str], list[str]]:
    """Read both message tables without modifying the archive."""
    store = MessageStore(database)
    try:
        return await store.messages(), await store.grouped_messages()
    finally:
        await store.close()


def train(database: Path, output_dir: Path, *, state_size: int = 2) -> None:
    """Train one chain from each message table in the archive.

    Parameters
    ----------
    database : Path
        The bot's message archive database.
    output_dir : Path
        The directory where to write the new chain to.
    state_size : int
        The state size of the chain. By default, 2.

    """
    messages, grouped_messages = load_training_data(database)
    individual_chain = train_chain(messages, state_size=state_size)
    grouped_chain = train_chain(grouped_messages, state_size=state_size, preserve_messages=True)
    if individual_chain is None:
        msg = "No usable messages in the messages table"
        raise ValueError(msg)
    if grouped_chain is None:
        msg = "No usable messages in the grouped_messages table; check the message archive backfill"
        raise ValueError(msg)

    output_dir.mkdir(parents=True, exist_ok=True)
    individual_file = output_dir / f"chain-{state_size}.pickle"
    grouped_file = output_dir / f"chain_grouped-{state_size}.pickle"
    save_chain(individual_chain, individual_file)
    save_chain(grouped_chain, grouped_file)
    print(f"Individual message chain created at {individual_file.resolve()}")  # noqa: T201
    print(f"Grouped message chain created at {grouped_file.resolve()}")  # noqa: T201


if __name__ == "__main__":
    ap = ArgumentParser(description="Train individual and grouped Markov chains from the bot's message archive.")
    ap.add_argument("database", type=Path, help="The bot's message archive database")
    ap.add_argument("output_dir", type=Path, help="The directory to write the output to")
    ap.add_argument("--state-size", default=2, type=int, help="The state size of the chain")
    args = ap.parse_args()
    train(args.database, args.output_dir, state_size=args.state_size)
