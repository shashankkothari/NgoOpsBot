# =============================================================================
# NGO OpsBot — developer convenience commands
# =============================================================================
# Usage:
#   make setup        # First-time environment setup
#   make dev          # Start API server with hot reload
#   make test         # Run full test suite
#   make lint         # Lint + type check
#   make format       # Auto-fix formatting
#   make seed         # Seed dev database
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: dev test test-unit lint format migrate migrate-new seed setup \
        docker-up docker-down dashboard clean check-env help

# Detect the Python / venv binary
PYTHON       := .venv/bin/python
PIP          := .venv/bin/pip
UVICORN      := .venv/bin/uvicorn
PYTEST       := .venv/bin/pytest
RUFF         := .venv/bin/ruff
MYPY         := .venv/bin/mypy
ALEMBIC      := .venv/bin/alembic
PRECOMMIT    := .venv/bin/pre-commit

# Fallback: if .venv doesn't exist yet, use system python3
ifeq (,$(wildcard .venv/bin/python))
PYTHON   := python3
PIP      := pip3
UVICORN  := uvicorn
PYTEST   := pytest
RUFF     := ruff
MYPY     := mypy
ALEMBIC  := alembic
PRECOMMIT := pre-commit
endif

# ---------------------------------------------------------------------------
# Development server
# ---------------------------------------------------------------------------
dev: ## Start local dev server with hot reload
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
test: ## Run full test suite with coverage
	$(PYTEST) tests/ -x --cov=app --cov-report=term-missing --cov-report=html:htmlcov --cov-fail-under=60

test-unit: ## Run only unit tests (fast, no service containers required)
	$(PYTEST) tests/unit/ -x -q

# ---------------------------------------------------------------------------
# Linting & formatting
# ---------------------------------------------------------------------------
lint: ## Run ruff linter + mypy type checker
	$(RUFF) check app/ tests/
	$(RUFF) format --check app/ tests/
	$(MYPY) app/ --ignore-missing-imports

format: ## Auto-fix formatting with ruff
	$(RUFF) check --fix app/ tests/
	$(RUFF) format app/ tests/

# ---------------------------------------------------------------------------
# Database migrations
# ---------------------------------------------------------------------------
migrate: ## Run alembic upgrade head
	$(ALEMBIC) upgrade head

migrate-new: ## Create new migration: make migrate-new name="add_column_x"
ifndef name
	$(error Usage: make migrate-new name="describe_your_migration")
endif
	$(ALEMBIC) revision --autogenerate -m "$(name)"

# ---------------------------------------------------------------------------
# Database seeding
# ---------------------------------------------------------------------------
seed: ## Seed dev database with Demo NGO and sample data
	$(PYTHON) scripts/seed_db.py

# ---------------------------------------------------------------------------
# First-time setup
# ---------------------------------------------------------------------------
setup: ## Full dev setup (first time — installs deps, hooks, starts services, runs migrations)
	bash scripts/setup_dev.sh

# ---------------------------------------------------------------------------
# Docker services
# ---------------------------------------------------------------------------
docker-up: ## Start postgres + redis via docker compose
	docker compose up -d postgres redis

docker-down: ## Stop all docker compose services
	docker compose down

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
dashboard: ## Start Next.js dashboard dev server
	cd dashboard && npm run dev

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
clean: ## Remove __pycache__, .pyc files, coverage artifacts
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -not -path "./.venv/*" -delete 2>/dev/null || true
	rm -rf htmlcov .coverage coverage.xml .pytest_cache .mypy_cache .ruff_cache

# ---------------------------------------------------------------------------
# Environment validation
# ---------------------------------------------------------------------------
check-env: ## Validate all required env vars are set (run before deploy)
	$(PYTHON) scripts/check_env.py

# ---------------------------------------------------------------------------
# Help (auto-generated from ## comments)
# ---------------------------------------------------------------------------
help: ## Show this help message
	@echo ""
	@echo "NGO OpsBot — developer commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
