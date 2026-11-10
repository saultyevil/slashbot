import importlib.util
import pickle
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import DatabaseError

from slashbot.cogs.markov.cog import UPDATE_TIME, Markov
from slashbot.markov import (
    MarkovGeneratorType,
    MarkovTextGenerator,
    OnTheFly,
    clean,
    prepare_training_data,
    save_chain,
    train_chain,
)
from slashbot.settings import BotSettings


def test_markov_generate(markov_model: MarkovTextGenerator) -> None:
    """Test that Markov generation works."""
    response = markov_model.generate_response()
    assert len(response) == 1
    response = markov_model.generate_response(2)
    assert len(response) == 2


CORPUS = [
    "the cat sat on the mat",
    "the dog ate the bone",
    "the cat ate the bone today",
    "a dog sat on the mat",
    "the cat chased the dog around the garden",
    "the dog chased the cat around the house",
]


@pytest.fixture
def chain_file(tmp_path: Path) -> Path:
    """Create a trained chain on disk."""
    chain = train_chain(CORPUS)
    assert chain is not None
    path = tmp_path / "chain.pickle"
    save_chain(chain, path)
    return path


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello there", "hello there"),
        ("", ""),
        ("   ", "   "),
        ("/command arg", ""),
        ("!bang", ""),
        ("hello @user", ""),
    ],
)
def test_clean(text: str, expected: str) -> None:
    assert clean(text) == expected


def test_prepare_training_data() -> None:
    data = ["hi there.", "what\nis this?", "/cmd", "no end", "@x y", ""]
    assert prepare_training_data(data) == "hi there.\nwhat\nis this?\nno end"


def test_prepare_training_data_empty() -> None:
    assert prepare_training_data(["", "/cmd"]) == ""


def test_grouped_training_preserves_each_message() -> None:
    """Keep embedded newlines and sentence boundaries inside each group."""
    messages = ["hello there. what\nis up?", "different person here", "/ignored"]
    assert prepare_training_data(messages, preserve_messages=True) == "hello there. what is up?\ndifferent person here"
    chain = train_chain(messages, state_size=1, preserve_messages=True)
    assert chain is not None
    assert chain.model[("what",)] == {"is": 1}
    assert chain.model[("there.",)] == {"what": 1}


def test_train_chain_no_data() -> None:
    assert train_chain(["", "/cmd", "@a"]) is None


def test_train_chain_state_size() -> None:
    chain = train_chain(CORPUS, state_size=1)
    assert chain is not None
    assert chain.state_size == 1


def test_save_and_load_chain(chain_file: Path) -> None:
    gen = MarkovTextGenerator(chain_file)
    assert gen.type == MarkovGeneratorType.ON_THE_FLY
    assert len(gen.generate_response(3)) == 3


def test_on_the_fly_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        OnTheFly(tmp_path / "missing.pickle")


def test_on_the_fly_seed_word(chain_file: Path) -> None:
    sentence = OnTheFly(chain_file).generate("cat")
    assert isinstance(sentence, str)
    assert sentence


def test_replace_chain_in_place(chain_file: Path) -> None:
    model = OnTheFly(chain_file)
    new_chain = train_chain(["zebras eat grass daily", "zebras drink water daily"])
    model.replace_chain(new_chain, compile_chain=False)
    assert model._model.chain is new_chain  # noqa: SLF001
    assert "zebras" in model.generate("zebras")


def test_update_extends_chain_and_saves(chain_file: Path) -> None:
    model = OnTheFly(chain_file)
    count = model.update(["zebras eat grass daily", "zebras drink water daily", "/cmd", "@x y"])
    assert count == 2

    # backup of the old chain, and the saved chain contains the new words
    assert chain_file.with_name("chain.pickle.bak").exists()
    reloaded = OnTheFly(chain_file)
    assert reloaded.generate("zebras")
    with chain_file.open("rb") as f:
        saved = pickle.load(f)  # noqa: S301
    assert any("zebras" in state for state in saved.model)

    # old words are still known
    assert any("cat" in state for state in saved.model)


def test_update_nothing_to_learn(chain_file: Path) -> None:
    model = OnTheFly(chain_file)
    before = chain_file.read_bytes()
    assert model.update(["", "/cmd", "@x"]) == 0
    assert chain_file.read_bytes() == before
    assert not chain_file.with_name("chain.pickle.bak").exists()


