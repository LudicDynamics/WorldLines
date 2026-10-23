"""Ontology 数据面(M30 V1)契约回归。

唯一数据权威:名册/位置/场景读取 + move_entity(校验在工具内脏,
拒绝带回而不破坏调用)。fixture 沿用 stoneford-elena 模板
(elena 与玩家同在 north-gate;rowan 在 T004 异地)。
"""

import shutil
from pathlib import Path

from neonrp.core.ontology import get_location, get_roster, get_scene, move_entity
from neonrp.core.skills import SKILL_SCHEMAS

_TPL = Path("src/neonrp/templates/stoneford-elena")


def _install(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(_TPL, root)
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    return root


def test_get_roster_present_away_split(tmp_path: Path) -> None:
    root = _install(tmp_path)
    roster = get_roster(root)
    present = {r["instance_id"]: r for r in roster["present"]}
    away = {r["instance_id"]: r for r in roster["away"]}
    assert "si-elena0001" in present  # 与玩家同场
    assert away  # rowan 在 T004(异地)
    # 唯一数据:每行都带位置视图,名字是本地化名
    assert present["si-elena0001"]["name"] == "艾琳娜"
    assert present["si-elena0001"]["location"]["node"]
    assert roster["player"]["location"]["node"]


def test_get_location_player_and_soul_and_unknown(tmp_path: Path) -> None:
    root = _install(tmp_path)
    p = get_location(root, "player")
    assert p["ok"] and p["location"]["node"]
    s = get_location(root, "艾琳娜")  # 名字解析(soul_aliases)
    assert s["ok"] and s["entity"] == "si-elena0001"
    bad = get_location(root, "不存在的人")
    assert not bad["ok"] and "查无此人" in bad["error"]


def test_get_scene_known_and_unknown(tmp_path: Path) -> None:
    root = _install(tmp_path)
    player_node = get_location(root, "player")["location"]["node"]
    bare = player_node.split("/")[-1]
    sc = get_scene(root, bare)
    assert sc["ok"] and sc["name"]
    assert isinstance(sc["scene_state"], dict)  # 无场景层记录 ⇒ 显式空
    bad = get_scene(root, "地图上没有的地方xyz")
    assert not bad["ok"]


def test_move_entity_intra_town_scoped_landing(tmp_path: Path) -> None:
    # 同镇合法移动:落位且 scoped 到当前镇(T001/main_street),防瞬移语义保持
    root = _install(tmp_path)
    out = move_entity(root, "si-elena0001", "main_street")
    assert out["ok"] and out["moved"]
    assert get_location(root, "艾琳娜")["location"]["node"] == "T001/main_street"


def test_move_entity_unmapped_is_narrative_freedom(tmp_path: Path) -> None:
    # judge_move 契约(M25):地图描述不了的目标 = 叙事自由区,放行不拒
    # (荒野/未映射);工具必须带回落点事实,leader 自己决定怎么叙。
    root = _install(tmp_path)
    out = move_entity(root, "si-elena0001", "并不存在的幽灵城堡")
    assert out["ok"] and "location" in out


def test_move_entity_cross_town_goes_through_gates(tmp_path: Path) -> None:
    # cross-town: one beat walks out by the gate and into the next town (10-19 — no beat stopped at one's own gate);
    # a town-level target lands at the gate the road comes in by
    root = _install(tmp_path)
    assert move_entity(root, "si-elena0001", "main_street")["moved"]
    out = move_entity(root, "si-elena0001", "T004/tavern")
    assert out["ok"] and (out["location"]["node"] or "") == "T004/tavern"
    out = move_entity(root, "si-elena0001", "T001")
    assert out["ok"] and (out["location"]["node"] or "").startswith("T001/")


def test_move_entity_player_lands_run_state(tmp_path: Path) -> None:
    root = _install(tmp_path)
    before = get_location(root, "player")["location"]["node"]
    out = move_entity(root, "player", "main_street")
    assert out["ok"] and out["moved"]
    after = get_location(root, "player")["location"]["node"]
    assert after != before and after.endswith("main_street")


def test_ontology_tools_registered_in_skills() -> None:
    for name in ("get_roster", "get_location", "get_scene", "move_entity"):
        assert name in SKILL_SCHEMAS
        assert SKILL_SCHEMAS[name]["name"] == name
