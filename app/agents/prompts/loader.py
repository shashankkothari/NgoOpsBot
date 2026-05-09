"""
Layer 2 + 3 prompt assembly with Redis caching.

Layers 2 and 3 are derived from the NGO database record and change rarely
(admin edits), so we cache the assembled string in Redis for 10 minutes.
Layer 1 (platform base) is prepended at assembly time and is NOT cached
separately — it's cheap to format and must always be fresh.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.agents.prompts.platform_base import get_platform_base
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.models.ngo import NGO, NGOSettings

logger = get_logger(__name__)

# Ten-minute TTL matches the admin editing cadence; long enough to absorb
# traffic bursts, short enough that prompt updates propagate quickly.
_CACHE_TTL_SECONDS = 600


async def build_system_prompt(
    agent_name: str,
    ngo: "NGO",
    ngo_settings: list["NGOSettings"],
    redis_client,
) -> str:
    """
    Assemble the 3-layer system prompt for an agent turn.

    Returns the fully assembled system prompt string.  Layers 2+3 are
    served from Redis when available; Layer 1 is always rendered fresh.
    """
    cache_key = f"prompt:{ngo.slug}:{agent_name}"

    # -- Redis cache lookup (layers 2+3 only) --
    cached = await redis_client.get(cache_key)
    if cached:
        logger.debug("prompt_cache_hit", ngo_slug=ngo.slug, agent_name=agent_name)
        # Layer 1 is prepended after cache retrieval so the platform base
        # is never stale even if the cached entry was written by an older
        # deploy that had a different platform base.
        layer1 = get_platform_base(ngo.name)
        layers_2_3 = cached if isinstance(cached, str) else cached.decode()
        return f"{layer1}\n\n{layers_2_3}"

    logger.debug("prompt_cache_miss", ngo_slug=ngo.slug, agent_name=agent_name)

    # -- Layer 2: NGO profile --
    google_drive_status = (
        "connected (Google Drive and Sheets are available)"
        if ngo.google_master_sheet_id
        else "not connected"
    )

    active_agent_names = [
        s.agent_name for s in ngo_settings if s.is_enabled
    ]
    active_agents_str = (
        ", ".join(active_agent_names) if active_agent_names else "none"
    )

    layer2 = (
        f"NGO Profile:\n"
        f"- Name: {ngo.name}\n"
        f"- Timezone: {ngo.timezone}\n"
        f"- Primary language: {ngo.language}\n"
        f"- Active agents: {active_agents_str}\n"
        f"- Google Drive / Sheets: {google_drive_status}\n"
        f"- Your assigned agent: {agent_name}"
    )

    # -- Layer 3: agent-specific custom prompt from NGO admin --
    # Find the matching NGOSettings row; custom_prompt may be None.
    agent_setting = next(
        (s for s in ngo_settings if s.agent_name == agent_name), None
    )
    layer3 = ""
    if agent_setting and agent_setting.custom_prompt:
        layer3 = (
            f"Organisation-specific instructions for {agent_name}:\n"
            f"{agent_setting.custom_prompt}"
        )

    layers_2_3 = layer2 if not layer3 else f"{layer2}\n\n{layer3}"

    # -- Cache layers 2+3 --
    await redis_client.set(cache_key, layers_2_3, ex=_CACHE_TTL_SECONDS)

    layer1 = get_platform_base(ngo.name)
    return f"{layer1}\n\n{layers_2_3}"
