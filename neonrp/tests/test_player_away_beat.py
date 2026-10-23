"""A beat with the player away (10-21 · TEMPLATE-LAYERS-1019 §2.2 / stage B): ``turn_v3.solve_turn(player_present=False)``
settles what someone in the world does and lands nothing on the player — no move of theirs, no value of theirs, no thing
they hold (sdk.verify refuses it, world scope). The default (the player's own turn) is unchanged. Stub model, no network."""
from __future__ import annotations

from pathlib import Path

from _paths import PRODUCT_TEMPLATES
from neonrp.core import graph_test as G
from neonrp.core import sdk, turn_v3
from neonrp.core.registry import load_registry

PROSE = "<lines>\n薇拉在工坊里敲了一下午,港务所那边都听见了。\n</lines>"
MOVES = "<vars>\nlocation = T001/workshop\nplayer.gold = 5\ntown.alert = 1\n</vars>\n<files>\n</files>"


def _run(tmp_path: Path, name: str) -> Path:
    return G._world({"template": str(PRODUCT_TEMPLATES / "wuwu.template"), "root": str(tmp_path / name)}, tmp_path)


def _vals(root: Path) -> dict:
    reg = load_registry(root)
    return {k: reg.variables[k].value for k in ("location", "player.gold", "town.alert")}


def _solve(root: Path, monkeypatch, **kw) -> dict:
    world = G._ScriptAdapter([PROSE, MOVES])
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root, provider: world)
    return turn_v3.solve_turn(root, user_text="", provider=None, turn=0, soul_reports=[{"name": "薇拉", "text": "去工坊敲打绞盘"}], **kw)


def test_with_the_player_away_nothing_lands_on_them(tmp_path, monkeypatch):
    root = _run(tmp_path, "away")
    before = _vals(root)
    out = _solve(root, monkeypatch, player_present=False)
    after = _vals(root)
    assert after["town.alert"] == 1, "what happens in the world lands"
    assert after["location"] == before["location"] and after["player.gold"] == before["player.gold"], "nothing of the player's moves"
    whys = [r for r in (out.get("verify") or {}).get("refused") or [] if "player is not here" in str(r.get("why"))]
    assert {r["field"] for r in whys} >= {"who", "var"}, "verify said why: the player's move and the player's value"
    assert sdk.PLAYER_AWAY.get() is False, "the flag is the beat's only"


def test_the_players_own_turn_is_as_before(tmp_path, monkeypatch):
    root = _run(tmp_path, "here")
    _solve(root, monkeypatch)
    after = _vals(root)
    assert after["player.gold"] == 5 and after["town.alert"] == 1 and after["location"] == "T001/workshop"


def test_touches_player_reads_ids_names_vars_and_what_they_hold(tmp_path):
    reg = load_registry(_run(tmp_path, "reg"))
    assert sdk.touches_player(reg, {"op": "move_to", "who": "player", "to": "T001/workshop"}) == "who"
    assert sdk.touches_player(reg, {"op": "set", "var": "player.gold", "value": 1}) == "var"
    assert sdk.touches_player(reg, {"op": "set", "var": "town.alert", "value": 1}) is None
    assert sdk.touches_player(reg, {"op": "move_to", "who": "si-vera0001", "to": "T001/workshop", "note": "player"}) is None, "free text is not read"
