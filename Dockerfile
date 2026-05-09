# =============================================================================
# NGO OpsBot — Multi-stage Dockerfile
# Stage 1 (builder): installs Python dependencies into a virtual environment.
# Stage 2 (final):   copies the venv, copies app source, runs uvicorn.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# System deps needed to compile certain Python packages (asyncpg, cryptography, Pillow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Create an isolated virtual environment so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy only the dependency manifests first (better layer caching)
COPY pyproject.toml ./

# Install project dependencies (no editable install in builder — deps only)
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    httpx \
    "python-telegram-bot[job-queue]>=20.8" \
    "sqlalchemy[asyncio]>=2.0.30" \
    asyncpg \
    alembic \
    "redis[hiredis]" \
    apscheduler \
    anthropic \
    openai \
    google-api-python-client \
    google-auth-oauthlib \
    google-auth-httplib2 \
    sendgrid \
    pydantic \
    pydantic-settings \
    cryptography \
    pillow \
    structlog \
    "sentry-sdk[fastapi]"

# ---------------------------------------------------------------------------
# Stage 2 — final runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS final

LABEL maintainer="NGO OpsBot Team"
LABEL org.opencontainers.image.description="Multi-tenant SaaS Telegram bot platform for NGOs"

# Only runtime system libs (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy the pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy project source
COPY --chown=appuser:appgroup . .

# Editable install so 'app' package is resolvable
RUN pip install --no-cache-dir -e . --no-deps

# Alembic migrations are run separately (e.g. Railway release command).
# The container just runs the API server.

USER appuser

# Expose the port uvicorn will bind to
EXPOSE 8000

# Health-check endpoint (FastAPI exposes /health)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command — Railway overrides $PORT at runtime
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--log-level", "info"]
