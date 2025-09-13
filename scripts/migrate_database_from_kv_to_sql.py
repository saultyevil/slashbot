import asyncio
import datetime
from pathlib import Path

from slashbot.core.database import DatabaseKV, DatabaseSQL, ReminderKV, ReminderSQL, UserKV, UserSQL
from slashbot.core.logger import setup_logging
from slashbot.settings import BotSettings

setup_logging()


async def main():
    database_kv_path = Path("data/slashbot.db.json").absolute()
    database_kv = await DatabaseKV.open(filepath=database_kv_path)
    database_sql = DatabaseSQL(BotSettings.files.database)
    await database_sql.init()

    users_kv = await database_kv.get_users()
    for user in users_kv:
        await database_sql.add_user(
            UserSQL(
                discord_id=user.user_id,
                username=user.user_name,
                city=user.city,
                country_code=user.country_code,
                bad_word=user.bad_word,
            )
        )

    reminders_kv = await database_kv.get_reminders()
    for reminder in reminders_kv:
        await database_sql.add_reminder(
            ReminderSQL(
                user_id=reminder.user_id,
                channel_id=reminder.channel_id,
                date=datetime.datetime.fromisoformat(reminder.date_iso),
                content=reminder.content,
                tagged_users=reminder.tagged_users,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
