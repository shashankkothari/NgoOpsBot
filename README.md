# NGO OpsBot

A multi-tenant SaaS platform that gives NGOs an AI-powered operations team — accessible via Telegram bot and a dedicated staff web portal. Powered by Anthropic Claude with real tool access: Google Sheets, Gmail, Calendar, web search, and safe arithmetic.

---

## What it does

Staff message their NGO's Telegram bot (or use the web portal) and get routed to a specialist AI agent:

| Agent | Handles |
|---|---|
| **Fundraising** | Donor tracking, grant management, 80G receipts, FCRA compliance, re-engagement drafts |
| **Finance** | Budget vs actuals, expense categorisation, TDS guidance, board reports |
| **HR** | Leave tracking, offer letters, volunteer coordination, Indian labour law |
| **Marketing** | Campaign planning, social content, impact stories, donor communications |
| **Compliance** | FCRA filings, 12A/80G renewals, ITR-7, audit timelines, regulatory lookups |
| **General** | Intent classifier — routes to the right specialist automatically |

Agents can take real actions: read/write Google Sheets, search Gmail, create calendar events, draft emails, and run financial calculations — with a tool-use loop that handles multi-step tasks autonomously.

---

## Architecture

```
┌──────────────────────┐   ┌──────────────────────────┐
│  Telegram Bot        │   │  Staff Portal (Next.js)  │
│  (per-NGO webhook)   │   │  staff-portal/           │
└──────────┬───────────┘   └────────────┬─────────────┘
           │                            │ JWT auth
           │ HTTPS webhook              │ /api/v1/staff/*
┌──────────▼────────────────────────────▼─────────────┐
│  FastAPI Backend (app/)                              │
│  ├── api/v1/admin/    Admin REST API                 │
│  ├── api/v1/staff/    Staff portal API (JWT)         │
│  ├── bot/handlers/    Telegram update handlers       │
│  ├── agents/          Claude specialist agents       │
│  │   └── tools/       Calculator, web search,        │
│  │                    Gmail, Calendar, Sheets         │
│  ├── integrations/    Google Workspace               │
│  └── scheduler/       APScheduler (reminders)        │
└────────┬────────────────────┬────────────────────────┘
         │                    │
┌────────▼───────┐   ┌────────▼───────┐
│  PostgreSQL    │   │  Redis         │
│  (async ORM)   │   │  (cache)       │
└────────────────┘   └────────────────┘

┌─────────────────────────────────┐
│  Admin Dashboard (Next.js)      │
│  dashboard/   — manage NGOs,    │
│  agents, staff, and settings    │
└─────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI 0.111+ (Python 3.12) |
| Telegram | python-telegram-bot v20+ (webhook mode) |
| Database | PostgreSQL 16 + SQLAlchemy 2 async + Alembic |
| Cache | Redis 7 |
| AI | Anthropic Claude (claude-sonnet-4-6 with tool use) |
| Voice transcription | OpenAI Whisper API |
| Scheduler | APScheduler 3.x |
| Email | SendGrid |
| SMS / WhatsApp | MSG91 |
| Google APIs | Sheets, Gmail, Calendar, Drive |
| Staff portal | Next.js + Tailwind (`/staff-portal`) |
| Admin dashboard | Next.js + Tailwind (`/dashboard`) |
| Hosting | Railway.app |
| Observability | Sentry + structlog + Prometheus |

---

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose

### 1. Clone and configure

```bash
git clone https://github.com/your-org/ngo-opsbot.git
cd ngo-opsbot
cp .env.example .env
# Fill in values — see Environment Variables below
```

### 2. Python backend

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

docker compose up postgres redis -d
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

API: `http://localhost:8000` · Docs: `http://localhost:8000/docs`

### 3. Admin dashboard

```bash
cd dashboard
npm install
npm run dev        # http://localhost:3001
```

### 4. Staff portal

```bash
cd staff-portal
npm install
npm run dev        # http://localhost:3002
```

Staff log in with Google OAuth scoped to their NGO slug (set via cookie before the OAuth flow). The portal connects to the FastAPI backend via JWT tokens issued on sign-in.

---

## Environment Variables

Copy `.env.example` to `.env`. Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | asyncpg DSN (`postgresql+asyncpg://...`) |
| `SYNC_DATABASE_URL` | psycopg2 DSN for Alembic migrations |
| `REDIS_URL` | Redis connection string |
| `ENCRYPTION_KEY` | Fernet key for encrypting secrets at rest |
| `ADMIN_API_KEY` | Key protecting admin REST endpoints |
| `STAFF_JWT_SECRET` | Secret for signing staff portal JWT tokens |
| `ANTHROPIC_API_KEY` | Platform-level Claude API key (NGO key overrides per-request) |
| `OPENAI_API_KEY` | OpenAI key for Whisper transcription |
| `SENDGRID_API_KEY` | SendGrid email API key |
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client secret |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL |
| `NEXTAUTH_SECRET` | NextAuth secret (staff portal) |
| `NEXTAUTH_URL` | Staff portal public URL |
| `SENTRY_DSN` | Sentry error tracking DSN |
| `APP_BASE_URL` | Public HTTPS URL (for webhook registration) |

Generate keys:
```bash
# Fernet encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Random API / JWT keys
openssl rand -hex 32
```

---

## Agent Tools

