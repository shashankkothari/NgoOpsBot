"""Pydantic v2 schemas for Conversation and ConversationThread resources."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ngo_id: uuid.UUID
    staff_id: Optional[uuid.UUID] = None
    telegram_message_id: int
    telegram_chat_id: int
    agent_name: Optional[str] = None
    role: str  # user | assistant
    content: str
    language_detected: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ConversationThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ngo_id: uuid.UUID
    staff_id: Optional[uuid.UUID] = None
    agent_name: str
    message_count: int
    is_active: bool
    started_at: datetime
    last_activity_at: datetime
    # Populated only when fetching a single thread with ?include_messages=true
    messages: list[ConversationRead] = []


class PaginatedConversations(BaseModel):
    items: list[ConversationRead]
    total: int
    page: int
    page_size: int
