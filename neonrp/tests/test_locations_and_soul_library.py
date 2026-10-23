"""任务 B1/B2:角色 cast 后进库;地点是文件夹,agent 玩着玩着
能新建并细化,地图同步看得见。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp.core import locations as L
from neonrp.core.skills import SkillRegistry


def _world(root: Path) -> Path:
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "world").mkdir(parents=True)
    (root / "game" / "locations").mkdir(parents=True)
    (root / "game" / "world" / "world_map.json").write_text(
        json.dumps({"name": "雾港", "nodes": [{"id": "gate", "name": "北门", "pos": [4, 3], "links": []}]}), encoding="utf-8"
    )
    (root / "game" / "locations" / "gate.json").write_text(
        json.dumps({"id": "gate", "kind": "location", "name": "北门", "connections": []}), encoding="utf-8"
    )
    return root


def _registry(root: Path) -> SkillRegistry:
    return SkillRegistry(root=root, run_id="r", agent_id="world-agent", read_globs=["**"], deny_globs=[], direct_write_globs=["**"], allow_protected_paths=True)


# ── B2 · locations ────────────────────────────────────────────────────


def test_create_location_writes_a_folder_and_links_both_ways(tmp_path):
    root = _world(tmp_path / "w")
    res = L.create_location(root, name="河灯旅店", summary="河边的旅店", connections=["北门"], notes="二楼有个望河的房间")
    folder = root / "game" / "locations" / "河灯旅店"
    assert (folder / "location.json").is_file() and (folder / "notes.md").is_file()
    rec = json.loads((folder / "location.json").read_text(encoding="utf-8"))
    assert rec["id"] == "河灯旅店" and rec["connections"] == ["gate"], "名字解析成 id"
    gate = json.loads((root / "game" / "locations" / "gate.json").read_text(encoding="utf-8"))
    assert gate["connections"] == ["河灯旅店"], "对方也连回来(文件形态照改)"
    assert "望河" in (folder / "notes.md").read_text(encoding="utf-8")
    assert res["map_node_added"]
    nodes = json.loads((root / "game" / "world" / "world_map.json").read_text(encoding="utf-8"))["nodes"]
    assert any(n["id"] == "河灯旅店" for n in nodes), "地图有它"


def test_iter_reads_both_forms(tmp_path):
    root = _world(tmp_path / "w")
    L.create_location(root, name="旅店")
    (root / "game" / "locations" / "旅店" / "scene_state.json").write_text("{}", encoding="utf-8")
    ids = [i for i, _, _ in L.iter_locations(root)]
    assert ids == ["gate", "旅店"], ids  # scene_state.json is not a place


def test_duplicate_is_refused(tmp_path):
    root = _world(tmp_path / "w")
    L.create_location(root, name="旅店")
    with pytest.raises(L.LocationError):
        L.create_location(root, name="旅店")


def test_update_location_refines_and_keeps_links_symmetric(tmp_path):
    root = _world(tmp_path / "w")
    L.create_location(root, name="旅店")
    L.create_location(root, name="集市")
    res = L.update_location(root, "旅店", summary="河边的旅店", add_connections=["集市"], notes_append="酒保叫老周")
    assert res["connections"] == ["集市"]
    market = L.read_location(root, "集市")
    assert market["connections"] == ["旅店"]
    assert "老周" in (root / "game" / "locations" / "旅店" / "notes.md").read_text(encoding="utf-8")
    L.update_location(root, "旅店", remove_connections=["集市"])
    assert L.read_location(root, "集市")["connections"] == []
    nodes = json.loads((root / "game" / "world" / "world_map.json").read_text(encoding="utf-8"))["nodes"]
    assert next(n for n in nodes if n["id"] == "旅店")["summary"] == "河边的旅店"


def test_parent_makes_a_child_node(tmp_path):
    root = _world(tmp_path / "w")
    L.create_location(root, name="旅店")
    L.create_location(root, name="二楼客房", parent="旅店")
    nodes = json.loads((root / "game" / "world" / "world_map.json").read_text(encoding="utf-8"))["nodes"]
    child = next(n for n in nodes if n["id"] == "二楼客房")
    assert child["parent"] == "旅店"


def test_tools_create_and_update_through_the_registry(tmp_path):
    root = _world(tmp_path / "w")
    reg = _registry(root)
    res = reg.invoke("new_location", {"name": "旅店", "connections": ["北门"], "summary": "河边"})
    assert res.success, res.error
    assert res.data["id"] == "旅店" and res.data["connections"] == ["gate"]
    assert any("world_map.json" in c.get("path", "") for c in res.data["changes"] if isinstance(c, dict)) or res.data["changes"]
    res2 = reg.invoke("update_location", {"id": "旅店", "notes_append": "夜里很吵"})
    assert res2.success, res2.error
    assert reg.invoke("update_location", {"id": "nowhere"}).success is False
    assert reg.invoke("new_location", {"name": ""}).success is False


def test_location_tools_are_offered_in_play_even_with_an_allowlist():
    from neonrp.core.conversation import _filter_tool_schemas_by_agent_config as _apply_agent_tool_allowlist

    schemas = [{"name": "new_location"}, {"name": "update_location"}, {"name": "write_file"}, {"name": "read_file"}]
    agent = {"tools": ["read_file"]}
    play = {s["name"] for s in _apply_agent_tool_allowlist(schemas, agent, mode="play")}
    assert play == {"read_file", "new_location", "update_location"}
    build = {s["name"] for s in _apply_agent_tool_allowlist(schemas, agent, mode="build")}
    assert "write_file" in build and "new_location" in build


def test_vault_and_header_read_the_folder_form(tmp_path):
    from neonrp.core import vault as V
    from neonrp.tui.location_header import _resolve_location_node

    root = _world(tmp_path / "w")
    (root / "game" / "meta" / "run_state.json").write_text("{}", encoding="utf-8")
    L.create_location(root, name="旅店", summary="河边")
    V.project_vault(root)
    assert (root / "vault" / "地点" / "旅店.md").exists()
    node = _resolve_location_node(root, "旅店")
    assert node and node["name"] == "旅店"


# ── B1 · soul library ─────────────────────────────────────────────────


def _draft(root: Path, sid: str = "rowan") -> Path:
    d = root / ".neonrp" / "soul-drafts" / sid
    (d / "persona").mkdir(parents=True)
    (d / "soul.json").write_text(json.dumps({"sid": sid, "name": "Rowan", "name_local": "罗文"}), encoding="utf-8")
    (d / "persona" / "core.md").write_text("# 罗文", encoding="utf-8")
    (d / "run_state.json").write_text("{}", encoding="utf-8")
    return d


def test_archive_soul_copies_into_the_library_without_run_state(tmp_path, monkeypatch):
    import neonrp.core.souls as S

    monkeypatch.setattr(S, "SOUL_HOME", tmp_path / "lib")
    d = _draft(tmp_path / "w")
    dest = S.archive_soul(d)
    assert dest == tmp_path / "lib" / "rowan"
    assert (dest / "persona" / "core.md").read_text(encoding="utf-8") == "# 罗文"
    assert not (dest / "run_state.json").exists()
    # second time: no-op unless overwrite
    (d / "persona" / "core.md").write_text("changed", encoding="utf-8")
    S.archive_soul(d)
    assert (dest / "persona" / "core.md").read_text(encoding="utf-8") == "# 罗文"
    S.archive_soul(d, overwrite=True)
    assert (dest / "persona" / "core.md").read_text(encoding="utf-8") == "changed"


def test_cast_resolves_a_library_soul(tmp_path, monkeypatch):
    import neonrp.core.souls as S

    monkeypatch.setattr(S, "SOUL_HOME", tmp_path / "lib")
    lib = tmp_path / "lib" / "elena"
    lib.mkdir(parents=True)
    (lib / "soul.json").write_text(json.dumps({"sid": "elena", "name": "Elena"}), encoding="utf-8")
    reg = _registry(_world(tmp_path / "w"))
    assert reg._resolve_draft_soul_dir("elena") == lib
    assert reg._resolve_draft_soul_dir("../lib/elena") is None, "路径不能跳出 project 去猜"


def test_cast_resolves_a_timestamped_library_soul(tmp_path, monkeypatch):
    """/import 与 launcher 建的库文件夹叫 <sid>-<时间戳>;cast_soul 也要认。"""
    import neonrp.core.placement as P
    import neonrp.core.souls as S

    monkeypatch.setattr(S, "SOUL_HOME", tmp_path / "lib")
    monkeypatch.setattr(P, "SOUL_HOME", tmp_path / "lib", raising=False)
    lib = tmp_path / "lib" / "elena-20260101-000000"
    lib.mkdir(parents=True)
    (lib / "soul.json").write_text(json.dumps({"sid": "elena", "name": "Elena"}), encoding="utf-8")
    reg = _registry(_world(tmp_path / "w"))
    assert reg._resolve_draft_soul_dir("elena") == lib
    assert reg._resolve_draft_soul_dir("nobody") is None


def test_create_soul_workshop_skeleton_and_dedupe(tmp_path, monkeypatch):
    import json as _json

    import neonrp.core.souls as S

    monkeypatch.setattr(S, "SOUL_HOME", tmp_path / "lib")
    monkeypatch.setattr("neonrp.presets.build_config_dict", lambda ref: {"llm": {"model_ref": ref}, "models": {ref: {"provider": "openai"}}})
    d = S.create_soul_workshop("罗文", model_ref="qwen")
    assert d == tmp_path / "lib" / "罗文"
    assert (d / "soul.json").is_file() and (d / "persona" / "core.md").is_file() and (d / "assets").is_dir()
    meta = _json.loads((d / "soul.json").read_text(encoding="utf-8"))
    assert meta["sid"] == "罗文" and meta["name_local"] == "罗文"
    cfg = _json.loads((d / ".neonrp" / "config.json").read_text(encoding="utf-8"))
    assert cfg["llm"]["model_ref"] == "qwen", "工坊自己带模型"
    assert S.is_soul_workshop(d) and not S.is_soul_workshop(tmp_path)
    assert S.create_soul_workshop("罗文").name == "罗文-2"
    with pytest.raises(ValueError):
        S.create_soul_workshop("  ")


def test_build_prompt_switches_to_the_character_workshop_rule(tmp_path):
    from neonrp.core.prompts import build_system_prompt

    d = tmp_path / "luowen"
    d.mkdir()
    (d / "soul.json").write_text("{}", encoding="utf-8")
    txt = build_system_prompt("world-agent", "luowen", "main", "build", project_root=str(d))
    assert "Character workshop" in txt and "cast_soul` — there is no" in txt
    assert "Creating a character (M31)" not in txt
    w = tmp_path / "w"
    (w / "game").mkdir(parents=True)
    txt2 = build_system_prompt("world-agent", "w", "main", "build", project_root=str(w))
    assert "Creating a character (M31)" in txt2 and "Character workshop" not in txt2


def test_soul_workshop_is_an_initialized_project_without_a_game_dir(tmp_path, monkeypatch):
    """工坊里 agent 报「NeonRP project not initialized」。"""
    import neonrp.core.souls as S
    from neonrp.core.paths import get_manifest_path

    monkeypatch.setattr(S, "SOUL_HOME", tmp_path / "lib")
    monkeypatch.setattr("neonrp.presets.build_config_dict", lambda ref: {"llm": {"model_ref": ref}, "models": {ref: {"provider": "stub"}}})
    d = S.create_soul_workshop("niko", model_ref="stub")
    assert get_manifest_path(d).is_file()
    assert not (d / "game").exists() and S.is_soul_workshop(d)
    # an older workshop without the manifest gets it on app start
    old = tmp_path / "lib" / "old"
    old.mkdir()
    (old / "soul.json").write_text("{}", encoding="utf-8")
    from neonrp.tui.app import NeonRPApp

    NeonRPApp(root=old, mode="build")
    assert get_manifest_path(old).is_file()


def test_workshop_turn_gets_past_the_init_check(tmp_path, monkeypatch):
    import neonrp.core.souls as S
    from neonrp.core.conversation import ConversationSession

    monkeypatch.setattr(S, "SOUL_HOME", tmp_path / "lib")
    monkeypatch.setattr("neonrp.presets.build_config_dict", lambda ref: {"llm": {"model_ref": "stub"}, "models": {"stub": {"provider": "stub", "model": "stub"}}})
    d = S.create_soul_workshop("niko", model_ref="stub")
    session = ConversationSession(root=d, agent_id="world-agent", mode="build")
    res = session.send("你好")
    assert "not initialized" not in str(getattr(res, "error", "") or ""), res
