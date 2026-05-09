"""
Async SQLAlchemy engine, session factory, and FastAPI dependency.

Uses asyncpg as the database driver.  Configuration is sourced from
``app.core.config.settings`` (reads ``DATABASE_URL``, ``DB_POOL_SIZE``,
``DB_MAX_OVERFLOW``, and ``DEBUG`` from the environment / .env file).

Public API
----------
``engine``           — module-level AsyncEngine singleton.
``AsyncSessionLocal``— session factory (async_sessionmaker).
``get_db``           — FastAPI dependency (also aliased as ``get_db_session``).
``init_db``          — call during app startup to validate connectivity.
``close_db``         — call during app shutdown to dispose the pool.
``get_engine``       — returns the engine, raising if not yet created.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.models.base import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons — built once at import time from settings
# ---------------------------------------------------------------------------

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,   # detect stale connections before use
    pool_recycle=1800,    # recycle connections every 30 min
    echo=settings.DEBUG,
    future=True,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # avoids lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Lifespan helpers
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """
    Validate database connectivity on startup.

    Does NOT run migrations — use Alembic for that.
    Call this from the FastAPI lifespan startup handler.
    """
    async with engine.connect() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    logger.info("Database connectivity confirmed (driver: asyncpg)")


async def close_db() -> None:
    """
    Dispose of the engine connection pool on shutdown.

    Call this from the FastAPI lifespan teardown handler.
    """
    await engine.dispose()
    logger.info("Database engine disposed")


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a transactional ``AsyncSession``.

    Each request gets its own session.  The session is committed on a
    clean exit and rolled back on any exception before being closed.

    Usage::

        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Alias kept for backward-compat with any existing callers
get_db_session = get_db


# ---------------------------------------------------------------------------
# Low-level helpers (useful for Alembic env.py or test fixtures)
# ---------------------------------------------------------------------------

def get_engine() -> AsyncEngine:
    """Return the module-level engine."""
    return engine


async def create_all_tables(connection: AsyncConnection) -> None:
    """
    Create all tables from the SQLAlchemy metadata.

    Intended only for development / test environments.
    Production deployments must use Alembic migrations.
    """
    await connection.run_sync(Base.metadata.create_all)


async def drop_all_tables(connection: AsyncConnection) -> None:
    """Drop all tables — test environments only."""
    await connection.run_sync(Base.metadata.drop_all)
