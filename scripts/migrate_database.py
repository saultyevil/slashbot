import asyncio

import slashbot.core.database as old_database
import slashbot.core.database_NEW as new_database
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


if __name__ == "__main__":
    asyncio.run(main())
