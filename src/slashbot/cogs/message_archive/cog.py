"""Cog which archives chat messages to a database for training Markov chains.

The archive is a small SQLite database, accessed with SQLAlchemy like the other
databases, which contains only the message ID and the message text. The ID is
kept so that edited and deleted messages can be updated or removed, and so that
messages are never stored twice.
"""

import asyncio
from pathlib import Path

import disnake
from disnake.ext import commands, tasks
from sqlalchemy import BigInteger, Text, delete, func, select, update
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.database.base_sql import BaseDatabaseSQL
from slashbot.markov import clean
from slashbot.settings import BotSettings

ArchiveBase = declarative_base()


class ArchivedMessageSQL(ArchiveBase):
    """SQLAlchemy ORM model for an archived message.

    Attributes
    ----------
    id : int
        The Discord message ID, which is the primary key.
    content : str
        The cleaned text of the message.

    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class MessageStore(BaseDatabaseSQL):
    """An asynchronous SQLite store of message text, keyed by message ID."""

    def __init__(self, location: Path) -> None:
        """Create the store, the tables are created by calling `init`.

        Parameters
        ----------
        location : Path
            The location of the database file.

        """
        location.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(location, ArchiveBase, logger_label="[MessageStore]")

    async def upsert(self, message_id: int, content: str) -> None:
        """Add a message, or replace the text of an existing message."""
        async with self._get_async_session() as session:
            await session.merge(ArchivedMessageSQL(id=message_id, content=content))
            await session.commit()

    async def delete(self, message_id: int) -> None:
        """Remove a message, if it is in the store."""
        async with self._get_async_session() as session:
            await session.execute(delete(ArchivedMessageSQL).where(ArchivedMessageSQL.id == message_id))
            await session.commit()

    async def update_if_present(self, message_id: int, content: str) -> None:
        """Replace the text of a message only if it is in the store."""
        async with self._get_async_session() as session:
            await session.execute(
                update(ArchivedMessageSQL).where(ArchivedMessageSQL.id == message_id).values(content=content)
            )
            await session.commit()

    async def contains(self, message_id: int) -> bool:
        """Check if a message is in the store."""
        async with self._get_async_session() as session:
            result = await session.execute(select(ArchivedMessageSQL.id).where(ArchivedMessageSQL.id == message_id))
            return result.first() is not None

    async def messages(self) -> list[str]:
        """Get the text of all of the messages, oldest first."""
        async with self._get_async_session() as session:
            result = await session.execute(select(ArchivedMessageSQL.content).order_by(ArchivedMessageSQL.id))
            return list(result.scalars().all())

    async def count(self) -> int:
        """Get the number of stored messages."""
        async with self._get_async_session() as session:
            result = await session.execute(select(func.count()).select_from(ArchivedMessageSQL))
            return result.scalar_one()

    async def close(self) -> None:
        """Close the database."""
        await self.engine.dispose()


class MessageArchive(CustomCog):
    """Cog which saves messages from the channels the bot is in to a database."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot : CustomInteractionBot
            The bot to pass to the cog.

        """
        super().__init__(bot)
        self.store = MessageStore(BotSettings.cogs.message_archive.database_location)

    async def cog_load(self) -> None:
        """Create the database tables before any listener or task can use them."""
        await self.store.init()
        await super().cog_load()

    def cog_unload(self) -> None:
        """Close the database when the cog is unloaded."""
        asyncio.get_running_loop().create_task(self.store.close())

    @staticmethod
    def _should_archive(message: disnake.Message) -> bool:
        """Check if a message is from a human in a server, and so can be stored."""
        return not message.author.bot and message.guild is not None

    async def _backfill_channel(
        self, channel: disnake.abc.Messageable, limit: int | None, *, stop_at_archived: bool = True
    ) -> int:
        """Archive messages missed while offline, for a single channel.

        Walks back from the newest message and, by default, stops at the first
        message which is already archived.

        Parameters
        ----------
        channel : disnake.abc.Messageable
            The channel to read the history of.
        limit : int | None
            The maximum number of messages to look at, or None for the entire
            history.
        stop_at_archived : bool
            Whether to stop at the first archived message. This should be False
            for a full backfill, where messages archived live while it runs
            would otherwise end the walk early.

        Returns
        -------
        int
            The number of messages which were added.

        """
        added = 0
        async for message in channel.history(limit=limit):
            if stop_at_archived and await self.store.contains(message.id):
                break
            if not self._should_archive(message):
                continue
            content = clean(message.clean_content)
            if content:
                await self.store.upsert(message.id, content)
                added += 1
        return added

    @tasks.loop(count=1)
    async def backfill_archive(self) -> None:
        """Catch up on messages sent while the bot was not running."""
        limit = BotSettings.cogs.message_archive.backfill_limit
        if limit <= 0:
            return
        # with an empty archive, we want the entire history of every channel
        full_history = await self.store.count() == 0
        if full_history:
            self.log_info("Message archive is empty, backfilling the entire history")
        total = 0
        for guild in self.bot.guilds:
            for channel in [*guild.text_channels, *guild.threads]:
                if not channel.permissions_for(guild.me).read_message_history:
                    continue
                try:
                    total += await self._backfill_channel(
                        channel, None if full_history else limit, stop_at_archived=not full_history
                    )
                except disnake.HTTPException:
                    self.log_exception("Unable to backfill messages from channel %s", channel.id)
        self.log_info("Message archive backfill complete, %d messages added", total)

    @backfill_archive.before_loop
    async def backfill_archive_before(self) -> None:
        """Wait for the bot to be connected before backfilling."""
        await self.bot.wait_until_ready()

    @commands.Cog.listener("on_message")
    async def archive_message(self, message: disnake.Message) -> None:
        """Save a message to the database.

        Parameters
        ----------
        message : disnake.Message
            The message to save.

        """
        if not self._should_archive(message):
            return
        content = clean(message.clean_content)
        if content:
            await self.store.upsert(message.id, content)

    @commands.Cog.listener("on_message_edit")
    async def update_edited_message(self, _before: disnake.Message, after: disnake.Message) -> None:
        """Update the saved text of an edited message.

        Parameters
        ----------
        _before : disnake.Message
            The message before it was edited, unused.
        after : disnake.Message
            The message after it was edited.

        """
        if not self._should_archive(after):
            return
        content = clean(after.clean_content)
        if content:
            await self.store.update_if_present(after.id, content)
        else:
            await self.store.delete(after.id)

    @commands.Cog.listener("on_raw_message_delete")
    async def remove_deleted_message(self, payload: disnake.RawMessageDeleteEvent) -> None:
        """Remove a deleted message from the database.

        Parameters
        ----------
        payload : disnake.RawMessageDeleteEvent
            The payload of the delete event.

        """
        await self.store.delete(payload.message_id)
