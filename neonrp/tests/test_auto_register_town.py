"""TODO #5:新地点 / 新角色不只落文件夹,还要自动登记进
town 与 game 的正式结构 —— town_map 节点、town npcs 名册、soul 位置。"""

from __future__ import annotations

import json
from pathlib import Path

from neonrp.core import locations as L
from neonrp.core.playthrough import Playthrough, WorldAgentTeam, WorldRef, read_playthrough, write_playthrough
from neonrp.core.skills import SkillRegistry


def _town_world(root: Path, *, player_node: str = "main_street") -> Path:
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "world").mkdir(parents=True)
    (root / "game" / "locations").mkdir(parents=True)
    t = root / "game" / "towns" / "T004"
    t.mkdir(parents=True)
    (t / "town_map.json").write_text(json.dumps({
        "town_id": "T004",
        "nodes": [
            {"id": "gate_west", "name": "西门", "type": "gate", "pos": {"x": 100, "y": 300}, "links": ["main_street"]},
            {"id": "main_street", "name": "矿工大道", "type": "street", "pos": {"x": 350, "y": 300}, "links": ["gate_west"]},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (t / "npcs.json").write_text(json.dumps({"town_id": "T004", "npcs": []}), encoding="utf-8")
    (root / "game" / "meta" / "run_state.json").write_text(json.dumps({
        "turn_count": 1,
        "location": {"node_id": "T004", "subnode_id": player_node},
    }), encoding="utf-8")
    (root / "game" / "meta" / "game-start.json").write_text(json.dumps({
        "startup": {"read_first": ["game/towns/T004/town.json"]},
    }), encoding="utf-8")
    (root / "game" / "world" / "world_map.json").write_text(json.dumps({"nodes": []}), encoding="utf-8")
    return root


def _registry(root: Path) -> SkillRegistry:
    return SkillRegistry(root=root, run_id="r", agent_id="world-agent", read_globs=["**"], deny_globs=[], direct_write_globs=["**"], allow_protected_paths=True)


def _draft(root: Path, sid: str = "luowen") -> Path:
    draft = root / ".neonrp" / "soul-drafts" / sid
    (draft / "persona").mkdir(parents=True)
    (draft / "soul.json").write_text(json.dumps({"sid": sid, "name": "罗文"}, ensure_ascii=False), encoding="utf-8")
    (draft / "persona" / "kernel.md").write_text("沉默寡言的铁匠。", encoding="utf-8")
    return draft


def _town_map(root: Path) -> dict:
    return json.loads((root / "game" / "towns" / "T004" / "town_map.json").read_text(encoding="utf-8"))


# ── places ─────────────────────────────────────────────────────────────


def test_new_place_lands_in_the_players_town_map(tmp_path):
    root = _town_world(tmp_path)
    res = L.create_location(root, name="河灯旅店", summary="河边的小旅店", connections=["main_street"])
    assert res["town"] == "T004" and res["town_node_added"]
    nodes = {n["id"]: n for n in _town_map(root)["nodes"]}
    assert nodes["河灯旅店"]["links"] == ["main_street"] and nodes["河灯旅店"]["description"] == "河边的小旅店"
    assert "河灯旅店" in nodes["main_street"]["links"], "镇图连线双向"
    rec = json.loads((root / "game" / "locations" / "河灯旅店" / "location.json").read_text(encoding="utf-8"))
    assert rec["town"] == "T004"
    assert any(p.endswith("town_map.json") for p in res["written"])
    # movement can now resolve it inside the town
    from neonrp.core.place_nav import resolve_move_target

    assert resolve_move_target(root, "河灯旅店", current_location="T004/main_street") == "T004/河灯旅店"


def test_town_is_taken_from_the_parent_or_explicit_arg_before_the_player(tmp_path):
    root = _town_world(tmp_path)
    (root / "game" / "towns" / "T001").mkdir()
    (root / "game" / "towns" / "T001" / "town_map.json").write_text(json.dumps({"town_id": "T001", "nodes": [{"id": "guild", "name": "公会", "links": []}]}), encoding="utf-8")
    a = L.create_location(root, name="密室", parent="T001/guild")
    assert a["town"] == "T001"
    assert any(n["id"] == "密室" and "guild" in n["links"] for n in json.loads((root / "game" / "towns" / "T001" / "town_map.json").read_text(encoding="utf-8"))["nodes"])
    b = L.create_location(root, name="废矿", town="T001")
    assert b["town"] == "T001"
    c = L.create_location(root, name="荒野驿站")
    assert c["town"] == "T004", "都没给就跟玩家所在的镇"


def test_a_world_without_towns_stays_the_old_shape(tmp_path):
    root = tmp_path / "w"
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "world").mkdir()
    res = L.create_location(root, name="北门")
    assert res["town"] is None and res["town_node_added"] is False
    assert not (root / "game" / "towns").exists()


def test_update_location_keeps_the_town_node_in_sync(tmp_path):
    root = _town_world(tmp_path)
    L.create_location(root, name="河灯旅店")
    L.update_location(root, "河灯旅店", name="河灯客栈", summary="改了名", add_connections=["gate_west"])
    nodes = {n["id"]: n for n in _town_map(root)["nodes"]}
    assert nodes["河灯旅店"]["name"] == "河灯客栈" and nodes["河灯旅店"]["description"] == "改了名"
    assert "gate_west" in nodes["河灯旅店"]["links"] and "河灯旅店" in nodes["gate_west"]["links"]


def test_new_location_tool_reports_the_town_map_change(tmp_path):
    root = _town_world(tmp_path)
    res = _registry(root).invoke("new_location", {"name": "河灯旅店", "connections": ["main_street"], "town": "T004"})
    assert res.success, res.error
    paths = [c.get("path", "") for c in res.data["changes"] if isinstance(c, dict)]
    assert any("town_map.json" in p for p in paths) and any("world_map.json" in p for p in paths)


# ── characters ─────────────────────────────────────────────────────────


def test_cast_into_a_town_world_joins_the_town_roster(tmp_path):
    root = _town_world(tmp_path)
    _draft(root)
    res = _registry(root).invoke("cast_soul", {"sid": "luowen"})
    assert res.success, res.error
    roster = json.loads((root / "game" / "towns" / "T004" / "npcs.json").read_text(encoding="utf-8"))
    entry = next(n for n in roster["npcs"] if n["id"] == "luowen")
    assert entry["location"] == "main_street" and entry["name"] == "罗文"
    assert res.data["town"] == "T004" and res.data["location"] == "main_street"
    gs = json.loads((root / "game" / "meta" / "game-start.json").read_text(encoding="utf-8"))
    assert "game/towns/T004/npcs.json" in gs["startup"]["read_first"], "开局就读到他"
    assert not (root / "game" / "npc" / "luowen.json").exists(), "不再落成孤儿 game/npc"
    assert any("npcs.json" in c.get("path", "") for c in res.data["registered"])


def test_cast_with_an_explicit_location_uses_it(tmp_path):
    root = _town_world(tmp_path)
    _draft(root)
    res = _registry(root).invoke("cast_soul", {"sid": "luowen", "location": "gate_west"})
    assert res.success, res.error
    roster = json.loads((root / "game" / "towns" / "T004" / "npcs.json").read_text(encoding="utf-8"))
    assert roster["npcs"][0]["location"] == "gate_west"


def _multiagent_town_world(root: Path) -> Path:
    _town_world(root)
    write_playthrough(root, Playthrough(
        schema_version=2, playthrough_id="pt-5",
        world=WorldRef(wid="w", instance_id="wi-0000000000ff", version_hash="sha256:x", head_commit=""),
        world_agent_team=WorldAgentTeam(seeded_from="t", agents=[]), souls=[], created_at="2026-09-11T00:00:00Z", active_souls=(),
    ))
    return root


def test_multiagent_cast_seeds_the_souls_location_beside_the_player(tmp_path):
    root = _multiagent_town_world(tmp_path)
    _draft(root)
    res = _registry(root).invoke("cast_soul", {"sid": "luowen"})
    assert res.success, res.error
    iid = res.data["instance_id"]
    state = json.loads((root / "souls" / f"luowen-{iid}" / "run_state.json").read_text(encoding="utf-8"))
    assert state["location"] == "T004/main_street" == res.data["location"]
    from neonrp.core.ontology import get_roster

    roster = get_roster(root)
    assert [r["sid"] for r in roster["present"]] == ["luowen"] and roster["away"] == []
    assert [s.sid for s in read_playthrough(root).souls] == ["luowen"]


def test_multiagent_cast_with_a_bare_node_scopes_it_to_the_current_town(tmp_path):
    root = _multiagent_town_world(tmp_path)
    _draft(root)
    res = _registry(root).invoke("cast_soul", {"sid": "luowen", "location": "gate_west"})
    assert res.success, res.error
    state = json.loads((root / "souls" / f"luowen-{res.data['instance_id']}" / "run_state.json").read_text(encoding="utf-8"))
    assert state["location"] == "T004/gate_west"
    from neonrp.core.ontology import get_location

    assert get_location(root, "luowen")["location"]["town"] == "T004"


def test_place_made_in_play_then_character_cast_there(tmp_path):
    """两步连起来:先 new_location 再 cast_soul(location=那个新地方)。"""
    root = _multiagent_town_world(tmp_path)
    _draft(root)
    reg = _registry(root)
    assert reg.invoke("new_location", {"name": "铁匠铺", "connections": ["main_street"]}).success
    res = reg.invoke("cast_soul", {"sid": "luowen", "location": "铁匠铺"})
    assert res.success, res.error
    assert res.data["location"] == "T004/铁匠铺"
