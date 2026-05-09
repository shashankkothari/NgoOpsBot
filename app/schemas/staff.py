"""Pydantic v2 schemas for Staff resources."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StaffCreate(BaseModel):
    ngo_id: uuid.UUID
    telegram_user_id: int
    telegram_username: Optional[str] = Field(default=None, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., pattern="^(admin|staff)$")
    # Empty list means no agent access until explicitly granted
    allowed_agents: list[str] = Field(default_factory=list)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[EmailStr] = None


class StaffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ngo_id: uuid.UUID
    telegram_user_id: int
    telegram_username: Optional[str] = None
    name: str
    role: str
    allowed_agents: list[str]
    is_active: bool
    phone: Optional[str] = None
    email: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @property
    def agent_count(self) -> int:
        """Convenience count; avoids the caller having to measure the list."""
        return len(self.allowed_agents)


class StaffUpdate(BaseModel):
    """Partial update — only supplied fields are applied."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    role: Optional[str] = Field(default=None, pattern="^(admin|staff)$")
    allowed_agents: Optional[list[str]] = None
    is_active: Optional[bool] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[EmailStr] = None
    telegram_username: Optional[str] = Field(default=None, max_length=255)


class PaginatedStaff(BaseModel):
    items: list[StaffRead]
    total: int
    page: int
    page_size: int
