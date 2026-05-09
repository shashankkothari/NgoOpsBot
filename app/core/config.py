"""Application settings — single source of truth for all configuration.

Loaded from environment variables and/or a .env file via pydantic-settings.
Import `get_settings()` everywhere; never import `settings` directly from
other modules so the lru_cache singleton is honoured and tests can override.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------------------------------------------------------------- #
    # Application identity                                                     #
    # ---------------------------------------------------------------------- #
    APP_VERSION: str = "0.1.0"
    APP_BASE_URL: str = "http://localhost:8000"
    ENV: Literal["development", "production", "test"] = "development"
    DEBUG: bool = True
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING"] = "INFO"

    # ---------------------------------------------------------------------- #
    # Database                                                                 #
    # ---------------------------------------------------------------------- #
    # asyncpg for runtime; psycopg2 URL used only by Alembic's sync engine
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ngoopsbot"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/ngoopsbot"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ---------------------------------------------------------------------- #
    # Redis                                                                    #
    # ---------------------------------------------------------------------- #
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---------------------------------------------------------------------- #
    # Security                                                                 #
    # ---------------------------------------------------------------------- #
    ENCRYPTION_KEY: str = ""  # 32-byte Fernet key, base64-encoded
    WEBHOOK_SECRET: str = ""  # HMAC secret embedded in Telegram webhook URL
    ADMIN_API_KEY: str = ""   # Bearer token for /api/v1/admin/* routes
    SECRET_KEY: str = "change-me"

    # ---------------------------------------------------------------------- #
    # AI — platform-level fallbacks; NGOs override with their own keys        #
    # ---------------------------------------------------------------------- #
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-4-5"
    ANTHROPIC_MAX_TOKENS: int = 4096
    OPENAI_API_KEY: str = ""  # Whisper transcription
    WHISPER_MODEL: str = "whisper-1"

    # ---------------------------------------------------------------------- #
    # Communications                                                           #
    # ---------------------------------------------------------------------- #
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "noreply@example.com"
    SENDGRID_FROM_NAME: str = "NGO OpsBot"
    MSG91_API_KEY: str = ""
    MSG91_SENDER_ID: str = "NGOBOT"
    MSG91_BASE_URL: str = "https://api.msg91.com/api/v5"

    # ---------------------------------------------------------------------- #
    # Google OAuth / APIs                                                      #
    # ---------------------------------------------------------------------- #
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""

    # ---------------------------------------------------------------------- #
    # Observability                                                            #
    # ---------------------------------------------------------------------- #
    SENTRY_DSN: str = ""
    # Lower sample rate in prod to control cost; set to 1.0 in dev for full visibility
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""  # optional; empty disables OTEL export

    # ---------------------------------------------------------------------- #
    # Scheduler                                                                #
    # ---------------------------------------------------------------------- #
    SCHEDULER_TIMEZONE: str = "UTC"

    # ---------------------------------------------------------------------- #
    # Rate limiting                                                            #
    # ---------------------------------------------------------------------- #
    RATE_LIMIT_PER_MINUTE: int = 60

    # ---------------------------------------------------------------------- #
    # Computed properties                                                      #
    # ---------------------------------------------------------------------- #

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def is_test(self) -> bool:
        return self.ENV == "test"

    # ---------------------------------------------------------------------- #
    # Validators                                                               #
    # ---------------------------------------------------------------------- #

    @field_validator("SENTRY_TRACES_SAMPLE_RATE")
    @classmethod
    def _clamp_sample_rate(cls, v: float) -> float:
        # Pydantic won't catch 0–1 range automatically for floats
        if not 0.0 <= v <= 1.0:
            raise ValueError("SENTRY_TRACES_SAMPLE_RATE must be between 0.0 and 1.0")
        return v

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def _validate_encryption_key(cls, v: str) -> str:
        """Validate ENCRYPTION_KEY is a valid 32-byte Fernet key at startup.

        Failing loudly here (import time) is far preferable to discovering a
        bad key at runtime when the first encrypt_field() call fails mid-request,
        possibly corrupting a DB write.

        Fernet key format: 32 raw bytes encoded as URL-safe base64 (44 chars,
        no padding issues because 32 % 3 != 0, so base64 pads to 44 chars).
        """
        if not v:
            # Allow empty in test/dev; production validator below catches it
            return v
        try:
            decoded = base64.urlsafe_b64decode(v.strip().encode())
        except Exception as exc:
            raise ValueError(
                "ENCRYPTION_KEY is not valid URL-safe base64. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            ) from exc
        if len(decoded) != 32:
            raise ValueError(
                f"ENCRYPTION_KEY decoded to {len(decoded)} bytes; Fernet requires exactly 32."
            )
        return v

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """Enforce that critical secrets are set in production.

        In development or test, empty values are tolerated so developers can
        run the app without a full .env.  In production, an empty secret is a
        misconfiguration that must be caught at startup, not at first use.
        """
        if self.ENV != "production":
            return self

        missing: list[str] = []
        if not self.ENCRYPTION_KEY:
            missing.append("ENCRYPTION_KEY")
        if not self.ADMIN_API_KEY:
            missing.append("ADMIN_API_KEY")
        if not self.SECRET_KEY or self.SECRET_KEY == "change-me":
            missing.append("SECRET_KEY (must not be the default 'change-me')")

        if missing:
            raise ValueError(
                f"The following required secrets are not set for production: "
                f"{', '.join(missing)}. "
                "Set them in the environment or .env file before starting."
            )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton.

    Using lru_cache means .env is parsed exactly once.  Tests that need
    different values should call get_settings.cache_clear() after patching
    the environment.
    """
    return Settings()


# Module-level alias — database.py and security.py import this directly.
# All new code should prefer get_settings().
settings = get_settings()
