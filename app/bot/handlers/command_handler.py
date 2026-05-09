"""
Slash command handler for group chat commands.

Commands are the only interaction that does not require @mention because
Telegram delivers /commands to the bot regardless of mention status when
the bot is an admin in the group.
"""

from __future__ import annotations

from typing import Optional

import structlog

from app.bot.ngo_bot_registry import bot_registry
from app.core.logging import get_logger
from app.models.ngo import NGO, NGOSettings
from app.models.staff import Staff

# Import here only for type annotation; actual agent list is derived from NGOSettings
from app.bot.update_parser import ParsedUpdate

log: structlog.stdlib.BoundLogger = get_logger(__name__)

_AGENT_DESCRIPTIONS: dict[str, str] = {
    "fundraising": "Donor management, grant tracking, campaigns",
    "finance": "Budgets, expenses, invoices, financial reporting",
    "marketing": "Social media posts, content planning, outreach",
    "hr": "Staff & volunteer management, leave, payroll",
    "compliance": "Legal filings, audits, FCRA/CSR compliance",
}

_ADMIN_DASHBOARD_PATH = "/dashboard"


async def handle_command(
    parsed: ParsedUpdate,
    ngo: NGO,
    staff: Optional[Staff],
    ngo_settings: list[NGOSettings],
    db: object,  # AsyncSession — typed as object to avoid circular import at module level
) -> None:
    """
    Route slash commands to their handlers.

    Unknown commands are silently ignored — responding to every unknown command
    would spam the group chat and leak which commands the bot does or doesn't support.
    """
    ngo_slug = ngo.slug
    chat_id = parsed.chat_id
    command = parsed.command

    bound_log = log.bind(
        ngo_slug=ngo_slug,
        command=command,
        staff_id=str(staff.id) if staff else None,
        telegram_user_id=parsed.telegram_user_id,
    )

    if command == "help":
        await _handle_help(parsed, ngo, staff, ngo_settings, bound_log)

    elif command == "status":
        await _handle_status(parsed, ngo, ngo_settings, bound_log)

    elif command == "myaccess":
        await _handle_myaccess(parsed, ngo, staff, ngo_settings, bound_log)

    elif command == "settings":
        await _handle_settings(parsed, ngo, staff, bound_log)

    else:
        # Silently ignore — unknown commands must never trigger a response
        bound_log.debug("command_ignored_unknown")


async def _handle_help(
    parsed: ParsedUpdate,
    ngo: NGO,
    staff: Optional[Staff],
    ngo_settings: list[NGOSettings],
    bound_log: structlog.stdlib.BoundLogger,
) -> None:
    """List agents this staff member can use."""
    if staff is None:
        await bot_registry.send_message(
            ngo.slug,
            parsed.chat_id,
            "You are not registered in this NGO's system. Please ask your admin to add you.",
            parse_mode="HTML",
        )
        return

    enabled_agents = {s.agent_name for s in ngo_settings if s.is_enabled}
    # Empty allowed_agents means all-access (admins typically)
    permitted = set(staff.allowed_agents) if staff.allowed_agents else enabled_agents

    accessible = enabled_agents & permitted
    if not accessible:
        await bot_registry.send_message(
            ngo.slug,
            parsed.chat_id,
            "You don't currently have access to any agents. Contact your admin.",
        )
        return

    lines = ["<b>Available Agents</b>\n"]
    for agent in sorted(accessible):
        desc = _AGENT_DESCRIPTIONS.get(agent, "")
        lines.append(f"• <b>{agent.capitalize()}</b> — {desc}")
    lines.append(
        "\n<i>Mention me and describe your task, e.g.:</i>\n"
        "<code>@bot Help me write a donor update email</code>"
    )

    await bot_registry.send_message(ngo.slug, parsed.chat_id, "\n".join(lines), parse_mode="HTML")
    bound_log.info("command_help_sent", accessible_agents=list(accessible))


async def _handle_status(
    parsed: ParsedUpdate,
    ngo: NGO,
    ngo_settings: list[NGOSettings],
    bound_log: structlog.stdlib.BoundLogger,
) -> None:
    """Show NGO integration status — useful for admins debugging config."""
    google_connected = bool(ngo.google_refresh_token)
    drive_linked = bool(ngo.google_drive_folder_id)
    enabled_agents = [s.agent_name for s in ngo_settings if s.is_enabled]
    group_registered = bool(ngo.telegram_group_chat_id)

    status_lines = [
        f"<b>NGO OpsBot Status — {ngo.name}</b>\n",
        f"{'✅' if google_connected else '❌'} Google account connected",
        f"{'✅' if drive_linked else '❌'} Google Drive linked",
        f"{'✅' if group_registered else '❌'} Telegram group registered",
        f"\n<b>Active agents:</b> {', '.join(enabled_agents) if enabled_agents else 'none'}",
    ]

    await bot_registry.send_message(
        ngo.slug, parsed.chat_id, "\n".join(status_lines), parse_mode="HTML"
    )
    bound_log.info("command_status_sent")


async def _handle_myaccess(
    parsed: ParsedUpdate,
    ngo: NGO,
    staff: Optional[Staff],
    ngo_settings: list[NGOSettings],
    bound_log: structlog.stdlib.BoundLogger,
) -> None:
    """Tell a staff member exactly which agents they can invoke."""
    if staff is None:
        await bot_registry.send_message(
            ngo.slug,
            parsed.chat_id,
            "You are not registered. Ask your admin to add you.",
        )
        return

    enabled_agents = {s.agent_name for s in ngo_settings if s.is_enabled}
    # Empty allowed_agents means all-access
    permitted = set(staff.allowed_agents) if staff.allowed_agents else enabled_agents
    accessible = sorted(enabled_agents & permitted)

    name = staff.name or "there"
    if accessible:
        agent_list = ", ".join(a.capitalize() for a in accessible)
        msg = f"Hi {name}! You have access to: <b>{agent_list}</b>."
    else:
        msg = f"Hi {name}. You don't have access to any agents right now."

    await bot_registry.send_message(ngo.slug, parsed.chat_id, msg, parse_mode="HTML")
    bound_log.info("command_myaccess_sent", accessible=accessible)


async def _handle_settings(
    parsed: ParsedUpdate,
    ngo: NGO,
    staff: Optional[Staff],
    bound_log: structlog.stdlib.BoundLogger,
) -> None:
    """
    Settings command is admin-only.

    Sending a clickable link instead of inline config prevents accidental
    misconfiguration inside Telegram where there is no undo.
    """
    if staff is None or staff.role != "admin":
        await bot_registry.send_message(
            ngo.slug,
            parsed.chat_id,
            "⚠️ The /settings command is only available to admins.",
        )
        bound_log.info(
            "command_settings_denied",
            role=staff.role if staff else "unknown",
        )
        return

    from app.core.config import get_settings

    base_url = get_settings().APP_BASE_URL
    dashboard_url = f"{base_url}{_ADMIN_DASHBOARD_PATH}"
    msg = (
        f"<b>NGO Settings</b>\n"
        f"Manage agents, staff, and integrations on the web dashboard:\n"
        f'<a href="{dashboard_url}">{dashboard_url}</a>'
    )
    await bot_registry.send_message(ngo.slug, parsed.chat_id, msg, parse_mode="HTML")
    bound_log.info("command_settings_sent")
