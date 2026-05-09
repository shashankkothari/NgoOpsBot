# NGO OpsBot — Security Documentation

Last updated: 2026-05-08
Maintainer: NGO OpsBot Team

---

## 1. Threat Model

### Actors

| Actor | Trust level | Description |
|---|---|---|
| Platform admin | High | Holds `ADMIN_API_KEY`; can create/modify all NGOs |
| NGO staff | Medium | Authenticated via Telegram identity in group chat |
| Telegram (Bot API) | Medium | Delivers webhook POSTs; validated by per-NGO `webhook_secret` |
| External SMTP/SMS | Low | SendGrid and MSG91 receive message content; we authenticate to them |
| Google | Low | Holds OAuth tokens we issue; we authenticate via client secret |
| Anonymous internet | Untrusted | Can reach all public HTTP endpoints |

### Primary attack surfaces

1. **Webhook endpoints** — publicly reachable, unauthenticated by network layer.
   Mitigated by per-NGO path-embedded `webhook_secret` (256-bit CSPRNG) and per-NGO
   rate limiting (30 req/min sliding window via Redis).

2. **Admin API** — protected by `ADMIN_API_KEY` on all `/api/v1/admin/*` routes via
   `NGOAuthMiddleware`. Key comparison is constant-time (`hmac.compare_digest`).

3. **Google OAuth callback** — CSRF-protected by a one-time state token stored in
   Redis with 10-minute TTL. The token is atomically consumed on callback
   (`GETDEL`), preventing replay attacks.

4. **Dependency supply chain** — all dependencies have upper-bound version pins;
   `cryptography` is pinned tightly. A `pip audit` step is recommended in CI.

### Assets (ranked by sensitivity)

| Asset | Location | Protection |
|---|---|---|
| Telegram bot tokens | PostgreSQL `ngo.telegram_bot_token` | Fernet-encrypted at rest |
| Anthropic API keys | PostgreSQL `ngo.anthropic_api_key` | Fernet-encrypted at rest |
| Google refresh tokens | PostgreSQL `ngo.google_refresh_token` | Fernet-encrypted at rest |
| `ENCRYPTION_KEY` | Environment variable | Never persisted; must be in secret manager |
| `ADMIN_API_KEY` | Environment variable | Never persisted; must be in secret manager |
| Donor/staff PII | PostgreSQL staff, reminder tables | Access controlled at ORM layer; PII masked in logs |
| Conversation history | PostgreSQL conversation table | Per-NGO tenant isolation via `ngo_id` foreign key |
| SendGrid / MSG91 keys | Environment variables | Never persisted to DB or Redis |

---

## 2. Sensitive Data Inventory

### What is encrypted at rest (Fernet / AES-128-CBC + HMAC-SHA256)

| Field | Model | Encrypted column |
|---|---|---|
| Telegram bot token | `NGO` | `telegram_bot_token` |
| Anthropic API key | `NGO` | `anthropic_api_key` |
| Google OAuth refresh token | `NGO` | `google_refresh_token` |

**Key facts:**
- Encryption is performed by `app/core/security.py` using `cryptography.Fernet`.
- The `ENCRYPTION_KEY` is validated at startup (32-byte URL-safe base64). An invalid
  key causes an immediate startup failure rather than silent runtime corruption.
- Plaintext tokens are decrypted only at point of use (inside `NGOBotRegistry.get_bot`,
  `credentials_manager.get_ngo_credentials`). They are never written to Redis, logs,
  or error responses.

### What is NOT encrypted (by design)

- NGO names, slugs, timezones — public metadata.
- Staff names, Telegram user IDs — used for routing, low sensitivity.
- Conversation transcripts — stored as plaintext; consider column-level encryption if
  conversations contain PII (donor names, financial details).

### Log sanitisation

- Phone numbers: logged as last-4 digits only (`****1234`).
- Email addresses: logged as `us***@example.com`.
- API tokens: logged as first-8-chars + `***`.
- Message content is NOT logged at any level.
- Sentry `send_default_pii = False` prevents automatic PII capture.

---

## 3. Authentication Model

### ADMIN_API_KEY

