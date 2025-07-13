from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from slashbot.core.database.models import WikiFeetModel, WikiFeetPicture, WikiFeetSqlBase


class WikiFeetDatabase:
    """A class to interact with the WikiFeet database."""

    def __init__(self, database_url: str) -> None:
        """Initialize the WikiFeetDatabase with a database URL.

        Parameters
        ----------
        database_url : str
            The database connection URL.

        """
        self.engine = create_async_engine(database_url, echo=False)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init_database(self) -> None:
        """Initialize the database and create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(WikiFeetSqlBase.metadata.create_all)

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Asynchronous context manager for database session.

        Returns
        -------
        AsyncGenerator[AsyncSession, None]
            An async generator yielding an AsyncSession.

        """
        async with self.session_factory() as session:
            yield session

    async def add_model(self, model: WikiFeetModel) -> None:
        """Add a WikiFeetModel instance to the database.

        Parameters
        ----------
        model : WikiFeetModel
            The model instance to add.

        """
        async for session in self.get_session():
            session.add(model)
            await session.commit()

    async def add_picture(self, picture: WikiFeetPicture) -> None:
        """Add a WikiFeetPicture instance to the database.

        Parameters
        ----------
        picture : WikiFeetPicture
            The picture instance to add.

        """
        async for session in self.get_session():
            session.add(picture)
            await session.commit()

    async def get_model(self, model_name: str) -> WikiFeetModel | None:
        """Retrieve a WikiFeetModel by name.

        Parameters
        ----------
        model_name : str
            The name of the model to retrieve.

        Returns
        -------
        WikiFeetModel or None
            The model instance if found, otherwise None.

        """
        async for session in self.get_session():
            query = select(WikiFeetModel).where(WikiFeetModel.name == model_name)
            model = await session.execute(query)

        return model.scalar_one_or_none()
