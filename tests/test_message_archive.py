from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

from slashbot.cogs.message_archive.cog import MessageArchive, MessageStore
from slashbot.markov import train_chain
from slashbot.settings import BotSettings


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> MessageStore:
    """Create a store in a directory which does not exist yet."""
    store = MessageStore(tmp_path / "nested" / "messages.db")
    await store.init()
    yield store
    await store.close()


def _message(
    msg_id: int, content: str, *, bot: bool = False, guild: bool = True, author_id: int = 1
) -> SimpleNamespace:
    return SimpleNamespace(
        id=msg_id,
        clean_content=content,
        author=SimpleNamespace(bot=bot, id=author_id),
        channel=SimpleNamespace(id=1),
        guild=object() if guild else None,
    )


def _cog(store: MessageStore) -> SimpleNamespace:
    return SimpleNamespace(store=store, _should_archive=MessageArchive._should_archive)  # noqa: SLF001


@pytest.mark.asyncio
async def test_group_consecutive_messages(store: MessageStore) -> None:
    """Adjacent messages from the same author are joined without changing case."""
    await store.upsert(1, "hello", author_id=10, channel_id=100)
    await store.upsert(2, "what is up guys?", author_id=10, channel_id=100)
    await store.upsert(3, "how is everyone doing?", author_id=10, channel_id=100)
    await store.upsert(4, "Good thanks!", author_id=20, channel_id=100)
    await store.upsert(5, "another channel", author_id=10, channel_id=200)
    assert await store.grouped_messages() == [
        "hello. what is up guys? how is everyone doing?",
        "Good thanks!",
        "another channel",
    ]
    assert await store.count() == 5  # noqa: PLR2004


@pytest.mark.asyncio
async def test_groups_handle_out_of_order_messages_edits_and_deletions(store: MessageStore) -> None:
    """Historical inserts and later edits keep groups and individual messages consistent."""
    await store.upsert(4, "again", author_id=10, channel_id=100)
    await store.upsert(2, "reply", author_id=20, channel_id=100)
    await store.upsert(1, "hello", author_id=10, channel_id=100)
    await store.upsert(3, "what?", author_id=10, channel_id=100)
    assert await store.grouped_messages() == ["hello", "reply", "what? again"]

    await store.update_if_present(3, "Fine!")
    assert await store.grouped_messages() == ["hello", "reply", "Fine! again"]
    await store.delete(2)
    assert await store.grouped_messages() == ["hello. Fine! again"]
    await store.delete(3)
    assert await store.grouped_messages() == ["hello. again"]
    await store.upsert(2, "back", author_id=20, channel_id=100)
    assert await store.grouped_messages() == ["hello", "back", "again"]


@pytest.mark.asyncio
async def test_filtered_messages_are_boundaries(store: MessageStore) -> None:
    """Messages omitted from the original archive still interrupt a group."""
    cog = _cog(store)
    for message in [
        _message(1, "one"),
        _message(3, "two"),
        _message(2, "/command"),
        _message(4, "bot", bot=True),
        _message(5, "three"),
    ]:
        await MessageArchive.archive_message(cog, message)
    assert await store.messages() == ["one", "two", "three"]
    assert await store.grouped_messages() == ["one", "two", "three"]

    await MessageArchive.remove_deleted_message(cog, SimpleNamespace(message_id=2))
    assert await store.grouped_messages() == ["one. two", "three"]
    await MessageArchive.update_edited_message(cog, _message(3, "two"), _message(3, "/changed"))
    assert await store.grouped_messages() == ["one", "three"]
    await MessageArchive.update_edited_message(cog, _message(3, "/changed"), _message(3, "restored"))
    assert await store.grouped_messages() == ["one. restored", "three"]


@pytest.mark.asyncio
async def test_groups_persist_and_channel_order_is_independent(tmp_path: Path) -> None:
    """Interleaved channels are grouped independently and survive reopening."""
    path = tmp_path / "messages.db"
    first = MessageStore(path)
    await first.init()
    await first.upsert(1, "first", author_id=10, channel_id=100)
    await first.upsert(2, "elsewhere", author_id=20, channel_id=200)
    await first.upsert(3, "second", author_id=10, channel_id=100)
    await first.mark_grouping_backfilled(100)
    await first.close()

    second = MessageStore(path)
    await second.init()
    assert await second.grouped_messages() == ["first. second", "elsewhere"]
    assert await second.grouping_backfilled(100)
    assert not await second.grouping_backfilled(200)
    await second.close()


@pytest.mark.asyncio
async def test_store_upsert_replace_delete(store: MessageStore) -> None:
    """Messages are stored once per ID, can be replaced and deleted."""
    await store.upsert(1, "hello there")
    await store.upsert(2, "general kenobi")
    await store.upsert(1, "hello again")
    assert await store.messages() == ["hello again", "general kenobi"]
    assert await store.count() == 2  # noqa: PLR2004
    await store.delete(1)
    await store.delete(99)
    assert await store.messages() == ["general kenobi"]


