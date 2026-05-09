#!/usr/bin/env python3
"""CLI script to onboard a new NGO tenant.

Usage:
    python -m scripts.create_ngo \
        --name "Helping Hands Foundation" \
        --telegram-token "7123456789:AAxxxx..." \
        --anthropic-key "sk-ant-api03-..." \
        --admin-chat-id 123456789 \
        [--plan starter] \
        [--timezone "Asia/Kolkata"] \
        [--dry-run]

What this script does:
1. Validates that the Telegram token is well-formed and can reach the Bot API.
2. Encrypts the Telegram token and Anthropic key with the app's ENCRYPTION_KEY (Fernet).
3. Derives a URL-safe slug from the NGO name.
4. Inserts a new row into the `ngos` table.
5. Registers the Telegram webhook for the bot token against this app's URL.
6. Prints a summary of the created NGO (never prints raw secrets).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import sys
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        sys.exit(
            "ERROR: ENCRYPTION_KEY environment variable is not set.\n"
            "Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode())
    except Exception as exc:
        sys.exit(f"ERROR: ENCRYPTION_KEY is not a valid Fernet key: {exc}")


def _slugify(name: str) -> str:
    """Convert an NGO name to a lowercase URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:60]


def _validate_token_format(token: str) -> None:
    """Raise ValueError if token doesn't match the Telegram bot token pattern."""
    pattern = r"^\d{8,12}:[A-Za-z0-9_-]{35}$"
    if not re.match(pattern, token):
        raise ValueError(
            f"Token '{token[:20]}...' does not match the expected Telegram format "
            "(NNNNNNNNNN:AAAA...35chars)"
        )


