"""
Models package — import every model here so that Alembic's autogenerate
(and SQLAlchemy's mapper registry) can discover all tables.

Import order respects foreign-key dependencies:
  Base → NGO → Staff → Conversation/Reminder → AuditLog
"""

from app.models.base import Base, TimestampMixin, UUIDMixin  # noqa: F401
from app.models.ngo import NGO, NGOSettings  # noqa: F401
from app.models.staff import Staff  # noqa: F401
from app.models.conversation import Conversation, ConversationThread  # noqa: F401
from app.models.reminder import Reminder, ReminderLog  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.support import SupportTicket  # noqa: F401

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "NGO",
    "NGOSettings",
    "Staff",
    "Conversation",
    "ConversationThread",
    "Reminder",
    "ReminderLog",
    "AuditLog",
    "SupportTicket",
]
