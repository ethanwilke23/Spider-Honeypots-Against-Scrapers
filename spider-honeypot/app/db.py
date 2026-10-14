"""Async SQLAlchemy engine and session setup for Postgres (asyncpg driver)."""
import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=(settings.app_env == "development"),
    future=True,
)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Shared declarative base for the ORM models."""


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def check_connection() -> bool:
    """Check that the database is reachable. Used by the /health endpoint."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True


async def wait_for_database(max_attempts: int = 10, delay_seconds: float = 2.0) -> None:
    """
    Try to connect to the database, retrying a fixed number of times.

    Postgres can report that its container has started before it is ready
    to accept logins, so connecting straight after `docker compose up -d`
    can fail, sometimes with an authentication error rather than a
    connection error. A few retries avoid that start-up race.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            await check_connection()
            return
        except Exception as exc:  # noqa: BLE001 - asyncpg raises its own error types
            last_error = exc
            if attempt < max_attempts:
                await asyncio.sleep(delay_seconds)
    raise RuntimeError(
        f"Could not reach the database after {max_attempts} attempts "
        f"({max_attempts * delay_seconds:.0f}s). Last error: {last_error}"
    ) from last_error