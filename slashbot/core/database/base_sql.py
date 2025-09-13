from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slashbot.core.database.sql_models import DeclarativeBase, ReminderSQL, UserSQL, WatchedMovieSQL
from slashbot.core.logger import Logger


class BaseDatabaseSQL(Logger):
    """Asynchronous database class, using SQLite."""

    def __init__(self, database_location: str | Path, logger_label: str = "[DatabaseSQL]") -> None:
        """Initialize the database.

        Parameters
        ----------
        database_location : str | Path
            The location of the database on the file system.
        logger_label : str
            A label to prepend to all logging output to indicate where the
            log entry came from.

        """
        super().__init__(prepend_msg=logger_label)

        database_url = f"sqlite+aiosqlite:///{Path(database_location).absolute()}"
        self.engine = create_async_engine(database_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.initialised = False

    async def init(self) -> None:
        """Initialize the database and create all tables."""
        if self.initialised:
            return
        async with self.engine.begin() as conn:
            await conn.run_sync(DeclarativeBase.metadata.create_all)
        self.initialised = True

    @asynccontextmanager
    async def _get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Asynchronous context manager for database session.

        Returns
        -------
        AsyncGenerator[AsyncSession, None]
            An async generator yielding an AsyncSession.

        """
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def upsert_row(
        self, model: UserSQL | ReminderSQL | WatchedMovieSQL
    ) -> UserSQL | ReminderSQL | WatchedMovieSQL:
        """Add a new row to the database.

        Update a user row:
            user.username = "new_name"
            updated_user = await db.update_row(user)
        Add a new reminder:
            reminder = ReminderSQL(user_id=1, message="Hello")
            saved_reminder = await db.update_row(reminder)

        Parameters
        ----------
        model : User | Reminder | WatchedMovie
            An SQLAlchemy ORM object representing the row to either add or
            update.

        Returns
        -------
        User | Reminder | WatchedMovie
            The updated instance, e.g. with primary key.

        """
        if not isinstance(model, UserSQL | ReminderSQL | WatchedMovieSQL):
            exc_msg = f"Unknown model '{type(model)}' for database"
            raise TypeError(exc_msg)
        async with self._get_async_session() as session:
            try:
                session.add(model)
                await session.commit()
                await session.refresh(model)
            except IntegrityError as exc:
                await session.rollback()
                self.log_error(
                    "Integrity error when adding %s to %s: %s", type(model).__name__, model.__tablename__, exc
                )
                raise
            else:
                return model

    async def delete_row(self, model: UserSQL | ReminderSQL | WatchedMovieSQL) -> None:
        """Remove a row from the database.

        Delete a user row:
            await db.delete_row(user)
        Delete a watched movie row:
            await db.delete_row(movie)

        Parameters
        ----------
        model : User | Reminder | WatchedMovie
            An SQLAlchemy ORM object representing the row to remove.

        """
        model_cls = type(model)
        pk_cols = [col.name for col in model_cls.__table__.primary_key.columns]
        filters = [getattr(model_cls, col) == getattr(model, col) for col in pk_cols]
        async with self._get_async_session() as session:
            await session.execute(
                delete(model_cls).where(*filters),
            )
            await session.commit()

    async def query(
        self,
        model_cls: type[UserSQL] | type[ReminderSQL] | type[WatchedMovieSQL],
        *filters: Any,
    ) -> list[UserSQL | ReminderSQL | WatchedMovieSQL]:
        """Query rows from the database.

        Query all users:
            users = await db.query(User)
        Query reminders for a specific user:
            reminders = await db.query(Reminder, Reminder.user_id == some_user_id)

        Parameters
        ----------
        model_cls : type[User] | type[Reminder] | type[WatchedMovie]
            The ORM model class to query.
        *filters
            Optional SQLAlchemy filter expressions.

        Returns
        -------
        list[User | Reminder | WatchedMovie]
            List of ORM objects matching the query.

        """
        async with self._get_async_session() as session:
            statement = select(model_cls)
            if filters:
                statement = statement.where(*filters)
            return list(
                (
                    await session.execute(
                        statement,
                    )
                )
                .scalars()
                .all()
            )
