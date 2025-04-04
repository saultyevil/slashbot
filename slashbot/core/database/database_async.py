import asyncio
import json
from pathlib import Path

import aiofiles

from slashbot.core.database.models import Reminder, User
from slashbot.settings import BotSettings


class Database:
    """Asynchronous database class."""

    def __init__(self, *, filename: str | None = None) -> None:
        """Initialise the database.

        Parameters
        ----------
        filename : str, optional
            The filename of the database, by default None where the value of it
            is taken from BotSettings.

        """
        self._filename = filename or BotSettings.files.database
        self._filename = Path(self._filename)
        if not self._filename.exists():
            msg = f"Database file does not exist at {self._filename}"
            raise FileNotFoundError(msg)

        self._lock = asyncio.Lock()
        self._tables = {"user_data": {}, "reminders": {}}
        self._load_database()

    async def _load_database(self) -> None:
        async with self._lock, aiofiles.open(self._filename) as file_in:
            content = await file_in.read()
            data = json.loads(content)
            raw_users = data.get("tables", {}).get("user_data", {})
            self._tables["user_data"] = {int(k): User.from_dict(v) for k, v in raw_users.items()}
            self._tables["reminders"] = data.get("tables", {}).get("reminders", {})

    async def _save_database(self) -> None:
        async with self._lock:
            serialisable_tables = {
                "user_data": {user_id: user.to_dict() for user_id, user in self._tables["user_data"].items()},
                "reminders": {
                    reminder_id: reminder.to_dict() for reminder_id, reminder in self._tables["reminders"].items()
                },
            }
            async with aiofiles.open(self._filename, mode="w") as f:
                await f.write(json.dumps({"tables": serialisable_tables}, indent=4))

    async def _create_empty_user(self, user_id: int) -> None:
        raise NotImplementedError

    async def get_users():
        raise NotImplementedError

    async def get_user():
        raise NotImplementedError

    async def update_user():
        raise NotImplementedError

    async def get_reminders():
        raise NotImplementedError

    async def get_reminders_for_user():
        raise NotImplementedError

    async def get_reminder():
        raise NotImplementedError

    async def add_reminder():
        raise NotImplementedError

    async def remove_reminder():
        raise NotImplementedError
