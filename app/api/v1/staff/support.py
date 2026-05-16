"""
Staff support ticket endpoints.

GET  /api/v1/staff/support  — list own tickets
POST /api/v1/staff/support  — create a ticket
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.comms.telegram_sender import send_to_group
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.staff_auth import get_current_staff
from app.models.ngo import NGO
from app.models.staff import Staff
from app.models.support import SupportTicket
from app.schemas.support import SupportTicketCreate, SupportTicketRead

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


@router.get("/support", response_model=list[SupportTicketRead])
async def list_support_tickets(
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> list[SupportTicketRead]:
    """Return all support tickets submitted by the authenticated staff member."""
    result = await db.execute(
        select(SupportTicket)
        .where(SupportTicket.staff_id == staff.id)
        .order_by(SupportTicket.created_at.desc())
    )
    tickets = result.scalars().all()

    # Fetch NGO name for enrichment
    ngo_result = await db.execute(select(NGO).where(NGO.id == staff.ngo_id))
    ngo = ngo_result.scalar_one_or_none()
    ngo_name = ngo.name if ngo else None

    reads = []
    for ticket in tickets:
        r = SupportTicketRead.model_validate(ticket)
        r.staff_name = staff.name
        r.ngo_name = ngo_name
        reads.append(r)

    return reads


@router.post("/support", response_model=SupportTicketRead, status_code=201)
async def create_support_ticket(
    payload: SupportTicketCreate,
    staff: Staff = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
) -> SupportTicketRead:
    """
    Create a support ticket for the authenticated staff member's NGO.

    On creation, a Telegram notification is sent to the NGO group:
    "New support request from {staff.name}: {title}"
    """
    # Fetch NGO for Telegram notification
    ngo_result = await db.execute(select(NGO).where(NGO.id == staff.ngo_id))
    ngo = ngo_result.scalar_one_or_none()

    ticket = SupportTicket(
        ngo_id=staff.ngo_id,
        staff_id=staff.id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        priority=payload.priority,
        status="open",
    )
    db.add(ticket)
    await db.flush()

    # Notify group
    if ngo is not None:
        try:
            await send_to_group(
                ngo=ngo,
                message=f"\U0001f4e9 New support request from {staff.name}: {payload.title}",
            )
        except Exception as exc:
            log.warning(
                "support_ticket_notify_failed",
                ticket_id=str(ticket.id),
                error=str(exc),
            )

    log.info(
        "support_ticket_created",
        ticket_id=str(ticket.id),
        staff_id=str(staff.id),
        ngo_id=str(staff.ngo_id),
    )

    read = SupportTicketRead.model_validate(ticket)
    read.staff_name = staff.name
    read.ngo_name = ngo.name if ngo else None
    return read