@pytest.mark.asyncio
async def test_store_update_if_present(store: MessageStore) -> None:
    """Updating a message which is not stored does nothing."""
    await store.update_if_present(5, "not there")
    assert await store.count() == 0
    await store.upsert(5, "old")
    await store.update_if_present(5, "new")
    assert await store.messages() == ["new"]


@pytest.mark.asyncio
async def test_store_persists(tmp_path: Path) -> None:
    """Messages survive reopening the database."""
    path = tmp_path / "messages.db"
    first = MessageStore(path)
    await first.init()
    await first.upsert(1, "persisted")
    await first.close()
    second = MessageStore(path)
    await second.init()
    assert await second.messages() == ["persisted"]
    await second.close()


@pytest.mark.asyncio
async def test_archive_message_filters(store: MessageStore) -> None:
    """Only clean human messages from servers are archived."""
    cog = _cog(store)
    for message in [
        _message(1, "a good message"),
        _message(2, "from a bot", bot=True),
        _message(3, "in a dm", guild=False),
        _message(4, "/command"),
        _message(5, "hello @someone"),
        _message(6, "   "),
        _message(7, "  spaced   out  "),
    ]:
        await MessageArchive.archive_message(cog, message)
    assert await store.messages() == ["a good message", "   ", "  spaced   out  "]


@pytest.mark.asyncio
async def test_edit_and_delete(store: MessageStore) -> None:
    """Edits update stored messages and deletes remove them."""
    cog = _cog(store)
    await MessageArchive.archive_message(cog, _message(1, "original"))
    await MessageArchive.archive_message(cog, _message(2, "other"))

    await MessageArchive.update_edited_message(cog, _message(1, "original"), _message(1, "edited"))
    assert await store.messages() == ["edited", "other"]

    # an edit which is no longer learnable removes the message
    await MessageArchive.update_edited_message(cog, _message(1, "edited"), _message(1, "/edited"))
    assert await store.messages() == ["other"]

    # bots are ignored
    await MessageArchive.update_edited_message(cog, _message(2, "other"), _message(2, "changed", bot=True))
    assert await store.messages() == ["other"]

    await MessageArchive.remove_deleted_message(cog, SimpleNamespace(message_id=2))
    assert await store.messages() == []


@pytest.mark.asyncio
async def test_archive_can_train_chain(store: MessageStore) -> None:
    """The archived messages can be used directly to train a chain."""
    cog = _cog(store)
    corpus = ["the cat sat on the mat", "the dog ate the bone", "the cat ate the bone today"]
    for i, text in enumerate(corpus):
        await MessageArchive.archive_message(cog, _message(i, text))
    assert train_chain(await store.messages()) is not None


class _Channel:
    """A fake channel with a newest-first message history."""

    def __init__(self, messages: list[SimpleNamespace]) -> None:
        self._messages = messages
        self.seen = 0

    async def history(self, limit: int | None) -> AsyncIterator[SimpleNamespace]:
        for message in self._messages[:limit]:
            self.seen += 1
            yield message


@pytest.mark.asyncio
async def test_backfill_stops_at_archived_message(store: MessageStore) -> None:
    """Backfilling adds missed messages and stops at the first archived one."""
    await store.upsert(3, "already here")
    cog = SimpleNamespace(store=store, _should_archive=MessageArchive._should_archive)  # noqa: SLF001
    cog._backfill_channel = lambda c, n: MessageArchive._backfill_channel(cog, c, n)  # noqa: SLF001
    channel = _Channel(
        [
            _message(6, "newest message"),
            _message(5, "a bot said this", bot=True),
            _message(4, "/command"),
            _message(3, "already here"),
            _message(2, "should not be reached"),
        ]
    )
    assert await cog._backfill_channel(channel, 100) == 1  # noqa: SLF001
    assert await store.messages() == ["already here", "newest message"]
    assert channel.seen == 4  # noqa: PLR2004

    # running again adds nothing and does not duplicate
    assert await cog._backfill_channel(_Channel([_message(6, "newest message"), _message(3, "x")]), 100) == 0  # noqa: SLF001
    assert await store.count() == 2  # noqa: PLR2004


@pytest.mark.asyncio
async def test_backfill_respects_limit(store: MessageStore) -> None:
    """Only the configured number of messages are examined."""
    cog = SimpleNamespace(store=store, _should_archive=MessageArchive._should_archive)  # noqa: SLF001
    channel = _Channel([_message(i, f"message {i}") for i in range(10, 0, -1)])
    assert await MessageArchive._backfill_channel(cog, channel, 3) == 3  # noqa: SLF001, PLR2004


