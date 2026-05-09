"""Pydantic v2 schemas for NGO and NGO settings resources.

Intentionally separate from SQLAlchemy models: schemas validate API I/O,
models own persistence.  Sensitive fields (tokens, API keys) are write-only —
they appear in Create payloads but are excluded from Read responses so they
are never accidentally echoed back in API responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# NGOSettings schemas (nested in NGOWithSettings)
# ---------------------------------------------------------------------------

class NGOSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_name: str
    custom_prompt: Optional[str] = None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class NGOSettingUpsert(BaseModel):
    """Used for POST /api/v1/admin/ngos/{id}/settings."""
    agent_name: str = Field(..., max_length=50)
    custom_prompt: Optional[str] = None
    is_enabled: bool = True


# ---------------------------------------------------------------------------
# NGO schemas
# ---------------------------------------------------------------------------

class NGOCreate(BaseModel):
    """Write-only fields required to provision a new NGO tenant."""
    name: str = Field(..., min_length=2, max_length=255)
    # token is plaintext in the request; the service layer encrypts before storing
    telegram_bot_token: str = Field(..., min_length=10)
    # If omitted, the platform ANTHROPIC_API_KEY is used as fallback
    anthropic_api_key: Optional[str] = Field(default=None)
    timezone: str = Field(default="UTC", max_length=64)
    language: str = Field(default="en", max_length=10)


class NGORead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    telegram_group_chat_id: Optional[int] = None
    google_drive_folder_id: Optional[str] = None
    google_master_sheet_id: Optional[str] = None
    timezone: str
    language: str
    created_at: datetime
    updated_at: datetime


class NGOUpdate(BaseModel):
    """All fields are optional; only provided fields are updated (PATCH semantics)."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    telegram_bot_token: Optional[str] = Field(default=None, min_length=10)
    anthropic_api_key: Optional[str] = None
    telegram_group_chat_id: Optional[int] = None
    google_drive_folder_id: Optional[str] = Field(default=None, max_length=255)
    google_master_sheet_id: Optional[str] = Field(default=None, max_length=255)
    timezone: Optional[str] = Field(default=None, max_length=64)
    language: Optional[str] = Field(default=None, max_length=10)
    is_active: Optional[bool] = None


class NGOWithSettings(NGORead):
    """Full NGO representation including per-agent settings."""
    settings: list[NGOSettingRead] = []


class NGOAdminRead(NGORead):
    """Admin-only view that includes decrypted sensitive fields.

    Only returned by admin endpoints after the caller has been authenticated.
    Never include this schema in public API responses.
    """
    telegram_bot_token_decrypted: Optional[str] = None
    anthropic_api_key_decrypted: Optional[str] = None


class NGOStats(BaseModel):
    """Aggregated usage statistics for a single NGO."""
    ngo_id: uuid.UUID
    ngo_slug: str
    total_messages: int
    total_tokens: int
    active_staff_count: int
    reminder_count: int
    last_activity_at: Optional[datetime] = None


class PaginatedNGOs(BaseModel):
    items: list[NGORead]
    total: int
    page: int
    page_size: int
