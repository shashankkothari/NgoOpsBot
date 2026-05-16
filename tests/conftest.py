"""
Root pytest configuration — sets environment variables before any app module
is imported, so Settings() and security helpers read the right test values.

All test fixtures live in tests/integration/conftest.py.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()

os.environ.setdefault("ENV", "test")
os.environ.setdefault("ENCRYPTION_KEY", _TEST_FERNET_KEY)
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("STAFF_JWT_SECRET", "test-staff-jwt-secret")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://shashankkothari@127.0.0.1:5432/ngoopsbot_test",
)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from app.core.config import get_settings  # noqa: E402
from app.core.security import _get_fernet  # noqa: E402

get_settings.cache_clear()
_get_fernet.cache_clear()
