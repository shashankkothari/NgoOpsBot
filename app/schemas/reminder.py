"""Pydantic v2 schemas for Reminder and ReminderLog resources."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    reminder_type: str = Field(
        ...,
        pattern="^(date_based|inactivity|threshold|recurring|event_triggered)$",
    )
    agent_name: Optional[str] = Field(default=None, max_length=50)
    config: dict[str, Any] = Field(default_factory=dict)
    target_audience: str = Field(
        ..., pattern="^(staff_group|specific_staff|external)$"
    )
    target_details: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = True


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ngo_id: uuid.UUID
    title: str
    reminder_type: str
    agent_name: Optional[str] = None
    config: dict[str, Any]
    target_audience: str
    target_details: dict[str, Any]
    requires_approval: bool
    is_active: bool
    last_fired_at: Optional[datetime] = None
    next_fire_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ReminderLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reminder_id: uuid.UUID
    ngo_id: uuid.UUID
    approved_by_staff_id: Optional[uuid.UUID] = None
    fired_at: datetime
    status: str  # sent | pending_approval | approved | rejected | failed
    content: str
    sent_via: str  # telegram | sms | email
    error_message: Optional[str] = None
