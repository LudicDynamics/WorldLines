"""The orchestration graph (worldlines.orchestration/1):
states as nodes, transitions as edges; generated from today's behaviour when no one wrote one; the template / run
override (game/meta/orchestration.json) changes what the engine does, edge by edge."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from test_engine_v3 import _install
from test_template_packs import _werewolf

from neonrp.core import modes, orchestration, sdk
from neonrp.core.registry import load_registry
from _paths import PRODUCT_TEMPLATES


def _override(root: Path, d: dict) -> None:
    p = orchestration.override_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _ids(g: dict) -> set[str]:
    return {e["id"] for e in g["edges"]}


# ── O1: read / generate / print ──────────────────────────────────────────────

def test_the_default_graph_is_todays_behaviour(tmp_path):
    root = _install(tmp_path)
    g = orchestration.graph(root)
    assert g["schema"] == "worldlines.orchestration/1" and g["start"] == "plan"
    assert {"plan", "resolve", "combat", "dungeon", "referee"} <= set(g["nodes"])
    # D-20261018: the combat layer is a one-shot node the Resolve calls, never a state the world is in
    assert g["nodes"]["dungeon"]["kind"] == "place" and g["nodes"]["combat"]["kind"] == "one_shot" and "exit" not in g["nodes"]["combat"]
    assert {"plan>resolve:event", "plan>resolve:words", "plan>resolve:host", "plan>resolve:dm", "plan>resolve:judge",
            "resolve>plan", "resolve>combat:call", "dungeon>combat:call", "resolve>referee:call", "*>dungeon:here"} <= _ids(g)
    assert not {"*>combat:call", "resolve>combat:op", "combat>@return:end_combat", "*>combat:encounter", "*>combat:gate"} & _ids(g)


# ── O2: the two beats are nodes; their ending rules are edges ────────────────

def _plan_world(tmp_path, monkeypatch, *, settled_says=0.95):
    from neonrp.core import plan_loop

    root = _install(tmp_path)
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n好,就这么办。\n</lines>\n<board>\n玩家: 去杂货铺买药\n</board>\nnext: wait")
    asked = []
    monkeypatch.setattr(plan_loop, "settled", lambda *a, **k: (asked.append(1), settled_says)[1])
    monkeypatch.setattr(plan_loop, "check_gap", lambda *a, **k: None)
    monkeypatch.setattr(plan_loop, "overrode", lambda *a, **k: None)
    return root, plan_loop, asked


def test_the_judge_edge_ends_the_talk_and_without_it_the_talk_goes_on(tmp_path, monkeypatch):
    root, plan_loop, asked = _plan_world(tmp_path, monkeypatch)
    out = plan_loop.step(root, user_text="我去杂货铺买药。", last_narration="雾。")
    assert out["kind"] == "resolve" and out["advanced_by"] == "judge:settled" and asked
    root2, plan_loop2, asked2 = _plan_world(tmp_path / "b", monkeypatch)
    _override(root2, {"remove": ["plan>resolve:judge"]})
    out2 = plan_loop2.step(root2, user_text="我去杂货铺买药。", last_narration="雾。")
    assert out2["kind"] == "plan" and not asked2, "no judge edge: the judge is not asked, the talk goes on"


def test_without_the_dm_edge_an_at_dm_does_not_switch(tmp_path, monkeypatch):
    root, plan_loop, _asked = _plan_world(tmp_path, monkeypatch, settled_says=None)
    monkeypatch.setattr(plan_loop, "_host", lambda root_, system, user: "<lines>\n走。\n</lines>\n<board>\n玩家: 进城\n</board>\nnext: advance")
    assert plan_loop.step(root, user_text="@dm 我进城", last_narration="雾。")["advanced_by"] == "player"
    root2, plan_loop2, _a2 = _plan_world(tmp_path / "b", monkeypatch, settled_says=None)
    monkeypatch.setattr(plan_loop2, "_host", lambda root_, system, user: "<lines>\n走。\n</lines>\n<board>\n玩家: 进城\n</board>\nnext: advance")
    _override(root2, {"remove": ["plan>resolve:dm"]})
    assert plan_loop2.step(root2, user_text="@dm 我进城", last_narration="雾。")["kind"] == "plan"


def test_commit_words_are_an_edge_and_an_author_can_add_his_own(tmp_path, monkeypatch):
    root, plan_loop, _a = _plan_world(tmp_path, monkeypatch, settled_says=None)
    plan_loop.save(root, {"board": {"玩家": "去杂货铺"}, "talk": ["玩家:去杂货铺"]})
    _override(root, {"remove": ["plan>resolve:words"],
                     "add": [{"id": "plan>resolve:mine", "from": "plan", "to": "resolve", "on": {"words": ["开干"]}}]})
    assert plan_loop.step(root, user_text="定", last_narration="雾。")["kind"] == "plan", "the commit word's edge was removed"
    plan_loop.save(root, {"board": {"玩家": "去杂货铺"}, "talk": ["玩家:去杂货铺"]})
    assert plan_loop.step(root, user_text="开干", last_narration="雾。")["advanced_by"] == "player"


# ── O3: every switch goes through the edge table ─────────────────────────────

def test_a_one_shot_call_needs_its_edge(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    op = {"op": "combat", "roster": "山贼×2"}
    assert orchestration.refuses_op(root, reg, op) is None
    _override(root, {"remove": ["resolve>combat:call"]})
    why = orchestration.refuses_op(root, reg, op)
    assert why and "combat" in why
    assert any("orchestration" in r.why for r in sdk.verify(root, [op], reg).refused)


def test_a_fight_under_way_is_world_data_not_a_node(tmp_path):
    """D-20261018: foes standing here are kept between beats, but the world stays in the Resolve (the talk still runs)."""
    from neonrp.packs.rpg import combat

    root = _install(tmp_path)
    reg = load_registry(root)
    st = combat.spawn(root, reg, roster="山贼×1", turn=1)
    combat.write(root, {**st, "at": reg.player_location})
    reg = load_registry(root)
    assert "foe.bandit1.hp" in reg.variables
    assert modes.read_mode(root) is None and orchestration.current(root, reg) == orchestration.RESOLVE


def test_the_place_layer_is_an_edge(tmp_path):
    root = _install(tmp_path)
    reg = load_registry(root)
    room = next(e for e in reg.of_class("room"))
    reg.player_location = room.id
    assert modes.here_layer(root, reg) == "dungeon" and orchestration.current(root, reg) == "dungeon"
    assert orchestration.refuses_op(root, reg, {"op": "combat"}) is None, "a place layer may still call a fight"
    _override(root, {"remove": ["*>dungeon:here"]})
    assert modes.here_layer(root, reg) is None
    # an override may also add one: the same layer keyed by another class
    _override(root, {"add": [{"id": "*>dungeon:town", "from": "*", "to": "dungeon", "on": {"here_class": "place"}}]})
    reg2 = load_registry(root)
    assert reg2.entries[reg2.player_location].cls == "place"
    assert modes.here_layer(root, reg2) == "dungeon", "an added here-class edge is honoured"


def test_werewolf_phase_moves_along_its_edges(tmp_path):
    root = _werewolf(tmp_path)
    reg = load_registry(root)
    assert orchestration.refuses_op(root, reg, {"op": "phase", "value": "night"}) is None
    _override(root, {"remove": ["day>night:phase"]})
    assert orchestration.refuses_op(root, reg, {"op": "phase", "value": "night"})
    assert sdk.verify(root, [{"op": "phase", "value": "night"}], reg).refused
    (root / "game" / "meta" / "orchestration.json").unlink()
    vr = sdk.verify(root, [{"op": "phase", "value": "night"}], load_registry(root))
    assert vr.accepted and not vr.refused
    sdk.apply(root, vr.accepted, load_registry(root), turn=1)
    assert orchestration.phase_node(root, load_registry(root)) == "night"


def test_a_template_carries_its_edit_of_the_graph_into_the_run(tmp_path):
    import shutil

    from neonrp import template as T

    src = PRODUCT_TEMPLATES / "stoneford-elena.template"
    tdir = tmp_path / "t.template"
    shutil.copytree(src, tdir)
    d = json.loads((tdir / "template.json").read_text(encoding="utf-8"))
    d["orchestration"] = {"remove": ["plan>resolve:judge"]}
    (tdir / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    run = tmp_path / "run"
    T.build(tdir, run)
    g = orchestration.graph(run)
    assert "plan>resolve:judge" not in _ids(g) and "plan>resolve:dm" in _ids(g)


def test_leaving_a_layer_returns_to_the_one_it_was_entered_from(tmp_path):
    """O4 (10-06), the engine's own stateful layers (a pack may still declare one): a layer entered from another
    remembers it; leaving goes back there."""
    from test_engine_v3 import _install

    from neonrp.core import modes
    from neonrp.core.registry import load_registry

    root = _install(tmp_path)
    reg = load_registry(root)
    modes.write_mode(root, {"name": "dungeon", "since_turn": 1, "note": "", "state": {"room": "R1"}})
    modes.enter(root, reg, "duel", turn=2, note="")
    m = modes.read_mode(root)
    assert m["name"] == "duel" and m["return"]["name"] == "dungeon"
    modes.leave(root)
    back = modes.read_mode(root)
    assert back and back["name"] == "dungeon" and back["state"] == {"room": "R1"}
    modes.enter(root, load_registry(root), "duel", turn=3, note="")
    modes.leave(root)
    modes.leave(root)
    assert modes.read_mode(root) is None, "no layer before: leaving ends in none, as before"


def test_hooks_lists_what_an_editor_may_pick(tmp_path):
    """O5 (10-06): seams + the handler in use, handler names, edge triggers, judges, ops, modes, ticks."""
    from test_engine_v3 import _install

    from neonrp.core import orchestration

    root = _install(tmp_path)
    h = orchestration.hooks(root)
    assert set(h["on"]) >= {"op", "dm", "judge", "here_class"} and h["judges"] == ["settled"]
    assert "roll_check" in h["seams"] and h["seams"]["roll_check"]
    assert "combat" in h["modes"] and h["modes"]["combat"]["one_shot"] is True and "exit" not in h["modes"]["combat"]
    assert "dice" in h["ops"] and h["ops"]["dice"]["kind"] == "tool"
    assert any("downed" in t for t in h["ticks"]) and h["handlers"]


def test_graph_test_runs_a_script_through_a_stub_and_reports_the_walk():
    """O6 (10-06): scripted lines through a stub model → the state sequence and the edges walked; no network."""
    from neonrp.core import graph_test

    res = graph_test.run({"world": "stoneford-elena", "lines": ["开始游戏", "我四处看看", "@dm 去主街"],
                          "replies": ["<lines>\n雾很重。\n</lines>\nnext: wait", "<lines>\n去主街。\n</lines>\nnext: advance",
                                      "<lines>\n你走上主街。\n</lines>", "<vars>\nlocation = T001/main_street\n</vars>\n<files>\n</files>"]})
    assert [s["nodes"] for s in res["steps"]] == [["plan"], ["plan"], ["plan", "resolve"]]
    assert res["steps"][2]["advanced_by"] == "player"
    assert "plan>resolve:dm" in res["edges"]["walked"] and "plan>resolve:judge" not in res["edges"]["walked"]
    assert "host" in res["model_calls"] and "transition" in res["model_calls"]


def test_background_units_are_declared_checked_and_held_to_their_scope(tmp_path, monkeypatch):
    """O7 (10-06): ticks and the characters elsewhere are units of the graph — what each may write, LLM or not;
    overlapping writes lint as a conflict; a unit's op outside its declared writes is refused at apply."""
    from test_engine_v3 import _install

    from neonrp.core import orchestration as O
    from neonrp.core import sdk
    from neonrp.core.registry import load_registry
    from neonrp.packs.rpg import downed

    root = _install(tmp_path)
    g = O.graph(root)
    names = {u["name"]: u for u in g["units"]}
    assert {"effects", "souls_elsewhere", "downed", "effects_clock"} <= set(names) and names["souls_elsewhere"]["llm"]
    assert not [x for x in g["lint"] if x["code"] == "orch.unit_conflict"], g["lint"]
    clash = O.lint_units([{"name": "a", "writes": ["var:faction.*"]}, {"name": "b", "writes": ["var:faction.guard.power"]}])
    assert clash and clash[0]["code"] == "orch.unit_conflict"
    orig = downed.tick

    def rogue(root_, reg, *, turn=0, res=None):
        return [{"op": "set", "var": "town.alert", "value": 5}] + orig(root_, reg, turn=turn, res=res)

    rogue.unit = orig.unit
    monkeypatch.setattr(downed, "tick", rogue)
    reg = load_registry(root)
    if "town.alert" not in reg.variables:
        return
    a0 = reg.variables["town.alert"].value
    r = sdk.apply(root, [], reg, turn=1)
    assert any("outside its declared writes" in str(x.get("why")) for x in r.refused)
    assert load_registry(root).variables["town.alert"].value == a0
