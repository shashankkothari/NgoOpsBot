"""Health and readiness endpoints.

/health      — liveness probe: returns 200 immediately. Railway and Docker
               use this to decide whether to restart the container.  Must
               never depend on external services — if the app is running, it's
               alive, period.

/health/ready — readiness probe: checks DB and Redis before returning 200.
               k8s uses this to decide whether to send traffic; Railway uses
               it during deploy to gate the old instance shutdown.

/metrics     — Prometheus scrape endpoint. Protected by ADMIN_API_KEY in prod
               so the scrape target credentials are not public.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.cache import ping_redis

log = get_logger(__name__)
router = APIRouter(tags=["meta"])


@router.get("/health", summary="Liveness probe")
async def liveness() -> dict[str, str]:
    """Returns 200 immediately — the container is alive if this responds."""
    settings = get_settings()
    return {"status": "ok", "version": settings.APP_VERSION}


@router.get("/health/ready", summary="Readiness probe")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Check DB connectivity and Redis reachability.

    Returns HTTP 503 if any dependency is unhealthy so the load balancer
    stops routing traffic to this instance during a partial outage.
    """
    status: dict[str, Any] = {"database": "unknown", "redis": "unknown"}
    healthy = True

    try:
        await db.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception as exc:
        log.error("readiness_db_failed", error=str(exc))
        status["database"] = "error"
        healthy = False

    try:
        ok = await ping_redis()
        status["redis"] = "ok" if ok else "error"
        if not ok:
            healthy = False
    except Exception as exc:
        log.error("readiness_redis_failed", error=str(exc))
        status["redis"] = "error"
        healthy = False

    status["status"] = "ready" if healthy else "degraded"

    if not healthy:
        raise HTTPException(status_code=503, detail=status)
    return status


@router.get("/metrics", summary="Prometheus metrics scrape endpoint")
async def metrics(request: Request) -> Response:
    """Expose Prometheus metrics.

    Gated behind ADMIN_API_KEY in production to prevent metric leakage.
    In development the endpoint is open for local scraping convenience.
    """
    settings = get_settings()
    if settings.is_production:
        api_key = request.headers.get("X-Admin-API-Key") or request.headers.get(
            "Authorization", ""
        ).removeprefix("Bearer ")
        if not api_key or api_key != settings.ADMIN_API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
