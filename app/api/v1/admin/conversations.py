"""Admin read-only endpoints for conversation history.

No mutations here — conversations are immutable records of what was said.
Pagination is mandatory; returning unbounded conversation history would
exhaust memory for high-volume NGOs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.conversation import Conversation, ConversationThread
from app.schemas.conversation import (
    ConversationRead,
    ConversationThreadRead,
    PaginatedConversations,
)

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/admin/conversations", tags=["admin-conversations"])


@router.get("", response_model=PaginatedConversations)
async def list_conversations(
    ngo_id: Optional[uuid.UUID] = Query(None),
    agent_name: Optional[str] = Query(None, max_length=50),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> PaginatedConversations:
    from sqlalchemy import func

    query = select(Conversation)

    if ngo_id is not None:
        query = query.where(Conversation.ngo_id == ngo_id)
    if agent_name is not None:
        query = query.where(Conversation.agent_name == agent_name)
    if date_from is not None:
        query = query.where(Conversation.created_at >= date_from)
    if date_to is not None:
        query = query.where(Conversation.created_at <= date_to)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = (
        query.order_by(Conversation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    convs = result.scalars().all()

    return PaginatedConversations(
        items=[ConversationRead.model_validate(c) for c in convs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{thread_id}", response_model=ConversationThreadRead)
async def get_thread(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ConversationThreadRead:
    """Return a thread with all its messages.

    Messages are fetched via a second query rather than a joined load to keep
    the thread row lightweight for callers who only need metadata.  The
    thread endpoint is expected to be a low-frequency admin view, not a
    hot path.
    """
    result = await db.execute(
        select(ConversationThread).where(ConversationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Fetch messages belonging to this thread's NGO + agent within the thread timespan.
    # ConversationThread doesn't have a direct FK to Conversation rows in the current
    # schema — conversations are scoped to (ngo_id, agent_name).  We match on
    # ngo_id + agent_name + started_at window as the closest proxy.
    messages_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.ngo_id == thread.ngo_id,
            Conversation.agent_name == thread.agent_name,
            Conversation.staff_id == thread.staff_id,
            Conversation.created_at >= thread.started_at,
        )
        .order_by(Conversation.created_at.asc())
        .limit(500)  # hard cap — thread detail view is not infinite scroll
    )
    messages = messages_result.scalars().all()

    data = ConversationThreadRead.model_validate(thread)
    data.messages = [ConversationRead.model_validate(m) for m in messages]
    return data
