"""V1–V3 (TESTBENCH-AUTOVIEW-1005) + G5 scale (10-06)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from test_engine_v3 import _install

from neonrp.core import sdk, view_schema
from neonrp.core.registry import load_registry


def test_view_schema_has_classes_variables_and_units(tmp_path):
    root = _install(tmp_path)
    v = view_schema.view_schema(root)
    assert v["classes"]["status"]["effect"] and "turns" in v["classes"]["status"]["props"]
    assert "player.hp" in v["variables"] and "path" not in v["variables"]["player.hp"]
    assert any(u["name"] == "downed" for u in v["units"])


def test_var_history_comes_from_the_ledger(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    hp = int(reg.variables["player.hp"].value)
    sdk.apply(root, [{"op": "add", "var": "player.hp", "delta": -3}], reg, turn=1)
    sdk.apply(root, [{"op": "add", "var": "player.hp", "delta": -2}], load_registry(root), turn=2)
    h = view_schema.var_history(root, "player.hp")
    assert [(x["from"], x["to"]) for x in h][-2:] == [(hp, hp - 3), (hp - 3, hp - 5)]


def test_scale_is_shown_and_an_unknown_one_linted(tmp_path):
    from neonrp.core.map_lint import lint_map
    from neonrp.core.place_tree import level_graph

    w = tmp_path / "w"
    shutil.copytree("src/neonrp/templates/stoneford-elena", w)
    rec = w / "game" / "locations" / "T001" / "gate_north" / "location.json"
    d = json.loads(rec.read_text(encoding="utf-8"))
    d["scale"] = "building"
    rec.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    g = level_graph(w, "T001")
    assert next(n for n in g["nodes"] if n["id"] == "gate_north")["scale"] == "building"
    d["scale"] = "galaxy"
    rec.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert any(x["code"] == "map.scale_unknown" for x in lint_map(w))


def test_round_bundle_reads_a_trace(tmp_path):
    from neonrp.core.orchestration_trace import TurnTrace, append_turn_trace

    root = _install(tmp_path)
    t = TurnTrace(turn_seq=1, player_input="去主街", player_intent_kind="act", world_location="T001/gate_north")
    t.apply = {"beat": {"kind": "resolve", "advanced_by": "player"}, "applied": [{"op": "add", "var": "player.hp", "from": 24, "to": 23, "by": "tick:effects"},
               {"op": "move_to", "who": "player", "to": "T001/main_street"}], "tool_returns": [{"request": "dice 1d20", "text": "12"}],
               "narration_plain": "你走上主街。"}
    append_turn_trace(root, "main", t)
    b = view_schema.round_bundle(root, 0)
    assert b["nodes"] == ["resolve"] and b["advanced_by"] == "player" and b["units"]["effects"][0]["to"] == 23
    assert b["diff"]["applied"] == [{"op": "move_to", "who": "player", "to": "T001/main_street"}] and b["tools"][0]["request"] == "dice 1d20"
    assert view_schema.round_bundle(root, 5) is None
