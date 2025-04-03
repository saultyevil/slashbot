import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.future import select
from sqlalchemy.orm import relationship, sessionmaker

from slashbot.core.logger import Logger
from slashbot.settings import BotSettings

Base = declarative_base()


# Models
class User(Base):
    """User model for database storage."""

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    user_name = Column(String(100), nullable=False)
    city = Column(String(100), default="")
    country_code = Column(String(2), default="")
    bad_word = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.now)

    # Relationship with reminders
    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, user_name='{self.user_name}')>"


class Reminder(Base):
    """Reminder model for database storage."""

    __tablename__ = "reminders"

    reminder_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    remind_at = Column(DateTime, nullable=False)
    completed = Column(Boolean, default=False)

    # Relationship with user
    user = relationship("User", back_populates="reminders")

    def __repr__(self) -> str:
        return f"<Reminder(id={self.reminder_id}, user_id={self.user_id}, remind_at='{self.remind_at}')>"


# Base Database Class
class Database(Logger):
    """Base database class for async SQLAlchemy operations."""

    def __init__(self, db_path: Union[str, Path, None] = None):
        """Initialize database connection."""
        super().__init__()
        self.db_path = Path(db_path or BotSettings.files.database)

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create async database connection
        db_url = f"sqlite+aiosqlite:///{self.db_path}"
        self.engine = create_async_engine(
            db_url,
            pool_pre_ping=True,  # Test connections before use
            pool_size=5,  # Maximum number of connections in the pool
            max_overflow=10,  # Maximum overflow connections
            echo=False,  # Set to True for SQL logging
        )

        self.Session = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Don't expire objects after commit
        )

        # Database access lock
        self._lock = asyncio.Lock()
        self.log_info(f"Async database initialized at {self.db_path}")

    async def initialize_tables(self):
        """Create tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            self.log_info("Database tables created/verified")

    async def get_session(self) -> AsyncSession:
        """Get a new async database session."""
        return self.Session()

    async def execute_with_lock(self, callback, *args, **kwargs):
        """Execute database operations with a lock to prevent simultaneous access."""
        async with self._lock:
            async with self.Session() as session:
                async with session.begin():
                    try:
                        result = await callback(session, *args, **kwargs)
                        return result
                    except Exception as e:
                        self.log_error(f"Database error: {e}")
                        raise


# User Management Class
class UserManager(Database):
    """User management class for handling user operations."""

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get a user by their ID."""

        async def _get_user(session, user_id):
            query = select(User).where(User.user_id == user_id)
            result = await session.execute(query)
            return result.scalars().first()

        return await self.execute_with_lock(_get_user, user_id)

    async def create_user(self, user_id: int, user_name: str) -> User:
        """Create a new user."""

        async def _create_user(session, user_id, user_name):
            user = User(user_id=user_id, user_name=user_name)
            session.add(user)
            await session.flush()
            self.log_info(f"Created user: {user_id} ({user_name})")
            return user

        return await self.execute_with_lock(_create_user, user_id, user_name)

    async def get_or_create_user(self, user_id: int, user_name: str) -> User:
        """Get a user or create them if they don't exist."""
        user = await self.get_user(user_id)
        if not user:
            user = await self.create_user(user_id, user_name)
        return user

    async def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user attributes."""

        async def _update_user(session, user_id, kwargs):
            query = select(User).where(User.user_id == user_id)
            result = await session.execute(query)
            user = result.scalars().first()
            if user:
                for key, value in kwargs.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                await session.flush()
                self.log_info(f"Updated user: {user_id}")
                return user
            return None

        return await self.execute_with_lock(_update_user, user_id, kwargs)

    async def get_all_users(self) -> list[User]:
        """Get all users."""

        async def _get_all_users(session):
            query = select(User)
            result = await session.execute(query)
            return result.scalars().all()

        return await self.execute_with_lock(_get_all_users)

    async def delete_user(self, user_id: int) -> bool:
        """Delete a user and all their reminders."""

        async def _delete_user(session, user_id):
            query = select(User).where(User.user_id == user_id)
            result = await session.execute(query)
            user = result.scalars().first()
            if user:
                await session.delete(user)
                self.log_info(f"Deleted user: {user_id}")
                return True
            return False

        return await self.execute_with_lock(_delete_user, user_id)


# Reminder Management Class
class ReminderManager(Database):
    """Reminder management class for handling reminder operations."""

    async def create_reminder(self, user_id: int, content: str, remind_at: datetime) -> Optional[Reminder]:
        """Create a new reminder."""

        async def _create_reminder(session, user_id, content, remind_at):
            # Check if user exists
            query = select(User).where(User.user_id == user_id)
            result = await session.execute(query)
            user = result.scalars().first()
            if not user:
                self.log_warning(f"Cannot create reminder: User {user_id} not found")
                return None

            reminder = Reminder(user_id=user_id, content=content, remind_at=remind_at)
            session.add(reminder)
            await session.flush()
            self.log_info(f"Created reminder for user {user_id}")
            return reminder

        return await self.execute_with_lock(_create_reminder, user_id, content, remind_at)

    async def get_reminder(self, reminder_id: int) -> Optional[Reminder]:
        """Get a reminder by ID."""

        async def _get_reminder(session, reminder_id):
            query = select(Reminder).where(Reminder.reminder_id == reminder_id)
            result = await session.execute(query)
            return result.scalars().first()

        return await self.execute_with_lock(_get_reminder, reminder_id)

    async def get_user_reminders(self, user_id: int) -> list[Reminder]:
        """Get all reminders for a user."""

        async def _get_user_reminders(session, user_id):
            query = select(Reminder).where(Reminder.user_id == user_id)
            result = await session.execute(query)
            return result.scalars().all()

        return await self.execute_with_lock(_get_user_reminders, user_id)

    async def mark_reminder_completed(self, reminder_id: int) -> bool:
        """Mark a reminder as completed."""

        async def _mark_completed(session, reminder_id):
            query = select(Reminder).where(Reminder.reminder_id == reminder_id)
            result = await session.execute(query)
            reminder = result.scalars().first()
            if reminder:
                reminder.completed = True
                await session.flush()
                self.log_info(f"Marked reminder {reminder_id} as completed")
                return True
            return False

        return await self.execute_with_lock(_mark_completed, reminder_id)

    async def delete_reminder(self, reminder_id: int) -> bool:
        """Delete a reminder."""

        async def _delete_reminder(session, reminder_id):
            query = select(Reminder).where(Reminder.reminder_id == reminder_id)
            result = await session.execute(query)
            reminder = result.scalars().first()
            if reminder:
                await session.delete(reminder)
                self.log_info(f"Deleted reminder {reminder_id}")
                return True
            return False

        return await self.execute_with_lock(_delete_reminder, reminder_id)

    async def get_pending_reminders(self) -> list[Reminder]:
        """Get all pending reminders (not completed and due)."""

        async def _get_pending(session):
            now = datetime.now()
            query = select(Reminder).where(Reminder.completed == False, Reminder.remind_at <= now)
            result = await session.execute(query)
            return result.scalars().all()

        return await self.execute_with_lock(_get_pending)


# Main Bot Database Class
class BotDatabase:
    """Main database class for the bot that provides access to all managers."""

    def __init__(self, db_path: Union[str, Path, None] = None):
        """Initialize database managers."""
        self.db_path = db_path
        self.users = UserManager(db_path)
        self.reminders = ReminderManager(db_path)

    async def initialize(self):
        """Initialize database tables."""
        await self.users.initialize_tables()

    async def close(self):
        """Close database connections."""
        if hasattr(self.users, "engine"):
            await self.users.engine.dispose()


# Example usage
async def main():
    # Create a database instance
    db = BotDatabase("test.db")
    await db.initialize()

    # Create a user
    user = await db.users.create_user(123456789, "TestUser")

    # Create a reminder
    remind_time = datetime.now().replace(hour=20, minute=0, second=0)
    reminder = await db.reminders.create_reminder(123456789, "Time to play games!", remind_time)

    # Get pending reminders
    pending = await db.reminders.get_pending_reminders()
    print(f"Pending reminders: {pending}")

    # Close connections
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