def test_generator_update_chain(chain_file: Path) -> None:
    gen = MarkovTextGenerator(chain_file)
    assert gen.update_chain(["zebras eat grass daily", "zebras drink water daily"]) == 2
    assert gen.generate_response(1, "zebras")


def test_generator_update_chain_pregen_raises() -> None:
    gen = MarkovTextGenerator(Path(__file__).parent / "../data/markov/markov-sentences.json")
    with pytest.raises(TypeError):
        gen.update_chain(["hello world"])


def test_generate_chain_script_rejects_text_file(tmp_path: Path) -> None:
    """The trainer accepts archive databases rather than text corpora."""
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("\n".join(CORPUS))
    script = Path(__file__).parent / "../scripts/markov/generate_chain.py"
    spec = importlib.util.spec_from_file_location("generate_chain", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(DatabaseError):
        module.train(corpus, tmp_path, state_size=1)


# Cog ------------------------------------------------------------------------


def _fake_cog(generator: MarkovTextGenerator | None) -> SimpleNamespace:
    return SimpleNamespace(
        bot=SimpleNamespace(get_cog=lambda _name: None),
        markov_generator=generator,
        markov_training_sample={},
        log_info=lambda *_a, **_k: None,
        log_exception=lambda *_a, **_k: None,
    )


def _message(msg_id: int, content: str, *, bot: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=msg_id, clean_content=content, author=SimpleNamespace(bot=bot))


@pytest.fixture
def training_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BotSettings.markov, "enable_markov_training", True, raising=False)


def test_cog_update_time() -> None:
    assert UPDATE_TIME.hour == BotSettings.cogs.markov.update_hour
    assert UPDATE_TIME.minute == BotSettings.cogs.markov.update_minute


@pytest.mark.asyncio
async def test_cog_listener_records_messages(training_enabled: None) -> None:  # noqa: ARG001
    cog = _fake_cog(None)
    listener = Markov.add_message_to_markov_training_sample
    await listener(cog, _message(1, "hello world"))
    await listener(cog, _message(2, "i am a bot", bot=True))
    assert cog.markov_training_sample == {1: "hello world"}


@pytest.mark.asyncio
async def test_cog_update_loop_trains_and_clears(chain_file: Path, training_enabled: None) -> None:  # noqa: ARG001
    gen = MarkovTextGenerator(chain_file)
    cog = _fake_cog(gen)
    cog.markov_training_sample = {1: "zebras eat grass daily", 2: "zebras drink water daily", 3: "/cmd"}
    await Markov.markov_chain_update_loop.coro(cog)
    assert cog.markov_training_sample == {}
    assert gen.generate_response(1, "zebras")
    with chain_file.open("rb") as f:
        assert any("zebras" in state for state in pickle.load(f).model)  # noqa: S301


@pytest.mark.asyncio
async def test_cog_update_loop_rebuilds_grouped_chain(
    chain_file: Path,
    training_enabled: None,
    tmp_path: Path,  # noqa: ARG001
) -> None:
    """Rebuild groups from the archive so deletions are reflected."""
    from slashbot.cogs.message_archive.cog import MessageStore

    store = MessageStore(tmp_path / "messages.db")
    await store.init()
    try:
        await store.upsert(1, "zebras eat grass", author_id=1, channel_id=1)
        await store.upsert(2, "zebras drink water", author_id=1, channel_id=1)
        cog = _fake_cog(MarkovTextGenerator(chain_file))
        cog.bot.get_cog = lambda _name: SimpleNamespace(store=store)
        cog.markov_training_sample = {1: "zebras eat grass", 2: "zebras drink water"}
        await Markov.markov_chain_update_loop.coro(cog)
        grouped_file = chain_file.with_name("chain_grouped.pickle")
        with grouped_file.open("rb") as file:
            grouped = pickle.load(file)  # noqa: S301
        assert grouped.model[("eat", "grass.")] == {"zebras": 1}
        with chain_file.open("rb") as file:
            regular = pickle.load(file)  # noqa: S301
        assert ("eat", "grass.") not in regular.model

        await store.delete(1)
        await Markov.markov_chain_update_loop.coro(cog)
        with grouped_file.open("rb") as file:
            grouped = pickle.load(file)  # noqa: S301
        assert ("eat", "grass.") not in grouped.model
        with chain_file.open("rb") as file:
            regular = pickle.load(file)  # noqa: S301
        assert ("zebras", "eat") not in regular.model
        assert ("zebras", "drink") in regular.model
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_grouped_training_failure_does_not_block_regular_training(
    chain_file: Path,
    training_enabled: None,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ARG001
) -> None:
    """A failure rebuilding the grouped chain does not discard regular training."""
    generator = MarkovTextGenerator(chain_file)
    cog = _fake_cog(generator)
    cog.markov_training_sample = {1: "zebras eat grass daily"}

    async def grouped_messages() -> list[str]:
        return ["a grouped message"]

    async def messages() -> list[str]:
        return ["zebras eat grass daily"]

    def fail(_messages: list[str]) -> int:
        raise OSError("disk error")

    monkeypatch.setattr(generator, "rebuild_grouped_chain", fail)
    cog.bot.get_cog = lambda _name: SimpleNamespace(
        store=SimpleNamespace(messages=messages, grouped_messages=grouped_messages)
    )
    errors = []
    cog.log_exception = errors.append
    await Markov.markov_chain_update_loop.coro(cog)
    assert cog.markov_training_sample == {}
    assert errors == ["Failed to rebuild the grouped Markov chain"]
    with chain_file.open("rb") as file:
        assert any("zebras" in state for state in pickle.load(file).model)  # noqa: S301


