"""
Admin support ticket management.

Uses the existing X-Admin-API-Key auth (enforced by NGOAuthMiddleware).

GET   /api/v1/admin/support       — paginated list; ?ngo_id=, ?status=, ?priority=
GET   /api/v1/admin/support/{id}  — single ticket with staff/ngo names
PATCH /api/v1/admin/support/{id}  — update status and/or reply; sends Telegram notifications
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.comms.telegram_sender import send_to_group, send_to_staff
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.ngo import NGO
from app.models.staff import Staff
from app.models.support import SupportTicket
from app.schemas.support import SupportTicketRead, SupportTicketUpdate

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/admin/support", tags=["admin-support"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PaginatedTickets(BaseModel):
    items: list[SupportTicketRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _enrich_ticket(
    ticket: SupportTicket,
    db: AsyncSession,
) -> SupportTicketRead:
    """Add staff_name and ngo_name to a SupportTicketRead."""
    staff_result = await db.execute(select(Staff).where(Staff.id == ticket.staff_id))
    staff = staff_result.scalar_one_or_none()

    ngo_result = await db.execute(select(NGO).where(NGO.id == ticket.ngo_id))
    ngo = ngo_result.scalar_one_or_none()

    read = SupportTicketRead.model_validate(ticket)
    read.staff_name = staff.name if staff else None
    read.ngo_name = ngo.name if ngo else None
    return read


async def _get_ticket_or_404(ticket_id: uuid.UUID, db: AsyncSession) -> SupportTicket:
    result = await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    return ticket


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedTickets)
async def list_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ngo_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None, pattern="^(open|in_progress|resolved|closed)$"),
    priority: Optional[str] = Query(None, pattern="^(high|medium|low)$"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedTickets:
    """Paginated list of all support tickets with optional filters."""
    query = select(SupportTicket)

    if ngo_id is not None:
        query = query.where(SupportTicket.ngo_id == ngo_id)
    if status is not None:
        query = query.where(SupportTicket.status == status)
    if priority is not None:
        query = query.where(SupportTicket.priority == priority)

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    query = (
        query.order_by(SupportTicket.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    tickets = result.scalars().all()

    items = [await _enrich_ticket(t, db) for t in tickets]
    return PaginatedTickets(items=items, total=total, page=page, page_size=page_size)


@router.get("/{ticket_id}", response_model=SupportTicketRead)
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SupportTicketRead:
    """Return a single support ticket with staff and NGO names."""
    ticket = await _get_ticket_or_404(ticket_id, db)
    return await _enrich_ticket(ticket, db)


@router.patch("/{ticket_id}", response_model=SupportTicketRead)
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: SupportTicketUpdate,
    db: AsyncSession = Depends(get_db),
) -> SupportTicketRead:
    """
    Update a ticket's status and/or admin reply.

    When a reply is provided:
    - Sends a Telegram message to the NGO group:
        "Admin reply to '{title}': {reply}"
    - Sends a direct Telegram message to the staff member:
        "Your request '{title}' has been updated: {reply}"
    """
    ticket = await _get_ticket_or_404(ticket_id, db)

    if payload.status is not None:
        ticket.status = payload.status

    if payload.reply is not None:
        ticket.admin_reply = payload.reply

    await db.flush()

    # Fetch related objects for notifications
    ngo_result = await db.execute(select(NGO).where(NGO.id == ticket.ngo_id))
    ngo = ngo_result.scalar_one_or_none()

    staff_result = await db.execute(select(Staff).where(Staff.id == ticket.staff_id))
    staff = staff_result.scalar_one_or_none()

    if payload.reply and ngo is not None:
        # Notify group
        try:
            await send_to_group(
                ngo=ngo,
                message=f"Admin reply to '{ticket.title}': {payload.reply}",
            )
        except Exception as exc:
            log.warning(
                "admin_support_group_notify_failed",
                ticket_id=str(ticket_id),
                error=str(exc),
            )

        # DM the staff member
        if staff is not None:
            try:
                await send_to_staff(
                    ngo=ngo,
                    staff=staff,
                    message=(
                        f"Your request '{ticket.title}' has been updated: {payload.reply}"
                    ),
                )
            except Exception as exc:
                log.warning(
                    "admin_support_staff_dm_failed",
                    ticket_id=str(ticket_id),
                    staff_id=str(ticket.staff_id),
                    error=str(exc),
                )

    log.info(
        "support_ticket_updated",
        ticket_id=str(ticket_id),
        status=ticket.status,
        has_reply=payload.reply is not None,
    )

    read = SupportTicketRead.model_validate(ticket)
    read.staff_name = staff.name if staff else None
    read.ngo_name = ngo.name if ngo else None
    return read
