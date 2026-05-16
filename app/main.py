"""NGO OpsBot — FastAPI application factory.

Startup order matters:
  1. structlog is configured before anything else so that import-time log
     calls from other modules are already formatted correctly.
  2. Sentry is initialised before the app is created so that errors during
     app construction (e.g. bad config) are captured.
  3. Middleware is added in reverse-desired-call-order because Starlette
     prepends each add_middleware call, so the last-added runs first:
       add RequestContextMiddleware last → it runs first on every request.
     Desired inbound order:
       RequestContextMiddleware → NGOAuthMiddleware → RequestLoggingMiddleware
     So we add them: RequestLoggingMiddleware, NGOAuthMiddleware, RequestContextMiddleware.
  4. Routers are included after middleware.
  5. prometheus-fastapi-instrumentator is mounted after routers so it can
     instrument all registered routes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.core.config import get_settings
from app.core.database import close_db, init_db
from app.core.logging import RequestContextMiddleware, configure_logging, get_logger
from app.core.middleware import NGOAuthMiddleware, RequestLoggingMiddleware
from app.core.cache import close_redis, ping_redis
from app.scheduler.engine import start_scheduler, stop_scheduler


def _init_sentry(settings: object) -> None:  # type: ignore[type-arg]
    """Initialise Sentry SDK.  No-op if SENTRY_DSN is empty (local dev)."""
    dsn = getattr(settings, "SENTRY_DSN", "")
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.1),
        environment=getattr(settings, "ENV", "development"),
        release=getattr(settings, "APP_VERSION", "0.1.0"),
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        # Avoid sending PII in breadcrumbs — NGO data is sensitive
        send_default_pii=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan: startup before yield, shutdown after."""
    settings = get_settings()
    log = get_logger(__name__)

    # Validate DB connectivity — fail fast rather than serving 500s for every request
    try:
        await init_db()
        log.info("database_ready")
    except Exception as exc:
        log.error("database_startup_failed", error=str(exc))
        raise

    # Redis is optional for liveness but required for scheduler dedup
    redis_ok = await ping_redis()
    if redis_ok:
        log.info("redis_ready")
    else:
        log.warning("redis_unreachable_at_startup")

    # Start the APScheduler after DB/Redis so poll jobs can reach both.
    await start_scheduler()
    log.info("scheduler_ready")

    log.info(
        "ngoopsbot_started",
        version=settings.APP_VERSION,
        env=settings.ENV,
    )

    yield  # ----------------------------------------------------------------

    # Shutdown — drain pools gracefully before the process exits
    await stop_scheduler()
    await close_db()
    await close_redis()
    log.info("ngoopsbot_shutdown")


def _add_exception_handlers(app: FastAPI) -> None:
    """Register a catch-all 500 handler that never leaks stack traces.

    FastAPI's default exception handler returns the exception detail string,
    which for unhandled exceptions may contain internal paths, SQL, or PII.
    We replace it with a generic message and log the full detail server-side.
    """
    log = get_logger(__name__)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal server error occurred."},
        )


def create_app() -> FastAPI:
    settings = get_settings()

    # Step 1: configure structured logging before any other import triggers log calls
    configure_logging(settings)
    log = get_logger(__name__)

    # Step 2: Sentry before app construction
    _init_sentry(settings)

    _app = FastAPI(
        title="NGO OpsBot API",
        description="Multi-tenant SaaS Telegram bot platform for NGOs",
        version=settings.APP_VERSION,
        # Docs only in non-production — avoids leaking schema details and
        # also removes the overhead of serving Swagger UI in prod
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Register catch-all exception handler before any middleware or routers
    _add_exception_handlers(_app)

    # ---------------------------------------------------------------------- #
    # Middleware — added in reverse desired-call-order (Starlette prepends)   #
    # ---------------------------------------------------------------------- #

    # Outermost CORS layer — must be before auth middleware so OPTIONS
    # preflight requests from the dashboard are not rejected with 401.
    #
    # Security notes:
    #   - allow_origins=["*"] with allow_credentials=True is forbidden by the
    #     CORS spec and browsers will block such responses.  In development we
    #     use wildcard origins but disable credentials.  In production we
    #     restrict origins to APP_BASE_URL and re-enable credentials so the
    #     admin dashboard can send X-Admin-API-Key with session cookies.
    if settings.is_production:
        cors_origins = [settings.APP_BASE_URL]
        cors_credentials = True
    else:
        cors_origins = ["*"]
        cors_credentials = False  # wildcard + credentials is a CORS spec violation

    _app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_credentials,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Admin-API-Key"],
    )

    # Request logging — runs after auth so it can record 401 status codes too
    _app.add_middleware(RequestLoggingMiddleware)

    # Admin auth — validates X-Admin-API-Key on /api/admin/* routes
    _app.add_middleware(NGOAuthMiddleware)

    # Request context — generates request_id and binds it to structlog context.
    # Must be innermost (added last) so request_id exists for ALL middleware above.
    _app.add_middleware(RequestContextMiddleware)

    # ---------------------------------------------------------------------- #
    # Routers                                                                  #
    # ---------------------------------------------------------------------- #
    from app.api.v1.health import router as health_router
    from app.api.v1.webhook import router as webhook_router
    from app.api.v1.admin.ngos import router as ngos_router
    from app.api.v1.admin.staff import router as staff_router
    from app.api.v1.admin.conversations import router as conversations_router
    from app.api.v1.admin.reminders import router as reminders_router
    from app.api.v1.admin.support import router as admin_support_router
    from app.api.v1.google_oauth import router as google_router
    from app.api.v1.staff.auth import router as staff_auth_router
    from app.api.v1.staff.me import router as staff_me_router
    from app.api.v1.staff.chat import router as staff_chat_router
    from app.api.v1.staff.threads import router as staff_threads_router
    from app.api.v1.staff.reminders import router as staff_reminders_router
    from app.api.v1.staff.support import router as staff_support_router

    _app.include_router(health_router)
    _app.include_router(webhook_router)
    _app.include_router(ngos_router)
    _app.include_router(staff_router)
    _app.include_router(conversations_router)
    _app.include_router(reminders_router)
    _app.include_router(admin_support_router)
    # Google OAuth routes at /api/v1/google — prefix applied here so the router
    # stays mountable at different prefixes in tests without code changes
    _app.include_router(google_router, prefix="/api/v1/google")
    # Staff portal routes — JWT-authenticated, no admin key required
    _app.include_router(staff_auth_router)
    _app.include_router(staff_me_router)
    _app.include_router(staff_chat_router)
    _app.include_router(staff_threads_router)
    _app.include_router(staff_reminders_router)
    _app.include_router(staff_support_router)

    # ---------------------------------------------------------------------- #
    # Prometheus instrumentation                                               #
    # ---------------------------------------------------------------------- #
    # Mounted after routers so it sees all registered paths for the
    # `handler` label on http_requests_total.  The /metrics scrape endpoint
    # is defined in health.py with admin auth; the instrumentator's own
    # expose() is not called — we manage the endpoint ourselves.
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        # Exclude health/metrics from latency histograms — probe noise skews p99
        excluded_handlers=["/health", "/health/ready", "/metrics"],
    ).instrument(_app)

    log.info("app_configured", env=settings.ENV, version=settings.APP_VERSION)
    return _app


app = create_app()