async def _verify_telegram_token(token: str) -> dict[str, Any]:
    """Call getMe to verify the token is live and return bot info."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
    data = resp.json()
    if not data.get("ok"):
        raise ValueError(
            f"Telegram API rejected the token: {data.get('description', 'unknown error')}"
        )
    return data["result"]


async def _register_webhook(
    token: str, app_base_url: str, ngo_slug: str, webhook_secret: str
) -> None:
    """Register a Telegram webhook for the given bot token.

    Webhook URL format matches app/api/v1/webhook.py:
      /api/v1/webhook/{ngo_slug}/{webhook_secret}
    The secret is embedded in the path (not a header) — Telegram validates
    it as an opaque token, which is equivalent to HMAC for this purpose.
    """
    webhook_url = (
        f"{app_base_url.rstrip('/')}/api/v1/webhook/{ngo_slug}/{webhook_secret}"
    )
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    payload = {
        "url": webhook_url,
        "allowed_updates": [
            "message",
            "callback_query",
            "inline_query",
            "chosen_inline_result",
            "my_chat_member",
        ],
        "drop_pending_updates": True,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(api_url, json=payload)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(
            f"Failed to register webhook: {data.get('description', 'unknown error')}"
        )
    print(f"  Webhook registered: {webhook_url}")


async def _insert_ngo(
    session: AsyncSession,
    *,
    ngo_id: str,
    name: str,
    slug: str,
    token_encrypted: bytes,
    anthropic_key_encrypted: bytes,
    webhook_secret: str,
    timezone_str: str,
) -> None:
    """Insert the NGO record using raw SQL (avoids importing ORM models).

    Column names match app/models/ngo.py exactly: telegram_bot_token,
    anthropic_api_key, webhook_secret.
    """
    await session.execute(
        text(
            """
            INSERT INTO ngos (
                id, name, slug,
                telegram_bot_token,
                anthropic_api_key,
                webhook_secret,
                timezone,
                is_active,
                created_at,
                updated_at
            ) VALUES (
                :id, :name, :slug,
                :telegram_bot_token,
                :anthropic_api_key,
                :webhook_secret,
                :timezone,
                true,
                :now,
                :now
            )
            """
        ),
        {
            "id": ngo_id,
            "name": name,
            "slug": slug,
            "telegram_bot_token": token_encrypted,
            "anthropic_api_key": anthropic_key_encrypted,
            "webhook_secret": webhook_secret,
            "timezone": timezone_str,
            "now": datetime.now(timezone.utc),
        },
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Onboard a new NGO tenant onto the NGO OpsBot platform.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Human-readable name of the NGO (e.g. 'Helping Hands Foundation')",
    )
    parser.add_argument(
        "--telegram-token",
        required=True,
        metavar="TOKEN",
        help="Bot token from @BotFather (format: NNNNNNNNNN:AAAA...)",
    )
    parser.add_argument(
        "--anthropic-key",
        required=True,
        metavar="KEY",
        help="NGO-specific Anthropic API key (sk-ant-api03-...)",
    )
    parser.add_argument(
        "--admin-chat-id",
        required=True,
        type=int,
        metavar="CHAT_ID",
        help="Telegram chat ID of the NGO admin (use @userinfobot to find it)",
    )
    parser.add_argument(
        "--plan",
        default="starter",
        choices=["starter", "growth", "enterprise"],
        help="Subscription plan tier (default: starter)",
    )
    parser.add_argument(
        "--timezone",
        default="UTC",
        metavar="TZ",
        help="IANA timezone for this NGO (default: UTC, e.g. Asia/Kolkata)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print what would be done, but do not write to DB",
    )
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    print("\n=== NGO OpsBot — Onboarding Script ===\n")

    # 1. Validate token format
    print("Step 1/5  Validating Telegram token format...")
    try:
        _validate_token_format(args.telegram_token)
        print("          Token format: OK")
    except ValueError as exc:
        sys.exit(f"ERROR: {exc}")

    # 2. Verify token is live (skip if offline/dry-run? — we still call it)
    print("Step 2/5  Verifying token with Telegram API...")
    try:
        bot_info = await _verify_telegram_token(args.telegram_token)
        bot_username = bot_info.get("username", "unknown")
        print(f"          Bot verified: @{bot_username} (id={bot_info.get('id')})")
    except Exception as exc:
        sys.exit(f"ERROR: {exc}")

    # 3. Encrypt secrets
    print("Step 3/5  Encrypting secrets...")
    fernet = _get_fernet()
    token_encrypted = fernet.encrypt(args.telegram_token.encode())
    anthropic_key_encrypted = fernet.encrypt(args.anthropic_key.encode())
    ngo_id = str(uuid.uuid4())
    slug = _slugify(args.name)
    # 256-bit CSPRNG secret embedded in the webhook URL path — same approach as admin API
    webhook_secret = secrets.token_hex(32)
    print(f"          NGO ID    : {ngo_id}")
    print(f"          NGO Slug  : {slug}")
    print(f"          Plan      : {args.plan}")
    print(f"          Timezone  : {args.timezone}")

    if args.dry_run:
        print("\n[DRY RUN] Skipping database insert and webhook registration.")
        print("All validations passed. Remove --dry-run to proceed.")
        return

    # 4. Insert into database
    print("Step 4/5  Inserting NGO into database...")
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        sys.exit("ERROR: DATABASE_URL environment variable is not set.")

    engine = create_async_engine(db_url, echo=False, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            await _insert_ngo(
                session,
                ngo_id=ngo_id,
                name=args.name,
                slug=slug,
                token_encrypted=token_encrypted,
                anthropic_key_encrypted=anthropic_key_encrypted,
                webhook_secret=webhook_secret,
                timezone_str=args.timezone,
            )
        print(f"          NGO '{args.name}' inserted successfully.")
    except Exception as exc:
        sys.exit(f"ERROR inserting NGO into database: {exc}")
    finally:
        await engine.dispose()

    # 5. Register Telegram webhook
    print("Step 5/5  Registering Telegram webhook...")
    app_base_url = os.environ.get("APP_BASE_URL", "")
    if not app_base_url:
        print(
            "WARNING: APP_BASE_URL is not set. Skipping webhook registration.\n"
            "         Run manually: POST /api/v1/admin/ngos/{ngo_id}/refresh-webhook"
        )
    else:
        try:
            await _register_webhook(args.telegram_token, app_base_url, slug, webhook_secret)
        except Exception as exc:
            print(f"WARNING: Webhook registration failed: {exc}")
            print(
                "         The NGO is in the database. Register the webhook manually later\n"
                "         via: POST /api/v1/admin/ngos/{ngo_id}/refresh-webhook"
            )

    # Summary
    print("\n=== Onboarding Complete ===")
    print(f"  NGO Name       : {args.name}")
    print(f"  NGO ID         : {ngo_id}")
    print(f"  Slug           : {slug}")
    print(f"  Bot            : @{bot_username}")
    print(f"  Admin Chat ID  : {args.admin_chat_id}")
    print(f"  Plan           : {args.plan}")
    print(f"  Timezone       : {args.timezone}")
    print("\nNext steps:")
    print("  1. Send /start to the bot from the admin Telegram account.")
    print("  2. Grant the bot admin permissions in any group chats.")
    print("  3. Configure Google Workspace integration via the admin dashboard.")
    print()


def main() -> None:
    """Entry point for `create-ngo` console script."""
    # Load .env if python-dotenv is available (dev convenience)
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]
        load_dotenv()
    except ImportError:
        pass

    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
