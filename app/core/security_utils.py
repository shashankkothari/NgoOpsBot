"""
Security utility helpers for NGO OpsBot.

Import from here rather than scattering hmac/secrets/re calls across the codebase.
All functions are pure (no I/O) so they are safe to call at import time and in tests.
"""

from __future__ import annotations

import hmac
import hashlib
import secrets
import re
from typing import Optional


def constant_time_compare(a: str, b: str) -> bool:
    """Timing-safe string comparison. Use for all secret/token comparisons.

    Python's == short-circuits on the first mismatched byte, leaking timing
    information that an attacker can exploit to enumerate valid secrets byte-
    by-byte.  hmac.compare_digest always examines the full string.
    """
    return hmac.compare_digest(a.encode(), b.encode())


def generate_webhook_secret() -> str:
    """Cryptographically secure 32-byte hex token for Telegram webhook URLs.

    32 bytes = 256 bits of entropy — far beyond brute-force range.
    hex encoding avoids URL-encoding issues in path segments.
    """
    return secrets.token_hex(32)


def generate_encryption_key() -> str:
    """Generates a valid Fernet key (base64-encoded 32 bytes).

    Print on first deploy and store in the ENCRYPTION_KEY environment variable.
    Never commit the output to source control.
    """
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def sanitize_telegram_text(text: str) -> str:
    """Strip control characters from user-supplied text before logging or DB insert.

    Telegram allows Unicode but we reject null bytes and direction-override chars
    which could corrupt structured logs or exploit log viewers.
    RTL/LTR override characters (U+202E, U+202D) can make log lines appear
    to say something different from what they actually contain.
    """
    dangerous = [
        '\x00',   # null byte — corrupts C-string consumers
        '‮', # RIGHT-TO-LEFT OVERRIDE — reverses displayed text
        '‭', # LEFT-TO-RIGHT OVERRIDE
        '​', # ZERO WIDTH SPACE — invisible character
        ' ', # NO-BREAK SPACE — can disguise word boundaries
        '⁠', # WORD JOINER
    ]
    for char in dangerous:
        text = text.replace(char, '')
    return text[:4096]  # Telegram's max message length


def validate_phone_e164(phone: str) -> bool:
    """Validates phone is E.164 format: +[country][number], 8-15 digits total."""
    return bool(re.match(r'^\+[1-9]\d{7,14}$', phone))


def validate_email(email: str) -> bool:
    """Basic email validation — not RFC-compliant but catches obvious garbage."""
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email)) and len(email) <= 254


def mask_token(token: str) -> str:
    """Returns first 8 chars + *** for safe logging of API tokens.

    Never log a full bot token or API key — partial prefix is enough to
    correlate log lines without enabling token reuse.
    """
    if len(token) <= 8:
        return '***'
    return token[:8] + '***'


def mask_email_for_log(email: str) -> str:
    """Returns us***@example.com for log-safe email display."""
    parts = email.split('@')
    if len(parts) != 2:
        return '***'
    local = parts[0]
    prefix = local[:2] if len(local) >= 2 else local[:1]
    return f"{prefix}***@{parts[1]}"


def mask_phone_for_log(phone: str) -> str:
    """Returns last 4 digits only: ****1234 for log-safe phone display."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 4:
        return '****'
    return '****' + digits[-4:]
