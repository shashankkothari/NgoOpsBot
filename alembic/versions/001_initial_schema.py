"""Initial schema — all NGO OpsBot tables.

Revision ID: 001
Revises:
Create Date: 2026-05-08

Creates the following tables (in dependency order):
  ngos → ngo_settings
  staff
  conversations, conversation_threads
  reminders → reminder_logs
  audit_logs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------
revision: str = "001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid_pk() -> sa.Column:
    """Standard UUID primary-key column."""
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )


def _timestamps() -> list[sa.Column]:
    """created_at / updated_at pair with server-side defaults."""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ------------------------------------------------------------------
    # ngos
    # ------------------------------------------------------------------
    op.create_table(
        "ngos",
        _uuid_pk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("telegram_bot_token", sa.Text, nullable=False),
        sa.Column("anthropic_api_key", sa.Text, nullable=False),
        sa.Column("google_refresh_token", sa.Text, nullable=True),
        sa.Column("webhook_secret", sa.String(255), nullable=False),
        sa.Column("telegram_group_chat_id", sa.BigInteger, nullable=True),
        sa.Column("google_drive_folder_id", sa.String(255), nullable=True),
        sa.Column("google_master_sheet_id", sa.String(255), nullable=True),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "timezone", sa.String(64), nullable=False, server_default=sa.text("'UTC'")
        ),
        sa.Column(
            "language", sa.String(10), nullable=False, server_default=sa.text("'en'")
        ),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_ngos_name"),
        sa.UniqueConstraint("slug", name="uq_ngos_slug"),
    )
    # Slug index used by the webhook router to resolve NGO from URL path
    op.create_index("ix_ngos_slug", "ngos", ["slug"], unique=True)

    # ------------------------------------------------------------------
    # ngo_settings
    # ------------------------------------------------------------------
    op.create_table(
        "ngo_settings",
        _uuid_pk(),
        sa.Column(
            "ngo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ngos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("custom_prompt", sa.Text, nullable=True),
        sa.Column(
            "is_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        *_timestamps(),
        sa.UniqueConstraint(
            "ngo_id", "agent_name", name="uq_ngo_settings_ngo_agent"
        ),
    )
    op.create_index("ix_ngo_settings_ngo_id", "ngo_settings", ["ngo_id"])

    # ------------------------------------------------------------------
    # staff
    # ------------------------------------------------------------------
    op.create_table(
        "staff",
        _uuid_pk(),
        sa.Column(
            "ngo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ngos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_user_id", sa.BigInteger, nullable=False),
        sa.Column("telegram_username", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column(
            "allowed_agents",
            postgresql.ARRAY(sa.String),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "ngo_id", "telegram_user_id", name="uq_staff_ngo_telegram_user"
        ),
    )
    # Composite index used for every inbound Telegram-message lookup
    op.create_index(
        "ix_staff_ngo_id_telegram_user_id",
        "staff",
        ["ngo_id", "telegram_user_id"],
    )

    # ------------------------------------------------------------------
    # conversations
    # ------------------------------------------------------------------
    op.create_table(
        "conversations",
        _uuid_pk(),
        sa.Column(
            "ngo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ngos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("telegram_message_id", sa.BigInteger, nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger, nullable=False),
        sa.Column("agent_name", sa.String(50), nullable=True),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("language_detected", sa.String(10), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        *_timestamps(),
    )
    # Tenant-scoped history queries ordered by time
    op.create_index(
        "ix_conversations_ngo_id_created_at",
        "conversations",
        ["ngo_id", "created_at"],
    )
    op.create_index("ix_conversations_staff_id", "conversations", ["staff_id"])

    # ------------------------------------------------------------------
    # conversation_threads
    # ------------------------------------------------------------------
    op.create_table(
        "conversation_threads",
        _uuid_pk(),
        sa.Column(
            "ngo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ngos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "message_count", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
    )
    op.create_index(
        "ix_conversation_threads_ngo_id", "conversation_threads", ["ngo_id"]
    )
    op.create_index(
        "ix_conversation_threads_staff_id", "conversation_threads", ["staff_id"]
    )

    # ------------------------------------------------------------------
    # reminders
    # ------------------------------------------------------------------
    op.create_table(
        "reminders",
        _uuid_pk(),
        sa.Column(
            "ngo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ngos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("reminder_type", sa.String(30), nullable=False),
        sa.Column("agent_name", sa.String(50), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("target_audience", sa.String(30), nullable=False),
        sa.Column(
            "target_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "requires_approval",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    # Partial index: scheduler only queries active reminders; filter keeps it lean
    op.create_index(
        "ix_reminders_ngo_id_next_fire_at_active",
        "reminders",
        ["ngo_id", "next_fire_at"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ------------------------------------------------------------------
    # reminder_logs
    # ------------------------------------------------------------------
    op.create_table(
        "reminder_logs",
        _uuid_pk(),
        sa.Column(
            "reminder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reminders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ngo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ngos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sent_via", sa.String(20), nullable=False),
        sa.Column("error_message", sa.String(1024), nullable=True),
    )
    op.create_index("ix_reminder_logs_reminder_id", "reminder_logs", ["reminder_id"])
    op.create_index("ix_reminder_logs_ngo_id", "reminder_logs", ["ngo_id"])
    op.create_index(
        "ix_reminder_logs_approved_by_staff_id",
        "reminder_logs",
        ["approved_by_staff_id"],
    )

    # ------------------------------------------------------------------
    # audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        _uuid_pk(),
        sa.Column(
            "ngo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ngos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "staff_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_logs_ngo_id", "audit_logs", ["ngo_id"])
    op.create_index("ix_audit_logs_staff_id", "audit_logs", ["staff_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("audit_logs")
    op.drop_table("reminder_logs")
    op.drop_table("reminders")
    op.drop_table("conversation_threads")
    op.drop_table("conversations")
    op.drop_table("staff")
    op.drop_table("ngo_settings")
    op.drop_table("ngos")
