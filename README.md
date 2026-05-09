# NGO OpsBot

A multi-tenant SaaS Telegram bot platform that helps NGOs automate internal operations — task management, volunteer coordination, donor communication, meeting transcription, and reporting — powered by Anthropic Claude AI.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Telegram Clients (per-NGO bots)                                │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS webhook per bot token
┌────────────────────────▼────────────────────────────────────────┐
│  FastAPI (app/)                                                  │
│  ├── api/v1/        REST endpoints (admin, integrations, health) │
│  ├── bot/handlers/  Telegram update handlers (per-tenant)        │
│  ├── agents/        Claude-powered AI agents                     │
│  ├── scheduler/     APScheduler jobs (reminders, reports)        │
│  ├── integrations/  Google Workspace, SendGrid, MSG91            │
│  └── comms/         Email + SMS dispatch layer                   │
└───────┬──────────────────────┬──────────────────────────────────┘
        │                      │
┌───────▼──────┐     ┌─────────▼─────────┐
│  PostgreSQL  │     │   Redis            │
│  (SQLAlchemy │     │   (cache, rate     │
│  + Alembic)  │     │   limit, sessions) │
└──────────────┘     └───────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI 0.111+ (Python 3.12) |
| Telegram | python-telegram-bot v20+ (webhook mode) |
| Database | PostgreSQL 16 + SQLAlchemy 2 async + Alembic |
| Cache | Redis 7 |
| AI | Anthropic Claude API |
| Voice transcription | OpenAI Whisper API |
| Scheduler | APScheduler 3.x |
| Email | SendGrid |
| SMS / WhatsApp | MSG91 |
| Google APIs | google-api-python-client |
| Admin dashboard | Next.js + Tailwind (in `/dashboard`) |
| Hosting | Railway.app |
| Observability | Sentry + structlog |

---

## Local Development Setup

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- `git`

### 1. Clone and configure

```bash
git clone https://github.com/your-org/ngo-opsbot.git
cd ngo-opsbot
cp .env.example .env
# Edit .env and fill in real values (see Environment Variables below)
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Start infrastructure (PostgreSQL + Redis)

```bash
docker compose up postgres redis -d
```

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the development server

```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### 6. (Optional) Run the full stack via Docker Compose

```bash
# Build and start everything, including migrations
docker compose --profile migrate up --build
```

---

## Environment Variables

Copy `.env.example` to `.env`. Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | asyncpg DSN (`postgresql+asyncpg://...`) |
| `SYNC_DATABASE_URL` | psycopg2 DSN for Alembic migrations |
| `REDIS_URL` | Redis connection string |
| `ENCRYPTION_KEY` | Fernet key for encrypting NGO bot tokens |
| `WEBHOOK_SECRET` | HMAC secret for Telegram webhook verification |
| `ADMIN_API_KEY` | API key protecting admin REST endpoints |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key (platform-level fallback) |
| `OPENAI_API_KEY` | OpenAI key for Whisper transcription |
| `SENDGRID_API_KEY` | SendGrid email API key |
| `MSG91_API_KEY` | MSG91 SMS/WhatsApp API key |
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client secret |
| `SENTRY_DSN` | Sentry error tracking DSN |
| `APP_BASE_URL` | Public HTTPS URL (used for webhook registration) |

Generate an ENCRYPTION_KEY:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Onboarding a New NGO

Use the bundled CLI script to create a new tenant:

```bash
python -m scripts.create_ngo \
  --name "Helping Hands Foundation" \
  --telegram-token "7123456789:AAxxxx..." \
  --anthropic-key "sk-ant-api03-..." \
  --admin-chat-id 123456789 \
  --plan starter \
  --timezone "Asia/Kolkata"
```

Flags:
- `--dry-run` — validate inputs without writing to DB or registering webhook
- `--plan` — `starter` | `growth` | `enterprise`
- `--timezone` — IANA timezone string (default `UTC`)

