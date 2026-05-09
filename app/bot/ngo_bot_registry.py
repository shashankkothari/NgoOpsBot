"""
Bot registry — one Bot instance per NGO token, shared across all requests.

python-telegram-bot's Bot object holds an httpx client internally; creating
one per request would exhaust file descriptors under load and incur TCP
handshake overhead on every Telegram API call.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from telegram import Bot, Message
from telegram.error import TelegramError

from app.core.logging import get_logger
from app.core.security import decrypt_field

log: structlog.stdlib.BoundLogger = get_logger(__name__)


class NGOBotRegistry:
    """Thread-safe cache of Bot instances keyed by ngo_slug."""

    def __init__(self) -> None:
        self._bots: dict[str, Bot] = {}
        # Per-slug locks prevent duplicate Bot creation on concurrent first requests
        self._slug_locks: dict[str, asyncio.Lock] = {}
        # One global lock to safely initialise per-slug locks
        self._registry_lock = asyncio.Lock()

    async def _get_slug_lock(self, ngo_slug: str) -> asyncio.Lock:
        # Double-checked locking: fast path skips the global lock after first access
        if ngo_slug not in self._slug_locks:
            async with self._registry_lock:
                if ngo_slug not in self._slug_locks:
                    self._slug_locks[ngo_slug] = asyncio.Lock()
        return self._slug_locks[ngo_slug]

    async def get_bot(self, ngo_slug: str, encrypted_token: str) -> Bot:
        """Return a cached Bot or create one. Thread-safe via per-slug locking."""
        if ngo_slug in self._bots:
            return self._bots[ngo_slug]

        slug_lock = await self._get_slug_lock(ngo_slug)
        async with slug_lock:
            # Re-check after acquiring lock — another coroutine may have populated
            if ngo_slug in self._bots:
                return self._bots[ngo_slug]

            token = decrypt_field(encrypted_token)
            bot = Bot(token=token)
            # Warm the bot info cache so username lookups don't cost an extra API call
            await bot.initialize()
            self._bots[ngo_slug] = bot

            log.info(
                "bot_created",
                ngo_slug=ngo_slug,
                # Log only the non-secret prefix so we can correlate bot IDs in logs
                bot_id=token.split(":")[0] if ":" in token else "unknown",
            )
            return bot

    async def send_message(
        self,
        ngo_slug: str,
        chat_id: int,
        text: str,
        **kwargs: Any,
    ) -> Message | None:
        """Send a message, catching all TelegramError so callers never crash."""
        bot = self._bots.get(ngo_slug)
        if bot is None:
            log.error("send_message_no_bot", ngo_slug=ngo_slug, chat_id=chat_id)
            return None

        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except TelegramError as exc:
            log.error(
                "telegram_send_failed",
                ngo_slug=ngo_slug,
                chat_id=chat_id,
                error=str(exc),
                # error_code helps differentiate 403 (bot kicked) vs 429 (rate limit)
                error_code=getattr(exc, "message", None),
            )
            return None

    async def send_typing_action(self, ngo_slug: str, chat_id: int) -> None:
        """Fire-and-forget typing indicator — failure is non-fatal."""
        bot = self._bots.get(ngo_slug)
        if bot is None:
            return
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except TelegramError as exc:
            # Typing indicator failure is cosmetic; log at debug to avoid noise
            log.debug(
                "typing_action_failed",
                ngo_slug=ngo_slug,
                chat_id=chat_id,
                error=str(exc),
            )

    async def remove_bot(self, ngo_slug: str) -> None:
        """Evict the Bot from the cache and shut it down cleanly."""
        slug_lock = await self._get_slug_lock(ngo_slug)
        async with slug_lock:
            bot = self._bots.pop(ngo_slug, None)
            if bot is not None:
                await bot.shutdown()
                log.info("bot_removed", ngo_slug=ngo_slug)


# Module-level singleton — imported by webhook handler and all bot modules
bot_registry = NGOBotRegistry()
