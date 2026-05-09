"""Admin CRUD for NGO tenants.

All routes require ADMIN_API_KEY (enforced upstream by NGOAuthMiddleware).
Sensitive fields (telegram_bot_token, anthropic_api_key) are encrypted before
persistence and decrypted only in the NGOAdminRead response schema — never
leak plaintext into regular NGORead objects or logs.

Every mutation writes an AuditLog row so the admin has a complete audit trail.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.metrics import active_ngos
from app.core.security import decrypt_field, encrypt_field
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.ngo import NGO, NGOSettings
from app.models.staff import Staff
from app.schemas.ngo import (
    NGOAdminRead,
    NGOCreate,
    NGORead,
    NGOSettingRead,
    NGOSettingUpsert,
    NGOStats,
    NGOUpdate,
    NGOWithSettings,
    PaginatedNGOs,
)

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/admin/ngos", tags=["admin-ngos"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Generate a URL-safe slug from an NGO name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:100]


async def _get_ngo_or_404(ngo_id: uuid.UUID, db: AsyncSession) -> NGO:
    result = await db.execute(select(NGO).where(NGO.id == ngo_id))
    ngo = result.scalar_one_or_none()
    if ngo is None:
        raise HTTPException(status_code=404, detail="NGO not found")
    return ngo


async def _write_audit(
    db: AsyncSession,
    action: str,
    ngo_id: Optional[uuid.UUID],
    details: dict[str, Any],
    request: Request,
) -> None:
    entry = AuditLog(
        ngo_id=ngo_id,
        action=action,
        details=details,
        ip_address=request.client.host if request.client else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    # Flush within the same transaction — the caller's session.commit() persists it


async def _register_telegram_webhook(bot_token: str, webhook_url: str) -> None:
    """Call Telegram setWebhook API. Raises on HTTP or API error."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={"url": webhook_url},
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("ok"):
            raise ValueError(f"Telegram setWebhook failed: {body.get('description')}")


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=NGOAdminRead, status_code=201)
async def create_ngo(
    payload: NGOCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> NGOAdminRead:
    slug = _slugify(payload.name)

    # Ensure slug uniqueness before inserting
    existing = await db.execute(select(NGO).where(NGO.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"NGO slug '{slug}' already exists")

    settings_obj = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    # secrets.token_hex(32) = 256 bits of CSPRNG entropy vs uuid4's ~122 bits
    webhook_secret = secrets.token_hex(32)

    encrypted_token = encrypt_field(payload.telegram_bot_token)
    # Fall back to platform key if not supplied — keeps the column non-null
    raw_key = payload.anthropic_api_key or settings_obj.ANTHROPIC_API_KEY
    encrypted_key = encrypt_field(raw_key) if raw_key else encrypt_field("platform")

    ngo = NGO(
        name=payload.name,
        slug=slug,
        telegram_bot_token=encrypted_token,
        anthropic_api_key=encrypted_key,
        webhook_secret=webhook_secret,
        timezone=payload.timezone,
        language=payload.language,
    )
    db.add(ngo)
    await db.flush()  # get ngo.id before the Telegram call

    # Register webhook after we have the NGO id and secret
    webhook_url = (
        f"{settings_obj.APP_BASE_URL}/api/v1/webhook/{ngo.slug}/{webhook_secret}"
    )
    try:
        await _register_telegram_webhook(payload.telegram_bot_token, webhook_url)
        log.info("telegram_webhook_set", ngo_id=str(ngo.id), slug=ngo.slug)
    except Exception as exc:
        log.error("telegram_webhook_failed", ngo_id=str(ngo.id), error=str(exc))
        # Don't abort the NGO creation — the admin can call /refresh-webhook later

    await _write_audit(db, "ngo_created", ngo.id, {"slug": slug, "name": payload.name}, request)
    active_ngos.inc()

    log.info("ngo_created", ngo_id=str(ngo.id), slug=ngo.slug)
    return NGOAdminRead.model_validate(ngo)


@router.get("", response_model=PaginatedNGOs)
async def list_ngos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=100),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedNGOs:
    query = select(NGO)
    if search:
        query = query.where(NGO.name.ilike(f"%{search}%"))
    if is_active is not None:
        query = query.where(NGO.is_active == is_active)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(NGO.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    ngos = result.scalars().all()

    return PaginatedNGOs(
        items=[NGORead.model_validate(n) for n in ngos],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{ngo_id}", response_model=NGOWithSettings)
async def get_ngo(
    ngo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> NGOWithSettings:
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(NGO).options(selectinload(NGO.settings)).where(NGO.id == ngo_id)
    )
    ngo = result.scalar_one_or_none()
    if ngo is None:
        raise HTTPException(status_code=404, detail="NGO not found")

    data = NGOWithSettings.model_validate(ngo)
    data.settings = [NGOSettingRead.model_validate(s) for s in ngo.settings]
    return data


@router.patch("/{ngo_id}", response_model=NGORead)
async def update_ngo(
    ngo_id: uuid.UUID,
    payload: NGOUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> NGORead:
    ngo = await _get_ngo_or_404(ngo_id, db)

    changed: dict[str, Any] = {}
    if payload.name is not None:
        ngo.name = payload.name
        changed["name"] = payload.name
    if payload.telegram_bot_token is not None:
        ngo.telegram_bot_token = encrypt_field(payload.telegram_bot_token)
        changed["telegram_bot_token"] = "***"
    if payload.anthropic_api_key is not None:
        ngo.anthropic_api_key = encrypt_field(payload.anthropic_api_key)
        changed["anthropic_api_key"] = "***"
    if payload.telegram_group_chat_id is not None:
        ngo.telegram_group_chat_id = payload.telegram_group_chat_id
        changed["telegram_group_chat_id"] = payload.telegram_group_chat_id
    if payload.google_drive_folder_id is not None:
        ngo.google_drive_folder_id = payload.google_drive_folder_id
        changed["google_drive_folder_id"] = payload.google_drive_folder_id
    if payload.google_master_sheet_id is not None:
        ngo.google_master_sheet_id = payload.google_master_sheet_id
        changed["google_master_sheet_id"] = payload.google_master_sheet_id
    if payload.timezone is not None:
        ngo.timezone = payload.timezone
        changed["timezone"] = payload.timezone
    if payload.language is not None:
        ngo.language = payload.language
        changed["language"] = payload.language
    if payload.is_active is not None:
        ngo.is_active = payload.is_active
        changed["is_active"] = payload.is_active

    await _write_audit(db, "ngo_updated", ngo.id, changed, request)
    log.info("ngo_updated", ngo_id=str(ngo.id), changed_fields=list(changed.keys()))
    return NGORead.model_validate(ngo)


@router.delete("/{ngo_id}", status_code=204)
async def delete_ngo(
    ngo_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete: sets is_active=False. Hard deletes require a DB migration."""
    ngo = await _get_ngo_or_404(ngo_id, db)
    ngo.is_active = False
    await _write_audit(db, "ngo_deactivated", ngo.id, {"slug": ngo.slug}, request)
    active_ngos.dec()
    log.info("ngo_deactivated", ngo_id=str(ngo.id), slug=ngo.slug)


# ---------------------------------------------------------------------------
# Settings endpoint
# ---------------------------------------------------------------------------

@router.post("/{ngo_id}/settings", response_model=NGOSettingRead, status_code=200)
async def upsert_ngo_settings(
    ngo_id: uuid.UUID,
    payload: NGOSettingUpsert,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> NGOSettingRead:
    """Create or update per-agent settings for an NGO."""
    await _get_ngo_or_404(ngo_id, db)

    result = await db.execute(
        select(NGOSettings).where(
            NGOSettings.ngo_id == ngo_id,
            NGOSettings.agent_name == payload.agent_name,
        )
    )
    setting = result.scalar_one_or_none()

    if setting is None:
        setting = NGOSettings(
            ngo_id=ngo_id,
            agent_name=payload.agent_name,
            custom_prompt=payload.custom_prompt,
            is_enabled=payload.is_enabled,
        )
        db.add(setting)
    else:
        setting.custom_prompt = payload.custom_prompt
        setting.is_enabled = payload.is_enabled

    await _write_audit(
        db,
        "ngo_settings_upserted",
        ngo_id,
        {"agent_name": payload.agent_name, "is_enabled": payload.is_enabled},
        request,
    )
    await db.flush()
    log.info(
        "ngo_settings_upserted",
        ngo_id=str(ngo_id),
        agent_name=payload.agent_name,
    )
    return NGOSettingRead.model_validate(setting)


# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------

@router.get("/{ngo_id}/stats", response_model=NGOStats)
async def get_ngo_stats(
    ngo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> NGOStats:
    """Aggregate DB stats for a single NGO."""
    ngo = await _get_ngo_or_404(ngo_id, db)

    msg_count_result = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.ngo_id == ngo_id)
    )
    total_messages = msg_count_result.scalar_one() or 0

    token_result = await db.execute(
        select(func.coalesce(func.sum(Conversation.tokens_used), 0)).where(
            Conversation.ngo_id == ngo_id
        )
    )
    total_tokens = int(token_result.scalar_one() or 0)

    staff_result = await db.execute(
        select(func.count(Staff.id)).where(
            Staff.ngo_id == ngo_id, Staff.is_active == True  # noqa: E712
        )
    )
    active_staff_count = staff_result.scalar_one() or 0

    from app.models.reminder import Reminder
    reminder_result = await db.execute(
        select(func.count()).where(
            Reminder.ngo_id == ngo_id, Reminder.is_active == True  # noqa: E712
        )
    )
    reminder_count = reminder_result.scalar_one() or 0

    last_activity_result = await db.execute(
        select(func.max(Conversation.created_at)).where(Conversation.ngo_id == ngo_id)
    )
    last_activity_at = last_activity_result.scalar_one()

    return NGOStats(
        ngo_id=ngo.id,
        ngo_slug=ngo.slug,
        total_messages=total_messages,
        total_tokens=total_tokens,
        active_staff_count=active_staff_count,
        reminder_count=reminder_count,
        last_activity_at=last_activity_at,
    )


# ---------------------------------------------------------------------------
# Webhook refresh
# ---------------------------------------------------------------------------

@router.post("/{ngo_id}/refresh-webhook", status_code=200)
async def refresh_webhook(
    ngo_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Re-register the Telegram webhook, rotating the secret in the URL."""
    ngo = await _get_ngo_or_404(ngo_id, db)

    settings_obj = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
    new_secret = secrets.token_hex(32)
    ngo.webhook_secret = new_secret

    webhook_url = f"{settings_obj.APP_BASE_URL}/api/v1/webhook/{ngo.slug}/{new_secret}"
    try:
        plain_token = decrypt_field(ngo.telegram_bot_token)
        await _register_telegram_webhook(plain_token, webhook_url)
    except Exception as exc:
        log.error("refresh_webhook_failed", ngo_id=str(ngo_id), error=str(exc))
        raise HTTPException(status_code=502, detail=f"Telegram API error: {exc}") from exc

    await _write_audit(db, "webhook_refreshed", ngo.id, {"new_secret": "***"}, request)
    log.info("webhook_refreshed", ngo_id=str(ngo.id), slug=ngo.slug)
    return {"status": "ok", "webhook_url": webhook_url}
