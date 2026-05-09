"""
Agent registry and dispatcher.

`AGENT_REGISTRY` is populated at import time via the `@register_agent`
decorator — importing any agent module is sufficient to register it.
`dispatch` is the single entry-point called by the Telegram message handler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.base import AgentResponse, BaseAgent
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.ngo import NGO, NGOSettings
    from app.models.staff import Staff

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Maps agent_name → agent class; populated by @register_agent at import time.
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}


def register_agent(cls: type[BaseAgent]) -> type[BaseAgent]:
    """Class decorator that auto-registers an agent in AGENT_REGISTRY."""
    if not cls.agent_name:
        raise ValueError(f"{cls.__name__} must define agent_name")
    AGENT_REGISTRY[cls.agent_name] = cls
    logger.debug("agent_registered", agent_name=cls.agent_name)
    return cls


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class AgentNotFoundError(KeyError):
    """Raised when the requested agent_name is not in the registry."""


class AgentNotEnabledError(PermissionError):
    """Raised when the agent exists but is disabled for this NGO."""


class AgentNotPermittedError(PermissionError):
    """Raised when the staff member's allowed_agents list excludes this agent."""


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

async def dispatch(
    agent_name: str,
    user_message: str,
    ngo: "NGO",
    staff: "Staff",
    conversation_history: list[dict],
    ngo_settings: list["NGOSettings"],
    db: "AsyncSession",
    redis_client,
) -> AgentResponse:
    """
    Route a user message to the correct specialist agent.

    Checks performed in order (fail-fast):
      1. Agent registered in AGENT_REGISTRY
      2. Agent enabled for this NGO (NGOSettings.is_enabled)
      3. Staff member has the agent in their allowed_agents list

    Raises one of: AgentNotFoundError, AgentNotEnabledError,
    AgentNotPermittedError, or any exception from the agent itself.
    """
    # -- 1. Registry lookup --
    agent_cls = AGENT_REGISTRY.get(agent_name)
    if agent_cls is None:
        # Import all agent modules to ensure registration has occurred.
        # This handles cases where the dispatcher is called before the agent
        # modules have been imported (e.g. in tests or CLI scripts).
        _ensure_agents_imported()
        agent_cls = AGENT_REGISTRY.get(agent_name)

    if agent_cls is None:
        raise AgentNotFoundError(
            f"Agent '{agent_name}' is not registered. "
            f"Available agents: {sorted(AGENT_REGISTRY)}"
        )

    # -- 2. NGO-level enablement check --
    # "general" has no NGOSettings row — it's a system agent, always enabled.
    if agent_name != "general":
        setting = next(
            (s for s in ngo_settings if s.agent_name == agent_name), None
        )
        if setting is None or not setting.is_enabled:
            raise AgentNotEnabledError(
                f"Agent '{agent_name}' is not enabled for NGO '{ngo.slug}'"
            )

    # -- 3. Staff permission check --
    # "general" is a system-level orchestrator — always permitted.
    # For specialist agents: allowed_agents=[] (or None) means all-access.
    if agent_name != "general" and staff.allowed_agents and agent_name not in staff.allowed_agents:
        raise AgentNotPermittedError(
            f"Staff member '{staff.name}' is not permitted to use agent '{agent_name}'"
        )

    logger.info(
        "dispatching_agent",
        agent_name=agent_name,
        ngo_slug=ngo.slug,
        staff_id=str(staff.id),
    )

    agent_instance = agent_cls()
    return await agent_instance.invoke(
        user_message=user_message,
        ngo=ngo,
        staff=staff,
        conversation_history=conversation_history,
        ngo_settings=ngo_settings,
        db=db,
        redis_client=redis_client,
    )


def _ensure_agents_imported() -> None:
    """Import all agent modules so their @register_agent decorators fire."""
    import importlib

    _agent_modules = [
        "app.agents.fundraising",
        "app.agents.finance",
        "app.agents.marketing",
        "app.agents.hr",
        "app.agents.compliance",
        "app.agents.general",
    ]
    for module_path in _agent_modules:
        try:
            importlib.import_module(module_path)
        except ImportError:
            pass  # module may not exist yet during early development
