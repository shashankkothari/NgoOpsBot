"""Application middleware stack.

Order in main.py matters:
  1. RequestContextMiddleware  — must be outermost so request_id exists for all
                                 subsequent log calls, including auth failures.
  2. NGOAuthMiddleware         — auth errors are logged with the request_id from (1).
  3. RequestLoggingMiddleware  — logs final status + duration after all inner
                                 middleware have run, so it captures auth rejections.
  4. CORSMiddleware (FastAPI)  — must be inside logging so CORS preflight hits are
                                 recorded; keeps the two concerns separate.

All middleware is implemented as pure ASGI (not BaseHTTPMiddleware) to avoid
anyio task-group / asyncpg event-loop conflicts when testing with ASGITransport.
"""

from __future__ import annotations

import hmac
import json
import time
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Admin auth middleware
# ---------------------------------------------------------------------------

_ADMIN_PATH_PREFIX = "/api/v1/admin"


class NGOAuthMiddleware:
    """Reject requests to /api/v1/admin/* that lack a valid ADMIN_API_KEY header.

    Telegram webhooks (/api/v1/webhook/*) and health endpoints (/health) are
    intentionally excluded from auth — they authenticate via their own mechanisms.

    The key is compared with hmac.compare_digest (constant-time) to eliminate
    timing side-channels that could allow byte-by-byte secret enumeration.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "")

        if method == "OPTIONS" or not path.startswith(_ADMIN_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        headers: dict[str, str] = {
            k.decode(): v.decode()
            for k, v in scope.get("headers", [])
        }
        api_key = headers.get("x-admin-api-key") or headers.get(
            "authorization", ""
        ).removeprefix("Bearer ").removeprefix("bearer ")

        settings = get_settings()
        valid = bool(api_key) and hmac.compare_digest(
            api_key.encode(), settings.ADMIN_API_KEY.encode()
        )

        if not valid:
            log.warning("admin_auth_rejected", path=path, method=method)
            body = json.dumps({"detail": "Invalid or missing admin API key"}).encode()
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body, "more_body": False})
            return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

_SKIP_LOG_PATHS = frozenset({"/health", "/metrics", "/health/ready"})


class RequestLoggingMiddleware:
    """Log every request with method, path, status code, and wall-clock duration.

    Health and metrics endpoints are skipped to avoid flooding logs with
    Railway / k8s probe noise (they fire every 5–10 s).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path in _SKIP_LOG_PATHS:
            await self.app(scope, receive, send)
            return

        method: str = scope.get("method", "")
        status_code = 0
        start = time.perf_counter()

        async def _send_wrapper(message: Any) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            client: Any = scope.get("client")
            log.info(
                "http_request",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=client[0] if client else None,
            )