The script will:
1. Validate the Telegram token format and verify it with the Bot API
2. Encrypt the token and Anthropic key with your `ENCRYPTION_KEY`
3. Insert the NGO record into the database
4. Register the Telegram webhook at `APP_BASE_URL/api/v1/bot/{token}/webhook`

---

## Railway Deployment

### First deploy

1. Create a new Railway project and link this repo.
2. Add a PostgreSQL plugin and a Redis plugin from the Railway dashboard.
3. Set all environment variables from `.env.example` in Railway's variable editor.
4. Railway reads `railway.toml` automatically — it will:
   - Install dependencies with `pip install -e .`
   - Run `alembic upgrade head` as the release command
   - Start the server with `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Environment variables on Railway

```bash
# Using Railway CLI
railway login
railway link
railway variables set ENCRYPTION_KEY="$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")"
railway variables set ADMIN_API_KEY="$(openssl rand -hex 32)"
railway variables set WEBHOOK_SECRET="$(openssl rand -hex 24)"
# ... set remaining variables
railway up
```

### Subsequent deploys

Push to your main branch — Railway auto-deploys and runs `alembic upgrade head` before swapping traffic.

---

## Telegram Bot Setup (per NGO)

1. Message [@BotFather](https://t.me/BotFather) on Telegram.
2. Send `/newbot` and follow the prompts to get a bot token.
3. Enable inline mode: `/setinline` → choose your bot → set placeholder text.
4. Set bot commands: `/setcommands` → paste the contents of `scripts/bot_commands.txt`.
5. Run the onboarding script (see above) with the token.
6. The webhook is automatically registered — no polling needed.

---

## Running Tests

```bash
# Unit + integration tests with coverage
pytest

# Run only unit tests
pytest tests/unit/

# Run with verbose output and no coverage
pytest -v --no-cov

# Run a specific test file
pytest tests/unit/test_encryption.py -v
```

Tests use an in-memory SQLite database by default. Set `TEST_DATABASE_URL` to a real PostgreSQL DSN for integration tests.

---

## Database Migrations

```bash
# Create a new migration (after changing models)
alembic revision --autogenerate -m "add volunteer table"

# Apply all pending migrations
alembic upgrade head

# Roll back the last migration
alembic downgrade -1

# Show current revision
alembic current

# Show migration history
alembic history --verbose
```

---

## Project Structure

```
ngo-opsbot/
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── core/                    # Config, DB engine, security utils
│   ├── models/                  # SQLAlchemy ORM models
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── api/v1/                  # REST API routers
│   ├── bot/
│   │   └── handlers/            # Telegram update handlers
│   ├── agents/
│   │   └── prompts/templates/   # Claude prompt templates (Jinja2)
│   ├── integrations/
│   │   └── google/              # Google Workspace integration
│   ├── scheduler/jobs/          # APScheduler job definitions
│   └── comms/                   # Email (SendGrid) + SMS (MSG91)
├── alembic/
│   ├── env.py                   # Async-compatible Alembic env
│   ├── script.py.mako           # Migration file template
│   └── versions/                # Migration files (auto-generated)
├── dashboard/                   # Next.js admin dashboard
├── tests/
│   ├── conftest.py              # Shared pytest fixtures
│   ├── unit/                    # Fast, isolated unit tests
│   └── integration/             # Tests against real DB/Redis
├── scripts/
│   └── create_ngo.py            # NGO onboarding CLI
├── Dockerfile                   # Multi-stage production image
├── docker-compose.yml           # Local development stack
├── railway.toml                 # Railway deployment config
├── alembic.ini                  # Alembic CLI config
└── pyproject.toml               # Python project + tool config
```

---

## Contributing

1. Fork the repository and create a feature branch.
2. Install dev dependencies: `pip install -e ".[dev]"`
3. Install pre-commit hooks: `pre-commit install`
4. Write tests for new functionality.
5. Run `ruff check . && ruff format .` before committing.
6. Open a pull request against `main`.

---

## License

MIT — see `LICENSE` for details.
