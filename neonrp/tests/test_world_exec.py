"""One world execution off the player's screen (10-21 · TEMPLATE-LAYERS-1019 §2.3, stage B): core/world_exec.run — the
one who acts + everyone else elsewhere (S2's away path, once each, in parallel) → the world settles it with the player
away → a world result (world_results.jsonl) · the host's inbox · each person's memory. Under the run's lock. Stub model."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp.core import graph_test as G
from neonrp.core import mechanics, run_lock, sdk, turn_v3, world_exec
from neonrp.core.registry import load_registry

VERA, KITE, MO = "si-vera0001", "si-silverkite0001", "si-oldmo0001"


@pytest.fixture(autouse=True)
def _own_run_locks(monkeypatch):
    """This module's tests see only their own runs' locks. core/run_lock is process-wide and ``world_exec.run`` (its
    ``try_hold(alone=True)``) is busy while any run's turn holds its lock in this process — a turn thread an earlier test
    module left running (its server shut down mid-turn) made two of these cases fail in the full suite under load and
    pass alone (10-21 integrate/next). A fresh table for each test here, the real one back afterwards: nothing else
    changes (a module-scoped server elsewhere keeps its own lock object, 10-22 test_system_basics)."""
    monkeypatch.setattr(run_lock, "_LOCKS", {})


def _setup(tmp_path: Path, monkeypatch):
    root = G._world({"template": str(PRODUCT_TEMPLATES / "wuwu.template"), "root": str(tmp_path / "run")}, tmp_path)
    world = G._ScriptAdapter(["<lines>\n薇拉在工坊修好了绞盘;银鸢去了灯塔。\n</lines>",
                              "<vars>\ntown.alert = 1\nplayer.gold = 9\n</vars>\n<files>\n</files>"])
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root, provider: world)
    calls: list[str] = []
    real = mechanics.get

    def get(root, seam):
        if seam != "soul_turn":
            return real(root, seam)

        def soul_turn(root, iid, **kw):
            calls.append(iid)
            assert kw.get("variant") == "S-direct"
            return {"ok": True, "name": iid, "text": "我在灯塔上看雾" if iid == KITE else "我在灯塔守夜",
                    "proposed_move": "T001/lighthouse" if iid == KITE else None}
        return soul_turn

    monkeypatch.setattr(mechanics, "get", get)
    return root, calls


def test_the_one_acts_the_others_take_their_turn_elsewhere_and_the_world_settles(tmp_path, monkeypatch):
    root, calls = _setup(tmp_path, monkeypatch)
    gold = load_registry(root).variables["player.gold"].value
    out = world_exec.run(root, {"iid": VERA, "name": "薇拉", "text": "去工坊修绞盘", "where": "T001/workshop"}, by="tick:vera")
    assert out["ok"] and sorted(calls) == sorted([KITE, MO]), "everyone else once, the one who acts not"
    reg = load_registry(root)
    assert reg.entries[VERA].parent == "T001/workshop" and reg.entries[KITE].parent == "T001/lighthouse", "their moves land"
    assert reg.variables["town.alert"].value == 1 and reg.variables["player.gold"].value == gold, "the world changes, the player's own does not"
    card = world_exec.results(root)[-1]
    assert card["by"] == "tick:vera" and [(i["iid"], i["kind"]) for i in card["items"]][0] == (VERA, "act")
    assert {i["iid"] for i in card["items"] if i["kind"] == "away"} == {KITE, MO} and any(c.get("var") == "town.alert" for c in card["changes"])
    host = sdk.render_pack(sdk.pack(root))
    assert f"world_result:{card['id']}" in host and "修好了绞盘" in host, "the host sees it next turn"
    kite = next(Path(p) for p in (root / "souls").glob(f"*-{KITE}"))
    evs = json.loads((kite / "short-term-memo" / "recent_events.json").read_text(encoding="utf-8"))["events"]
    assert any(e.get("by") == "world_result" and e.get("result") == card["id"] for e in evs), "each person remembers her line"


def test_busy_run_writes_nothing(tmp_path, monkeypatch):
    root, calls = _setup(tmp_path, monkeypatch)
    lk = run_lock.of(root)
    lk.acquire()
    try:
        assert world_exec.run(root, {"iid": VERA, "name": "薇拉", "text": "去工坊"}) == {"ok": False, "why": "busy"}
    finally:
        lk.release()
    assert calls == [] and world_exec.results(root) == []


def test_an_explicit_list_and_nobody_elsewhere(tmp_path, monkeypatch):
    root, calls = _setup(tmp_path, monkeypatch)
    out = world_exec.run(root, {"iid": VERA, "name": "薇拉", "text": "在工坊待着"}, away=[])
    assert out["ok"] and calls == [] and out["away"] == []
    assert set(world_exec.elsewhere(root, VERA)) == {KITE, MO}


def test_inside_the_players_own_turn_no_second_lock(tmp_path, monkeypatch):
    """A seam at the start of the player's turn (the turn already writes the run) settles with ``locked=True``."""
    root, calls = _setup(tmp_path, monkeypatch)
    lk = run_lock.of(root)
    lk.acquire()
    try:
        out = world_exec.run(root, {"iid": VERA, "name": "薇拉", "text": "去工坊"}, locked=True)
    finally:
        lk.release()
    assert out["ok"] and len(world_exec.results(root)) == 1
