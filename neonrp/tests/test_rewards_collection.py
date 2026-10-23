"""World rewards → the player's collection (10-18, core/rewards): a template declares its reward cards as data (``rewards``,
conditions from the achievements' list), its play contract lets them out (``rewards.player`` has ``cards``), the engine
hands each out once when its conditions hold (event ``reward.granted``), the card and its picture are kept beside the
player's record and never taken back; an author's new version can be pulled. Plus the generic 「打完一局」(``runs`` +
``run_complete``) and a contract's own achievements."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from neonrp import template
from neonrp.core import achievements, beat_events, player_data, rewards, sdk
from neonrp.core.registry import load_registry
from neonrp.template import contract as C

TEMPLATES = Path(__file__).resolve().parents[1] / "worldlines" / "templates"


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setattr(player_data, "HOME", tmp_path / "player-data")
    rewards._STORE.clear()


def _build(name: str, dest: Path, edit=None) -> Path:
    src = TEMPLATES / f"{name}.template"
    if edit is not None:
        cp = dest.parent / f"{name}-copy.template"
        shutil.copytree(src, cp)
        edit(cp)
        src = cp
    template.build(template.load(src), dest)
    return dest


def _edit(fn):
    def go(cp: Path) -> None:
        p = cp / "template.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return go


def _beat(root: Path, turn: int, says: str = "", ops: list | None = None):
    return sdk.apply(root, list(ops or []), load_registry(root), turn=turn, player_says=says, narration=says)


def _stage(root: Path, turn: int, n: int):
    return _beat(root, turn, "", [{"op": "set", "var": "P01.stage", "value": n}])


# ── 灰橡宅 (mystery-trpg) ────────────────────────────────────────────────────

def test_a_stage_reached_hands_out_its_card_once_with_its_picture(tmp_path):
    root = _build("pct-house", tmp_path / "run")
    r = _stage(root, 1, 1)
    assert [c["id"] for c in r.rewards] == ["half_burnt_diary"]
    got = r.rewards[0]
    assert got["kind"] == "card" and got["rarity"] == "common" and got["title"] == "烧了一半的日记"
    assert got["image"] and got["image"].startswith("/api/v1/local/player-data/card?world=pct-house")
    kept = player_data.read()["cards"]
    assert len(kept) == 1 and kept[0]["version"] == "0.2" and kept[0]["run"] == "run"
    assert (rewards.card_dir("pct-house") / kept[0]["image"]).is_file(), "the picture is copied beside the record"
    assert _stage(root, 2, 1).rewards == [], "once"
    evs, _ = beat_events.from_traces([{"turn_seq": 1, "apply": r.to_dict()}])
    assert ("reward.granted", {"turn": 1, **got}) in evs


def test_an_ending_hands_out_its_card_settles_the_run_and_unlocks_the_contracts_achievement(tmp_path):
    root = _build("pct-house", tmp_path / "run")
    _stage(root, 1, 1)
    r = _beat(root, 2, "我要离开这里,逃出去")
    assert r.ended and r.ended["id"] == "E02" and r.settled
    assert {c["id"] for c in r.rewards} == {"way_out_in_fog"}
    assert r.settled["rewards"]["player"]["cards"] == ["half_burnt_diary", "way_out_in_fog"]
    st = json.loads((root / "game" / "meta" / "settlement.json").read_text(encoding="utf-8"))
    assert st["rewards"]["player"]["cards"] == ["half_burnt_diary", "way_out_in_fog"]
    runs = player_data.read()["runs"]
    assert runs == [{**runs[0], "world": "pct-house", "run": "run", "exit": "ending", "ending": "E02", "version": "0.2"}]
    ids = {a["id"] for a in r.achievements}
    assert {"run_complete", "first_ending", "walked_out"} <= ids, ids
    walked = next(a for a in r.achievements if a["id"] == "walked_out")
    assert walked["title"] == "另一扇门" and walked["points"] == 10
    assert achievements.describe("walked_out", "pct-house", "en")["title"] == "Another Door"


def test_the_same_card_in_a_second_run_is_not_handed_out_again(tmp_path):
    _stage(_build("pct-house", tmp_path / "run"), 1, 1)
    assert _stage(_build("pct-house", tmp_path / "run2"), 1, 1).rewards == []
    assert len(player_data.read()["cards"]) == 1


def test_a_free_zone_template_hands_no_cards_out_and_lint_says_so(tmp_path):
    def open_zone(d):
        d["zone"] = "open"
        d.pop("forkable", None)
    root = _build("pct-house", tmp_path / "run", _edit(open_zone))
    assert _stage(root, 1, 1).rewards == []
    msgs = [p["msg"] for p in template.lint(template.load(tmp_path / "pct-house-copy.template"))["problems"] if p["code"] == "meta.rewards"]
    assert any("Free-Zone" in m for m in msgs)


def test_a_contract_without_cards_hands_none_out(tmp_path, monkeypatch):
    real = C.load

    def no_cards(ref):
        d = real(ref)
        d["rewards"] = {**d["rewards"], "player": [x for x in d["rewards"]["player"] if x != "cards"]}
        return d
    monkeypatch.setattr(C, "load", no_cards)
    root = _build("pct-house", tmp_path / "run")
    assert _stage(root, 1, 1).rewards == []
    probs = template.lint(template.load(TEMPLATES / "pct-house.template"))["problems"]
    assert any(p["code"] == "meta.rewards" and "does not hand out" in p["msg"] for p in probs)


# ── 石津镇 (open-adventure) ──────────────────────────────────────────────────

def test_flags_and_all_three_vars_hand_out_the_towns_cards(tmp_path):
    root = _build("stoneford-town", tmp_path / "run")
    r = _beat(root, 1, "", [{"op": "flag", "key": "has_map"}])
    assert [c["id"] for c in r.rewards] == ["old_fog_map"]
    _beat(root, 2, "", [{"op": "set", "var": "P20.pass", "value": 1}, {"op": "set", "var": "P20.route", "value": 1}])
    assert "three_for_the_gate" not in {c["id"] for c in player_data.read()["cards"]}, "a list = every condition"
    r = _beat(root, 3, "", [{"op": "set", "var": "P20.road", "value": 1}])
    assert [c["id"] for c in r.rewards] == ["three_for_the_gate"] and r.rewards[0]["image"] is None, "no picture = plain face"


def test_the_built_in_worlds_rewards_lint_clean():
    for t in ("pct-house", "stoneford-town"):
        probs = template.lint(template.load(TEMPLATES / f"{t}.template"))["problems"]
        assert not [p for p in probs if p["code"] == "meta.rewards"], (t, probs)


# ── lint / contracts ─────────────────────────────────────────────────────────

def test_reward_rows_are_linted_mostly_as_warnings():
    probs = rewards.validate([{"title": "x"}, {"id": "a", "when": "ending:E99", "kind": "sticker", "rarity": "mythic"},
                              {"id": "a", "title": "dup", "when": "nonsense"}, {"id": "b", "title": "ok", "when": ["flag:x", "var:k:2"]}],
                             endings={"E01"})
    lv = {(lvl, m.split(" ")[0]) for lvl, m in probs}
    assert ("block", "rewards[0]") in lv and ("block", "rewards[2].id") in lv
    text = " | ".join(m for _, m in probs)
    assert "E99" in text and "sticker" in text and "rarity" in text and "rewards[2].when" in text and "rewards[3]" not in text
    assert rewards.validate("nope")[0][0] == "block"


@pytest.mark.parametrize("cid", sorted(C.available()))
def test_each_contract_lets_cards_out_and_its_achievements_name_no_worlds_things(cid):
    c = C.load(cid)
    assert rewards.allows(c)
    assert achievements.validate(c.get("achievements"), heads=achievements.CONTRACT_WHEN, where="achievements") == []
    for r in c.get("achievements") or []:
        assert set(r["title"]) == {"zh", "en", "ja", "ko"} and set(r["desc"]) == {"zh", "en", "ja", "ko"}, (cid, r["id"])


def test_a_contract_achievement_may_not_name_a_worlds_ending_or_flag():
    bad = achievements.validate([{"id": "x", "title": "x", "when": "ending:E01"}, {"id": "y", "title": "y", "when": "flag:k"}],
                                heads=achievements.CONTRACT_WHEN)
    assert len(bad) == 2


def test_new_conditions():
    ctx = {"ended": "E1", "ended_kind": "true", "vars": {"P.stage": 2, "k": 3}, "run_end": True}
    assert achievements.holds("ending_kind:true", ctx) and not achievements.holds("ending_kind:fail", ctx)
    assert achievements.holds("stage:P:2", ctx) and not achievements.holds("stage:P:3", ctx)
    assert achievements.holds("var:k:3", ctx) and not achievements.holds("var:missing:1", ctx)
    assert achievements.holds("run_end", ctx) and not achievements.holds("quiz_perfect", ctx)
    assert achievements.when_ok("var:a.b:1") and not achievements.when_ok("var:a.b") and achievements.when_ok("run_end")


# ── the collection (Hub) ─────────────────────────────────────────────────────

def _store(tmp_path: Path, monkeypatch, fn=None) -> Path:
    """A copy of the template standing in for the store (the author's new version)."""
    cp = tmp_path / f"store{len(list(tmp_path.glob('store*')))}" / "pct-house.template"
    shutil.copytree(TEMPLATES / "pct-house.template", cp)
    if fn is not None:
        _edit(fn)(cp)
    monkeypatch.setattr(rewards, "store_template", lambda world: template.load(cp) if world == "pct-house" else None)
    rewards._STORE.clear()
    return cp


def test_a_new_version_can_be_pulled_and_a_dropped_card_stays(tmp_path, monkeypatch):
    _stage(_build("pct-house", tmp_path / "run"), 1, 1)
    row = rewards.listing("en")["cards"][0]
    assert row["title"] == "The Half-Burnt Diary" and not row["upd"] and not row["gone"]

    def bump(d):
        d["version"] = "0.3"
        d["rewards"][0]["title"] = {"zh": "日记(新版)", "en": "The Diary, Revised"}
    _store(tmp_path, monkeypatch, bump)
    row = rewards.listing("en")["cards"][0]
    assert row["upd"] and row["title"] == "The Half-Burnt Diary", "not pulled yet"
    assert rewards.refresh("cards", "pct-house", "half_burnt_diary")["ok"]
    row = rewards.listing("en")["cards"][0]
    assert row["title"] == "The Diary, Revised" and row["version"] == "0.3" and not row["upd"]

    def drop(d):
        d["version"] = "0.4"
        d["rewards"] = d["rewards"][1:]
    _store(tmp_path, monkeypatch, drop)
    row = rewards.listing("zh")["cards"][0]
    assert row["gone"] and not row["upd"] and row["title"] == "日记(新版)", "never taken back"
    assert rewards.refresh("cards", "pct-house", "half_burnt_diary") == {"ok": False, "error": "gone"}
    assert rewards.refresh("stickers", "pct-house", "x")["error"] == "bad_kind"


# a gained character's new version from its author: the player chooses item by item (tests/test_soul_update.py, 10-20)


def test_a_reward_has_its_own_picture_slot_in_the_asset_workbench(tmp_path):
    cp = tmp_path / "pct-house.template"
    shutil.copytree(TEMPLATES / "pct-house.template", cp)
    _edit(lambda d: d["rewards"].append({"id": "new_card", "title": {"zh": "新卡"}, "when": "run_end"}))(cp)
    t = template.load(cp)
    slot = next(s for s in template.asset_slots(t, classes=False) if s["slot"] == "reward:new_card")
    assert slot["cls"] == "reward" and not slot["have"]
    assert not any(s["slot"] == "reward:half_burnt_diary" for s in template.asset_slots(t, classes=False)), "a slot reuse has none"
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    template.put_asset(t, "reward:new_card", png, ext=".png")
    t = template.load(cp)
    assert next(r for r in t.data["rewards"] if r["id"] == "new_card")["image"] == "assets/reward-new_card.png"
    assert template.slot_file(t, "reward:new_card") == (cp / "assets" / "reward-new_card.png").resolve()


def test_http_player_data_cards_picture_and_pull(tmp_path, monkeypatch):
    import threading
    import urllib.error
    import urllib.request
    from unittest.mock import patch

    from neonrp.commands.web import make_server

    _stage(_build("pct-house", tmp_path / "run"), 1, 1)
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                out = r.read()
                return out if "/card?" in path else json.loads(out)
        try:
            d = call("/api/v1/local/player-data?lang=ja")
            card = d["cards"][0]
            assert card["id"] == "half_burnt_diary" and card["title"] == "焼けかけの日記" and card["upd"] is False
            assert call(card["image"])[:4] == b"RIFF", "the kept picture (webp)"
            bump = _store(tmp_path, monkeypatch, lambda t: t.update(version="0.3"))
            assert bump.is_dir() and call("/api/v1/local/player-data?lang=ja")["cards"][0]["upd"] is True
            assert call("/api/v1/local/player-data/refresh", {"kind": "cards", "world": "pct-house", "id": "half_burnt_diary"})["ok"]
            assert call("/api/v1/local/player-data?lang=ja")["cards"][0]["upd"] is False
            for body, code in (({"kind": "cards", "world": "pct-house"}, 400), ({"kind": "cards", "world": "pct-house", "id": "nope"}, 404)):
                try:
                    call("/api/v1/local/player-data/refresh", body)
                    raise AssertionError(body)
                except urllib.error.HTTPError as e:
                    assert e.code == code
            try:
                call("/api/v1/local/player-data/card?world=pct-house&id=nope")
                raise AssertionError("404")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown()
