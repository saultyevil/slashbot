import asyncio
import datetime

import slashbot.core.database as old_database
import slashbot.core.database as new_database
from slashbot.core.logger import setup_logging
from slashbot.settings import BotSettings

setup_logging()


async def main():
    BotSettings.files.database = "data/slashbot.db.json"
    db_new = await new_database.Database.open(filepath="data/slashbot_NEW.db.json")
    users_to_migrate = old_database.get_users()

    for user_id, user_data in users_to_migrate.items():
        user_id = int(user_id)
        await db_new.add_user(user_id, user_data["user_name"])
        await db_new.update_user(user_id, "city", user_data["city"])
        await db_new.update_user(user_id, "country_code", user_data["country_code"])
        user = await db_new.update_user(user_id, "bad_word", user_data["bad_word"])
        print(user)

    reminders_to_migrate = old_database.get_all_reminders()

    for reminder in reminders_to_migrate:
        user_id = int(reminder["user_id"])
        channel_id = int(reminder["channel"])
        date = reminder["date"]
        content = reminder["reminder"]
        tagged_users = reminder["tagged_users"]

        new_reminder = new_database.Reminder(user_id, channel_id, date, content, tagged_users)
        await db_new.add_reminder(new_reminder)

    print(await db_new.get_reminders())


if __name__ == "__main__":
    asyncio.run(main())
