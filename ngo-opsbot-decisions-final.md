# NGO OpsBot — Final Decision Log
## All decisions locked. Ready to build.

---

## DELIVERY
| Decision | Choice | Implication |
|---|---|---|
| Channel | Telegram (native Bot API) | No third-party platforms, full control |
| Bot type | One bot per NGO | Separate token, webhook, identity per NGO |
| Staff interaction | Group chat — all staff in one NGO group | Bot responds to @mentions and /commands |
| Bot response to voice | Text only | Staff sends voice → Whisper transcribes → Claude replies in text |

---

## AI & AGENTS
| Decision | Choice | Implication |
|---|---|---|
| AI model | Claude (Anthropic API) | Per-NGO key, NGO pays their own bill |
| Agent modules (v1) | Fundraising, Finance, Marketing, HR, Compliance | 5 agents + Comms module |
| Agent prompts | 3-layer system (platform base + NGO profile + NGO custom) | NGOs can customize via /settings |
| Staff agent access | Role-based, set by admin per staff member | Stored in ngo_staff table |
| Language | Multilingual, auto-detected | Claude detects and responds in same language |
| Voice input | Yes (v1) via OpenAI Whisper | Voice note → text → Claude → text reply |

---

## DATA & INTEGRATIONS
| Decision | Choice | Implication |
|---|---|---|
| Google account | Each NGO connects their own via OAuth | Platform stores encrypted refresh token |
| Google Drive | Auto-created folder + Master Tracker sheet | All agents read/write to NGO's own Drive |
| Database | PostgreSQL (Railway) | NGO configs, staff, conversations, rules |
| Cache/Queue | Redis (Railway) | Session state, scheduler jobs |

---

## COMMUNICATIONS
| Audience | Channel | Provider |
|---|---|---|
| NGO staff reminders | Telegram (in group) | Native Bot API |
| NGO staff reminders | SMS | MSG91 (India) |
| External contacts (donors, volunteers) | Email | SendGrid |
| External contacts | SMS | MSG91 / Twilio |
| WhatsApp | v2 — not in scope now | — |

---

## ADMIN
| Decision | Choice |
|---|---|
| NGO onboarding | Done by you (admin) |
| Staff management | Done by you (admin) for now |
| Admin tools | Web dashboard + Config sheet + Admin Telegram bot |
| NGO self-service | Edit agent custom prompts via /settings only |

---

## PROACTIVE REMINDERS
| Decision | Choice |
|---|---|
| Reminder engine | APScheduler (runs every 15 min) |
| Reminder types | Date-based, inactivity, threshold, recurring, event-triggered |
| Reminder tone | Claude-generated (natural, not templates) |
| External send approval | Staff approves via inline keyboard before send |
| Reminder config | Set by admin in config sheet / dashboard |

---

## TECH STACK (FINAL, LOCKED)
| Layer | Technology |
|---|---|
| Bot framework | python-telegram-bot v20+ (async) |
| Backend | FastAPI (Python) |
| Scheduler | APScheduler |
| Database | PostgreSQL |
| Cache | Redis |
| Hosting | Railway.app (backend + DB + Redis) |
| Admin dashboard | Next.js + Tailwind → Vercel |
| Google APIs | google-api-python-client |
| Voice → Text | OpenAI Whisper API |
| SMS | MSG91 (India primary) |
| Email | SendGrid |
| AI | Anthropic Claude API (per-NGO key) |

---

## BUILD ORDER
1. FastAPI skeleton + DB schema + Railway deploy
2. Telegram webhook handler + NGO router + group chat handling
3. Agent dispatcher + Claude integration + multilingual
4. Voice message handling (Whisper pipeline)
5. Fundraising agent (full prompts + Sheets)
6. Finance + HR + Marketing + Compliance agents
7. Google Drive OAuth + auto folder/sheet creation
8. Proactive reminder engine
9. Comms module (SMS + Email)
10. Role-based access per staff member
11. Admin dashboard (Next.js)
12. Admin Telegram bot
13. NGO /settings for custom prompts
14. End-to-end test with real NGO

---

## WHAT IS EXPLICITLY OUT OF SCOPE FOR V1
- WhatsApp integration
- NGO self-service staff management
- Voice responses from bot
- Payment processing
- Mobile app
- Per-staff private bot chat (group only)
