#!/usr/bin/env python3
"""
Seeds the local dev database with a Demo NGO and sample data.

Run after: alembic upgrade head

Usage:
    python scripts/seed_db.py

What gets created:
    - NGO:          "Demo NGO" (slug: demo-ngo)
    - Staff:        2 admins + 3 staff with varying agent access
    - NGO Settings: All 5 agents enabled with sample custom prompts
    - Reminders:    1 sample reminder of each type (5 total)

The script is idempotent — running it twice will skip creation of
records that already exist (matched on slug / telegram_user_id).
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure the project root is on sys.path so we can import app.*
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before importing app config
from dotenv import load_dotenv  # type: ignore[import-untyped]

load_dotenv(PROJECT_ROOT / ".env")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import encrypt_value
from app.models.base import Base  # noqa: F401 — needed to register all models
from app.models.ngo import NGO, NGOSettings
from app.models.reminder import Reminder
from app.models.staff import Staff

settings = get_settings()

# ---------------------------------------------------------------------------
# Use the synchronous URL for seeding (avoids asyncio complexity in a script)
# ---------------------------------------------------------------------------
SYNC_URL = settings.SYNC_DATABASE_URL or settings.DATABASE_URL.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)

engine = create_engine(SYNC_URL, echo=False)

# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

ALL_AGENTS = ["fundraising", "finance", "marketing", "hr", "compliance"]

AGENT_PROMPTS: dict[str, str] = {
    "fundraising": (
        "Focus on our primary funding streams: FCRA-regulated grants, CSR partnerships, "
        "and individual donors. Always flag grants with <60 days to deadline. "
        "Use INR for all monetary values."
    ),
    "finance": (
        "Apply Indian accounting standards (Ind AS). Fiscal year runs April–March. "
        "Flag any expense >₹50,000 that lacks a supporting invoice. "
        "Reconcile against our Tally ERP data when queried."
    ),
    "marketing": (
        "All external content must be reviewed for FCRA compliance before publishing. "
        "Maintain a warm, inclusive tone. Preferred hashtags: #DemoNGO #ImpactMatters. "
        "Do not quote beneficiary data without consent confirmation."
    ),
    "hr": (
        "We follow the Shops and Establishments Act (Maharashtra). "
        "Leave policy: 12 CL + 12 EL per year. "
        "Always remind staff of the grievance committee contact for HR disputes."
    ),
    "compliance": (
        "Monitor FCRA annual return deadlines (Dec 31). "
        "Flag any foreign contribution >₹1 crore for mandatory board review. "
        "Darpan registration renewal is due every 5 years."
    ),
}

STAFF_MEMBERS = [
    {
        "name": "Priya Sharma",
        "role": "admin",
        "telegram_user_id": 100000001,
        "telegram_username": "priya_demo",
        "email": "priya@demo-ngo.example.com",
        "phone": "+919000000001",
        "allowed_agents": ALL_AGENTS,
    },
    {
        "name": "Arjun Mehta",
        "role": "admin",
        "telegram_user_id": 100000002,
        "telegram_username": "arjun_demo",
        "email": "arjun@demo-ngo.example.com",
        "phone": "+919000000002",
        "allowed_agents": ALL_AGENTS,
    },
    {
        "name": "Sunita Rao",
        "role": "staff",
        "telegram_user_id": 100000003,
        "telegram_username": "sunita_demo",
        "email": "sunita@demo-ngo.example.com",
        "phone": "+919000000003",
        "allowed_agents": ["fundraising", "marketing"],
    },
    {
        "name": "Vikram Nair",
        "role": "staff",
        "telegram_user_id": 100000004,
        "telegram_username": "vikram_demo",
        "email": "vikram@demo-ngo.example.com",
        "phone": "+919000000004",
        "allowed_agents": ["finance", "compliance"],
    },
    {
        "name": "Kavya Pillai",
        "role": "staff",
        "telegram_user_id": 100000005,
        "telegram_username": "kavya_demo",
        "email": "kavya@demo-ngo.example.com",
        "phone": "+919000000005",
        "allowed_agents": ["hr"],
    },
]

REMINDERS = [
    {
        "title": "Monthly Donor Report",
        "reminder_type": "recurring",
        "agent_name": "fundraising",
        "config": {
            "cron": "0 9 1 * *",  # 9 AM on the 1st of every month
            "message": (
                "It's the start of a new month! Please prepare and share the donor "
                "activity report for last month. Tag @fundraising_agent for a summary."
            ),
        },
        "target_audience": "staff_group",
        "target_details": {},
    },
    {
        "title": "Quarterly Finance Review",
        "reminder_type": "date_based",
        "agent_name": "finance",
        "config": {
            "date": "2025-06-30",
            "time": "10:00",
            "message": (
                "Q1 finance review is due today. Please upload bank reconciliation "
                "statements and expense summaries to the shared Drive folder."
            ),
        },
        "target_audience": "staff_group",
        "target_details": {},
    },
    {
        "title": "Team Inactivity Alert",
        "reminder_type": "inactivity",
        "agent_name": "hr",
        "config": {
            "agent": "hr",
            "idle_days": 7,
            "message": (
                "No HR queries have been raised in the last 7 days. "
                "Reminder: you can ask the HR agent about leave balances, policies, and grievances."
            ),
        },
        "target_audience": "specific_staff",
        "target_details": {},  # will be updated with staff IDs after insert
    },
    {
        "title": "Donation Threshold Warning",
        "reminder_type": "threshold",
        "agent_name": "fundraising",
        "config": {
            "metric": "donations_ytd",
            "below": 500000,
            "message": (
                "Year-to-date donations are below ₹5 lakh. "
                "Please review the fundraising pipeline and escalate if needed."
            ),
        },
        "target_audience": "staff_group",
        "target_details": {},
    },
    {
        "title": "FCRA Annual Return Deadline",
        "reminder_type": "event_triggered",
        "agent_name": "compliance",
        "config": {
            "event": "fcra_annual_return",
            "days_before": 30,
            "message": (
                "FCRA Annual Return deadline is 30 days away (Dec 31). "
                "Please begin compiling foreign contribution receipts and FC-4 form."
            ),
        },
        "target_audience": "specific_staff",
        "target_details": {},
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encrypt_or_placeholder(value: str) -> str:
    """Encrypt value if ENCRYPTION_KEY is set, else return a plaintext placeholder."""
    try:
        return encrypt_value(value)
    except Exception:
        # In a seed context without a real key, store a safe placeholder
        return f"SEED_PLACEHOLDER:{value}"


def seed(session: Session) -> None:
    # ------------------------------------------------------------------
    # NGO
    # ------------------------------------------------------------------
    existing_ngo = session.execute(
        select(NGO).where(NGO.slug == "demo-ngo")
    ).scalar_one_or_none()

    if existing_ngo:
        print("[seed] NGO 'demo-ngo' already exists — skipping NGO creation.")
        ngo = existing_ngo
    else:
        ngo = NGO(
            name="Demo NGO",
            slug="demo-ngo",
            telegram_bot_token=_encrypt_or_placeholder("DEMO_BOT_TOKEN_REPLACE_ME"),
            anthropic_api_key=_encrypt_or_placeholder("DEMO_ANTHROPIC_KEY_REPLACE_ME"),
            webhook_secret="demo-webhook-secret-local-only",
            is_active=True,
            timezone="Asia/Kolkata",
            language="en",
        )
        session.add(ngo)
        session.flush()  # get the ID without committing
        print(f"[seed] Created NGO: {ngo.name!r} (id={ngo.id}, slug={ngo.slug!r})")

    # ------------------------------------------------------------------
    # NGO Settings (one per agent)
    # ------------------------------------------------------------------
    for agent_name in ALL_AGENTS:
        existing_setting = session.execute(
            select(NGOSettings).where(
                NGOSettings.ngo_id == ngo.id,
                NGOSettings.agent_name == agent_name,
            )
        ).scalar_one_or_none()

        if existing_setting:
            print(f"[seed]   Settings for agent '{agent_name}' already exist — skipping.")
        else:
            setting = NGOSettings(
                ngo_id=ngo.id,
                agent_name=agent_name,
                custom_prompt=AGENT_PROMPTS[agent_name],
                is_enabled=True,
            )
            session.add(setting)
            print(f"[seed]   Created NGOSettings for agent: {agent_name!r}")

    # ------------------------------------------------------------------
    # Staff
    # ------------------------------------------------------------------
    inserted_staff: list[Staff] = []
    for member_data in STAFF_MEMBERS:
        existing_staff = session.execute(
            select(Staff).where(
                Staff.ngo_id == ngo.id,
                Staff.telegram_user_id == member_data["telegram_user_id"],
            )
        ).scalar_one_or_none()

        if existing_staff:
            print(
                f"[seed]   Staff '{member_data['name']}' already exists — skipping."
            )
            inserted_staff.append(existing_staff)
        else:
            staff = Staff(
                ngo_id=ngo.id,
                telegram_user_id=member_data["telegram_user_id"],
                telegram_username=member_data.get("telegram_username"),
                name=member_data["name"],
                role=member_data["role"],
                allowed_agents=member_data["allowed_agents"],
                is_active=True,
                phone=member_data.get("phone"),
                email=member_data.get("email"),
            )
            session.add(staff)
            session.flush()
            inserted_staff.append(staff)
            print(
                f"[seed]   Created Staff: {staff.name!r} "
                f"(role={staff.role!r}, agents={staff.allowed_agents})"
            )

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------
    # Build a lookup of staff IDs for specific_staff reminders
    hr_staff = next(
        (s for s in inserted_staff if "hr" in s.allowed_agents and s.role == "staff"),
        inserted_staff[0] if inserted_staff else None,
    )
    compliance_admin = next(
        (s for s in inserted_staff if s.role == "admin"),
        inserted_staff[0] if inserted_staff else None,
    )

    for reminder_data in REMINDERS:
        existing_reminder = session.execute(
            select(Reminder).where(
                Reminder.ngo_id == ngo.id,
                Reminder.title == reminder_data["title"],
            )
        ).scalar_one_or_none()

        if existing_reminder:
            print(
                f"[seed]   Reminder '{reminder_data['title']}' already exists — skipping."
            )
            continue

        # Fill in specific_staff target_details with real IDs
        target_details = dict(reminder_data["target_details"])
        if reminder_data["reminder_type"] == "inactivity" and hr_staff:
            target_details = {"staff_ids": [str(hr_staff.id)]}
        elif reminder_data["reminder_type"] == "event_triggered" and compliance_admin:
            target_details = {"staff_ids": [str(compliance_admin.id)]}

        reminder = Reminder(
            ngo_id=ngo.id,
            title=reminder_data["title"],
            reminder_type=reminder_data["reminder_type"],
            agent_name=reminder_data.get("agent_name"),
            config=reminder_data["config"],
            target_audience=reminder_data["target_audience"],
            target_details=target_details,
            is_active=True,
        )
        session.add(reminder)
        print(
            f"[seed]   Created Reminder: {reminder.title!r} "
            f"(type={reminder.reminder_type!r})"
        )

    session.commit()
    print("\n[seed] Done. Database seeded successfully.")
    print(f"[seed] NGO slug: demo-ngo | ID: {ngo.id}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("[seed] Connecting to:", SYNC_URL.split("@")[-1])  # hide credentials
    with Session(engine) as session:
        seed(session)


if __name__ == "__main__":
    main()
