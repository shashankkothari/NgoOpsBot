"""Alembic environment — async-compatible with asyncpg.

Uses SYNC_DATABASE_URL (psycopg2 driver) for the synchronous Alembic runner,
and imports all SQLAlchemy models so autogenerate can detect schema changes.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ---------------------------------------------------------------------------
# Import the shared metadata from all models so autogenerate sees every table.
# Add new model modules here as they are created.
# ---------------------------------------------------------------------------
from app.models.base import Base  # noqa: F401 — registers metadata

# Ensure all model modules are imported so their tables appear in metadata.
# fmt: off
import app.models.ngo          # noqa: F401
import app.models.staff        # noqa: F401
import app.models.conversation  # noqa: F401
import app.models.task         # noqa: F401
import app.models.audit_log    # noqa: F401
# fmt: on

# ---------------------------------------------------------------------------
# Alembic Config object (gives access to .ini values)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging if present
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate support
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Read DB URL from environment — overrides whatever is in alembic.ini
# ---------------------------------------------------------------------------
def get_url() -> str:
    """Return the synchronous DB URL for Alembic migrations.

    We use the psycopg2-based SYNC_DATABASE_URL so Alembic's built-in
    synchronous engine works without any extra async wrappers.
    Falls back to DATABASE_URL with the async driver swapped out.
    """
    sync_url = os.environ.get("SYNC_DATABASE_URL")
    if sync_url:
        return sync_url

    async_url = os.environ.get("DATABASE_URL", "")
    # Convert asyncpg DSN to psycopg2 DSN for synchronous migrations
    return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


# ---------------------------------------------------------------------------
# Run migrations offline (no live DB connection — generates SQL script)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Generate migration SQL without connecting to the database.

    Useful for reviewing what will be applied, or for DBAs who apply SQL manually.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Run migrations online (synchronous path — Alembic default)
# ---------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Include schemas if you use PostgreSQL schemas other than 'public'
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection (synchronous)."""
    configuration: dict[str, Any] = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


# ---------------------------------------------------------------------------
# Async path (optional — kept for reference if you switch to async runner)
# ---------------------------------------------------------------------------
async def run_async_migrations() -> None:
    """Async migration runner — not used by default but available."""
    configuration: dict[str, Any] = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = os.environ.get(
        "DATABASE_URL",
        configuration.get("sqlalchemy.url", ""),
    )

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
