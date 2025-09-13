from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from slashbot.core.database.base_sql import BaseDatabaseSQL
from slashbot.core.database.models import Reminder, User, WatchedMovie


class Database(BaseDatabaseSQL):
    """Main database for storing user information."""

    async def add_watched_movie(self, movie: WatchedMovie) -> WatchedMovie:
        """Add a watched movie to the database.

        Parameters
        ----------
        movie : WatchedMovie
            The movie to add.

        Returns
        -------
        WatchedMovie
            The movie added to the database.

        """
        async with self._get_async_session() as session:
            try:
                session.add(movie)
                await session.commit()
                await session.refresh(movie)
            except IntegrityError as exc:
                await session.rollback()
                self.log_error(f"Integrity error when adding movie: {exc}")
                raise
            else:
                return movie

    async def add_reminder(self, reminder: Reminder) -> Reminder:
        """Add a reminder to the database.

        Parameters
        ----------
        reminder : Reminder
            The reminder to add.

        Returns
        -------
        Reminder
            The reminder added to the database.

        """
        async with self._get_async_session() as session:
            try:
                session.add(reminder)
                await session.commit()
                await session.refresh(reminder)
            except IntegrityError as exc:
                await session.rollback()
                self.log_error(f"Integrity error when adding reminder: {exc}")
                raise
            else:
                return reminder

    async def add_user(self, user: User) -> User:
        """Add a user to the database.

        Parameters
        ----------
        user : User
            The user to add.

        Returns
        -------
        User
            The user which was added to the database.

        """
        async with self._get_async_session() as session:
            try:
                session.add(user)
                await session.commit()
                await session.refresh(user)
            except IntegrityError:
                await session.rollback()
                self.log_error(f"{user} is already in the database")
                raise
            else:
                return user

    async def delete_reminder(self, reminder_id: int) -> None:
        """Delete a reminder from the database.

        Parameters
        ----------
        reminder_id : int
            The ID of the reminder to delete.

        """
        async with self._get_async_session() as session:
            await session.execute(
                delete(Reminder).where(Reminder.id == reminder_id),
            )
            await session.commit()

    async def delete_user(self, user_id: int) -> None:
        """Delete a user from the database.

        Parameters
        ----------
        user_id : int
            The ID of the user to delete.

        """
        async with self._get_async_session() as session:
            await session.execute(
                select(User).where(User.id == user_id),
            )
            await session.commit()

    async def get_all_reminders(self, *, include_stale: bool = False) -> list[Reminder]:
        """Get all reminders in the database.

        Parameters
        ----------
        include_stale : bool, optional
            Whether to include stale reminders, e.g. those which have already
            been sent to users. By default, only non-stale reminders are
            retrieved.

        Returns
        -------
        list[Reminders]
            A list of reminders.

        """
        async with self._get_async_session() as session:
            statement = (
                select(Reminder)
                if include_stale
                else select(Reminder).where(
                    Reminder.notified == False,  # noqa: E712
                )
            )
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def get_all_users(self) -> list[User]:
        """Get all users in the database.

        Returns
        -------
        list[Users]
            A list of users.

        """
        async with self._get_async_session() as session:
            return list(
                (
                    await session.execute(
                        select(
                            User,
                        )
                    )
                ).scalars()
            )

    async def get_reminder(self, reminder_id: int) -> Reminder | None:
        """Get a reminder from the database.

        Parameters
        ----------
        reminder_id : int
            The ID of the reminder to get.

        Returns
        -------
        Reminder | None
            The retrieved reminder, or None if there is no reminder with the
            given ID.

        """
        async with self._get_async_session() as session:
            return (
                await session.execute(
                    select(Reminder).where(Reminder.id == reminder_id),
                )
            ).scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> User | None:
        """Get a user by their ID in the database.

        Parameters
        ----------
        user_id : int
            The ID of the user.

        Returns
        -------
        User | None
            The retrieved user, or None if there is no user with the given
            Discord ID.

        """
        async with self._get_async_session() as session:
            return (
                await session.execute(
                    select(User).where(User.id == user_id),
                )
            ).scalar_one_or_none()

    async def get_user_by_discord_id(self, discord_id: int) -> User | None:
        """Get a user by their Discord ID.

        Parameters
        ----------
        discord_id : int
            The Discord ID of the user.

        Returns
        -------
        User | None
            The retrieved user, or None if there is no user with the given
            Discord ID.

        """
        async with self._get_async_session() as session:
            return (
                await session.execute(
                    select(User).where(User.discord_id == discord_id),
                )
            ).scalar_one_or_none()

    async def get_user_by_letterboxd_username(self, username: str) -> User | None:
        """Get a user by their Letterboxd user.

        Parameters
        ----------
        username : str
            The Letterboxd username for the user.

        Returns
        -------
        User | None
            The retrieved user, or None if there is no user with the given
            Letterboxd username.

        """
        async with self._get_async_session() as session:
            return (
                await session.execute(
                    select(User).where(User.letterboxd_user == username),
                )
            ).scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> User | None:
        """Get a user by their username.

        Parameters
        ----------
        username : str
            The username of the user.

        Returns
        -------
        User | None
            The retrieved user, or None if there is no user with the given
            Discord ID.

        """
        async with self._get_async_session() as session:
            return (
                await session.execute(
                    select(User).where(User.username == username),
                )
            ).scalar_one_or_none()

    async def get_users_reminders(self, discord_id: int, *, include_stale: bool = False) -> list[Reminder]:
        """Get the active reminders for a user.

        Parameters
        ----------
        discord_id : int
            The Discord ID of the user.
        include_stale : bool, optional
            Whether to include stale reminders, e.g. those which have already
            been sent to users. By default, only non-stale reminders are
            retrieved.

        Returns
        -------
        list[Reminder]
            A list of reminders for the user.

        """
        async with self._get_async_session() as session:
            statement = (
                select(Reminder).where(Reminder.user_id == discord_id)
                if include_stale
                else select(Reminder).where(
                    Reminder.notified == False and Reminder.user_id == discord_id,  # noqa: E712
                )
            )
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def mark_reminder_as_notified(self, reminder_id: int) -> None:
        """Update the "notified" column for a reminder.

        Parameters
        ----------
        reminder_id : int
            The ID of the reminder to update.

        """
        async with self._get_async_session() as session:
            reminder = (
                await session.execute(
                    select(Reminder).where(Reminder.id == reminder_id),
                )
            ).scalar_one_or_none()
            if not reminder:
                msg = f"No reminder with ID {reminder_id}"
                raise ValueError(msg)
            reminder.notified = True
            session.add(reminder)
            await session.commit()
            await session.refresh(reminder)

    async def update_user_by_discord_id(self, discord_id: int, field: str, value: Any) -> User:
        """Update a field for a user.

        Parameters
        ----------
        discord_id: int
            The Discord ID of the user.
        field : str
            The name of the field to update.
        value : str
            The new value of the field.

        Returns
        -------
        User
            The updated user.

        """
        if field not in User.__table__.columns:
            msg = f"{field} is not a valid attribute for a user"
            raise ValueError(msg)
        user = await self.get_user_by_discord_id(discord_id)
        if not user:
            msg = f"No user in database with discord ID {discord_id}"
            raise ValueError(msg)
        setattr(user, field, value)
        async with self._get_async_session() as session:
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

    async def get_letterboxd_users(self) -> list[User]:
        """Get a list of users with Letterboxd accounts.

        Returns
        -------
        list[User]
            A list of User rows with a letterboxd user set.

        """
        async with self._get_async_session() as session:
            return list(
                (
                    await session.execute(
                        select(
                            User,
                        ).where(User.letterboxd_user != None)  # noqa: E711
                    )
                ).scalars()
            )

    async def get_last_movie_for_user(self, letterboxd_username: str) -> WatchedMovie | None:
        """Get the last movie a user logged on Letterboxd."""
        async with self._get_async_session() as session:
            return (
                await session.execute(
                    select(WatchedMovie)
                    .join(User, WatchedMovie.user_id == User.id)
                    .where(User.letterboxd_user == letterboxd_username)
                    .order_by(
                        WatchedMovie.watched_date.desc(),
                        # Order by PK as tiebreaker. We have used an ascending
                        # order because newer movies are will have a lower primary
                        # key because of the order they are added
                        WatchedMovie.id.asc(),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
