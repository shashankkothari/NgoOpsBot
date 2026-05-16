"""
Staff chat endpoint — routes a message to the appropriate specialist agent.

POST /api/v1/staff/chat
  Body: {agent_name: str, message: str}
  Returns: {reply: str, thread_id: str, agent_name: str}
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.dispatcher import (
    AgentNotEnabledError,
    AgentNotFoundError,
    AgentNotPermittedError,
    dispatch,
)
from app.bot.conversation_store import get_conversation_history, save_conversation_turn
from app.core.cache import get_redis
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.staff_auth import get_current_staff
from app.models.conversation import ConversationThread
from app.models.ngo import NGO, NGOSettings
from app.models.staff import Staff

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/staff", tags=["staff"])

# Sentinel values used when persisting API-originated turns (no Telegram context)
_API_SENTINEL_CHAT_ID = 0
_API_SENTINEL_MSG_ID = 0


class ChatRequest(BaseModel):
    agent_name: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    agent_name: str


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Send a message to a specialist agent on behalf of the authenticated staff member.

    Validates that:
      1. The agent exists in the registry.
      2. The staff member is allowed to use the agent.
      3. The agent is enabled for this NGO.

    Conversation history is loaded and the new turns are persisted, mirroring
    the Telegram bot flow so threads are shared across channels.
    """
    agent_name = payload.agent_name.strip().lower()

    # -- Validate agent access at the staff level first (cheap check) --
    if (
        agent_name != "general"
        and staff.allowed_agents
        and agent_name not in staff.allowed_agents
    ):
        raise HTTPException(
            status_code=403,
            detail=f"You are not permitted to use agent '{agent_name}'",
        )

    # -- Load NGO with settings --
    result = await db.execute(
        select(NGO)
        .options(selectinload(NGO.settings))
        .where(NGO.id == staff.ngo_id, NGO.is_active.is_(True))
    )
    ngo = result.scalar_one_or_none()
    if ngo is None:
        raise HTTPException(status_code=403, detail="NGO not found or inactive")

    ngo_settings: list[NGOSettings] = list(ngo.settings)

    # -- Load conversation history --
    history = await get_conversation_history(
        ngo_id=ngo.id,
        staff_id=staff.id,
        agent_name=agent_name,
        db=db,
    )

    # -- Get Redis client for agent prompt caching --
    redis_client = await get_redis()

    # -- Dispatch to agent --
    try:
        response = await dispatch(
            agent_name=agent_name,
            user_message=payload.message,
            ngo=ngo,
            staff=staff,
            conversation_history=history,
            ngo_settings=ngo_settings,
            db=db,
            redis_client=redis_client,
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AgentNotEnabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AgentNotPermittedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        # Covers invalid Anthropic API key and other agent-level config errors.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # -- Persist user turn --
    await save_conversation_turn(
        ngo_id=ngo.id,
        staff_id=staff.id,
        agent_name=agent_name,
        role="user",
        content=payload.message,
        telegram_message_id=_API_SENTINEL_MSG_ID,
        chat_id=_API_SENTINEL_CHAT_ID,
        tokens_used=None,
        language_detected=None,
        db=db,
    )

    # -- Persist assistant turn --
    await save_conversation_turn(
        ngo_id=ngo.id,
        staff_id=staff.id,
        agent_name=agent_name,
        role="assistant",
        content=response.text,
        telegram_message_id=_API_SENTINEL_MSG_ID,
        chat_id=_API_SENTINEL_CHAT_ID,
        tokens_used=response.input_tokens + response.output_tokens,
        language_detected=response.language_detected,
        db=db,
    )

    # -- Fetch the active thread id for the response --
    thread_result = await db.execute(
        select(ConversationThread)
        .where(
            ConversationThread.ngo_id == ngo.id,
            ConversationThread.staff_id == staff.id,
            ConversationThread.agent_name == agent_name,
            ConversationThread.is_active.is_(True),
        )
        .order_by(ConversationThread.last_activity_at.desc())
        .limit(1)
    )
    thread = thread_result.scalar_one_or_none()
    thread_id = str(thread.id) if thread else str(uuid.uuid4())

    log.info(
        "staff_chat_completed",
        staff_id=str(staff.id),
        ngo_slug=ngo.slug,
        agent_name=agent_name,
        thread_id=thread_id,
    )

    return ChatResponse(
        reply=response.text,
        thread_id=thread_id,
        agent_name=agent_name,
    )
