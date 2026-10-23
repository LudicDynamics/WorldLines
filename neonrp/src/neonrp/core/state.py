"""UI state persistence for NeonRP.

Provides load/save operations for UI-specific state (like auto_apply toggle).
State is stored in .neonrp/state.json.

M6.5-T3: auto_apply Persistence
"""

import json
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_neonrp_dir
from neonrp.core.storage import atomic_write_json


DEFAULT_UI_STATE: dict[str, Any] = {"auto_apply": False}


def get_state_path(root: Path) -> Path:
    """Get path to UI state file.

    Args:
        root: Project root directory

    Returns:
        Path to state.json
    """
    return get_neonrp_dir(root) / "state.json"


def load_ui_state(root: Path) -> dict[str, Any]:
    """Load UI state from .neonrp/state.json.

    Args:
        root: Project root directory

    Returns:
        State dict (with defaults if file doesn't exist or is corrupted)
    """
    state_path = get_state_path(root)
    if not state_path.exists():
        return DEFAULT_UI_STATE.copy()

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        # Merge with defaults to ensure all keys exist
        result = DEFAULT_UI_STATE.copy()
        result.update(data)
        return result
    except (json.JSONDecodeError, IOError):
        return DEFAULT_UI_STATE.copy()


def save_ui_state(root: Path, state: dict[str, Any]) -> None:
    """Save UI state to .neonrp/state.json.

    Args:
        root: Project root directory
        state: State dict to save
    """
    state_path = get_state_path(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(state_path, state)


def get_auto_apply(root: Path) -> bool:
    """Get auto_apply setting from state.

    Args:
        root: Project root directory

    Returns:
        Current auto_apply setting
    """
    return bool(load_ui_state(root).get("auto_apply", False))


def set_auto_apply(root: Path, value: bool) -> None:
    """Set auto_apply setting in state.

    Args:
        root: Project root directory
        value: New auto_apply value
    """
    state = load_ui_state(root)
    state["auto_apply"] = value
    save_ui_state(root, state)