@pytest.mark.asyncio
async def test_full_backfill_ignores_limit_and_archived(store: MessageStore) -> None:
    """A full backfill reads the whole history, even past archived messages."""
    await store.upsert(10, "archived live while backfilling")
    cog = SimpleNamespace(store=store, _should_archive=MessageArchive._should_archive)  # noqa: SLF001
    channel = _Channel([_message(i, f"message {i}") for i in range(10, 0, -1)])
    added = await MessageArchive._backfill_channel(cog, channel, None, stop_at_archived=False)  # noqa: SLF001
    assert added == 10  # noqa: PLR2004
    assert await store.count() == 10  # noqa: PLR2004
    assert channel.seen == 10  # noqa: PLR2004


@pytest.mark.asyncio
async def test_full_backfill_groups_existing_archive(store: MessageStore) -> None:
    """A historical scan adds grouping information to pre-existing messages."""
    await store.upsert(1, "hello")
    await store.upsert(2, "what is up?")
    cog = _cog(store)
    channel = _Channel([_message(3, "fine", author_id=2), _message(2, "what is up?"), _message(1, "hello")])
    await MessageArchive._backfill_channel(cog, channel, None, stop_at_archived=False)  # noqa: SLF001
    assert await store.grouped_messages() == ["hello. what is up?", "fine"]
    assert await store.messages() == ["hello", "what is up?", "fine"]


@pytest.mark.asyncio
async def test_backfill_scans_existing_archive_once(store: MessageStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing archives get a full scan, then use the normal bounded catch-up."""
    await store.upsert(1, "oldest")
    channel = _Channel([_message(3, "newest"), _message(2, "middle"), _message(1, "oldest")])
    channel.id = 1
    channel.permissions_for = lambda _: SimpleNamespace(read_message_history=True)
    guild = SimpleNamespace(text_channels=[channel], threads=[], me=object())
    cog = SimpleNamespace(
        store=store,
        bot=SimpleNamespace(guilds=[guild]),
        _should_archive=MessageArchive._should_archive,  # noqa: SLF001
        log_info=lambda *_args: None,
        log_exception=lambda *_args: None,
    )
    cog._backfill_channel = lambda *args, **kwargs: MessageArchive._backfill_channel(cog, *args, **kwargs)  # noqa: SLF001
    monkeypatch.setattr(BotSettings.cogs.message_archive, "backfill_limit", 2)

    await MessageArchive.backfill_archive.coro(cog)
    assert channel.seen == 3  # noqa: PLR2004
    assert await store.grouped_messages() == ["oldest. middle. newest"]
    assert await store.grouping_backfilled(channel.id)

    await MessageArchive.backfill_archive.coro(cog)
    assert channel.seen == 4  # noqa: PLR2004


@pytest.mark.asyncio
async def test_generate_chain_script_from_archive(store: MessageStore, tmp_path: Path) -> None:
    """The training script can train from the message archive database."""
    import importlib.util
    import pickle
    import shutil

    for i, text in enumerate(["the cat sat on the mat", "the dog ate the bone", "the cat ate the bone today"]):
        await store.upsert(i, text, author_id=1, channel_id=1)
    await store.close()

    script = Path(__file__).parent / "../scripts/markov/generate_chain.py"
    spec = importlib.util.spec_from_file_location("generate_chain", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    database = next((tmp_path / "nested").glob("messages.db"))
    custom_database = tmp_path / "messages.archive"
    shutil.copyfile(database, custom_database)
    # asyncio.run cannot be nested, so the script is run from a worker thread
    import asyncio

    messages, grouped_messages = await asyncio.to_thread(module.load_training_data, database)
    assert len(messages) == 3  # noqa: PLR2004
    assert grouped_messages == ["the cat sat on the mat. the dog ate the bone. the cat ate the bone today"]
    with pytest.raises(FileNotFoundError):
        await asyncio.to_thread(module.load_training_data, tmp_path / "missing.db")

    await asyncio.to_thread(module.train, custom_database, tmp_path / "out", state_size=1)
    with (tmp_path / "out" / "chain.pickle").open("rb") as f:
        regular_chain = pickle.load(f)  # noqa: S301
    with (tmp_path / "out" / "chain_grouped.pickle").open("rb") as f:
        grouped_chain = pickle.load(f)  # noqa: S301
    assert regular_chain.state_size == grouped_chain.state_size == 1
    assert "the" not in regular_chain.model[("mat",)]
    assert grouped_chain.model[("mat.",)] == {"the": 1}


@pytest.mark.asyncio
async def test_generate_chain_script_requires_grouped_messages(store: MessageStore, tmp_path: Path) -> None:
    """An incomplete archive cannot silently produce only the individual chain."""
    import asyncio
    import importlib.util

    await store.upsert(1, "an individual message")
    await store.close()
    script = Path(__file__).parent / "../scripts/markov/generate_chain.py"
    spec = importlib.util.spec_from_file_location("generate_chain", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(ValueError, match="grouped_messages"):
        await asyncio.to_thread(module.train, tmp_path / "nested" / "messages.db", tmp_path / "out")
    assert not (tmp_path / "out" / "chain.pickle").exists()
