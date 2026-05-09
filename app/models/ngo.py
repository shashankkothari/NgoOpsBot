"""
NGO and NGO-level settings models.

Sensitive string fields (telegram_bot_token, anthropic_api_key,
google_refresh_token) are stored encrypted via app.core.security and
decrypted on access — encryption happens in the service layer, NOT here,
so the ORM columns are plain Text.  Keep that contract in mind.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.staff import Staff
    from app.models.conversation import Conversation, ConversationThread
    from app.models.reminder import Reminder, ReminderLog
    from app.models.audit import AuditLog


class NGO(UUIDMixin, TimestampMixin, Base):
    """One row per NGO tenant."""

    __tablename__ = "ngos"

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="URL-safe lowercase identifier used in routing",
    )

    # ------------------------------------------------------------------ #
    # Secrets (stored encrypted at rest via Fernet — see security.py)     #
    # ------------------------------------------------------------------ #
    telegram_bot_token: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Fernet-encrypted Telegram bot token"
    )
    anthropic_api_key: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Fernet-encrypted Anthropic API key"
    )
    google_refresh_token: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Fernet-encrypted Google OAuth refresh token"
    )
    webhook_secret: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="HMAC secret for Telegram webhook verification",
    )

    # ------------------------------------------------------------------ #
    # Telegram                                                             #
    # ------------------------------------------------------------------ #
    telegram_group_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Set after the bot receives its first group message",
    )

    # ------------------------------------------------------------------ #
    # Google Drive / Sheets                                                #
    # ------------------------------------------------------------------ #
    google_drive_folder_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    google_master_sheet_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # ------------------------------------------------------------------ #
    # Configuration                                                        #
    # ------------------------------------------------------------------ #
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC"
    )
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, default="en"
    )

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    settings: Mapped[list[NGOSettings]] = relationship(
        "NGOSettings", back_populates="ngo", cascade="all, delete-orphan"
    )
    staff: Mapped[list[Staff]] = relationship(
        "Staff", back_populates="ngo", cascade="all, delete-orphan"
    )
    conversations: Mapped[list[Conversation]] = relationship(
        "Conversation", back_populates="ngo", cascade="all, delete-orphan"
    )
    conversation_threads: Mapped[list[ConversationThread]] = relationship(
        "ConversationThread", back_populates="ngo", cascade="all, delete-orphan"
    )
    reminders: Mapped[list[Reminder]] = relationship(
        "Reminder", back_populates="ngo", cascade="all, delete-orphan"
    )
    reminder_logs: Mapped[list[ReminderLog]] = relationship(
        "ReminderLog", back_populates="ngo", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="ngo", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<NGO id={self.id} slug={self.slug!r}>"


class NGOSettings(UUIDMixin, TimestampMixin, Base):
    """Per-agent configuration overrides for an NGO."""

    __tablename__ = "ngo_settings"
    __table_args__ = (
        UniqueConstraint("ngo_id", "agent_name", name="uq_ngo_settings_ngo_agent"),
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
    # Columns                                                              #
    # ------------------------------------------------------------------ #
    agent_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="One of: fundraising, finance, marketing, hr, compliance",
    )
    custom_prompt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="NGO-specific additions appended to the base system prompt",
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    ngo: Mapped[NGO] = relationship("NGO", back_populates="settings")

    def __repr__(self) -> str:
        return (
            f"<NGOSettings ngo_id={self.ngo_id} agent={self.agent_name!r} "
            f"enabled={self.is_enabled}>"
        )
