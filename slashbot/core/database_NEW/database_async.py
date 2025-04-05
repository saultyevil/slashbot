import asyncio
import json
from dataclasses import fields
from pathlib import Path

import aiofiles

from slashbot.core.database_NEW.models import Reminder, User
from slashbot.core.logger import Logger
from slashbot.settings import BotSettings


class Database(Logger):
    """Asynchronous database class."""

    USER_DATA_KEY = "user_data"
    REMINDERS_KEY = "reminders"

    def __init__(self, *, filepath: str | Path | None = None) -> None:
        """Initialise the database class.

        Parameters
        ----------
        filepath: str | Path | None, optional
            The file location of the database, by default None
            If None, the default location is used.

        """
        super().__init__()
        self._filename = filepath or BotSettings.files.database
        self._lock = asyncio.Lock()
        self._tables = {self.USER_DATA_KEY: {}, self.REMINDERS_KEY: {}}

    async def _create_empty_database(self) -> None:
        async with aiofiles.open(self._filename, mode="w") as file_out:
            await file_out.write(json.dumps({self.USER_DATA_KEY: {}, self.REMINDERS_KEY: {}}, indent=4))

    async def _load_database(self) -> None:
        if not self._filename.exists():
            await self._create_empty_database()

        async with self._lock, aiofiles.open(self._filename) as file_in:
            content = await file_in.read()

            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                self.log_error("Failed to parse database. Creating new empty one. exc=%s", e)
                await self._create_empty_database()
                data = {self.USER_DATA_KEY: {}, self.REMINDERS_KEY: {}}

            self._tables[self.USER_DATA_KEY] = {int(k): User.from_dict(v) for k, v in data[self.USER_DATA_KEY].items()}
            self._tables[self.REMINDERS_KEY] = {
                int(k): Reminder.from_dict(v) for k, v in data[self.REMINDERS_KEY].items()
            }

    async def _save_database(self) -> None:
        async with self._lock:
            serialisable_tables = {
                self.USER_DATA_KEY: {
                    user_id: user.to_dict() for user_id, user in self._tables[self.USER_DATA_KEY].items()
                },
                self.REMINDERS_KEY: {
                    reminder_id: reminder.to_dict()
                    for reminder_id, reminder in self._tables[self.REMINDERS_KEY].items()
                },
            }
            async with aiofiles.open(self._filename, mode="w") as file_out:
                await file_out.write(json.dumps(serialisable_tables, indent=4))

    async def _create_empty_user(self, user_id: str, user_name: str) -> None:
        new_user = User(user_id, user_name)
        async with self._lock:
            self._tables[self.USER_DATA_KEY][user_id] = new_user
        await self._save_database()
        return self._tables[self.USER_DATA_KEY][user_id]

    @classmethod
    async def open(cls, *, filepath: str | None = None) -> "Database":
        """Open the database.

        Parameters
        ----------
        filepath: str | None, optional
            The file location of the database, by default None

        Returns
        -------
        Database
            An opened and initialised database.

        """
        filepath = Path(filepath or BotSettings.files.database)
        self = cls(filepath=filepath)
        await self._load_database()

        return self

    async def add_reminder(self) -> Reminder:
        raise NotImplementedError

    async def add_user(self, user_id: int, user_name: str) -> User:
        """Add a user to the database.

        This will create an empty user in the database, populating only the
        user_id and the user_name.

        Parameters
        ----------
        user_id : int
            The Discord ID for the user to add.
        user_name : str
            The username for the user to add.

        Returns
        -------
        User
            The user that was added to the database.

        """
        if user_id in self._tables[self.USER_DATA_KEY]:
            self.log_error("User %s already exists in database", user_id)
            return self._tables[self.USER_DATA_KEY][user_id]

        return await self._create_empty_user(user_id, user_name)

    async def get_reminder(self) -> Reminder:
        raise NotImplementedError

    async def get_reminders(self) -> list[Reminder]:
        """Get all the reminders in the database.

        Returns
        -------
        list[Reminder]
            A list of reminders from the database.

        """
        return self._tables[self.REMINDERS_KEY].values()

    async def get_user(self, user_id: int) -> User:
        """Get a user from the database.

        Parameters
        ----------
        user_id : int
            The Discord ID for the user to get.

        Returns
        -------
        User
            The user from the database.

        """
        try:
            return self._tables[self.USER_DATA_KEY][user_id]
        except KeyError:
            self.log_error("User %s not found in database", user_id)
            raise

    async def get_users(self) -> list[User]:
        """Get all the users in the database.

        Returns
        -------
        list[User]
            A list of users from the database.

        """
        return self._tables[self.USER_DATA_KEY].values()

    async def get_reminders_for_user(self, user_id: int) -> list[Reminder]:
        raise NotImplementedError

    async def remove_reminder(self, reminder_id: int) -> Reminder:
        raise NotImplementedError

    async def remove_user(self, user_id: int) -> User:
        """Remove a user from the database.

        Parameters
        ----------
        user_id : int
            The Discord ID for the user to remove.

        Returns
        -------
        User
            The user that was removed from the database.

        """
        try:
            removed_user = self._tables[self.USER_DATA_KEY].pop(user_id)
        except KeyError:
            self.log_error("User %s not found in database", user_id)
            raise
        else:
            await self._save_database()
            return removed_user

    async def update_user(self, user_id: str, field: str, value: str) -> User:
        """Update a user in the database.

        Parameters
        ----------
        user_id : int
            The Discord ID for the user to update.
        field : str
            The field to update.
        value : str
            The value to update the field to.

        Returns
        -------
        User
            The user that was updated in the database.

        """
        if field not in [f.name for f in fields(User)]:
            msg = f"{field} is an unknown field"
            raise ValueError(msg)
        user = await self.get_user(user_id)

        match field:
            case "city":
                user.city = value
            case "country_code":
                user.country_code = value
            case "bad_word":
                user.bad_word = value
            case _:
                msg = f"Unknown field {field}"
                raise ValueError(msg)
        await self._save_database()

        return user


if __name__ == "__main__":

    async def _main():
        db = await Database.open(filepath="data/slashbot_NEW.db.json")
        new_user = await db.add_user(1, "test_user")
        print("New user:", new_user)
        print("All users:", await db.get_users())
        await db.update_user(1, "city", "Paris")
        print("Updated user:", await db.get_user(1))

    asyncio.run(_main())
