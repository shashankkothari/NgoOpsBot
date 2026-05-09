# Cost Model and Pricing — NGO OpsBot

This document covers: what it costs to run the platform, how those costs
scale with NGO count, and what to charge NGOs to sustain operations.

All figures are in INR and USD. Exchange rate assumed: ₹85 = $1.

---

## Part 0 — Minimum Viable Pricing (Zero-Profit Model)

This section answers: **what is the bare minimum to charge NGOs to keep
the lights on with a 3-engineer team, with no profit motive?**

---

### Team cost — three scenarios

The team cost dominates everything else. Infrastructure at 50 NGOs is
~₹20,000/month. A 3-person team is ₹10–16x that.

| Role | Market rate | Mission rate | Part-time/contract |
|---|---|---|---|
| Senior engineer / tech lead | ₹1,20,000 | ₹80,000 | ₹80,000 (full-time) |
| Mid-level engineer | ₹80,000 | ₹55,000 | ₹30,000 (50%) |
| Junior engineer | ₹50,000 | ₹35,000 | ₹25,000 (50%) |
| **Subtotal salaries** | **₹2,50,000** | **₹1,70,000** | **₹1,35,000** |
| Benefits, PF, health (30%) | ₹75,000 | ₹51,000 | ~₹15,000 |
| **Total people cost** | **₹3,25,000** | **₹2,21,000** | **₹1,50,000** |

**Mission rate** = below-market pay for engineers who believe in the cause —
realistic for a non-profit or social enterprise.

**Part-time/contract** = one full-time senior who owns the system, two
part-time engineers for feature work and support. Most sustainable early model.

---

### Total monthly burn at 50 NGOs

| Scenario | People | Infra | Total/month |
|---|---|---|---|
| A — Market rate | ₹3,25,000 | ₹20,000 | **₹3,45,000** |
| B — Mission rate | ₹2,21,000 | ₹20,000 | **₹2,41,000** |
| C — Part-time/contract | ₹1,50,000 | ₹20,000 | **₹1,70,000** |

---

### Break-even per NGO at different NGO counts

This is the uncomfortable table. Team cost is largely fixed regardless of
how many NGOs are on the platform, so per-NGO cost drops as you grow.

| NGOs on platform | Scenario A | Scenario B | Scenario C |
|---|---|---|---|
| 10 | ₹34,500 | ₹24,100 | ₹17,000 |
| 20 | ₹17,250 | ₹12,050 | ₹8,500 |
| 30 | ₹11,500 | ₹8,033 | ₹5,667 |
| 50 | ₹6,900 | ₹4,820 | ₹3,400 |

**The honest problem:** Until you have 30+ NGOs, the per-NGO break-even
price is too high for most Indian NGOs. Below ₹5,000/month is the viable
zone — you only get there at 30+ NGOs on mission pay, or 50+ NGOs on
part-time model.

This is the chicken-and-egg problem every mission-driven platform faces.

---

### How to bridge the gap before reaching critical mass

**Option 1 — CSR/foundation grant covers team cost**

One corporate CSR grant of ₹20–25L/year (~₹1.7–2L/month) covers the
full team cost in Scenario B or C. NGOs then only pay for infrastructure
recovery: **₹400–500/NGO/month**. This is the most impactful lever.

Potential sources: Tata Trusts Tech4Good, Google.org, HDFC Bank Parivartan,
Microsoft Philanthropies, Azim Premji Foundation. A platform that digitises
NGO operations is a straightforward capacity-building grant proposal.

**Option 2 — Staged hiring**

Don't hire all 3 engineers on day one. Start with 1 senior (founder-mode),
hire the second at 15 NGOs, third at 30 NGOs. This changes the early math
dramatically:

| Phase | NGOs | Monthly burn | Per-NGO break-even |
|---|---|---|---|
| 1 engineer (founder) | 1–15 | ₹95,000–1,00,000 | ₹6,333–10,000 |
| 2 engineers | 15–30 | ₹1,50,000–1,60,000 | ₹5,000–10,667 |
| 3 engineers | 30–50 | ₹1,70,000–2,21,000 | ₹3,400–7,367 |

**Option 3 — Technical fellowship / volunteer engineering**

