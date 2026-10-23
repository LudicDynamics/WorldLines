"""Tests for active_agent state protocol (M12-T4)."""

import json
from pathlib import Path

import pytest

from neonrp.core.active_agent import (
    NARRATOR_AGENT,
    clear_active_agent,
    get_active_agent_id,
    get_narrator_agent_id,
    read_active_agent,
    validate_active_agent,
    write_active_agent,
)
from neonrp.core.validation import load_schema, validate_game_data


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a minimal project structure."""
    (tmp_path / "game" / "meta").mkdir(parents=True)
    (tmp_path / "agents" / "narrator").mkdir(parents=True)
    (tmp_path / "agents" / "town-agent").mkdir(parents=True)
    return tmp_path


# ── read / get ──────────────────────────────────────────────────


def test_read_missing_file(project: Path) -> None:
    """Missing active-agent.json returns None (backward compat)."""
    assert read_active_agent(project) is None


def test_get_default_when_missing(project: Path) -> None:
    """get_active_agent_id returns narrator when file is missing."""
    assert get_active_agent_id(project) == NARRATOR_AGENT


def test_get_default_router_falls_back_to_orchestrator_when_narrator_missing(tmp_path: Path) -> None:
    """orchestrator is accepted as a conventional default router id."""
    orchestrator_dir = tmp_path / "agents" / "orchestrator"
    orchestrator_dir.mkdir(parents=True)
    (orchestrator_dir / "agent.json").write_text(json.dumps({"id": "orchestrator"}), encoding="utf-8")

    assert get_narrator_agent_id(tmp_path) == "orchestrator"
    assert get_active_agent_id(tmp_path) == "orchestrator"


def test_get_default_router_prefers_narrator_when_both_default_names_exist(tmp_path: Path) -> None:
    """narrator wins if both narrator and orchestrator exist."""
    for agent_id in ("narrator", "orchestrator"):
        agent_dir = tmp_path / "agents" / agent_id
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent.json").write_text(json.dumps({"id": agent_id}), encoding="utf-8")

    assert get_narrator_agent_id(tmp_path) == "narrator"
    assert get_active_agent_id(tmp_path) == "narrator"


def test_read_invalid_json(project: Path) -> None:
    """Malformed JSON returns None gracefully."""
    state_path = project / "game" / "meta" / "active-agent.json"
    state_path.write_text("not valid json", encoding="utf-8")
    assert read_active_agent(project) is None


def test_read_non_object_json(project: Path) -> None:
    """JSON array instead of object returns None."""
    state_path = project / "game" / "meta" / "active-agent.json"
    state_path.write_text("[1, 2, 3]", encoding="utf-8")
    assert read_active_agent(project) is None


# ── write / round-trip ──────────────────────────────────────────


def test_write_and_read(project: Path) -> None:
    """Write then read round-trips correctly."""
    write_active_agent(
        project,
        "town-agent",
        reason="player entered town",
        exit_condition="player leaves town",
        updated_by="narrator",
    )
    state = read_active_agent(project)
    assert state is not None
    assert state["active_agent"] == "town-agent"
    assert state["reason"] == "player entered town"
    assert state["exit_condition"] == "player leaves town"
    assert state["updated_by"] == "narrator"
    assert "updated_at" in state

    assert get_active_agent_id(project) == "town-agent"


def test_write_creates_dir(tmp_path: Path) -> None:
    """Write creates parent dirs if they don't exist."""
    # game/meta/ doesn't exist yet
    write_active_agent(tmp_path, "dungeon-agent", reason="test")
    assert get_active_agent_id(tmp_path) == "dungeon-agent"


def test_written_state_is_schema_valid(project: Path) -> None:
    """active-agent state under game/meta must remain a valid entity."""
    write_active_agent(project, "town-agent", reason="player entered town")
    schema = load_schema(project)
    issues, _ = validate_game_data(project, schema)
    assert issues == []


# ── clear ───────────────────────────────────────────────────────


def test_clear_resets_to_narrator(project: Path) -> None:
    """clear_active_agent resets to narrator."""
    write_active_agent(project, "town-agent", reason="in town")
    assert get_active_agent_id(project) == "town-agent"

    clear_active_agent(project, updated_by="town-agent")
    assert get_active_agent_id(project) == NARRATOR_AGENT


# ── validate ────────────────────────────────────────────────────


def test_validate_missing_file(project: Path) -> None:
    """Validate returns no warnings for missing file."""
    assert validate_active_agent(project) == []


def test_validate_valid_narrator(project: Path) -> None:
    """Validate with narrator agent passes."""
    write_active_agent(project, NARRATOR_AGENT, reason="init")
    assert validate_active_agent(project) == []


def test_validate_valid_agent(project: Path) -> None:
    """Validate with existing agent dir passes."""
    write_active_agent(project, "town-agent", reason="in town")
    assert validate_active_agent(project) == []


def test_validate_missing_agent_dir(project: Path) -> None:
    """Validate warns about non-existent agent directory."""
    write_active_agent(project, "nonexistent-agent", reason="test")
    warnings = validate_active_agent(project)
    assert len(warnings) == 1
    assert "nonexistent-agent" in warnings[0]


def test_validate_missing_active_agent_field(project: Path) -> None:
    """Validate warns about missing active_agent field."""
    state_path = project / "game" / "meta" / "active-agent.json"
    state_path.write_text(json.dumps({"reason": "no agent field"}), encoding="utf-8")
    warnings = validate_active_agent(project)
    assert len(warnings) == 1
    assert "missing or invalid" in warnings[0]


def test_get_narrator_agent_id_from_project_config(tmp_path: Path) -> None:
    """Narrator/router id should be resolved from project .neonrp/config.json."""
    (tmp_path / ".neonrp").mkdir(parents=True)
    (tmp_path / ".neonrp" / "config.json").write_text(
        json.dumps({"tui": {"narrator_agent_id": "game-master"}}),
        encoding="utf-8",
    )
    assert get_narrator_agent_id(tmp_path) == "game-master"


def test_get_active_agent_uses_configured_narrator_when_state_missing(tmp_path: Path) -> None:
    """Missing state file should fall back to configured narrator/router id."""
    (tmp_path / ".neonrp").mkdir(parents=True)
    (tmp_path / ".neonrp" / "config.json").write_text(
        json.dumps({"tui": {"narrator_agent_id": "game-master"}}),
        encoding="utf-8",
    )
    assert get_active_agent_id(tmp_path) == "game-master"
