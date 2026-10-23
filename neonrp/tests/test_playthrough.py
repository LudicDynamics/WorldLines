"""Tests for the playthrough manifest parser (schema_version 2).

Spec: docs/M17_COMMIT_VERSIONING_DESIGN.md §2.4, docs/WORLD_SOUL_FOLDERS.md §3.4.
"""

import json
from pathlib import Path

import pytest

from neonrp.core.playthrough import (
    SCHEMA_VERSION,
    Playthrough,
    PlaythroughError,
    SoulRef,
    TeamAgent,
    WorldAgentTeam,
    WorldRef,
    read_playthrough,
    write_playthrough,
)


def _sample() -> Playthrough:
    """A manifest mirroring the §2.4 example, including nested team + souls."""
    return Playthrough(
        schema_version=SCHEMA_VERSION,
        playthrough_id="pt-7741abcd",
        world=WorldRef(
            wid="dark-train",
            instance_id="wi-9f2c",
            version_hash="b54b307b50ef",
            head_commit="c12af3b9e7d2",
        ),
        world_agent_team=WorldAgentTeam(
            seeded_from="game/agents/manifest.json@b54b307b50ef",
            agents=[
                TeamAgent(id="world-agent", role="orchestrator", singleton=True),
                TeamAgent(id="town-agent", role="domain"),
                TeamAgent(id="combat-referee", role="domain"),
                TeamAgent(id="story-narrative", role="domain"),
            ],
        ),
        souls=[
            SoulRef(
                sid="elena",
                instance_id="si-a1",
                version_hash="v-elena",
                head_commit="s9b71e22a4f8",
                role="player",
            ),
            SoulRef(
                sid="conductor",
                instance_id="si-b7",
                version_hash="v-cond",
                head_commit="s44ae0d7b316",
                role="npc",
            ),
        ],
        created_at="2026-05-15T13:00:00Z",
    )


def _write_raw(game_dir: Path, obj: object) -> None:
    target = game_dir / ".neonrp" / "playthrough.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(obj), encoding="utf-8")


def test_round_trip(tmp_path: Path) -> None:
    pt = _sample()
    write_playthrough(tmp_path, pt)
    assert read_playthrough(tmp_path) == pt


def test_nested_dataclass_fidelity(tmp_path: Path) -> None:
    pt = _sample()
    write_playthrough(tmp_path, pt)
    loaded = read_playthrough(tmp_path)
    assert loaded is not None

    # Team agents survive verbatim, including the singleton default expansion.
    assert loaded.world_agent_team.agents == pt.world_agent_team.agents
    assert loaded.world_agent_team.agents[0] == TeamAgent(
        id="world-agent", role="orchestrator", singleton=True
    )
    assert loaded.world_agent_team.agents[1].singleton is False

    # Soul refs survive verbatim.
    assert loaded.souls == pt.souls
    assert loaded.world == pt.world


def test_singleton_defaults_false_when_absent(tmp_path: Path) -> None:
    obj = json.loads(json.dumps(_to_json(_sample())))
    # Strip the optional `singleton` key entirely from a domain agent.
    del obj["world_agent_team"]["agents"][1]["singleton"]
    _write_raw(tmp_path, obj)

    loaded = read_playthrough(tmp_path)
    assert loaded is not None
    assert loaded.world_agent_team.agents[1].singleton is False


def test_absent_file_returns_none(tmp_path: Path) -> None:
    # No .neonrp/playthrough.json at all → legacy single-player, not an error.
    assert read_playthrough(tmp_path) is None


def test_malformed_json_raises(tmp_path: Path) -> None:
    target = tmp_path / ".neonrp" / "playthrough.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{ this is not valid json ", encoding="utf-8")

    with pytest.raises(PlaythroughError, match="malformed JSON"):
        read_playthrough(tmp_path)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    obj = _to_json(_sample())
    del obj["playthrough_id"]
    _write_raw(tmp_path, obj)

    with pytest.raises(PlaythroughError, match="missing required field 'playthrough_id'"):
        read_playthrough(tmp_path)


def test_missing_nested_required_field_raises(tmp_path: Path) -> None:
    obj = _to_json(_sample())
    del obj["world"]["version_hash"]
    _write_raw(tmp_path, obj)

    with pytest.raises(PlaythroughError, match="missing required field 'version_hash' in world"):
        read_playthrough(tmp_path)


def test_missing_soul_field_raises(tmp_path: Path) -> None:
    obj = _to_json(_sample())
    del obj["souls"][1]["role"]
    _write_raw(tmp_path, obj)

    with pytest.raises(PlaythroughError, match="missing required field 'role' in souls\\[1\\]"):
        read_playthrough(tmp_path)


def test_wrong_schema_version_raises_naming_both(tmp_path: Path) -> None:
    obj = _to_json(_sample())
    obj["schema_version"] = 1
    _write_raw(tmp_path, obj)

    with pytest.raises(PlaythroughError) as exc:
        read_playthrough(tmp_path)
    msg = str(exc.value)
    # Both the found and expected versions must be named (no silent migration).
    assert "1" in msg
    assert str(SCHEMA_VERSION) in msg
    assert "mismatch" in msg


def test_top_level_not_object_raises(tmp_path: Path) -> None:
    target = tmp_path / ".neonrp" / "playthrough.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(PlaythroughError, match="top-level value must be an object"):
        read_playthrough(tmp_path)


def test_integrations_round_trip_and_survive_head_advance(tmp_path: Path) -> None:
    """M22: the integration routing table round-trips through the manifest and
    is preserved by the M17 land path's playthrough rewrite (it silently
    dropped any field not passed through reconstruction)."""
    from dataclasses import replace

    from neonrp.core.commit_subsystem import _advance_manifest_heads

    integrations = (
        {"world_agent": "world-agent", "location": "north-gate", "souls": ["si-a1"]},
        {"world_agent": "loc:inn", "location": "inn", "souls": ["si-b7"]},
    )
    pt = replace(_sample(), integrations=integrations)
    write_playthrough(tmp_path, pt)
    loaded = read_playthrough(tmp_path)
    assert loaded is not None
    assert loaded.integrations == integrations

    _advance_manifest_heads(tmp_path, loaded, "w-new-head", {})
    reread = read_playthrough(tmp_path)
    assert reread is not None
    assert reread.integrations == integrations
    assert reread.world.head_commit == "w-new-head"


def _to_json(pt: Playthrough) -> dict:
    """Round-trip helper: serialize then reload as a mutable plain dict so
    tests can corrupt individual fields without touching production code."""
    from neonrp.core.playthrough import _to_dict

    return json.loads(json.dumps(_to_dict(pt)))
