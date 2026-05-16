#!/usr/bin/env bash
# =============================================================================
# NGO OpsBot — First-time dev environment setup
# Run once after cloning the repo:  bash scripts/setup.sh
# =============================================================================
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[setup]${RESET} $*"; }
success() { echo -e "${GREEN}[setup]${RESET} $*"; }
error()   { echo -e "${RED}[setup] ERROR:${RESET} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Check Homebrew postgres is installed and start it
# ---------------------------------------------------------------------------
info "Checking Homebrew postgresql@16..."
if ! brew list postgresql@16 &>/dev/null; then
    error "postgresql@16 is not installed. Run: brew install postgresql@16"
fi

info "Starting postgresql@16 via brew services..."
brew services start postgresql@16

# ---------------------------------------------------------------------------
# 2. Check Homebrew redis is installed and start it
# ---------------------------------------------------------------------------
info "Checking Homebrew redis..."
if ! brew list redis &>/dev/null; then
    error "redis is not installed. Run: brew install redis"
fi

info "Starting redis via brew services..."
brew services start redis

# ---------------------------------------------------------------------------
# 3. Wait for postgres to be ready
# ---------------------------------------------------------------------------
PG_READY_CMD="/opt/homebrew/opt/postgresql@16/bin/pg_isready -h 127.0.0.1 -p 5432"
info "Waiting for PostgreSQL to be ready..."
RETRIES=30
until $PG_READY_CMD -q; do
    RETRIES=$((RETRIES - 1))
    if [ "$RETRIES" -le 0 ]; then
        error "PostgreSQL did not become ready in time. Check 'brew services list'."
    fi
    sleep 1
done
success "PostgreSQL is ready."

# ---------------------------------------------------------------------------
# 4. Create ngoopsbot database if it doesn't exist
# ---------------------------------------------------------------------------
info "Ensuring database 'ngoopsbot' exists..."
DB_EXISTS=$(/opt/homebrew/opt/postgresql@16/bin/psql -h 127.0.0.1 -U shashankkothari -tAc \
    "SELECT 1 FROM pg_database WHERE datname='ngoopsbot'" 2>/dev/null || echo "")
if [ "$DB_EXISTS" != "1" ]; then
    /opt/homebrew/opt/postgresql@16/bin/createdb -h 127.0.0.1 -U shashankkothari ngoopsbot
    success "Database 'ngoopsbot' created."
else
    info "Database 'ngoopsbot' already exists."
fi

# ---------------------------------------------------------------------------
# 5. Load .env safely (strip comments and blank lines)
# ---------------------------------------------------------------------------
if [ ! -f .env ]; then
    error ".env file not found. Copy .env.example to .env and fill in values."
fi
info "Loading .env..."
set -o allexport
# shellcheck disable=SC1090
source <(grep -v '^\s*#' .env | grep -v '^\s*$')
set +o allexport

# ---------------------------------------------------------------------------
# 6. Run alembic migrations
# ---------------------------------------------------------------------------
info "Running alembic upgrade head..."
.venv/bin/alembic upgrade head

# ---------------------------------------------------------------------------
# 7. Done
# ---------------------------------------------------------------------------
success "Setup complete!"
echo ""
echo "  Next steps:"
echo "    make dev        — start the API server"
echo "    make seed       — seed the dev database with sample data"
echo "    make test       — run the test suite"
echo ""
