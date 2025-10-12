import pytest
from sqlalchemy import inspect

from slashbot.database import DatabaseSQL, UserSQL


@pytest.mark.asyncio
async def test_database_creation(test_db: DatabaseSQL) -> None:
    """Test that a database is created correctly."""
    expected_tables = {"users", "reminders", "watched_movies"}

    async with test_db.engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())

    assert expected_tables.issubset(set(tables))


@pytest.mark.asyncio
async def test_upsert_row_adds_new_row(test_db: DatabaseSQL) -> None:
    """Test that the upsert_row method can add a new row to a table."""


@pytest.mark.asyncio
async def test_upsert_row_updates_row(test_db: DatabaseSQL) -> None:
    """Test that the upsert_row method can update an existing row."""


@pytest.mark.asyncio
async def test_delete_row_deletes_a_row(test_db: DatabaseSQL) -> None:
    """Test that the delete_row method can delete a row."""


@pytest.mark.asyncio
async def test_query(test_db: DatabaseSQL) -> None:
    """Test that that the query method works correctly."""


@pytest.mark.asyncio
async def test_user_creation(test_db: DatabaseSQL) -> None:
    """Test that a user can be created."""
    user_model = UserSQL(discord_id=1, username="saultyevil")
    user = await test_db.upsert_row(user_model)

    assert user.id is not None


@pytest.mark.asyncio
async def test_user_modification(test_db: DatabaseSQL) -> None:
    """Test that a user can be modified."""


@pytest.mark.asyncio
async def test_reminder_creation(test_db: DatabaseSQL) -> None:
    """Test that a reminder can be added."""


@pytest.mark.asyncio
async def test_mark_reminder_as_notified(test_db: DatabaseSQL) -> None:
    """Test that a reminder can be marked as notified."""


@pytest.mark.asyncio
async def test_reminder_deletion(test_db: DatabaseSQL) -> None:
    """Test that a reminder can be deleted."""
