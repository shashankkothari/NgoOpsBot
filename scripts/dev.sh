#!/usr/bin/env bash
# =============================================================================
# NGO OpsBot — Start all dev services and the API server
# Usage: bash scripts/dev.sh   (or: make dev)
# =============================================================================
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[dev]${RESET} $*"; }
success() { echo -e "${GREEN}[dev]${RESET} $*"; }
error()   { echo -e "${RED}[dev] ERROR:${RESET} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Ensure postgres and redis are running
# ---------------------------------------------------------------------------
info "Ensuring postgresql@16 is running..."
brew services start postgresql@16 2>/dev/null || true

info "Ensuring redis is running..."
brew services start redis 2>/dev/null || true

# Brief wait for services to initialise if they were stopped
sleep 1

# ---------------------------------------------------------------------------
# 2. Source .env safely
# ---------------------------------------------------------------------------
if [ ! -f .env ]; then
    error ".env file not found. Run 'bash scripts/setup.sh' first."
fi
info "Loading .env..."
set -o allexport
# shellcheck disable=SC1090
source <(grep -v '^\s*#' .env | grep -v '^\s*$')
set +o allexport

# ---------------------------------------------------------------------------
# 3. Start uvicorn
# ---------------------------------------------------------------------------
success "Starting API server at http://0.0.0.0:8000 (reload enabled)"
exec .venv/bin/uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
