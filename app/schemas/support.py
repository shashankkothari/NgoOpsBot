"""Pydantic v2 schemas for SupportTicket resources."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SupportTicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    category: str = Field(
        ...,
        pattern="^(access_request|technical|agent_behaviour|other)$",
    )
    priority: str = Field(..., pattern="^(high|medium|low)$")


class SupportTicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ngo_id: uuid.UUID
    staff_id: uuid.UUID
    title: str
    description: str
    category: str
    priority: str
    status: str
    admin_reply: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Enriched fields — populated manually in route handlers
    staff_name: Optional[str] = None
    ngo_name: Optional[str] = None


class SupportTicketUpdate(BaseModel):
    """Admin-only update — status and/or reply."""

    status: Optional[str] = Field(
        default=None,
        pattern="^(open|in_progress|resolved|closed)$",
    )
    reply: Optional[str] = None
