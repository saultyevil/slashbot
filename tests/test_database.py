import pytest
from sqlalchemy import inspect

from slashbot.database import DatabaseSQL, UserSQL


async def create_test_user(db: DatabaseSQL) -> UserSQL:
    """Add a test user to the Users table.

    Parameters
    ----------
    db : DatabaseSQL
        The database to add the user to.

    Returns
    -------
    UserSQL
        The new user.

    """
    test_id = 1
    username = "saultyevil"
    user_model = UserSQL(discord_id=test_id, username=username)
    user = await db.upsert_row(user_model)
    assert user.id is not None

    return user


@pytest.mark.asyncio
async def test_database_creation(test_db: DatabaseSQL) -> None:
    """Test that a database is created correctly."""
    expected_tables = {"users", "reminders", "watched_movies"}

    async with test_db.engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())

    assert expected_tables.issubset(set(tables))


@pytest.mark.asyncio
async def test_upsert_row(test_db: DatabaseSQL) -> None:
    """Test that the upsert_row method can add or modify a row."""
    test_user = await create_test_user(test_db)

    test_city = "Wargrave"
    test_user.city = test_city
    updated_user = await test_db.upsert_row(test_user)
    assert updated_user.city == test_city


@pytest.mark.asyncio
async def test_delete_row_deletes_a_row(test_db: DatabaseSQL) -> None:
    """Test that the delete_row method can delete a row."""
    test_user = await create_test_user(test_db)
    username = test_user.username
    await test_db.delete_row(test_user)

    row = await test_db.query(UserSQL, UserSQL.username == username)
    assert row is None


@pytest.mark.asyncio
async def test_query(test_db: DatabaseSQL) -> None:
    """Test that that the query method works correctly."""
    test_user = await create_test_user(test_db)
    username = test_user.username

    row = await test_db.query(UserSQL, UserSQL.username == username)
    assert row
    assert isinstance(row, UserSQL)
    assert row.username == username


@pytest.mark.asyncio
async def test_get_user(test_db: DatabaseSQL) -> None:
    """Test that a user can be created."""
    test_id = 1
    username = "saultyevil"
    user_model = UserSQL(discord_id=test_id, username=username)
    test_user = await test_db.upsert_row(user_model)
    assert test_user.id is not None

    user = await test_db.get_user("id", test_user.id)
    assert user
    assert user.username == username
    assert user.discord_id == test_id

    user = await test_db.get_user("discord_id", test_id)
    assert user
    assert user.username == username
    assert user.discord_id == test_id

    user = await test_db.get_user("username", username)
    assert user
    assert user.username == username
    assert user.discord_id == test_id

    with pytest.raises(ValueError, match="is not a valid query field"):
        user = await test_db.get_user("city", "Wargrave")


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
