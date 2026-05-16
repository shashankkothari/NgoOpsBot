"""
Staff conversation threads endpoints.

GET /api/v1/staff/threads          — list threads for the authenticated staff member
GET /api/v1/staff/threads/{id}     — detail with ordered messages
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.staff_auth import get_current_staff
from app.models.conversation import Conversation, ConversationThread
from app.models.staff import Staff

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


# ---------------------------------------------------------------------------
# Response schemas (local — narrow read shapes for this resource)
# ---------------------------------------------------------------------------

class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_name: str
    started_at: datetime
    last_activity_at: datetime
    message_count: int
    is_active: bool


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    agent_name: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime


class ThreadDetail(ThreadRead):
    messages: list[MessageRead]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/threads", response_model=list[ThreadRead])
async def list_threads(
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> list[ThreadRead]:
    """Return all conversation threads for the authenticated staff member, newest first."""
    result = await db.execute(
        select(ConversationThread)
        .where(ConversationThread.staff_id == staff.id)
        .order_by(ConversationThread.last_activity_at.desc())
    )
    threads = result.scalars().all()
    return [ThreadRead.model_validate(t) for t in threads]


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: uuid.UUID,
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> ThreadDetail:
    """Return a single thread with its messages ordered oldest-first."""
    result = await db.execute(
        select(ConversationThread).where(
            ConversationThread.id == thread_id,
            ConversationThread.staff_id == staff.id,
        )
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    msg_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.ngo_id == staff.ngo_id,
            Conversation.staff_id == staff.id,
            Conversation.agent_name == thread.agent_name,
        )
        .order_by(Conversation.created_at.asc())
    )
    messages = msg_result.scalars().all()

    return ThreadDetail(
        id=thread.id,
        agent_name=thread.agent_name,
        started_at=thread.started_at,
        last_activity_at=thread.last_activity_at,
        message_count=thread.message_count,
        is_active=thread.is_active,
        messages=[MessageRead.model_validate(m) for m in messages],
    )
