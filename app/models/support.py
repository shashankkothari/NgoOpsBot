"""
SupportTicket model — staff-submitted support requests.

Staff submit tickets; platform admins triage and reply.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.ngo import NGO
    from app.models.staff import Staff


class SupportTicket(UUIDMixin, TimestampMixin, Base):
    """
    A support request raised by a staff member against the platform.

    ``category``: "access_request" | "technical" | "agent_behaviour" | "other"
    ``priority``: "high" | "medium" | "low"
    ``status``  : "open" | "in_progress" | "resolved" | "closed"
    """

    __tablename__ = "support_tickets"

    # ------------------------------------------------------------------ #
    # Foreign keys                                                         #
    # ------------------------------------------------------------------ #
    ngo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ngos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("staff.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Ticket body                                                          #
    # ------------------------------------------------------------------ #
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="One of: access_request, technical, agent_behaviour, other",
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="One of: high, medium, low",
    )

    # ------------------------------------------------------------------ #
    # Workflow                                                             #
    # ------------------------------------------------------------------ #
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="One of: open, in_progress, resolved, closed",
    )
    admin_reply: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    ngo: Mapped[NGO] = relationship("NGO", back_populates="support_tickets")
    staff: Mapped[Staff] = relationship("Staff", back_populates="support_tickets")

    def __repr__(self) -> str:
        return (
            f"<SupportTicket id={self.id} title={self.title!r} "
            f"status={self.status!r} priority={self.priority!r}>"
        )
