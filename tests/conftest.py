"""Pytest configuration and shared fixtures for NGO OpsBot test suite.

Fixtures provided:
- event_loop          — single asyncio event loop for the entire session
- async_engine        — SQLAlchemy async engine pointed at test DB
- async_session       — AsyncSession scoped per test (rolled back after)
- client              — HTTPX async test client wrapping the FastAPI app
- mock_ngo            — a minimal NGO row dict (no DB write)
- mock_staff          — a minimal Staff row dict (no DB write)
- override_settings   — monkeypatches Settings for a single test
- mock_ngo_model      — a fully-populated NGO SQLAlchemy model instance (not in DB)
- mock_staff_model    — a staff member with access to all agents
- mock_ngo_settings   — all 5 agents enabled with no custom prompts
- admin_headers       — X-Admin-API-Key header dict for admin endpoints
- sample_telegram_update — minimal valid Telegram Update dict for a text message
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Point tests at a dedicated test database — never the production one.
# Fall back to an in-memory SQLite for environments without PostgreSQL.
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///./test.db",
)

# ---------------------------------------------------------------------------
# Event loop — session-scoped so all async fixtures share one loop
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create a session-scoped event loop."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database engine — session-scoped (created once, dropped at end)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create all tables at the start of the test session, drop them at the end."""
    from app.models.base import Base  # noqa: PLC0415

    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ---------------------------------------------------------------------------
# Async session — function-scoped with automatic rollback
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional AsyncSession that is rolled back after each test.

    This keeps the database clean without needing to truncate tables.
    """
    async_session_factory = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async with async_engine.begin() as conn:
        # Use a nested transaction (SAVEPOINT) so we can rollback after the test
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            await session.begin_nested()
            yield session
            await session.rollback()


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async test client with dependency overrides for the DB session."""
    # Import lazily to avoid circular imports at collection time
    from app.main import app  # noqa: PLC0415
    from app.core.database import get_db_session  # noqa: PLC0415

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_session

    app.dependency_overrides[get_db_session] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Admin-API-Key": "test-admin-key"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Mock data factories
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_ngo() -> dict[str, Any]:
    """Return a dict representing a minimal NGO record (not persisted to DB)."""
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Test NGO",
        "slug": "test-ngo",
        "telegram_token_encrypted": b"encrypted-token-bytes",
        "anthropic_key_encrypted": b"encrypted-anthropic-key",
        "admin_chat_id": 123456789,
        "is_active": True,
        "plan": "starter",
        "timezone": "UTC",
    }


@pytest.fixture
def mock_staff() -> dict[str, Any]:
    """Return a dict representing a minimal Staff member (not persisted to DB)."""
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "ngo_id": "11111111-1111-1111-1111-111111111111",
        "telegram_user_id": 987654321,
        "name": "Test Staffer",
        "role": "coordinator",
        "is_active": True,
        "phone": "+919876543210",
        "email": "staffer@testngo.org",
    }


# ---------------------------------------------------------------------------
# Settings override helper
# ---------------------------------------------------------------------------
@pytest.fixture
def override_settings() -> Generator[MagicMock, None, None]:
    """Monkeypatch app.core.config.settings for a single test.

    Usage::

        def test_something(override_settings):
            override_settings.ADMIN_API_KEY = "my-test-key"
            ...
    """
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.ADMIN_API_KEY = "test-admin-key"
        mock_settings.ENV = "development"
        mock_settings.DEBUG = True
        mock_settings.ENCRYPTION_KEY = "Ynz3RkUqXjZVf7VbUlG0kNlHhN4aQyAqMFo4Y6T8Fg0="
        mock_settings.WEBHOOK_SECRET = "test-webhook-secret"
        mock_settings.ANTHROPIC_MODEL = "claude-opus-4-5"
        yield mock_settings


# ---------------------------------------------------------------------------
# Telegram bot mock
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_telegram_bot() -> AsyncMock:
    """Return a fully mocked python-telegram-bot Bot instance."""
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    bot.send_document = AsyncMock(return_value=MagicMock(message_id=2))
    bot.get_file = AsyncMock()
    return bot


# ---------------------------------------------------------------------------
# Model-level fixtures (in-memory, not persisted to DB)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ngo_model() -> Any:
    """A fully-populated NGO SQLAlchemy model instance (not in DB).

    Sensitive fields are encrypted with a throwaway test key so they
    can be round-tripped through decrypt_field() in tests that need it.
    """
    import os
    from cryptography.fernet import Fernet

    # Generate a fresh key for the fixture and set it as the active key
    # so encrypt_field/decrypt_field work without hitting the app config.
    test_key = Fernet.generate_key().decode()
    os.environ["ENCRYPTION_KEY"] = test_key

    from app.core.security import _get_fernet, encrypt_field
    _get_fernet.cache_clear()

    from app.models.ngo import NGO

    ngo = NGO.__new__(NGO)
    ngo.id = uuid4()
    ngo.name = "Test NGO"
    ngo.slug = "test-ngo"
    ngo.telegram_group_chat_id = -1001234567890
    ngo.is_active = True
    ngo.timezone = "Asia/Kolkata"
    ngo.language = "en"
    ngo.webhook_secret = "test-webhook-secret-abc123"
    ngo.telegram_bot_token = encrypt_field("1234567890:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQ")
    ngo.anthropic_api_key = encrypt_field("sk-ant-test")
    ngo.google_refresh_token = None
    ngo.google_drive_folder_id = None
    ngo.google_master_sheet_id = None
    return ngo


@pytest.fixture
def mock_staff_model(mock_ngo_model: Any) -> Any:
    """A staff member with access to all agents."""
    from app.models.staff import Staff

    staff = Staff.__new__(Staff)
    staff.id = uuid4()
    staff.ngo_id = mock_ngo_model.id
    staff.telegram_user_id = 987654321
    staff.telegram_username = "priya_sharma"
    staff.name = "Priya Sharma"
    staff.role = "admin"
    staff.allowed_agents = ["fundraising", "finance", "marketing", "hr", "compliance"]
    staff.is_active = True
    staff.phone = "+919876543210"
    staff.email = "priya@testngo.org"
    return staff


@pytest.fixture
def mock_ngo_settings(mock_ngo_model: Any) -> list:
    """All 5 agents enabled with no custom prompts."""
    from app.models.ngo import NGOSettings

    result = []
    for name in ["fundraising", "finance", "marketing", "hr", "compliance"]:
        s = NGOSettings.__new__(NGOSettings)
        s.id = uuid4()
        s.ngo_id = mock_ngo_model.id
        s.agent_name = name
        s.is_enabled = True
        s.custom_prompt = None
        result.append(s)
    return result


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """X-Admin-API-Key header dict for admin endpoint requests."""
    return {"X-Admin-API-Key": "test-admin-key"}


@pytest.fixture
def sample_telegram_update() -> dict[str, Any]:
    """Minimal valid Telegram Update dict for a text message with a @mention."""
    return {
        "update_id": 123456789,
        "message": {
            "message_id": 1,
            "from": {"id": 987654321, "is_bot": False, "first_name": "Priya"},
            "chat": {"id": -1001234567890, "type": "supergroup"},
            "text": "@testbot What donors haven't given in 6 months?",
            "entities": [{"type": "mention", "offset": 0, "length": 8}],
            "date": 1700000000,
        },
    }