Engage engineers through social impact fellowship programmes at subsidized
or zero cost for 6–12 month stints:
- Google.org fellows (donated engineering time)
- ThoughtWorks social impact programme
- iSpirt volunteers
- NASSCOM Foundation tech corps

One fellowship covering one engineer role reduces monthly burn by ₹55,000–80,000.

---

### Minimum viable pricing summary

| Funding model | What NGOs pay | Viable from NGO # |
|---|---|---|
| CSR grant covers team | ₹500/month (infra only) | Day 1 |
| CSR grant covers 50% of team | ₹1,500–2,000/month | NGO #5 |
| No external funding, part-time team | ₹3,400/month | NGO #50 |
| No external funding, mission-rate team | ₹4,820/month | NGO #50 |

**Recommended approach:** Raise one CSR grant upfront to fund the team for
year 1. Charge NGOs ₹999–1,499/month as a nominal commitment fee (skin in
the game, not cost recovery). Use year 1 to reach 20–30 NGOs. By year 2
the platform fee alone can cover operations without grant dependency.

---

---

## Part 1 — Platform Operating Costs

### Infrastructure (Railway.app)

| Service | Spec | Monthly Cost (USD) |
|---|---|---|
| API service (2 replicas) | 512MB RAM each | $10–20 |
| PostgreSQL | 8GB RAM, 50GB SSD | $20–25 |
| Redis | 256MB | $5–10 |
| Egress / bandwidth | Minimal (webhook payloads are tiny) | ~$2 |
| **Total infra** | | **$37–57/month** |

At 50 NGOs this works out to **$0.75–$1.15/NGO/month** for infrastructure.

Railway pricing is usage-based; the above assumes moderate traffic. At very low
traffic (early days) actual costs will be lower, closer to $20–30/month total.

---

### Communication services (platform-level)

| Service | Usage | Monthly Cost |
|---|---|---|
| SendGrid (email) | ~5,000 emails/month across all NGOs | Free (under 100/day) → $15/month at scale |
| MSG91 (SMS) | ~500 SMS/month across all NGOs | ~₹250–500 ($3–6) |
| Sentry (error tracking) | Team plan | $26/month |
| Domain + SSL | Annual | ~$15/year (~$1.25/month) |
| **Total comms** | | **$30–50/month** |

---

### Claude API costs

**This is the key variable: who pays?**

In the current architecture, each NGO provides their own Anthropic API key.
This means **Claude costs are borne entirely by the NGO**, not the platform.

Platform only pays Claude costs for:
- NGOs on a trial/pilot (using the platform fallback key)
- Internal testing

**Cost per NGO per month if platform were paying** (for reference):

| Usage level | Messages/month | Estimated Claude cost |
|---|---|---|
| Light (small NGO, 5 staff) | 300 | $1.50–2.50 |
| Moderate (typical NGO, 15 staff) | 1,500 | $7–12 |
| Heavy (active NGO, 30 staff) | 5,000 | $22–38 |

Assumptions: claude-sonnet-4-6 at $3/MTok input, $15/MTok output. Average turn:
~600 input tokens (system prompt cached at ~70% hit rate) + ~300 output tokens.
With prompt caching, effective input cost is ~40% of the rack rate.

---

### Total platform operating cost summary

| Scenario | Monthly cost (USD) | Monthly cost (INR) |
|---|---|---|
| Early (1–5 NGOs, all with own API keys) | $50–80 | ₹4,250–6,800 |
| Growth (20 NGOs, all with own API keys) | $70–110 | ₹5,950–9,350 |
| Scale (50 NGOs, all with own API keys) | $100–160 | ₹8,500–13,600 |

The platform cost is largely fixed — it doesn't scale linearly with NGOs because
the main costs (infra, SaaS tools) are capacity-based, not per-request.

---

## Part 2 — What to Charge NGOs

### Cost components per NGO

| Component | Who pays | Monthly cost to NGO |
|---|---|---|
| Platform infrastructure share | Billed by platform | ₹500–1,000 |
| Claude API usage | NGO pays Anthropic directly | ₹600–3,200 (light to moderate) |
| Google Workspace | NGO pays Google directly | ₹125–750/user (existing) |
| SMS (if used) | Platform bills through or NGO direct | ₹50–200 |
| **Platform fee** | Billed by platform | See tiers below |

---

### Recommended pricing tiers

#### Tier 1 — Starter ₹1,999/month (~$24)