@pytest.mark.asyncio
async def test_cog_update_loop_failure_keeps_samples(training_enabled: None) -> None:  # noqa: ARG001
    gen = SimpleNamespace(
        type=MarkovGeneratorType.ON_THE_FLY, update_chain=lambda _s: (_ for _ in ()).throw(OSError("disk"))
    )
    cog = _fake_cog(gen)
    cog.markov_training_sample = {1: "hello world"}
    await Markov.markov_chain_update_loop.coro(cog)
    assert cog.markov_training_sample == {1: "hello world"}


@pytest.mark.asyncio
async def test_cog_update_loop_keeps_messages_received_during_training(training_enabled: None) -> None:  # noqa: ARG001
    """Keep messages added or changed while training is in progress."""
    cog = _fake_cog(None)
    cog.markov_training_sample = {1: "old", 2: "unchanged"}

    def update_chain(_sentences: list[str]) -> int:
        cog.markov_training_sample[1] = "edited"
        cog.markov_training_sample[3] = "new"
        return 2

    cog.markov_generator = SimpleNamespace(type=MarkovGeneratorType.ON_THE_FLY, update_chain=update_chain)
    await Markov.markov_chain_update_loop.coro(cog)
    assert cog.markov_training_sample == {1: "edited", 3: "new"}


@pytest.mark.asyncio
async def test_cog_update_loop_no_generator(training_enabled: None) -> None:  # noqa: ARG001
    cog = _fake_cog(None)
    cog.markov_training_sample = {1: "hello world"}
    await Markov.markov_chain_update_loop.coro(cog)
    assert cog.markov_training_sample == {1: "hello world"}


def test_cog_generate_sentences(chain_file: Path) -> None:
    assert Markov.generate_sentences(_fake_cog(None)) == []
    cog = _fake_cog(MarkovTextGenerator(chain_file))
    assert len(Markov.generate_sentences(cog, "cat", 2)) == 2  # noqa: PLR2004


def _fake_inter() -> SimpleNamespace:
    async def _async(*_a: object, **_k: object) -> None:
        return None

    calls = []

    async def send_message(content: str, **_k: object) -> None:
        calls.append(("send", content))

    async def edit_original_message(content: str) -> None:
        calls.append(("edit", content))

    return SimpleNamespace(
        response=SimpleNamespace(send_message=send_message, defer=_async),
        edit_original_message=edit_original_message,
        calls=calls,
    )


@pytest.mark.asyncio
async def test_cog_command_rejects_multi_word_seed(chain_file: Path) -> None:
    """A seed word with spaces is rejected."""
    inter = _fake_inter()
    cog = _fake_cog(MarkovTextGenerator(chain_file))
    await Markov.markov_sentence.callback(cog, inter, "two words")
    assert inter.calls == [("send", "The seed word must be a single word.")]


@pytest.mark.asyncio
async def test_cog_command_no_chain() -> None:
    """The command reports when there is no chain."""
    inter = _fake_inter()
    await Markov.markov_sentence.callback(_fake_cog(None), inter, None)
    assert inter.calls[0][0] == "send"


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", [None, "cat", " cat "])
async def test_cog_command_generates(chain_file: Path, seed: str | None) -> None:
    """The command responds with a generated sentence."""
    inter = _fake_inter()
    cog = _fake_cog(MarkovTextGenerator(chain_file))
    cog.generate_sentences = lambda s, a: Markov.generate_sentences(cog, s, a)
    await Markov.markov_sentence.callback(cog, inter, seed)
    assert len(inter.calls) == 1
    assert inter.calls[0][0] == "edit"
    assert inter.calls[0][1]


