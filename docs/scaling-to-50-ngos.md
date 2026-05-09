# Scaling to 50 NGOs — Engineering Enhancements

Current architecture is deliberately simple: shared Postgres, shared Redis, single
Railway service, one asyncio event loop. This is appropriate for the 1–5 NGO pilot.
Below is a prioritised list of changes needed before onboarding 50 NGOs.

---

## Priority 1 — Do before onboarding NGO #10

### 1.1 Database connection pooling

**Problem:** SQLAlchemy's default async pool is 5 connections. At 50 NGOs each capable
of concurrent webhook bursts, the pool saturates and requests queue, adding latency to
every NGO's responses.

**Fix:** Add PgBouncer in transaction-pooling mode in front of Postgres, and raise the
SQLAlchemy pool size to 20–30. PgBouncer multiplexes thousands of application
connections over a small number of actual Postgres connections, which is exactly the
async/short-lived-query pattern we have.

```
App (20 pool) → PgBouncer (transaction mode) → Postgres (max_connections = 100)
```

Railway.app supports adding PgBouncer as a sidecar service.

---

### 1.2 Bot registry memory management

**Problem:** `NgooBotRegistry` currently keeps one `python-telegram-bot` Application
instance live in memory per registered NGO. At 50 NGOs that is 50 Application objects,
each holding an HTTP connection pool, scheduler, and in-memory state.

**Fix:** Replace the always-on registry with an LRU cache of the last N active bot
instances (e.g., N = 20). Bots for NGOs with no recent traffic are evicted and
reconstructed on demand. Startup time for an evicted bot is ~200ms — acceptable.

---

### 1.3 Onboarding automation

**Problem:** Onboarding today requires ~8 manual curl commands (create NGO, register
staff, create settings for each agent). At 50 NGOs this is error-prone and doesn't scale.

**Fix:** A `scripts/onboard_ngo.py` CLI that takes a YAML config file and calls all the
admin API endpoints in sequence, with validation and rollback on failure. Also add an
idempotency check so re-running the script is safe.

---

### 1.4 Alerting on top of existing Prometheus metrics

**Problem:** Prometheus metrics and Grafana dashboards exist but there are no alert rules.
An NGO going silent (webhook stopped working), an Anthropic key expiring, or DB
connection pool saturation will go unnoticed until a user complains.

**Fix:** Add Prometheus alert rules for:
- `agent_response_latency p95 > 10s` for any NGO
- `agent_invocations` drops to zero for an NGO that was active yesterday
- `db_query_latency p95 > 2s`
- HTTP 5xx rate > 1% over 5 minutes

Use Grafana Alerting or Alertmanager to route to email/Slack.

---

## Priority 2 — Do before onboarding NGO #25

### 2.1 Conversation archival job

**Problem:** The `conversations` table grows indefinitely. At 50 NGOs × 50 messages/day
= 2,500 rows/day = ~900K rows/year. Query performance degrades and storage costs
increase. Most NGOs never need operational context older than 90 days.

**Fix:** A nightly APScheduler job that:
1. Selects `conversations` rows older than 90 days
2. Exports them as JSONL to S3/GCS (cheap cold storage, queryable with Athena/BigQuery)
3. Hard-deletes the exported rows from Postgres
4. Logs a `conversations_archived` metric per NGO

Separately, hard-delete completed/cancelled `reminders` older than 90 days.
`audit_log` is compliance data — archive to cold storage after 1 year but never delete.

---

### 2.2 Horizontal scaling of the API service

**Problem:** A single Railway service means a single process handling all 50 NGOs'
webhooks. CPU-bound spikes (e.g., image processing for voice messages) can stall the
event loop.

**Fix:** Configure Railway to run 2–3 replicas behind its built-in load balancer.
The app is already stateless (all state in Postgres + Redis) so this requires no
application changes. Set `WEB_CONCURRENCY=2` per replica (2 uvicorn workers) so
Python's GIL doesn't bottleneck CPU-bound work.

---

### 2.3 Per-NGO application-layer rate limiting

**Problem:** Even with per-NGO Anthropic keys, a misconfigured NGO (e.g., a reminder
job that fires in a tight loop) could exhaust their key's rate limit and generate
cascading errors that add noise to shared logs and monitoring.

**Fix:** Add a Redis token-bucket rate limiter keyed by `ngo_id` before every Claude
call. Cap at, say, 60 Claude calls/minute per NGO. Return a friendly "slow down"
message to the user rather than propagating a 429 from Anthropic. The rate_limiter.py
module already has the sliding-window infrastructure — extend it.

---

### 2.4 Redis memory sizing and TTL hygiene

**Problem:** No per-NGO memory quota in Redis. As NGOs accumulate, the number of cached
keys grows. If Redis hits `maxmemory`, the eviction policy (`allkeys-lru` or similar)
evicts keys globally — a spike from one NGO evicts cache for others.

**Fix:**
- Set an explicit `maxmemory` on the Redis instance (e.g., 512MB) with
  `maxmemory-policy allkeys-lru`.
- Audit all `cache_set` calls and ensure every key has a TTL (currently true for NGO
  config cache at 5 min and prompt cache, but worth verifying systematically).
- Add a Prometheus metric for Redis memory usage and alert at 80% capacity.

---

## Priority 3 — Do before onboarding NGO #50

### 3.1 Admin dashboard for NGO health

**Problem:** At 50 NGOs, manually checking each via the API is impractical. Ops needs
a single view showing: last activity timestamp, total messages this week, active staff
count, webhook status, Google Drive connection status, and any recent errors.

**Fix:** Add a `/admin/ngos/health` API endpoint that aggregates per-NGO health signals
in one query. Expose it in the Next.js dashboard as a sortable table with status
indicators. Alert when any NGO has been silent for 24+ hours (likely a broken webhook).

---

### 3.2 Webhook replay and dead-letter handling

**Problem:** If the API is down when Telegram retries a webhook (up to 3 retries over
~1 minute), the update is lost. For Reminders or time-sensitive messages this matters.

**Fix:** On webhook receipt, immediately write the raw `update_data` to a Redis stream
(acts as a durable queue). A background consumer reads from the stream and processes
updates. Failed updates go to a dead-letter Redis key for manual inspection. This
decouples Telegram's delivery from our processing latency, and Railway restarts don't
lose in-flight messages.

---

### 3.3 Structured onboarding and offboarding flows

**Problem:** GDPR/DPDP Act compliance requires being able to fully delete an NGO's data
on request. Currently there is no offboarding flow — `delete_ngo` only sets
`is_active=False`.

**Fix:** Implement a hard-delete endpoint that:
1. Removes all rows in all tables where `ngo_id = ?` (cascade deletes handle most)
2. Purges all Redis keys matching the NGO slug prefix
3. Deregisters the Telegram webhook
4. Writes a final audit log entry before deletion
5. Exports a data package to S3 for the NGO's own records before purging

---

## What is NOT needed at 50 NGOs

- **Schema-per-tenant or database-per-tenant**: operational overhead far exceeds benefit
  at this scale. Revisit at 200+ NGOs or if a customer requires contractual data isolation.
- **Message queue (Celery/RQ)**: asyncio handles concurrent webhooks well up to hundreds
  of NGOs. Adds operational complexity without a real bottleneck to solve yet.
- **CDN or edge caching**: all traffic is Telegram webhooks and admin API calls, not
  public web traffic. Not applicable.
- **Read replicas**: the query load at 50 NGOs is modest. One Postgres primary is fine.
  Add a replica when you see read latency > 100ms on the stats endpoints.
