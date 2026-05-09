"""Application middleware stack.

Order in main.py matters:
  1. RequestContextMiddleware  — must be outermost so request_id exists for all
                                 subsequent log calls, including auth failures.
  2. NGOAuthMiddleware         — auth errors are logged with the request_id from (1).
  3. RequestLoggingMiddleware  — logs final status + duration after all inner
                                 middleware have run, so it captures auth rejections.
  4. CORSMiddleware (FastAPI)  — must be inside logging so CORS preflight hits are
                                 recorded; keeps the two concerns separate.

Starlette middleware runs in LIFO order for requests (outermost added last runs
first on the request path), but we add them in the order above via add_middleware
in main.py, which prepends each one, achieving the desired call order.
"""

from __future__ import annotations

import hmac
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Admin auth middleware
# ---------------------------------------------------------------------------

# Paths that begin with this prefix require ADMIN_API_KEY authentication.
# The prefix intentionally covers all versioned admin sub-paths
# (e.g. /api/v1/admin/ngos, /api/v1/admin/staff, /api/v1/admin/reminders).
_ADMIN_PATH_PREFIX = "/api/v1/admin"


class NGOAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests to /api/v1/admin/* that lack a valid ADMIN_API_KEY header.

    Telegram webhooks (/api/v1/webhook/*) and health endpoints (/health) are
    intentionally excluded from auth — they authenticate via their own mechanisms.

    The key is compared with hmac.compare_digest (constant-time) to eliminate
    timing side-channels that could allow byte-by-byte secret enumeration.
    This is defence-in-depth: the key is already high-entropy, but the cost
    of constant-time comparison is negligible and the habit is worth building.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if not request.url.path.startswith(_ADMIN_PATH_PREFIX):
            return await call_next(request)

        settings = get_settings()
        api_key = request.headers.get("X-Admin-API-Key") or request.headers.get(
            "Authorization", ""
        ).removeprefix("Bearer ")

        # Constant-time comparison prevents timing-based secret enumeration.
        # We check api_key is non-empty first to avoid compare_digest on empty bytes.
        valid = bool(api_key) and hmac.compare_digest(
            api_key.encode(), settings.ADMIN_API_KEY.encode()
        )

        if not valid:
            log.warning(
                "admin_auth_rejected",
                path=request.url.path,
                method=request.method,
            )
            return JSONResponse(
                status_code=401,
                # Generic message — do NOT reveal whether the key was missing vs wrong
                content={"detail": "Invalid or missing admin API key"},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

_SKIP_LOG_PATHS = frozenset({"/health", "/metrics", "/health/ready"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status code, and wall-clock duration.

    Health and metrics endpoints are skipped to avoid flooding logs with
    Railway / k8s probe noise (they fire every 5–10 s).
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path in _SKIP_LOG_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        log.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host if request.client else None,
        )
        return response
