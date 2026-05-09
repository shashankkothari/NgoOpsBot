"""
AuditLog model — append-only action trail across all NGO tenants.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.ngo import NGO
    from app.models.staff import Staff


class AuditLog(Base):
    """
    Append-only record of every significant action in the platform.

    Deliberately omits UUIDMixin and TimestampMixin so that:
      - ``id`` is defined inline for clarity.
      - Only ``created_at`` is needed (records are never mutated).
    """

    __tablename__ = "audit_logs"

    # ------------------------------------------------------------------ #
    # Primary key                                                          #
    # ------------------------------------------------------------------ #
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ------------------------------------------------------------------ #
    # Foreign keys (both nullable — system-level events may have neither)  #
    # ------------------------------------------------------------------ #
    ngo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ngos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("staff.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Event data                                                           #
    # ------------------------------------------------------------------ #
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment=(
            "Verb-noun slug, e.g. agent_invoked, reminder_sent, settings_changed"
        ),
    )
    details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Arbitrary structured context for the action",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),  # IPv6 max length
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    ngo: Mapped[NGO | None] = relationship("NGO", back_populates="audit_logs")
    staff: Mapped[Staff | None] = relationship("Staff", back_populates="audit_logs")

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"ngo_id={self.ngo_id}>"
        )
