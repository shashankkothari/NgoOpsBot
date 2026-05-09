"""
Field-level encryption for sensitive NGO secrets.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256) from the
``cryptography`` library.  All encrypted values are stored as plain ASCII
strings (URL-safe base64 produced by Fernet), which are safe to persist in
any TEXT/VARCHAR column.

Configuration
-------------
Set ``ENCRYPTION_KEY`` in the environment (or via your settings object) to a
32-byte URL-safe base64-encoded key.  Generate one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Never rotate this key without first decrypting all encrypted fields with
the old key and re-encrypting them with the new key — a helper for that
workflow should be implemented in a separate migration script.
"""

from __future__ import annotations

import base64
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

class EncryptionKeyError(RuntimeError):
    """Raised when the encryption key is absent or malformed."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """
    Return a cached ``Fernet`` instance built from ``ENCRYPTION_KEY``.

    Key resolution order:
      1. ``app.core.config.settings.ENCRYPTION_KEY`` (preferred — reads .env
         and environment, validated by Pydantic).
      2. ``os.environ["ENCRYPTION_KEY"]`` fallback (for scripts / CLIs that
         import security before the full app stack is initialised).

    The result is cached for the lifetime of the process.
    Call ``_get_fernet.cache_clear()`` in tests to swap keys between cases.
    """
    # Prefer the centralised settings object to avoid env-read duplication.
    try:
        from app.core.config import settings as _settings  # local import avoids circularity

        raw_key = _settings.ENCRYPTION_KEY.strip()
    except Exception:
        raw_key = os.environ.get("ENCRYPTION_KEY", "").strip()

    if not raw_key:
        raise EncryptionKeyError(
            "ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )

    # Validate: Fernet keys are 32 raw bytes encoded as URL-safe base64 (44 chars).
    try:
        decoded = base64.urlsafe_b64decode(raw_key.encode())
        if len(decoded) != 32:
            raise ValueError("wrong key length")
    except Exception as exc:
        raise EncryptionKeyError(
            "ENCRYPTION_KEY is not a valid 32-byte URL-safe base64 Fernet key."
        ) from exc

    return Fernet(raw_key.encode())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encrypt_field(value: str) -> str:
    """
    Encrypt a plaintext string and return an ASCII-safe ciphertext string.

    The returned value is safe to store in any TEXT/VARCHAR column and can
    be round-tripped back to plaintext with ``decrypt_field``.

    Parameters
    ----------
    value:
        The plaintext secret to encrypt (e.g. a Telegram bot token).

    Returns
    -------
    str
        URL-safe base64-encoded Fernet token (ASCII, no line breaks).

    Raises
    ------
    EncryptionKeyError
        If ``ENCRYPTION_KEY`` is missing or malformed.
    """
    fernet = _get_fernet()
    ciphertext: bytes = fernet.encrypt(value.encode("utf-8"))
    return ciphertext.decode("ascii")


def decrypt_field(value: str) -> str:
    """
    Decrypt a Fernet-encrypted ciphertext string and return the plaintext.

    Parameters
    ----------
    value:
        The ciphertext as returned by ``encrypt_field``.

    Returns
    -------
    str
        The original plaintext string.

    Raises
    ------
    EncryptionKeyError
        If ``ENCRYPTION_KEY`` is missing or malformed.
    ValueError
        If ``value`` is not a valid Fernet token or was encrypted with a
        different key (wraps ``cryptography.fernet.InvalidToken``).
    """
    fernet = _get_fernet()
    try:
        plaintext: bytes = fernet.decrypt(value.encode("ascii"))
    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt field — the ciphertext is invalid or was encrypted "
            "with a different key.  Check that ENCRYPTION_KEY has not been rotated "
            "without migrating existing data."
        ) from exc
    return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# Convenience helpers for nullable fields
# ---------------------------------------------------------------------------

def encrypt_nullable(value: str | None) -> str | None:
    """Encrypt ``value`` if it is not ``None``, otherwise return ``None``."""
    return encrypt_field(value) if value is not None else None


def decrypt_nullable(value: str | None) -> str | None:
    """Decrypt ``value`` if it is not ``None``, otherwise return ``None``."""
    return decrypt_field(value) if value is not None else None