Each agent can use a curated set of tools — Claude calls them automatically during a conversation:

| Tool | What it does | Agents |
|---|---|---|
| `calculator` | Safe AST-evaluated arithmetic (no `eval`) | All |
| `web_search` | DuckDuckGo search, no API key needed | All |
| `read_sheet_tab` | Read rows from NGO's Google Sheets Master Tracker | Fundraising, Finance, HR, Compliance |
| `append_sheet_row` | Add a new row to a tab | Fundraising, Finance, HR |
| `find_and_update_sheet_row` | Find by column value and update fields | Fundraising, Finance, HR |
| `search_emails` | Search NGO Gmail by query string | Fundraising, HR, Marketing |
| `get_email` | Fetch full email content by message ID | Fundraising, HR, Marketing |
| `create_email_draft` | Save to Gmail Drafts (never sends) | Fundraising, HR, Marketing |
| `list_calendar_events` | List upcoming Calendar events | Compliance, General |
| `create_calendar_event` | Create a Calendar event or deadline reminder | Compliance, General |

Google-dependent tools require the NGO to complete the OAuth flow from the admin dashboard. Tools fail gracefully with a descriptive message if Google isn't connected.

---

## Google Sheets Master Tracker

Each connected NGO gets a single spreadsheet with five tabs, created automatically on first connection:

| Tab | Columns |
|---|---|
| **Donors** | Name, Email, Phone, Last Gift Date, Last Gift Amount, Total Given, Status, Notes |
| **Grants** | Grant Name, Funder, Amount, Status, Application Date, Decision Date, Reporting Deadline, Utilization %, Notes |
| **Finance** | Month, Category, Budget, Actual, Variance, Notes |
| **Staff** | Name, Role, Join Date, Leave Balance, Phone, Email, Status |
| **Reminders** | Title, Type, Due Date, Status, Assigned To, Notes |

---

## Onboarding a New NGO

**Via admin dashboard** (`/dashboard`): Create NGO → configure agents and settings → set Anthropic API key → connect Google account.

**Via CLI** (scripted onboarding):

```bash
python -m scripts.create_ngo \
  --name "Helping Hands Foundation" \
  --telegram-token "7123456789:AAxxxx..." \
  --anthropic-key "sk-ant-api03-..." \
  --admin-chat-id 123456789 \
  --plan starter \
  --timezone "Asia/Kolkata"
```

The script validates the token, encrypts secrets, creates the DB record, and registers the Telegram webhook automatically.

---

## Staff Portal

The staff portal (`/staff-portal`) is a Next.js app for NGO staff who prefer a web interface over Telegram.

- **Chat**: per-agent conversations with persistent thread history
- **Reminders**: create, snooze, and acknowledge reminders
- **Support tickets**: submit issues to admins with priority and category

Staff authenticate via Google OAuth. On sign-in the portal calls `POST /api/v1/staff/auth/login`, which validates the Google email against the NGO's staff list and issues a short-lived JWT.

---

## Railway Deployment

1. Create a Railway project and add PostgreSQL + Redis plugins.
2. Set all env vars from `.env.example`.
3. Railway reads `railway.toml` — it runs `alembic upgrade head` as the release command then starts uvicorn.

```bash
railway login && railway link
railway variables set ENCRYPTION_KEY="$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")"
railway variables set ADMIN_API_KEY="$(openssl rand -hex 32)"
railway variables set STAFF_JWT_SECRET="$(openssl rand -hex 32)"
railway up
```

Push to `main` for auto-deploys thereafter.

---

## Running Tests

```bash
pytest                          # all tests with coverage
pytest tests/unit/             # unit tests only (no DB needed)
pytest tests/integration/      # requires TEST_DATABASE_URL
pytest -v --no-cov             # verbose, skip coverage
```

---

## Database Migrations

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic downgrade -1
alembic current
```

---

## Project Structure

```
ngo-opsbot/
├── app/
│   ├── main.py
│   ├── core/                    # Config, DB, security, staff auth
│   ├── models/                  # SQLAlchemy ORM models
│   ├── schemas/                 # Pydantic schemas
│   ├── api/v1/
│   │   ├── admin/               # Admin REST API
│   │   └── staff/               # Staff portal API (JWT)
│   ├── bot/handlers/            # Telegram update handlers
│   ├── agents/
│   │   ├── base.py              # Tool-use loop, prompt caching
│   │   ├── fundraising.py
│   │   ├── finance.py
│   │   ├── hr.py
│   │   ├── marketing.py
│   │   ├── compliance.py
│   │   ├── general.py           # Intent classifier + orchestrator
│   │   ├── tools/               # Calculator, web search, executor
│   │   └── prompts/             # System prompt builder (3 layers)
│   ├── integrations/
│   │   └── google/              # Sheets, Gmail, Calendar, Drive, OAuth
│   └── scheduler/               # APScheduler reminder jobs
├── alembic/versions/            # DB migrations
├── dashboard/                   # Next.js admin dashboard
├── staff-portal/                # Next.js staff-facing portal
├── tests/
│   ├── unit/
│   └── integration/
├── scripts/
│   ├── create_ngo.py
│   └── smoke_test.sh
├── Dockerfile
├── docker-compose.yml
├── railway.toml
└── pyproject.toml
```

---

## License

MIT — see `LICENSE` for details.
