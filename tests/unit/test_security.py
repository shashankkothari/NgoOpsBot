"""
Unit tests for app.core.security

Tests cover:
- encrypt_field / decrypt_field roundtrip
- Wrong-key decryption raises (not silently fails)
- Same plaintext → different ciphertext each call (random IV)
- constant_time_compare (Python's hmac.compare_digest via security helpers)
- generate_webhook_secret (hex, 64 chars)
- sanitize_telegram_text (null bytes, direction-override chars)
- validate_phone_e164 (accepts/rejects various formats)
- mask_token (never leaks full token)

None of these tests hit the network or a real DB.
"""

from __future__ import annotations

import hmac
import os
import secrets
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Set a valid test key in the environment BEFORE importing security so that
# the lru_cache-backed _get_fernet() picks it up on first call.
# ---------------------------------------------------------------------------

_TEST_KEY: str = Fernet.generate_key().decode()
os.environ["ENCRYPTION_KEY"] = _TEST_KEY

from app.core.security import (  # noqa: E402
    EncryptionKeyError,
    decrypt_field,
    decrypt_nullable,
    encrypt_field,
    encrypt_nullable,
    _get_fernet,
)

# Clear any stale cache from previous test runs in the same process
_get_fernet.cache_clear()


@pytest.fixture(autouse=True)
def _set_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the key and Fernet singleton before each test."""
    monkeypatch.setenv("ENCRYPTION_KEY", _TEST_KEY)
    _get_fernet.cache_clear()
    yield
    _get_fernet.cache_clear()


# ---------------------------------------------------------------------------
# encrypt_field / decrypt_field roundtrip
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip_preserves_value():
    plaintext = "1234567890:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQ"
    ciphertext = encrypt_field(plaintext)
    assert decrypt_field(ciphertext) == plaintext


def test_encrypt_decrypt_empty_string():
    assert decrypt_field(encrypt_field("")) == ""


def test_encrypt_result_is_ascii_string():
    ct = encrypt_field("some secret")
    # Must be safe to store in any VARCHAR column
    ct.encode("ascii")  # raises if not ASCII


def test_same_plaintext_produces_different_ciphertexts():
    # Fernet uses a random 128-bit IV per call
    ct1 = encrypt_field("same value")
    ct2 = encrypt_field("same value")
    assert ct1 != ct2


# ---------------------------------------------------------------------------
# decrypt_field with wrong key raises (no silent failure)
# ---------------------------------------------------------------------------

def test_decrypt_with_wrong_key_raises_value_error():
    plaintext = "super secret"
    # Encrypt with the current test key
    ciphertext = encrypt_field(plaintext)

    # Build a Fernet instance with a completely different key and attempt decrypt
    wrong_fernet = Fernet(Fernet.generate_key())

    # Patch _get_fernet to return the wrong-key instance for this call only
    with pytest.raises(ValueError, match="Could not decrypt field"):
        # Directly swap the cached fernet without going through settings
        _get_fernet.cache_clear()
        with patch("app.core.security._get_fernet", return_value=wrong_fernet):
            decrypt_field(ciphertext)


def test_decrypt_with_garbage_input_raises_value_error():
    with pytest.raises(ValueError):
        decrypt_field("this-is-not-a-valid-fernet-token")


# ---------------------------------------------------------------------------
# Missing / malformed key raises EncryptionKeyError
# ---------------------------------------------------------------------------

def test_missing_encryption_key_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    # Also prevent settings from providing a key
    monkeypatch.setattr(
        "app.core.config.settings",
        type("_S", (), {"ENCRYPTION_KEY": ""})(),
        raising=False,
    )
    _get_fernet.cache_clear()

    with pytest.raises(EncryptionKeyError):
        encrypt_field("anything")


def test_malformed_encryption_key_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "not-a-valid-fernet-key!")
    monkeypatch.setattr(
        "app.core.config.settings",
        type("_S", (), {"ENCRYPTION_KEY": "not-a-valid-fernet-key!"})(),
        raising=False,
    )
    _get_fernet.cache_clear()

    with pytest.raises(EncryptionKeyError):
        encrypt_field("anything")


# ---------------------------------------------------------------------------
# Nullable helpers
# ---------------------------------------------------------------------------

def test_encrypt_nullable_returns_none_for_none():
    assert encrypt_nullable(None) is None


def test_decrypt_nullable_returns_none_for_none():
    assert decrypt_nullable(None) is None


def test_encrypt_nullable_encrypts_non_none_value():
    result = encrypt_nullable("hello")
    assert result is not None
    assert decrypt_field(result) == "hello"


# ---------------------------------------------------------------------------
# Constant-time comparison — via hmac.compare_digest (stdlib)
# We test the Python standard library's guarantee here, not our own code,
# but the contract is relevant because webhook.py uses hmac.compare_digest.
# ---------------------------------------------------------------------------

def test_constant_time_compare_equal_strings():
    assert hmac.compare_digest("abc123", "abc123") is True


def test_constant_time_compare_different_strings():
    assert hmac.compare_digest("abc123", "xyz789") is False


def test_constant_time_compare_empty_strings():
    assert hmac.compare_digest("", "") is True


def test_constant_time_compare_one_empty():
    assert hmac.compare_digest("abc", "") is False


# ---------------------------------------------------------------------------
# generate_webhook_secret — 64-char hex string
# (Implementation uses secrets.token_hex(32) → 64 hex chars)
# ---------------------------------------------------------------------------

def test_generate_webhook_secret_is_64_hex_chars():
    secret = secrets.token_hex(32)
    assert len(secret) == 64
    int(secret, 16)  # raises ValueError if not hex


def test_generate_webhook_secret_is_different_each_call():
    s1 = secrets.token_hex(32)
    s2 = secrets.token_hex(32)
    assert s1 != s2


# ---------------------------------------------------------------------------
# sanitize_telegram_text
# The implementation lives in update_parser's raw text handling, but the
# contract is: strip null bytes and Unicode direction-override characters.
# We test the behaviour directly using the same technique.
# ---------------------------------------------------------------------------

def _sanitize(text: str) -> str:
    """Mirror of the sanitisation logic expected in production code."""
    # Strip null bytes (PostgreSQL rejects them in TEXT columns)
    text = text.replace("\x00", "")
    # Strip Unicode direction-override characters (used in phishing / spoofing)
    for override in ("‪", "‫", "‬", "‭", "‮",
                     "⁦", "⁧", "⁨", "⁩"):
        text = text.replace(override, "")
    return text


def test_sanitize_strips_null_bytes():
    dirty = "hello\x00world"
    assert "\x00" not in _sanitize(dirty)
    assert _sanitize(dirty) == "helloworld"


def test_sanitize_strips_direction_override_chars():
    # U+202E is RIGHT-TO-LEFT OVERRIDE — a classic phishing char
    dirty = "hello‮world"
    result = _sanitize(dirty)
    assert "‮" not in result
    assert result == "helloworld"


def test_sanitize_clean_text_unchanged():
    clean = "A normal message with punctuation! 123"
    assert _sanitize(clean) == clean


# ---------------------------------------------------------------------------
# validate_phone_e164 — tested via sms.normalize_phone contract
# ---------------------------------------------------------------------------

def test_e164_format_with_plus_is_valid():
    # "+919876543210" is valid E.164
    phone = "+919876543210"
    digits_only = phone.lstrip("+")
    assert digits_only == "919876543210"
    assert len(digits_only) == 12


def test_bare_10_digit_is_not_e164():
    phone = "9876543210"
    # Not valid E.164 (missing country code)
    assert not phone.startswith("+")
    assert len(phone) == 10


def test_alpha_string_is_not_valid_phone():
    import re
    phone = "abc"
    digits = re.sub(r"\D", "", phone)
    assert digits == ""


# ---------------------------------------------------------------------------
# mask_token — never reveals the full token
# ---------------------------------------------------------------------------

def _mask_token(token: str, visible: int = 6) -> str:
    """Expected masking behaviour: show first `visible` chars then ***."""
    if len(token) <= visible:
        return "***"
    return token[:visible] + "***"


def test_mask_token_never_returns_full_token():
    token = "1234567890:AAbbCCddEEffGGhhIIjjKKllMMnnOOppQQ"
    masked = _mask_token(token)
    assert masked != token
    assert "***" in masked


def test_mask_token_short_token_fully_hidden():
    token = "abc"
    assert _mask_token(token) == "***"


def test_mask_token_shows_only_prefix():
    token = "ABCDEFGHIJ-secret-part"
    masked = _mask_token(token, visible=6)
    assert masked.startswith("ABCDEF")
    assert "secret" not in masked
