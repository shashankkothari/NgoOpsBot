"""
Reminder and ReminderLog models.

Reminder    — declarative definition of when/how to fire a proactive message.
ReminderLog — immutable audit trail of every firing attempt.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.ngo import NGO
    from app.models.staff import Staff


class Reminder(UUIDMixin, TimestampMixin, Base):
    """
    Configurable proactive-reminder definition.

    ``config`` (JSONB) holds type-specific payload:
      - date_based:      {"date": "2025-12-31", "time": "09:00"}
      - inactivity:      {"agent": "finance", "idle_days": 7}
      - threshold:       {"metric": "donations_ytd", "below": 50000}
      - recurring:       {"cron": "0 9 * * MON"}
      - event_triggered: {"event": "grant_deadline_approaching", "days_before": 14}

    ``target_details`` (JSONB) holds audience-specific routing:
      - staff_group:     {} (uses ngo.telegram_group_chat_id)
      - specific_staff:  {"staff_ids": ["<uuid>", ...]}
      - external:        {"emails": [...], "phones": [...]}
    """

    __tablename__ = "reminders"

    # ------------------------------------------------------------------ #
    # Foreign key                                                          #
    # ------------------------------------------------------------------ #
    ngo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ngos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Definition                                                           #
    # ------------------------------------------------------------------ #
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reminder_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment=(
            "One of: date_based, inactivity, threshold, recurring, event_triggered"
        ),
    )
    agent_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Agent this reminder is associated with, if any",
    )
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Type-specific configuration (dates, cron, thresholds, …)",
    )

    # ------------------------------------------------------------------ #
    # Targeting                                                            #
    # ------------------------------------------------------------------ #
    target_audience: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="One of: staff_group, specific_staff, external",
    )
    target_details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Audience-specific routing payload (chat_ids, emails, phones, …)",
    )

    # ------------------------------------------------------------------ #
    # Workflow                                                             #
    # ------------------------------------------------------------------ #
    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="True for external messages; admin must approve before send",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_fire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Pre-computed next execution time; drives the scheduler query",
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    ngo: Mapped[NGO] = relationship("NGO", back_populates="reminders")
    logs: Mapped[list[ReminderLog]] = relationship(
        "ReminderLog", back_populates="reminder", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Reminder id={self.id} title={self.title!r} "
            f"type={self.reminder_type!r} active={self.is_active}>"
        )


class ReminderLog(UUIDMixin, Base):
    """
    Immutable record of every reminder-firing attempt.

    Intentionally has no TimestampMixin — ``fired_at`` is the authoritative
    timestamp and must be set explicitly by the scheduler.
    """

    __tablename__ = "reminder_logs"

    # ------------------------------------------------------------------ #
    # Foreign keys                                                         #
    # ------------------------------------------------------------------ #
    reminder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reminders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ngo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ngos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approved_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("staff.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Event data                                                           #
    # ------------------------------------------------------------------ #
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment=(
            "One of: sent, pending_approval, approved, rejected, failed"
        ),
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Exact message text that was (or would be) sent"
    )
    sent_via: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="One of: telegram, sms, email",
    )
    error_message: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, comment="Populated only when status='failed'"
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    reminder: Mapped[Reminder] = relationship("Reminder", back_populates="logs")
    ngo: Mapped[NGO] = relationship("NGO", back_populates="reminder_logs")
    approved_by_staff: Mapped[Staff | None] = relationship(
        "Staff",
        back_populates="approved_reminder_logs",
        foreign_keys=[approved_by_staff_id],
    )

    def __repr__(self) -> str:
        return (
            f"<ReminderLog id={self.id} reminder_id={self.reminder_id} "
            f"status={self.status!r} via={self.sent_via!r}>"
        )
