#!/usr/bin/env python3
"""
Validates that all required environment variables are set before a Railway deploy.

Usage:
    python scripts/check_env.py

Exit code 0 if all required vars are present and non-empty.
Exit code 1 if any required vars are missing — prints a clear summary.

Add this as a pre-deploy step in your CI workflow:
    - run: python scripts/check_env.py
"""

import os
import sys

# ---------------------------------------------------------------------------
# Required environment variables
# ---------------------------------------------------------------------------
REQUIRED_VARS: list[str] = [
    "DATABASE_URL",
    "REDIS_URL",
    "ENCRYPTION_KEY",
    "ADMIN_API_KEY",
    "SENDGRID_API_KEY",
    "MSG91_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "SENTRY_DSN",
]

# ---------------------------------------------------------------------------
# Optional vars that are checked but only produce warnings (not failures)
# ---------------------------------------------------------------------------
OPTIONAL_VARS: list[str] = [
    "ANTHROPIC_API_KEY",
    "APP_BASE_URL",
    "WEBHOOK_SECRET",
    "SENDGRID_FROM_EMAIL",
    "MSG91_SENDER_ID",
    "SECRET_KEY",
]


def main() -> None:
    missing: list[str] = []
    present: list[str] = []

    for var in REQUIRED_VARS:
        value = os.environ.get(var, "")
        if not value or value.strip() == "":
            missing.append(var)
        else:
            present.append(var)

    # Print status for all required vars
    print("=" * 60)
    print("NGO OpsBot — Environment Variable Check")
    print("=" * 60)

    for var in present:
        # Mask the actual value; show only that it is set
        raw = os.environ[var]
        masked = raw[:4] + "*" * max(0, len(raw) - 8) + raw[-4:] if len(raw) > 8 else "***"
        print(f"  [OK]      {var:<30} = {masked}")

    for var in missing:
        print(f"  [MISSING] {var}")

    # Warn about optional vars
    print()
    for var in OPTIONAL_VARS:
        value = os.environ.get(var, "")
        if not value or value.strip() == "":
            print(f"  [WARN]    {var} is not set (optional but recommended)")

    print("=" * 60)

    if missing:
        print(f"\nFAILED: {len(missing)} required variable(s) are missing:")
        for var in missing:
            print(f"  - {var}")
        print(
            "\nSet these in your Railway project dashboard:"
            "\n  https://railway.app/project/<your-project>/settings/variables"
        )
        sys.exit(1)
    else:
        print(f"\nPASSED: All {len(REQUIRED_VARS)} required variables are set.")
        sys.exit(0)


if __name__ == "__main__":
    main()
