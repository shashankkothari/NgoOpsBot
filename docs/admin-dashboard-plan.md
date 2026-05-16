# Admin Dashboard — Build Plan

The Next.js 14 scaffold already exists in `dashboard/` with routing, shadcn/ui
components, SWR data fetching, and NextAuth wired up. What's missing is working
data connections and several key screens. This plan completes it.

---

## What already exists (scaffold only, not wired)

| File | Status |
|---|---|
| `dashboard/page.tsx` | Stat cards + health — needs real API data |
| `dashboard/ngos/page.tsx` | NGO table — needs real API data |
| `dashboard/ngos/[id]/page.tsx` | Detail with tabs — needs real API data |
| `dashboard/conversations/page.tsx` | Placeholder |
| `dashboard/system/page.tsx` | Placeholder |
| `dashboard/audit/page.tsx` | Placeholder |
| `src/lib/api.ts` | Base client — needs full endpoint coverage |
| `src/components/ngos/ngo-form.tsx` | Form exists — needs webhook/agent steps |

---

## What needs to be built

### Phase 1 — Data layer (no UI changes, ~1 day)

**`src/lib/api.ts`** — Complete all API client functions:
- `getNGOs(page, search, is_active)` → `GET /api/v1/admin/ngos`
- `createNGO(payload)` → `POST /api/v1/admin/ngos`
- `updateNGO(id, payload)` → `PATCH /api/v1/admin/ngos/{id}`
- `deleteNGO(id)` → `DELETE /api/v1/admin/ngos/{id}`
- `getNGOStats(id)` → `GET /api/v1/admin/ngos/{id}/stats`
- `refreshWebhook(id)` → `POST /api/v1/admin/ngos/{id}/refresh-webhook`
- `upsertNGOSettings(id, payload)` → `POST /api/v1/admin/ngos/{id}/settings`
- `getStaff(ngoId)` → `GET /api/v1/admin/staff?ngo_id={id}`
- `createStaff(payload)` → `POST /api/v1/admin/staff`
- `updateStaff(id, payload)` → `PATCH /api/v1/admin/staff/{id}`
- `getConversations(filters)` → `GET /api/v1/admin/conversations`
- `getReminders(ngoId)` → `GET /api/v1/admin/reminders?ngo_id={id}`
- `getAuditLog(ngoId)` → `GET /api/v1/admin/audit`

Auth: every request sends `X-Admin-API-Key: {NEXT_PUBLIC_ADMIN_API_KEY}` header.

---

### Phase 2 — Overview page (0.5 day)

**Screen:** `/dashboard`

Wire the 4 stat cards to real data:
- Total NGOs / Active NGOs — from `GET /api/v1/admin/ngos` total count
- Messages Today — from aggregated conversation count (add endpoint if needed)
- Tokens Used Today — from Prometheus metric `tokens_consumed_total`

Health section — call `GET /health/ready` and parse DB/Redis status.

Recent activity feed — last 10 audit log entries across all NGOs.

SWR refresh intervals: stats 60s, health 15s.

---

### Phase 3 — NGO list + onboarding wizard (1.5 days)

**Screen:** `/dashboard/ngos`

Add per-row health indicators not currently shown:
- Webhook status (green/red) — call Telegram `getWebhookInfo` via backend or
  track last successful webhook receipt timestamp in DB
- Google Drive connected (yes/no) — from `NGO.google_drive_folder_id != null`
- Agents enabled count badge

**Onboarding wizard** — replace the current single-form Add NGO sheet with a
5-step wizard:

| Step | Content |
|---|---|
| 1. Basic info | Name, timezone, language |
| 2. Telegram | Bot token input + "Verify" button (live API check) |
| 3. Anthropic key | Optional — can use platform key |
| 4. Agents | Toggle each of 5 agents on/off |
| 5. Confirm | Summary + "Create NGO" button → POST → show webhook URL |

The wizard calls `POST /api/v1/admin/ngos` on step 5 and shows the generated
webhook URL so the operator can verify Telegram received it.

---

### Phase 4 — NGO detail page (1 day)

**Screen:** `/dashboard/ngos/[id]`

Four tabs — Overview, Staff, Agents, Reminders.

**Overview tab:**
- Stat cards: total messages, tokens used, active staff, active reminders
- Webhook URL (copy-to-clipboard button)
- Google Drive connection status + Connect/Disconnect button
- Danger zone: Deactivate NGO / Refresh webhook

**Staff tab:**
- Table: Name, Role, Telegram ID, Allowed agents, Active status
- Add staff sheet (name, email, telegram_user_id, allowed_agents checkboxes)
- Toggle active inline

**Agents tab:**
- Card per agent with enable/disable toggle
- Expandable custom prompt textarea per agent
- Save changes button

**Reminders tab:**
- Table: Type, Schedule/trigger, Last run, Next run, Active
- Readonly — reminders are created by NGO staff via Telegram; admins can
  deactivate or trigger manually via "Run now" button

---

### Phase 5 — System health (1 day)

**Screen:** `/dashboard/system`

Metrics sourced from `GET /metrics` (Prometheus text format, parsed client-side):

| Widget | Metric |
|---|---|
| Messages today | `messages_processed_total` sum |
| Agent latency chart (bar) | `agent_response_latency` p50/p95 per agent |
| Token usage by NGO (table) | `tokens_consumed_total` by ngo_slug label |
| Cache hit rate | `cache_hits_total / (cache_hits + cache_misses)` |
| DB query latency | `db_query_latency` p95 |
| Active NGOs gauge | `active_ngos` |
| Error rate | HTTP 5xx count from instrumentator metrics |

Use `recharts` (already a common Next.js choice) for the bar/line charts.
Parse Prometheus text format with a small utility function — no client library needed.

---

### Phase 6 — Conversations viewer (0.5 day)

**Screen:** `/dashboard/conversations`

Filters: NGO (dropdown), Agent (dropdown), Date range.

Table columns: NGO, Staff name, Agent, Last message preview (truncated), Turn count,
Tokens used, Last activity.

Click a row → expand inline to show the full conversation thread as a
chat bubble view (user=right, assistant=left).

---

### Phase 7 — Audit log (0.5 day)

**Screen:** `/dashboard/audit`

Chronological table: Timestamp, NGO, Action, Details (JSON expandable), IP address.
Filter by NGO and date range.

No write operations — readonly view.

---

## Pages summary

| Screen | Route | Priority | Effort |
|---|---|---|---|
| Overview | `/dashboard` | P1 | 0.5d |
| NGO list + onboarding | `/dashboard/ngos` | P1 | 1.5d |
| NGO detail | `/dashboard/ngos/[id]` | P1 | 1d |
| System health | `/dashboard/system` | P2 | 1d |
| Conversations | `/dashboard/conversations` | P2 | 0.5d |
| Audit log | `/dashboard/audit` | P3 | 0.5d |
| Data layer | `src/lib/api.ts` | P1 | 1d |
| **Total** | | | **~6 days** |

---

## Design decisions

- **No new dependencies** beyond what's in package.json + recharts for charts
- **API key auth only** — no NextAuth session complexity for an internal tool;
  store `NEXT_PUBLIC_ADMIN_API_KEY` in `.env.local`, gate the entire dashboard
  layout with a simple middleware check
- **SWR for all data** — no React Query, no Redux; SWR is already the pattern
- **shadcn/ui throughout** — all components already in `src/components/ui/`
- **Mobile not a priority** — this is an ops tool used at a desk; responsive
  enough to not break on tablet but not optimised for mobile