- Single shared secret for platform operations.
- Sent in `X-Admin-API-Key` header or `Authorization: Bearer <key>` header.
- Enforced on all `/api/v1/admin/*` routes by `NGOAuthMiddleware`.
- Comparison is constant-time via `hmac.compare_digest`.
- Minimum recommended length: 32 random bytes (hex-encoded = 64 chars).
  Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`

### Per-NGO webhook secret

- 256-bit CSPRNG token (`secrets.token_hex(32)`) embedded in the webhook URL path.
- Compared constant-time on every webhook request.
- Rotatable via `POST /api/v1/admin/ngos/{id}/refresh-webhook`.
- Never logged; stored in plaintext in DB (not a secret in the same sense as a token —
  it lives in the URL that Telegram has on file).

### Google OAuth state token

- 32-byte URL-safe random token generated per OAuth flow.
- Stored in Redis with 10-minute TTL under `google_oauth_state:{ngo_slug}`.
- Consumed atomically (GETDEL) on callback — one-time-use, replay-proof.

### Telegram identity

- Staff are identified by Telegram `user_id` matched against the `staff` table.
- Only messages from registered, active staff in the configured group chat are
  processed. Unknown users are silently ignored.

---

## 4. CORS Policy

| Environment | Allowed origins | Credentials |
|---|---|---|
| Development | `*` (wildcard) | `false` (spec forbids credentials with wildcard) |
| Production | `APP_BASE_URL` only | `true` |

The wildcard + `allow_credentials=true` combination is a CORS spec violation (browsers
reject it). Development mode deliberately disables credentials to comply.

---

## 5. Dependency Update Policy

- All production dependencies have both lower and upper version bounds in `pyproject.toml`.
- The `cryptography` package is pinned within a two-major-version window and must be
  reviewed against its changelog before bumping the upper bound.
- **Recommended CI step:** `pip-audit` or `safety check` on every PR targeting `main`.
- **Cadence:** Review and bump dependency bounds monthly or within 48 hours of a
  CVE disclosure affecting any direct dependency.
- Security-sensitive packages requiring priority review on CVE: `cryptography`,
  `fastapi`, `sqlalchemy`, `python-telegram-bot`, `httpx`, `redis`, `pillow`.

---

## 6. Infrastructure Hardening Checklist

- [ ] `ENCRYPTION_KEY`, `ADMIN_API_KEY`, `SECRET_KEY`, all API keys stored in a
      secrets manager (AWS Secrets Manager, GCP Secret Manager, Railway secrets)
      — never in `.env` files committed to source control.
- [ ] PostgreSQL: restrict connection to app subnet only; enable SSL.
- [ ] Redis: bind to private subnet; enable AUTH password; disable `CONFIG` command.
- [ ] HTTP: TLS termination at reverse proxy (nginx / Railway / Render); HSTS header.
- [ ] Webhook URLs: Telegram validates the certificate; use a valid TLS cert.
- [ ] Log aggregation: ship to a SIEM; alert on `admin_auth_rejected` spike,
      `webhook_invalid_secret` spike, `google_token_refresh_failed`.
- [ ] Rate limiting: the per-NGO webhook limiter (30 req/min) is implemented.
      Add IP-level rate limiting at the reverse proxy for all endpoints.
- [ ] Secrets rotation: rotate `ENCRYPTION_KEY` using a migration script that
      re-encrypts all Fernet-encrypted DB columns atomically.

---

## 7. Incident Response

### Contacts (fill in before going to production)

| Role | Name | Contact |
|---|---|---|
| Platform owner | _TBD_ | _TBD_ |
| On-call engineer | _TBD_ | _TBD_ |
| Security contact | _TBD_ | security@ngoopsbot.com |

### Response steps for key compromise

1. Immediately rotate the compromised key in the secrets manager.
2. Restart all app instances to clear `lru_cache` and pick up the new key.
3. If `ENCRYPTION_KEY` is compromised: run the key-rotation migration script to
   re-encrypt all Fernet columns with the new key.
4. Revoke any Telegram bot tokens or Google OAuth tokens that may have been exposed.
5. Review audit logs (`audit_log` table) for any actions taken under the compromised key.
6. Notify affected NGOs per your data-breach notification obligations under applicable law
   (India PDPB / DPDP Act 2023, or EU GDPR if applicable).

---

## 8. Known Limitations / Future Hardening

| # | Issue | Priority | Notes |
|---|---|---|---|
| 1 | Conversation transcripts stored in plaintext | Medium | Consider column-level AES encryption if conversations capture donor PII |
| 2 | Single `ADMIN_API_KEY` for all admin operations | Medium | Add per-NGO admin keys or short-lived JWT tokens for finer-grained access control |
| 3 | No mutual TLS between app and Telegram | Low | Telegram does not support client certificates; mitigated by webhook secret |
| 4 | Redis stores prompt layers without encryption | Low | Prompt content is not secret, but consider encryption if it ever includes PII |
| 5 | No audit log for failed admin auth attempts beyond log lines | Low | Persist failed auth attempts to `audit_log` table for forensic analysis |
| 6 | `ADMIN_API_KEY` is a shared long-lived secret | Medium | Replace with short-lived JWT or OAuth client credentials for production |
| 7 | No IP allowlist on admin endpoints | Low | Consider middleware or reverse proxy ACL for `/api/v1/admin/*` |
| 8 | Webhook secret in URL path (logged by some proxies) | Low | Migrate to `X-Telegram-Bot-Api-Secret-Token` header approach in a future release |
