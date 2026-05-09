"""Structured logging configuration for the entire application.

Configures structlog once at startup.  Every log line carries a request_id
(injected by RequestContextMiddleware), plus any ngo_id / agent_name / staff_id
that callers bind via `log = logger.bind(ngo_id=..., agent_name=...)`.

In production: JSON renderer → compatible with Datadog, Loki, CloudWatch, etc.
In development: colorised ConsoleRenderer with readable timestamps.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

if TYPE_CHECKING:
    from app.core.config import Settings

# ---------------------------------------------------------------------------
# Request-scoped context propagated via contextvars (not threading.local)
# so it works correctly with asyncio tasks.
# ---------------------------------------------------------------------------
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id_var.get()


def _add_request_id(
    logger: Any,  # noqa: ANN401
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """structlog processor: inject request_id from the current context."""
    rid = _request_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Configure structlog + stdlib logging.  Call exactly once at startup."""

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_request_id,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # JSON lines — each log is a self-contained, machine-parseable record
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    # Use stdlib LoggerFactory so add_logger_name can read logger.name,
    # and so uvicorn/sqlalchemy stdlib loggers flow through the same pipeline.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to *name*.

    Usage:
        log = get_logger(__name__)
        log.info("ngo_created", ngo_id=str(ngo.id), slug=ngo.slug)
    """
    return structlog.get_logger(name)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RequestContextMiddleware(BaseHTTPMiddleware):
    """Generate a request_id UUID and bind it to every log line in the request.

    Must be added before any middleware that logs (e.g. RequestLoggingMiddleware)
    so the ID is available throughout the entire request lifecycle.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = str(uuid.uuid4())
        token = _request_id_var.set(request_id)

        # structlog contextvars are per-task; clear before each request so
        # no context leaks between requests handled by the same event-loop task
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response: Response = await call_next(request)
        finally:
            _request_id_var.reset(token)
            structlog.contextvars.clear_contextvars()

        response.headers["X-Request-ID"] = request_id
        return response
