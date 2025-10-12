from typing import Any

from sqlalchemy import select

from slashbot.database.base_sql import BaseDatabaseSQL
from slashbot.database.sql_models import ReminderSQL, UserSQL, WatchedMovieSQL


class DatabaseSQL(BaseDatabaseSQL):
    """Main database for storing user information."""

    async def delete_reminder(self, reminder_id: int) -> None:
        """Delete a reminder from the database using delete_row.

        Parameters
        ----------
        reminder_id : int
            The ID of the reminder to delete.

        """
        reminders = await self.query(ReminderSQL, ReminderSQL.id == reminder_id)
        if reminders:
            await self.delete_row(reminders)

    async def get_all_reminders(self, *, include_stale: bool = False) -> list[ReminderSQL]:
        """Get all reminders in the database using query.

        Parameters
        ----------
        include_stale : bool, optional
            Whether to include stale reminders. By default, only non-stale reminders are retrieved.

        Returns
        -------
        list[ReminderSQL]
            A list of reminders.

        """
        if include_stale:
            return await self.query(ReminderSQL)
        return await self.query(ReminderSQL, ReminderSQL.notified == False)  # noqa: E712

    async def get_reminder(self, reminder_id: int) -> ReminderSQL | None:
        """Get a reminder from the database using query.

        Parameters
        ----------
        reminder_id : int
            The ID of the reminder to get.

        Returns
        -------
        ReminderSQL | None
            The retrieved reminder, or None if not found.

        """
        reminders = await self.query(ReminderSQL, ReminderSQL.id == reminder_id)
        return reminders if reminders else None

    async def get_users_reminders(self, discord_id: int, *, include_stale: bool = False) -> list[ReminderSQL]:
        """Get the active reminders for a user using query.

        Parameters
        ----------
        discord_id : int
            The Discord ID of the user.
        include_stale : bool, optional
            Whether to include stale reminders. By default, only non-stale reminders are retrieved.

        Returns
        -------
        list[ReminderSQL]
            A list of reminders for the user.

        """
        if include_stale:
            return await self.query(ReminderSQL, ReminderSQL.user_id == discord_id)
        return await self.query(ReminderSQL, ReminderSQL.notified == False, ReminderSQL.user_id == discord_id)  # noqa: E712

    async def mark_reminder_as_notified(self, reminder_id: int) -> None:
        """Update the "notified" column for a reminder using update_row.

        Parameters
        ----------
        reminder_id : int
            The ID of the reminder to mark as notified.

        """
        reminder = await self.query(ReminderSQL, ReminderSQL.id == reminder_id)
        if not reminder:
            msg = f"No reminder with ID {reminder_id}"
            raise ValueError(msg)
        if not isinstance(reminder, ReminderSQL):
            msg = "Internal error: query returned a row from the wrong table"
            raise TypeError(msg)
        reminder.notified = True
        await self.upsert_row(reminder)

    async def update_user(self, lookup_field: str, lookup_value: Any, field: str, value: Any) -> UserSQL:
        """Update a field for a user, looked up by any field.

        Parameters
        ----------
        lookup_field : str
            The field to look up the user by: id, discord_id, username"
        lookup_value : Any
            The value to look up the user by.
        field : str
            The field to update.
        value : Any
            The new value to set.

        Returns
        -------
        UserSQL
            The updated user.

        """
        if field not in UserSQL.__table__.columns:
            msg = f"{field} is not a valid attribute for a user"
            raise ValueError(msg)
        if lookup_field not in UserSQL.__table__.columns:
            msg = f"{lookup_field} is not a valid lookup attribute for a user"
            raise ValueError(msg)
        users = await self.query(UserSQL, getattr(UserSQL, lookup_field) == lookup_value)
        if not users:
            msg = f"No user in database with {lookup_field}={lookup_value}"
            raise ValueError(msg)
        user = users[0]
        setattr(user, field, value)
        user = await self.upsert_row(user)
        return user

    async def get_user(self, field: str, value: Any) -> UserSQL | None:
        """Get a user by any field using query.

        Parameters
        ----------
        field : str
            The field to look up the user by.
        value : Any
            The value to look up the user by.

        Returns
        -------
        UserSQL | None
            The retrieved user, or None if not found.

        """
        if field not in ["id", "discord_id", "username"]:
            msg = f"{field} is not a valid query field for a user"
            raise ValueError(msg)
        user = await self.query(UserSQL, getattr(UserSQL, field) == value)
        return user if user else None

    async def get_letterboxd_usernames(self) -> list[UserSQL]:
        """Get a list of users with Letterboxd accounts using query.

        Returns
        -------
        list[UserSQL]
            A list of users with a Letterboxd account.

        """
        usernames = await self.query(UserSQL, UserSQL.letterboxd_username != None)  # noqa: E711
        return usernames

    async def get_last_movie_for_letterboxd_user(self, username: str) -> WatchedMovieSQL | None:
        """Get the last movie a user logged on Letterboxd using query.

        Parameters
        ----------
        username : str
            The Letterboxd username of the user.

        Returns
        -------
        WatchedMovieSQLSQL | None
            The most recent watched movie, or None if not found.

        """
        async with self._get_async_session() as session:
            return (
                await session.execute(
                    select(WatchedMovieSQL)
                    .join(UserSQL, WatchedMovieSQL.user_id == UserSQL.id)
                    .where(UserSQL.letterboxd_username == username)
                    .order_by(
                        WatchedMovieSQL.published_date.desc(),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
