"""Scene-aware placement: read_world_native_cast surfaces a multi-agent
world's OWN souls (from .neonrp/playthrough.json + souls/) and its baked
protagonist (game/player/profile.json), with active_souls flagged. Orch /
fast worlds (no playthrough) return an empty soul cast.
"""

from __future__ import annotations

import json
from pathlib import Path

from neonrp.core.placement import read_world_native_cast


def _make_ma_world(root: Path) -> Path:
    nd = root / ".neonrp"
    nd.mkdir(parents=True)
    (nd / "playthrough.json").write_text(json.dumps({
        "schema_version": 2,
        "playthrough_id": "pt-test",
        "created_at": "2026-01-01T00:00:00+00:00",
        "world": {"wid": "w", "instance_id": "wi-1", "version_hash": "h", "head_commit": "c"},
        "world_agent_team": {"seeded_from": "x", "agents": [
            {"id": "world-agent", "role": "orchestrator", "singleton": True},
        ]},
        "players": [],
        "souls": [
            {"sid": "hane", "instance_id": "si-hane0001", "version_hash": "h", "head_commit": "c", "role": "npc"},
            {"sid": "kagami", "instance_id": "si-kagami001", "version_hash": "h", "head_commit": "c", "role": "npc"},
        ],
        "active_souls": ["si-hane0001"],
    }), encoding="utf-8")
    for sid, iid, nm, loc in [("hane", "si-hane0001", "Hane", "羽"), ("kagami", "si-kagami001", "Kagami", "镜")]:
        sd = root / "souls" / f"{sid}-{iid}"
        sd.mkdir(parents=True)
        (sd / "soul.json").write_text(
            json.dumps({"schema_version": 1, "sid": sid, "name": nm, "name_local": loc}),
            encoding="utf-8",
        )
    pd = root / "game" / "player"
    pd.mkdir(parents=True)
    (pd / "profile.json").write_text(
        json.dumps({"sid": "kakaru", "display_name": "Kakaru", "name_local": "カカル", "summary": "the PC"}),
        encoding="utf-8",
    )
    return root


def test_native_cast_surfaces_world_souls_with_active_flags(tmp_path: Path) -> None:
    world = _make_ma_world(tmp_path / "w")
    cast = read_world_native_cast(world, locale="en")

    souls = {s["sid"]: s for s in cast["souls"]}
    assert set(souls) == {"hane", "kagami"}
    assert all(s["native"] is True for s in cast["souls"])
    assert souls["hane"]["active"] is True       # in active_souls
    assert souls["kagami"]["active"] is False     # not in active_souls
    # display name resolved from the forked soul folder (not the sid fallback),
    # path points at it.
    assert "Hane" in souls["hane"]["display_name"]
    assert souls["hane"]["display_name"] != "hane"
    assert Path(souls["hane"]["path"]).is_dir()


def test_native_cast_surfaces_prior_protagonist(tmp_path: Path) -> None:
    world = _make_ma_world(tmp_path / "w")
    avatar = read_world_native_cast(world, locale="en")["avatar"]
    assert avatar is not None
    assert avatar["native"] is True
    assert "Kakaru" in avatar["name"]
    assert avatar["summary"] == "the PC"
    assert isinstance(avatar["data"], dict) and avatar["data"]["sid"] == "kakaru"


def test_reads_template_root_playthrough_pre_instantiation(tmp_path: Path) -> None:
    """Casting runs before instantiation, so the helper must also read a raw
    template's ROOT playthrough.json (no .neonrp/ yet)."""
    root = tmp_path / "tmpl"
    (root / "souls" / "hane-si-hane0001").mkdir(parents=True)
    (root / "souls" / "hane-si-hane0001" / "soul.json").write_text(
        json.dumps({"schema_version": 1, "sid": "hane", "name": "Hane", "name_local": "羽"}),
        encoding="utf-8",
    )
    # NOTE: at template root, NOT under .neonrp/
    (root / "playthrough.json").write_text(json.dumps({
        "schema_version": 2, "playthrough_id": "pt", "created_at": "2026-01-01T00:00:00+00:00",
        "world": {"wid": "w"}, "world_agent_team": {"agents": []}, "players": [],
        "souls": [{"sid": "hane", "instance_id": "si-hane0001", "role": "npc"}],
        "active_souls": ["si-hane0001"],
    }), encoding="utf-8")

    cast = read_world_native_cast(root, locale="en")
    assert [s["sid"] for s in cast["souls"]] == ["hane"]
    assert cast["souls"][0]["active"] is True
    assert "Hane" in cast["souls"][0]["display_name"]


def test_soul_bearing_templates_are_multiagent() -> None:
    """Invariant: a template that ships native souls (souls/ + playthrough.json)
    IS a multi-agent world and must be labelled so — else the casting screen's
    scene-aware gate skips it and its souls never surface (the kagura-island
    bug: orchestrator label + multi-agent structure → souls 出不来)."""
    import importlib.resources as res

    templates_root = Path(str(res.files("neonrp") / "templates"))
    offenders = []
    for d in templates_root.iterdir():
        if not d.is_dir():
            continue
        if (d / "souls").is_dir() and (d / "playthrough.json").is_file():
            rc = d / "runtime_contract.json"
            mode = None
            if rc.is_file():
                mode = json.loads(rc.read_text(encoding="utf-8")).get("router", {}).get("execution_mode")
            if mode != "multi-agent":
                offenders.append((d.name, mode))
    assert not offenders, f"soul-bearing templates must be multi-agent, got: {offenders}"


def test_mode_axes_soul_world_is_multiagent_only(tmp_path: Path) -> None:
    """A soul world (souls + playthrough) is multi-agent and that's its only
    valid execution mode — fast/orchestrator would orphan the souls."""
    from neonrp.core.runtime_contract import is_soul_world, valid_execution_modes

    world = _make_ma_world(tmp_path / "w")
    assert is_soul_world(world) is True
    assert valid_execution_modes(world) == ("multi-agent",)


def test_mode_axes_flat_world_is_orchestrator(tmp_path: Path) -> None:
    """A flat world (no playthrough/souls) toggles fast↔orchestrator and
    cannot be switched to multi-agent."""
    from neonrp.core.runtime_contract import is_soul_world, valid_execution_modes

    w = tmp_path / "flat"
    (w / ".neonrp").mkdir(parents=True)
    assert is_soul_world(w) is False
    assert valid_execution_modes(w) == ("orchestrator",)


def test_non_multiagent_world_has_empty_soul_cast(tmp_path: Path) -> None:
    # No .neonrp/playthrough.json (orch / fast world) → no native souls.
    w = tmp_path / "orch"
    (w / ".neonrp").mkdir(parents=True)
    cast = read_world_native_cast(w, locale="en")
    assert cast["souls"] == []
    assert cast["avatar"] is None  # also no baked PC here