Best for: Small NGOs, 1–5 staff using the bot, just getting started.

- Up to 5 staff accounts
- 3 agents enabled (choose any 3 of 5)
- 500 bot interactions/month included
- Email support, 48h response
- Google Drive integration
- No custom branding

#### Tier 2 — Standard ₹4,999/month (~$59)

Best for: Operational NGOs with an active field team.

- Up to 20 staff accounts
- All 5 agents enabled
- Unlimited bot interactions
- Proactive reminders (all 5 types)
- Priority support, 24h response
- Custom welcome message and bot name
- Monthly usage report

#### Tier 3 — Growth ₹9,999/month (~$118)

Best for: NGOs with multiple programmes, reporting to institutional donors.

- Up to 50 staff accounts
- All 5 agents + custom agent prompt per agent
- Unlimited interactions
- Dedicated onboarding session (2 hours)
- SLA: 4-hour response for critical issues
- Quarterly strategy review call
- Custom Sheets template setup

#### Tier 4 — Enterprise — Custom pricing

Best for: Networks of NGOs, foundations managing multiple grantees, government
programmes.

- Multiple NGO tenants under one account
- Custom agent development
- On-premises or private cloud deployment option
- Contractual data isolation (separate DB schema)
- Dedicated support manager
- MOU and formal SLA

---

### Unit economics at each tier

At 50 NGOs on the Standard tier:

| | Amount |
|---|---|
| Gross revenue | 50 × ₹4,999 = ₹2,49,950/month |
| Platform infra cost | ~₹13,600/month |
| Comms (SendGrid, MSG91) | ~₹4,250/month |
| Sentry + tooling | ~₹2,200/month |
| **Gross margin before team cost** | **~₹2,29,900/month (~92%)** |

The business is high-margin once infrastructure is covered because the
main variable cost (Claude API) is passed through to NGOs via their own API keys.

---

### What NGOs pay Anthropic directly

Give NGOs a clear estimate so they can budget:

| NGO size | Staff using bot | Est. messages/month | Est. Anthropic cost/month |
|---|---|---|---|
| Small | 5 | 300–500 | ₹500–1,000 |
| Medium | 15 | 1,000–2,000 | ₹1,700–3,400 |
| Large | 30 | 3,000–6,000 | ₹5,000–10,000 |

Anthropic offers startup/nonprofit credits — help NGOs apply. This can eliminate
their API cost entirely for the first 6–12 months.

---

## Part 3 — Go-to-Market Considerations

### Pilot pricing

Offer the first 5 NGOs **free for 6 months** in exchange for:
- Weekly feedback calls
- Permission to use as a case study
- Agreement to pay Standard tier after the pilot

This validates product-market fit before investing in sales infrastructure.

---

### CSR funding angle

Several Indian corporates have CSR mandates to support NGO capacity building.
NGO OpsBot can be funded as a CSR initiative where:
- A corporate pays for 10–20 NGO subscriptions as part of their CSR programme
- The corporate gets reporting on NGO efficiency gains
- Pricing to corporates: ₹5,000/NGO/month (slight premium for CSR reporting)

This is potentially a faster revenue path than selling to individual NGOs, who
often have stretched budgets and long procurement cycles.

---

### Pricing sensitivity for Indian NGOs

Most Indian NGOs have annual budgets under ₹1 crore. A ₹4,999/month subscription
is ₹59,988/year — roughly 5–6% of a ₹10L budget. This is meaningful but
justifiable if it replaces even one day per month of manual reporting work.

Frame pricing as: "Replaces 1 day of staff time per month" rather than
as a SaaS subscription. At ₹20,000/month for a programme officer, one day of
saved time = ₹1,000 — a 5x ROI on the Starter tier.

---

## Summary

| | Starter | Standard | Growth |
|---|---|---|---|
| Platform charge | ₹1,999/mo | ₹4,999/mo | ₹9,999/mo |
| NGO pays Anthropic | ₹500–1,000/mo | ₹1,700–3,400/mo | ₹5,000–10,000/mo |
| Total cost to NGO | ~₹2,500–3,000 | ~₹6,700–8,400 | ~₹15,000–20,000 |
| Staff limit | 5 | 20 | 50 |
| Agents | 3 | 5 | 5 + custom prompts |
