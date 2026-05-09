"""
Staff model — one row per NGO member who interacts via Telegram.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.ngo import NGO
    from app.models.conversation import Conversation, ConversationThread
    from app.models.reminder import ReminderLog
    from app.models.audit import AuditLog


class Staff(UUIDMixin, TimestampMixin, Base):
    """NGO staff member with role-based agent access."""

    __tablename__ = "staff"
    __table_args__ = (
        UniqueConstraint(
            "ngo_id", "telegram_user_id", name="uq_staff_ngo_telegram_user"
        ),
    )

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
    # Telegram identity                                                    #
    # ------------------------------------------------------------------ #
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="Telegram numeric user ID"
    )
    telegram_username: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Telegram @handle (without @)"
    )

    # ------------------------------------------------------------------ #
    # Profile                                                              #
    # ------------------------------------------------------------------ #
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="One of: admin, staff",
    )

    # ------------------------------------------------------------------ #
    # Agent access control                                                 #
    # ------------------------------------------------------------------ #
    allowed_agents: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
        comment="Array of agent names this staff member may invoke",
    )

    # ------------------------------------------------------------------ #
    # Status & contact                                                     #
    # ------------------------------------------------------------------ #
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    phone: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="E.164 phone number for SMS delivery"
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    ngo: Mapped[NGO] = relationship("NGO", back_populates="staff")
    conversations: Mapped[list[Conversation]] = relationship(
        "Conversation", back_populates="staff"
    )
    conversation_threads: Mapped[list[ConversationThread]] = relationship(
        "ConversationThread", back_populates="staff"
    )
    approved_reminder_logs: Mapped[list[ReminderLog]] = relationship(
        "ReminderLog",
        back_populates="approved_by_staff",
        foreign_keys="[ReminderLog.approved_by_staff_id]",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="staff"
    )

    def __repr__(self) -> str:
        return (
            f"<Staff id={self.id} name={self.name!r} "
            f"role={self.role!r} ngo_id={self.ngo_id}>"
        )
