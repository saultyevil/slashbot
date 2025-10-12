from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio

from slashbot.database import DatabaseSQL, DeclarativeBase


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
