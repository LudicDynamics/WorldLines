"""Active-agent state protocol for multi-agent delegation (M12-T4).

Provides persistent state tracking for which sub-agent is currently
handling player interactions. This prevents the narrator from
"forgetting" to delegate after a sub-agent returns.

State file: ``<data_dir>/<router.state_file>``
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neonrp.core.runtime_contract import load_runtime_contract, resolve_router_agent_id

logger = logging.getLogger(__name__)

# Sentinel for "no active sub-agent" (narrator is in control)
NARRATOR_AGENT = "narrator"

# Schema keys
_KEY_ID = "id"
_KEY_KIND = "kind"
_KEY_NAME = "name"
_KEY_ACTIVE = "active_agent"
_KEY_REASON = "reason"
_KEY_EXIT = "exit_condition"
_KEY_UPDATED_AT = "updated_at"
_KEY_UPDATED_BY = "updated_by"


def _state_path(root: Path) -> Path:
    """Return the canonical path for the active-agent state file."""
    contract = load_runtime_contract(root)
    return root / contract.active_agent_relpath


def get_narrator_agent_id(root: Path) -> str:
    """Return configured narrator/router agent id for this project."""
    try:
        return resolve_router_agent_id(root)
    except Exception:
        return NARRATOR_AGENT


def read_active_agent(root: Path) -> dict[str, Any] | None:
    """Read the current active-agent state.

    Returns:
        Parsed state dict, or ``None`` if the file is missing or invalid.
        Missing file is a normal condition (old projects without this feature).
    """
    path = _state_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("active-agent.json is not a JSON object, ignoring")
            return None
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read active-agent.json: %s", exc)
        return None


def get_active_agent_id(root: Path) -> str:
    """Return the currently active agent ID, defaulting to ``narrator``.

    This is the primary entry point for the conversation loop to
    check whether a sub-agent should be auto-delegated.
    """
    narrator_agent_id = get_narrator_agent_id(root)
    state = read_active_agent(root)
    if state is None:
        return narrator_agent_id
    active = state.get(_KEY_ACTIVE)
    if isinstance(active, str) and active.strip():
        return active
    return narrator_agent_id


def write_active_agent(
    root: Path,
    agent_id: str,
    *,
    reason: str = "",
    exit_condition: str = "",
    updated_by: str = "",
) -> Path:
    """Write or update the active-agent state file.

    Args:
        root: Project root directory.
        agent_id: The agent that should be active (e.g. ``"town-agent"``).
        reason: Human-readable reason for the state change.
        exit_condition: Condition under which the active agent should yield.
        updated_by: Which agent triggered the state change.

    Returns:
        Path to the written state file.
    """
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        _KEY_ID: "active-agent",
        _KEY_KIND: "meta",
        _KEY_NAME: "Active Agent State",
        _KEY_ACTIVE: agent_id,
        _KEY_REASON: reason,
        _KEY_EXIT: exit_condition,
        _KEY_UPDATED_AT: datetime.now(timezone.utc).isoformat(),
        _KEY_UPDATED_BY: updated_by or agent_id,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Active agent set to '%s' (reason: %s)", agent_id, reason)
    return path


def clear_active_agent(root: Path, *, updated_by: str = "narrator") -> Path:
    """Reset active agent to narrator (no sub-agent lock).

    This should be called when the exit condition is met
    (e.g. player leaves town).
    """
    narrator_agent_id = get_narrator_agent_id(root)
    return write_active_agent(
        root,
        narrator_agent_id,
        reason="exit condition met / control returned to narrator",
        exit_condition="",
        updated_by=updated_by,
    )


def validate_active_agent(root: Path) -> list[str]:
    """Validate the active-agent state file.

    Returns:
        List of warning messages. Empty list means valid.
    """
    narrator_agent_id = get_narrator_agent_id(root)
    warnings: list[str] = []
    state = read_active_agent(root)
    if state is None:
        return warnings  # Missing file is valid (backward compat)

    agent_id = state.get(_KEY_ACTIVE)
    if not agent_id or not isinstance(agent_id, str):
        warnings.append("active-agent.json: missing or invalid 'active_agent' field")
        return warnings

    # Check the agent directory exists
    agent_dir = root / "agents" / agent_id
    if agent_id != narrator_agent_id and not agent_dir.is_dir():
        warnings.append(
            f"active-agent.json: active_agent '{agent_id}' has no corresponding "
            f"agent directory at {agent_dir}"
        )

    return warnings
