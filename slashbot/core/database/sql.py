from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from slashbot.core.database.base_sql import BaseDatabaseSQL
from slashbot.core.database.models import Reminder, User


class Database(BaseDatabaseSQL):
    """Main database for storing user information."""

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

    async def delete_reminder(self, id: int) -> None:
        """Delete a reminder from the database.

        Paremeters
        ----------
        id : int
            The ID of the reminder to delete.

        """
        async with self._get_async_session() as session:
            await session.execute(
                delete(Reminder).where(Reminder.id == id),
            )

    async def delete_user(self, id: int) -> None:
        """Delete a user from the database.

        Parameters
        ----------
        id : int
            The ID of the user to delete.

        """
        async with self._get_async_session() as session:
            await session.execute(
                select(User).where(User.id == id),
            )

    async def get_all_reminders(self) -> list[Reminder]:
        """Get all reminders in the database.

        Returns
        -------
        list[Reminders]
            A list of reminders.

        """
        async with self._get_async_session() as session:
            return list(
                (
                    await session.execute(
                        select(
                            Reminder,
                        )
                    )
                ).scalars()
            )

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

    async def get_reminder(self, id: int) -> Reminder | None:
        """Get a reminder from the database.

        Parameters
        ----------
        id : int
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
                    select(Reminder).where(Reminder.id == id),
                )
            ).scalar_one_or_none()

    async def get_user_by_id(self, id: int) -> User | None:
        """Get a user by their ID in the database.

        Parameters
        ----------
        id : int
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
                    select(User).where(User.id == id),
                )
            ).scalar_one_or_none()

    async def get_user_by_discord_id(self, id: int) -> User | None:
        """Get a user by their Discord ID.

        Parameters
        ----------
        id : int
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
                    select(User).where(User.discord_id == id),
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

    async def update_user(self, id: int, field: str, value: Any) -> User:
        """Update a field for a user.

        Parameters
        ----------
        id: int
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
        user = await self.get_user_by_discord_id(id)
        if not user:
            msg = f"No user in database with discord ID {id}"
            raise ValueError(msg)
        setattr(user, field, value)
        async with self._get_async_session() as session:
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user
