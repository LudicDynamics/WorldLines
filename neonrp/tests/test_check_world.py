"""Tests for `check_world` — the world playability health-check behind
`neonrp validate`.

Fixture worlds are built on disk per test: a minimal playable multi-agent
bundle, broken variants (bad JSON, dangling cast, missing soul pieces,
dangling location, broken playthrough), a valid orchestrator world, and a
bare build project. Severity must mirror the runtime: blockers are things
that make the world play WRONG (silent flavor downgrade, lost content,
hollow cast); self-healing or degraded-but-playable states are warnings.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.validation import check_world


# ── fixture builders ─────────────────────────────────────────────


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _entity(kind: str, eid: str, name: str) -> dict:
    return {"id": eid, "kind": kind, "name": name}


def _build_multi_agent_world(root: Path) -> Path:
    """Minimal PLAYABLE multi-agent world: playthrough casting one complete
    soul, a town map, router agent + contract, game-start, one entity."""
    root.mkdir(parents=True, exist_ok=True)

    # game/ content
    _write_json(root / "game" / "npc" / "rowan.json", _entity("npc", "rowan", "Rowan"))
    _write_json(
        root / "game" / "meta" / "game-start.json",
        {**_entity("meta", "game-start", "Game Start"), "agent_routing": {"entry_agent": "world-agent"}},
    )
    _write_json(
        root / "game" / "towns" / "T001" / "town_map.json",
        {
            **_entity("towns", "town_map", "Riverside"),
            "town_id": "T001",
            "nodes": [
                {"id": "inn", "name": "河灯旅店", "links": ["market"]},
                {"id": "market", "name": "集市", "links": ["inn"]},
            ],
        },
    )

    # router agent + contract
    _write_json(root / "agents" / "world-agent" / "agent.json", {"id": "world-agent"})
    _write_json(
        root / ".neonrp" / "runtime_contract.json",
        {"router": {"agent_id": "world-agent", "execution_mode": "multi-agent"}},
    )

    # one complete soul bundle
    soul = root / "souls" / "elena-sielena0001"
    _write_json(soul / "soul.json", {"sid": "elena", "name": "Elena", "name_local": "艾琳娜"})
    (soul / "soul.md").write_text("# Elena — charter\n", encoding="utf-8")
    _write_json(soul / "persona" / "core_traits.json", {"sid": "elena", "personality_type": "warm"})
    _write_json(soul / "agents" / "manifest.json", {"agents": [{"id": "psyche", "role": "core"}]})
    _write_json(soul / "run_state.json", {"location": "T001/inn"})

    # playthrough binding
    _write_json(
        root / ".neonrp" / "playthrough.json",
        {
            "schema_version": 2,
            "playthrough_id": "pt-test",
            "world": {"wid": "riverside", "instance_id": "wi01", "version_hash": "v1", "head_commit": ""},
            "world_agent_team": {
                "seeded_from": "game/agents/manifest.json@v1",
                "agents": [{"id": "world-agent", "role": "orchestrator", "singleton": True}],
            },
            "souls": [
                {"sid": "elena", "instance_id": "sielena0001", "version_hash": "sv1", "head_commit": "", "role": "npc"}
            ],
            "active_souls": ["sielena0001"],
            "created_at": "2026-07-01T00:00:00Z",
        },
    )
    return root


def _build_orch_world(root: Path) -> Path:
    """Valid orchestrator world: agents + contract + game/, NO playthrough."""
    root.mkdir(parents=True, exist_ok=True)
    _write_json(root / "game" / "npc" / "mira.json", _entity("npc", "mira", "Mira"))
    _write_json(
        root / "game" / "meta" / "game-start.json",
        {**_entity("meta", "game-start", "Game Start"), "agent_routing": {"entry_agent": "narrator"}},
    )
    _write_json(root / "agents" / "narrator" / "agent.json", {"id": "narrator"})
    _write_json(
        root / ".neonrp" / "runtime_contract.json",
        {"router": {"agent_id": "narrator", "execution_mode": "orchestrator"}},
    )
    return root


def _codes(issues) -> set:
    return {i.code for i in issues}


# ── flavor detection + happy paths ───────────────────────────────


def test_playable_multi_agent_world(tmp_path: Path):
    root = _build_multi_agent_world(tmp_path / "world")
    health = check_world(root)
    assert health.playable, [i.to_dict() for i in health.blockers]
    assert health.flavor == "multi-agent"
    assert health.stats["souls"] == 1
    assert health.stats["active_souls"] == 1
    assert health.stats["locations"] == 2  # town_map nodes
    assert health.stats["router"] == "world-agent"
    assert "soul-incomplete" not in _codes(health.warnings)
    assert "location-dangling" not in _codes(health.warnings)


def test_valid_orch_world_no_false_blockers(tmp_path: Path):
    root = _build_orch_world(tmp_path / "orch")
    health = check_world(root)
    assert health.playable, [i.to_dict() for i in health.blockers]
    assert health.flavor == "orchestrator"
    assert health.stats["souls"] == 0
    # No soul/playthrough layer applied to an orch world.
    assert "soul-missing" not in _codes(health.blockers)


def test_bare_build_project_is_not_blocked(tmp_path: Path):
    # A fresh `neonrp init`-style dir must keep exiting 0 (CLI regression).
    health = check_world(tmp_path)
    assert health.playable
    assert health.flavor == "build"


# ── layer 1: JSON integrity (the deepseek quote bug) ─────────────


def test_broken_json_in_game_is_blocker_with_line_col(tmp_path: Path):
    root = _build_multi_agent_world(tmp_path / "world")
    bad = root / "game" / "npc" / "iris.json"
    bad.write_text('{"speech": "她说 "你好" 然后笑了", "id": "iris"}', encoding="utf-8")
    health = check_world(root)
    assert not health.playable
    [issue] = [i for i in health.blockers if i.code == "json-parse"]
    assert issue.file == "game/npc/iris.json"
    assert "line 1" in issue.message and "column" in issue.message


def test_broken_json_in_soul_is_blocker(tmp_path: Path):
    root = _build_multi_agent_world(tmp_path / "world")
    (root / "souls" / "elena-sielena0001" / "soul.json").write_text('{"sid": broken', encoding="utf-8")
    health = check_world(root)
    assert not health.playable
    assert any(
        i.code == "json-parse" and i.file.startswith("souls/") for i in health.blockers
    )


# ── layer 2: playthrough binding ─────────────────────────────────


def test_playthrough_schema_violation_is_blocker(tmp_path: Path):
    root = _build_multi_agent_world(tmp_path / "world")
    pt = json.loads((root / ".neonrp" / "playthrough.json").read_text(encoding="utf-8"))
    del pt["souls"]  # valid JSON, broken schema → silent single-agent downgrade
    _write_json(root / ".neonrp" / "playthrough.json", pt)
    health = check_world(root)
    assert not health.playable
    assert "playthrough-schema" in _codes(health.blockers)


def test_malformed_playthrough_json_reports_once(tmp_path: Path):
    root = _build_multi_agent_world(tmp_path / "world")
    (root / ".neonrp" / "playthrough.json").write_text("{not json", encoding="utf-8")
    health = check_world(root)
    assert not health.playable
    pt_issues = [i for i in health.blockers if i.file == ".neonrp/playthrough.json"]
    assert len(pt_issues) == 1  # layer-1 parse blocker; no duplicate schema blocker
    assert pt_issues[0].code == "json-parse"


# ── layer 4: soul bundles ────────────────────────────────────────


def test_missing_cast_soul_folder_is_blocker(tmp_path: Path):
    import shutil

    root = _build_multi_agent_world(tmp_path / "world")
    shutil.rmtree(root / "souls" / "elena-sielena0001")
    health = check_world(root)
    assert not health.playable
    [issue] = [i for i in health.blockers if i.code == "soul-missing"]
    assert "elena" in issue.message


def test_incomplete_soul_bundle_is_warning_not_blocker(tmp_path: Path):
    root = _build_multi_agent_world(tmp_path / "world")
    (root / "souls" / "elena-sielena0001" / "agents" / "manifest.json").unlink()
    (root / "souls" / "elena-sielena0001" / "soul.md").unlink()
    health = check_world(root)
    assert health.playable  # degrades, doesn't block
    incomplete = [i for i in health.warnings if i.code == "soul-incomplete"]
    assert {i.file for i in incomplete} == {
        "souls/elena-sielena0001/agents/manifest.json",
        "souls/elena-sielena0001/soul.md",
    }


# ── layer 5: location references (conservative) ──────────────────


def test_dangling_soul_location_is_warning(tmp_path: Path):
    root = _build_multi_agent_world(tmp_path / "world")
    _write_json(
        root / "souls" / "elena-sielena0001" / "run_state.json",
        {"location": "河灯旅店"},  # a NAME, not a mapped node id
    )
    health = check_world(root)
    assert health.playable
    [issue] = [i for i in health.warnings if i.code == "location-dangling"]
    assert "河灯旅店" in issue.message


def test_no_town_maps_skips_location_checks(tmp_path: Path):
    import shutil

    root = _build_multi_agent_world(tmp_path / "world")
    shutil.rmtree(root / "game" / "towns")
    _write_json(root / "souls" / "elena-sielena0001" / "run_state.json", {"location": "anywhere"})
    health = check_world(root)
    assert "location-dangling" not in _codes(health.warnings)  # name-only world: skip


# ── layers 3/6/7: scaffold, opening, legacy lint ─────────────────


def test_missing_router_agent_is_warning_launch_heals(tmp_path: Path):
    import shutil

    root = _build_multi_agent_world(tmp_path / "world")
    shutil.rmtree(root / "agents")
    health = check_world(root)
    assert health.playable  # ensure_playable_world scaffolds it at launch
    assert "router-missing" in _codes(health.warnings)


def test_missing_game_start_is_warning(tmp_path: Path):
    root = _build_multi_agent_world(tmp_path / "world")
    (root / "game" / "meta" / "game-start.json").unlink()
    health = check_world(root)
    assert health.playable
    assert "game-start-missing" in _codes(health.warnings)


def test_duplicate_entity_ids_stay_blockers(tmp_path: Path):
    root = _build_orch_world(tmp_path / "orch")
    _write_json(root / "game" / "item" / "mira.json", _entity("item", "mira", "Mira the Sword"))
    health = check_world(root)
    assert not health.playable
    assert "id-duplicate" in _codes(health.blockers)


def test_schema_drift_is_warning_not_blocker(tmp_path: Path):
    root = _build_orch_world(tmp_path / "orch")
    # kind mismatch with its folder: old validate failed the world on this.
    _write_json(root / "game" / "npc" / "ghost.json", _entity("spirit", "ghost", "Ghost"))
    health = check_world(root)
    assert health.playable
    assert "kind-mismatch" in _codes(health.warnings)


# ── CLI wiring ───────────────────────────────────────────────────


def test_cli_validate_playable_exit_0(tmp_path: Path, monkeypatch):
    root = _build_multi_agent_world(tmp_path / "world")
    monkeypatch.chdir(root)
    result = CliRunner().invoke(cli, ["validate"])
    assert result.exit_code == 0, result.output
    assert "✓ playable" in result.output
    assert "multi-agent" in result.output


def test_cli_validate_blockers_exit_1(tmp_path: Path, monkeypatch):
    root = _build_multi_agent_world(tmp_path / "world")
    (root / "game" / "npc" / "bad.json").write_text("{broken", encoding="utf-8")
    monkeypatch.chdir(root)
    result = CliRunner().invoke(cli, ["validate"])
    assert result.exit_code == 1
    assert "✗ NOT playable" in result.output
    assert "game/npc/bad.json" in result.output


def test_cli_validate_json_shape(tmp_path: Path, monkeypatch):
    root = _build_multi_agent_world(tmp_path / "world")
    monkeypatch.chdir(root)
    result = CliRunner().invoke(cli, ["validate", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True and payload["playable"] is True
    assert payload["flavor"] == "multi-agent"
    assert payload["stats"]["souls"] == 1
    assert payload["blockers"] == []
