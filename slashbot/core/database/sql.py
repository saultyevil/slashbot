from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slashbot.core.database.models import DeclarativeBase
from slashbot.core.logger import Logger


class DatabaseSQL(Logger):
    """Asynchronous database class, using SQLite."""

    def __init__(self, database_url: str, logger_label: str = "[DatabaseSQL]") -> None:
        """Initialize the database.

        Parameters
        ----------
        database_url : str
            The database connection URL.
        logger_label : str
            A label to prepend to all logging output to indicate where the
            log entry came from.

        """
        super().__init__(prepend_msg=logger_label)
        self.engine = create_async_engine(database_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self) -> None:
        """Initialize the database and create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(DeclarativeBase.metadata.create_all)

    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[AsyncSession, None]:
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
