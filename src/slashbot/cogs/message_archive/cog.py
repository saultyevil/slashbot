"""Cog which archives chat messages to a database for training Markov chains.

The original messages are retained alongside groups of consecutive messages
from the same author in the same channel.
"""

import asyncio
from pathlib import Path

import disnake
from disnake.ext import commands, tasks
from sqlalchemy import BigInteger, Index, Text, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
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


class GroupedMessageSQL(ArchiveBase):
    """A sequence of consecutive messages from one author in one channel."""

    __tablename__ = "grouped_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class MessageGroupingSQL(ArchiveBase):
    """The channel and author needed to maintain grouped messages."""

    __tablename__ = "message_grouping"
    __table_args__ = (Index("ix_message_grouping_channel_id_id", "channel_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)


class GroupingBackfillSQL(ArchiveBase):
    """Channels whose histories have been scanned for grouping."""

    __tablename__ = "grouping_backfill"

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)


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
        self._group_lock = asyncio.Lock()

    async def _regroup(self, session: AsyncSession, message_id: int, channel_id: int, group_id: int | None) -> None:
        neighbours = []
        for comparison, ordering in (
            (MessageGroupingSQL.id < message_id, MessageGroupingSQL.id.desc()),
            (MessageGroupingSQL.id > message_id, MessageGroupingSQL.id.asc()),
        ):
            result = await session.execute(
                select(MessageGroupingSQL)
                .where(MessageGroupingSQL.channel_id == channel_id, comparison)
                .order_by(ordering)
                .limit(1)
            )
            neighbour = result.scalar_one_or_none()
            if neighbour is not None:
                neighbours.append(neighbour)

        group_ids = {item.group_id for item in neighbours if item.group_id is not None}
        if group_id is not None:
            group_ids.add(group_id)
        result = await session.execute(
            select(MessageGroupingSQL, ArchivedMessageSQL.content)
            .outerjoin(ArchivedMessageSQL, ArchivedMessageSQL.id == MessageGroupingSQL.id)
            .where(
                MessageGroupingSQL.channel_id == channel_id,
                (MessageGroupingSQL.group_id.in_(group_ids))
                | (MessageGroupingSQL.id == message_id)
                | (MessageGroupingSQL.id.in_([item.id for item in neighbours])),
            )
            .order_by(MessageGroupingSQL.id)
        )
        rows = result.all()
        if group_ids:
            await session.execute(delete(GroupedMessageSQL).where(GroupedMessageSQL.id.in_(group_ids)))
        group = None
        for metadata, content in rows:
            if content is None:
                metadata.group_id = None
                group = None
                continue
            if group is None or group.author_id != metadata.author_id:
                group = GroupedMessageSQL(
                    id=metadata.id, channel_id=channel_id, author_id=metadata.author_id, content=content.strip()
                )
                session.add(group)
            else:
                group.content = group.content.rstrip()
                if group.content and group.content[-1] not in ".!?":
                    group.content += "."
                group.content += " " + content.strip()
            metadata.group_id = group.id

    async def upsert(
        self, message_id: int, content: str, *, author_id: int | None = None, channel_id: int | None = None
    ) -> None:
        """Add a message, or replace the text of an existing message."""
        async with self._group_lock, self._get_async_session() as session:
            metadata = await session.get(MessageGroupingSQL, message_id)
            await session.merge(ArchivedMessageSQL(id=message_id, content=content))
            if metadata is None and author_id is not None and channel_id is not None:
                metadata = MessageGroupingSQL(id=message_id, author_id=author_id, channel_id=channel_id)
                session.add(metadata)
            await session.flush()
            if metadata is not None:
                await self._regroup(session, message_id, metadata.channel_id, metadata.group_id)
            await session.commit()

    async def record_boundary(self, message_id: int, author_id: int, channel_id: int) -> None:
        """Record an unarchivable message so groups cannot cross it."""
        async with self._group_lock, self._get_async_session() as session:
            metadata = await session.get(MessageGroupingSQL, message_id)
            if metadata is None:
                metadata = MessageGroupingSQL(id=message_id, author_id=author_id, channel_id=channel_id)
                session.add(metadata)
            await session.execute(delete(ArchivedMessageSQL).where(ArchivedMessageSQL.id == message_id))
            await session.flush()
            await self._regroup(session, message_id, metadata.channel_id, metadata.group_id)
            await session.commit()

    async def delete(self, message_id: int) -> None:
        """Remove a message, if it is in the store."""
        async with self._group_lock, self._get_async_session() as session:
            metadata = await session.get(MessageGroupingSQL, message_id)
            await session.execute(delete(ArchivedMessageSQL).where(ArchivedMessageSQL.id == message_id))
            if metadata is not None:
                channel_id, group_id = metadata.channel_id, metadata.group_id
                await session.delete(metadata)
                await session.flush()
                await self._regroup(session, message_id, channel_id, group_id)
            await session.commit()

    async def update_if_present(self, message_id: int, content: str) -> None:
        """Update an archived or previously observed message."""
        async with self._group_lock, self._get_async_session() as session:
            result = await session.execute(
                update(ArchivedMessageSQL).where(ArchivedMessageSQL.id == message_id).values(content=content)
            )
            metadata = await session.get(MessageGroupingSQL, message_id)
            if not result.rowcount and metadata is not None:
                session.add(ArchivedMessageSQL(id=message_id, content=content))
                await session.flush()
            if metadata is not None:
                await self._regroup(session, message_id, metadata.channel_id, metadata.group_id)
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

    async def grouped_messages(self) -> list[str]:
        """Get grouped message text, ordered by the first message in each group."""
        async with self._get_async_session() as session:
            result = await session.execute(select(GroupedMessageSQL.content).order_by(GroupedMessageSQL.id))
            return list(result.scalars().all())

    async def grouping_backfilled(self, channel_id: int) -> bool:
        """Check whether a channel has had a full grouping backfill."""
        async with self._get_async_session() as session:
            return await session.get(GroupingBackfillSQL, channel_id) is not None

    async def mark_grouping_backfilled(self, channel_id: int) -> None:
        """Remember that a channel's full history was scanned."""
        async with self._get_async_session() as session:
            await session.merge(GroupingBackfillSQL(channel_id=channel_id))
            await session.commit()

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
            content = clean(message.clean_content) if self._should_archive(message) else ""
            if content:
                await self.store.upsert(message.id, content, author_id=message.author.id, channel_id=message.channel.id)
                added += 1
            else:
                await self.store.record_boundary(message.id, message.author.id, message.channel.id)
        return added

    @tasks.loop(count=1)
    async def backfill_archive(self) -> None:
        """Catch up on messages sent while the bot was not running."""
        limit = BotSettings.cogs.message_archive.backfill_limit
        if limit <= 0:
            return
        total = 0
        for guild in self.bot.guilds:
            for channel in [*guild.text_channels, *guild.threads]:
                if not channel.permissions_for(guild.me).read_message_history:
                    continue
                try:
                    full_history = not await self.store.grouping_backfilled(channel.id)
                    total += await self._backfill_channel(
                        channel, None if full_history else limit, stop_at_archived=not full_history
                    )
                    if full_history:
                        await self.store.mark_grouping_backfilled(channel.id)
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
        if message.guild is None:
            return
        content = clean(message.clean_content) if self._should_archive(message) else ""
        if content:
            await self.store.upsert(message.id, content, author_id=message.author.id, channel_id=message.channel.id)
        else:
            await self.store.record_boundary(message.id, message.author.id, message.channel.id)

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
        if after.guild is None or after.author.bot:
            return
        content = clean(after.clean_content)
        if content:
            await self.store.update_if_present(after.id, content)
        else:
            await self.store.record_boundary(after.id, after.author.id, after.channel.id)

    @commands.Cog.listener("on_raw_message_delete")
    async def remove_deleted_message(self, payload: disnake.RawMessageDeleteEvent) -> None:
        """Remove a deleted message from the database.

        Parameters
        ----------
        payload : disnake.RawMessageDeleteEvent
            The payload of the delete event.

        """
        await self.store.delete(payload.message_id)