def _chat_message(content: str, *, bot: bool = False) -> SimpleNamespace:
    sent: list[str] = []

    async def send(text: str) -> None:
        sent.append(text)

    @asynccontextmanager
    async def typing():  # noqa: ANN202
        yield

    return SimpleNamespace(
        content=content,
        author=SimpleNamespace(bot=bot),
        channel=SimpleNamespace(send=send, typing=typing),
        sent=sent,
    )


def _generating_cog(chain_file: Path) -> SimpleNamespace:
    cog = _fake_cog(MarkovTextGenerator(chain_file))
    cog.generate_sentences = lambda s, a: Markov.generate_sentences(cog, s, a)
    return cog


@pytest.mark.asyncio
async def test_seed_listener_responds(chain_file: Path) -> None:
    """A "?word" message gets a sentence using the word as the seed."""
    cog = _generating_cog(chain_file)
    seeds = []
    original = cog.generate_sentences
    cog.generate_sentences = lambda s, a: (seeds.append(s), original(s, a))[1]
    message = _chat_message("?cat and more")
    await Markov.respond_to_seed_word_message(cog, message)
    assert seeds == ["cat"]
    assert len(message.sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["hello", "what? no", "?", "  ", "", "???", "?!!!", "?…", "?___"])
async def test_seed_listener_ignores_non_seed(chain_file: Path, content: str) -> None:
    """Messages not starting with "?word" are ignored."""
    seeds = []
    cog = _generating_cog(chain_file)
    cog.generate_sentences = lambda seed, _: (seeds.append(seed), ["generated"])[1]
    message = _chat_message(content)
    await Markov.respond_to_seed_word_message(cog, message)
    assert message.sent == []
    assert seeds == []


@pytest.mark.asyncio
async def test_listeners_ignore_bots(chain_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither listener acts on bot messages."""
    monkeypatch.setattr("slashbot.cogs.markov.cog.random", SimpleNamespace(random=lambda: 0.0))
    cog = _generating_cog(chain_file)
    for listener, content in [(Markov.respond_to_seed_word_message, "?cat"), (Markov.respond_randomly, "hello")]:
        message = _chat_message(content, bot=True)
        await listener(cog, message)
        assert message.sent == []


@pytest.mark.asyncio
async def test_random_listener_chance(chain_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The random listener only responds when the roll succeeds."""
    cog = _generating_cog(chain_file)
    monkeypatch.setattr("slashbot.cogs.markov.cog.random", SimpleNamespace(random=lambda: 0.9))
    message = _chat_message("hello")
    await Markov.respond_randomly(cog, message)
    assert message.sent == []

    monkeypatch.setattr("slashbot.cogs.markov.cog.random", SimpleNamespace(random=lambda: 0.0))
    await Markov.respond_randomly(cog, message)
    assert len(message.sent) == 1


@pytest.mark.asyncio
async def test_random_listener_skips_seed_messages_and_no_chain(
    chain_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seed messages and a missing chain never trigger a random response."""
    monkeypatch.setattr("slashbot.cogs.markov.cog.random", SimpleNamespace(random=lambda: 0.0))
    message = _chat_message("?cat")
    await Markov.respond_randomly(_generating_cog(chain_file), message)
    message2 = _chat_message("hello")
    await Markov.respond_randomly(_fake_cog(None), message2)
    assert message.sent == message2.sent == []


def test_markov_cog_settings() -> None:
    """The configured settings are valid."""
    settings = BotSettings.cogs.markov
    assert 0.0 <= settings.random_response_chance <= 1.0
    assert 0 <= settings.update_hour <= 23  # noqa: PLR2004


@pytest.mark.asyncio
async def test_cog_update_loop_pregen_does_nothing(training_enabled: None) -> None:  # noqa: ARG001
    """A pregenerated generator cannot be trained, so samples are left alone."""
    gen = MarkovTextGenerator(Path(__file__).parent / "../data/markov/markov-sentences.json")
    cog = _fake_cog(gen)
    cog.markov_training_sample = {1: "hello world"}
    await Markov.markov_chain_update_loop.coro(cog)
    assert cog.markov_training_sample == {1: "hello world"}
