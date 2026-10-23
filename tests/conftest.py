from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from slashbot.database import DatabaseSQL, DeclarativeBase
from slashbot.markov_class import MarkovTextGenerator

load_dotenv()


@pytest_asyncio.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[DatabaseSQL, None]:
    """Fixture yielding an initialised in-memory async database."""
    db_path = tmp_path / "test.db"
    db = DatabaseSQL(db_path, DeclarativeBase)
    await db.init()
    yield db
    # teardown: drop tables and close engine
    async with db.engine.begin() as conn:
        await conn.run_sync(DeclarativeBase.metadata.drop_all)
    await db.engine.dispose()


@pytest.fixture
def markov_model() -> MarkovTextGenerator:
    """Fixture for creating a MarkovTextGenerator using pregenerated sentences."""
    parent = Path(__file__).parent
    return MarkovTextGenerator(Path(f"{parent}/../data/markov/markov-sentences.json"))
