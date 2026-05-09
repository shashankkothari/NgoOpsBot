"""
Conversation and ConversationThread models.

Conversation       — individual messages (one row per Telegram message turn).
ConversationThread — logical grouping of messages in a single agent session.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.ngo import NGO
    from app.models.staff import Staff


class Conversation(UUIDMixin, TimestampMixin, Base):
    """
    Single message turn within an NGO's bot interaction.

    Indexed on (ngo_id, created_at) for efficient conversation-history
    queries scoped to a tenant.
    """

    __tablename__ = "conversations"

    # ------------------------------------------------------------------ #
    # Foreign keys                                                         #
    # ------------------------------------------------------------------ #
    ngo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ngos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("staff.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Telegram context                                                     #
    # ------------------------------------------------------------------ #
    telegram_message_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="Telegram message_id of this turn"
    )
    telegram_chat_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="Telegram chat_id where the message lived"
    )

    # ------------------------------------------------------------------ #
    # Content                                                              #
    # ------------------------------------------------------------------ #
    agent_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Agent that handled this turn; null for non-agent messages",
    )
    role: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="One of: user, assistant",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language_detected: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="ISO 639-1 language code detected in content"
    )
    tokens_used: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Total tokens consumed by this LLM call"
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    ngo: Mapped[NGO] = relationship("NGO", back_populates="conversations")
    staff: Mapped[Staff | None] = relationship("Staff", back_populates="conversations")

    def __repr__(self) -> str:
        return (
            f"<Conversation id={self.id} role={self.role!r} "
            f"agent={self.agent_name!r}>"
        )


class ConversationThread(UUIDMixin, Base):
    """
    Logical thread grouping messages for one staff-agent session.

    No TimestampMixin — thread has its own started_at / last_activity_at
    semantics that differ from generic created_at/updated_at.
    """

    __tablename__ = "conversation_threads"

    # ------------------------------------------------------------------ #
    # Foreign keys                                                         #
    # ------------------------------------------------------------------ #
    ngo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ngos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("staff.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ------------------------------------------------------------------ #
    # Thread metadata                                                      #
    # ------------------------------------------------------------------ #
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    ngo: Mapped[NGO] = relationship("NGO", back_populates="conversation_threads")
    staff: Mapped[Staff | None] = relationship(
        "Staff", back_populates="conversation_threads"
    )

    def __repr__(self) -> str:
        return (
            f"<ConversationThread id={self.id} agent={self.agent_name!r} "
            f"active={self.is_active}>"
        )
