"""Play contracts (R1) and settlement (R5) — engine side (「死亡结算算在 Template 的合约里」)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_engine_v3 import _install

from neonrp.core import sdk, settlement
from neonrp.core.registry import VarSpec, load_registry
from neonrp.packs.rpg import plot as P
from neonrp.template import contract as C
from neonrp.template import load as load_template
from _paths import PRODUCT_TEMPLATES


# ── reading ──────────────────────────────────────────────────────────────────

def test_the_four_official_contracts_read_and_carry_deaths():
    for ref in ("mystery-trpg@1", "open-adventure@1", "murder-mystery@1", "romance-companion@1"):
        c = C.load(ref)
        d = C.deaths(c)
        assert C.ends_run(d["player"]) and d["player"]["ending_kind"] == "fail", ref
        assert not C.ends_run(d["other"]), ref
    assert C.ends_run(C.deaths(C.load("romance-companion@1"))["companion"]), "the beloved's death ends the route"
    assert not C.ends_run(C.deaths(C.load("mystery-trpg@1"))["companion"])
    assert C.ends_run(C.deaths(C.load("mystery-trpg@1"))["insanity"])


def test_unknown_contract_wrong_version_and_the_env_path(tmp_path, monkeypatch):
    with pytest.raises(C.ContractError):
        C.load("nope@1")
    with pytest.raises(C.ContractError):
        C.load("mystery-trpg@9")
    d = tmp_path / "contracts"
    d.mkdir()
    (d / "house.play-contract.json").write_text(json.dumps({"schema": C.SCHEMA, "id": "house", "version": 2}), encoding="utf-8")
    monkeypatch.setenv("NEONRP_PLAY_CONTRACT_PATH", str(d))
    assert C.load("house@2")["id"] == "house" and "house" in C.available()
    assert C.deaths(C.load("house@2")) == C.DEFAULT_DEATHS, "no deaths section: the defaults"


# ── lint by contract ─────────────────────────────────────────────────────────

def _tpl(tmp_path: Path, contract: str, *, opening: bool = True, souls: bool = True) -> tuple:
    w = tmp_path / "world"
    (w / "game" / "meta").mkdir(parents=True)
    if opening:
        (w / "game" / "meta" / "game-start.json").write_text(json.dumps({"startup": {"opening_scene": "雾。"}}), encoding="utf-8")
    td = tmp_path / "t.template"
    td.mkdir()
    (td / "template.json").write_text(json.dumps({"id": "t", "card": {"title": "T"}, "world": {"path": str(w)},
                                                  "souls": [{"sid": "a"}] if souls else [], "play_contract": contract}),
                                      encoding="utf-8")
    return load_template(td), w


def _plot(endings: dict, *, reach: bool = True, reveal: bool = False) -> dict:
    trig = {f"t_{e}": {"when": {"turn": True}, "then": [{"to": "end", "ending": e}]} for e in endings} if reach else {}
    return {"id": "P1", "endings": endings, "triggers": trig, **({"reveal": {"truth": "x"}} if reveal else {})}


def _codes(probs) -> set[str]:
    return {f"{lv}:{code}" for lv, code, _w, _m in probs}


def test_lint_unknown_contract(tmp_path):
    t, w = _tpl(tmp_path, "nope@1")
    assert _codes(C.lint(t, [], w)) == {"block:contract.unknown"}


def test_lint_entry_needs_an_opening_and_a_fixed_cast(tmp_path):
    t, w = _tpl(tmp_path, "mystery-trpg@1", opening=False, souls=False)
    codes = _codes(C.lint(t, [], w))
    assert "block:contract.entry" in codes
    entry = [x for x in C.lint(t, [], w) if x[1] == "contract.entry"]
    assert {x[2] for x in entry} == {"entry.opening", "entry.cast"}
    t2, w2 = (lambda tw: tw)(_tpl(tmp_path / "ok", "mystery-trpg@1"))
    assert not [x for x in C.lint(t2, [], w2) if x[1] == "contract.entry"]


def test_lint_exit_endings_reveal_rewards_deaths(tmp_path):
    t, w = _tpl(tmp_path, "mystery-trpg@1")
    bad = C.lint(t, [_plot({"E1": {"title": "a", "kind": "alt"}}, reach=False)], w)
    codes = {x[1] for x in bad}
    assert {"contract.exit", "contract.endings", "contract.reveal", "contract.rewards", "contract.deaths"} <= codes
    assert any(x[2] == "endings.require.true" for x in bad) and any(x[2] == "endings.min" for x in bad)
    deaths = [x for x in bad if x[1] == "contract.deaths"]
    assert {x[2] for x in deaths} == {"deaths.player", "deaths.insanity"} and {x[0] for x in deaths} == {"warn"}, \
        "the engine gives a plain death exit"
    img = {"assets": {"image": "e.png"}}
    good = C.lint(t, [_plot({"E1": {"title": "真相", "kind": "true", **img}, "E2": {"title": "逃离", "kind": "alt", **img},
                             "E3": {"title": "死", "kind": "fail", **img}}, reveal=True)], w)
    assert good == [], good


def test_the_dnd_like_template_meets_open_adventure_without_blocks():
    from neonrp.template import lint

    r = lint(PRODUCT_TEMPLATES / "stoneford-three-towns.template")
    contract = [p for p in r["problems"] if p["code"].startswith("contract.")]
    assert r["meta"].get("play_contract") == "open-adventure@1"
    assert not [p for p in contract if p["level"] == "block"], contract


# ── settlement ───────────────────────────────────────────────────────────────

def _run(tmp_path: Path, contract: str | None, *, endings: dict | None = None, trigger_end: str | None = None) -> Path:
    root = _install(tmp_path)
    meta = root / "game" / "meta"
    if contract:
        (meta / "play_contract.json").write_text(json.dumps({**C.load(contract), "_ref": contract}, ensure_ascii=False), encoding="utf-8")
    if endings:
        pd = tmp_path / "plot"
        pd.mkdir()
        trig = {"t_end": {"when": {"turn": True}, "then": [{"to": "end", "ending": trigger_end}], "once": True}} if trigger_end else {}
        (pd / "plot.json").write_text(json.dumps({"id": "P9", "title": "雾", "endings": endings, "triggers": trig}, ensure_ascii=False),
                                      encoding="utf-8")
        for e in endings.values():
            img = (e.get("assets") or {}).get("image")
            if img:
                (pd / img).write_bytes(b"\x89PNG\r\n\x1a\n")
        P.install(root, pd)
    return root


def _kill(root: Path, who: str) -> None:
    from neonrp.packs.rpg import character_state as cs

    cs.write(root, who, down=1, dead=1)


FAIL = {"E9": {"title": "雾里倒下", "kind": "fail", "text": "你没有再醒来。", "assets": {"image": "e9.png"}}}


def test_the_players_death_exits_on_the_fail_ending(tmp_path):
    root = _run(tmp_path, "mystery-trpg@1", endings=FAIL)
    _kill(root, "player")
    res = sdk.apply(root, [], load_registry(root), turn=5)
    s = settlement.read(root)
    assert s and s["exit"] == {"kind": "death", "id": "E9", "turn": 5} and s["cg_unlocked"] == ["E9"]
    assert s["epilogue"] == "你没有再醒来。" and s["contract"] == "mystery-trpg@1"
    assert [d["kind"] for d in s["deaths"]] == ["player"]
    assert res.settled == s and res.ended["id"] == "E9"
    assert json.loads((root / "game" / "meta" / "ending.json").read_text(encoding="utf-8"))["id"] == "E9"
    assert any(e.get("type") == "run.settled" for e in res.events)
    assert set(s["rewards"]) == {"player", "soul", "world"} and s["rewards"]["player"]["ending_cg"] == ["E9"]


def test_without_a_fail_ending_or_a_contract_the_death_is_a_plain_exit(tmp_path):
    root = _run(tmp_path, None)
    _kill(root, "player")
    sdk.apply(root, [], load_registry(root), turn=3)
    s = settlement.read(root)
    assert s["exit"]["kind"] == "death" and s["exit"]["id"] == "death" and s["cg_unlocked"] == [] and s["contract"] is None


def test_a_companions_death_is_recorded_and_the_run_goes_on(tmp_path):
    root = _run(tmp_path, "mystery-trpg@1", endings=FAIL)
    soul = next(e for e in load_registry(root).of_class("soul"))
    _kill(root, soul.id)
    res = sdk.apply(root, [], load_registry(root), turn=4)
    assert settlement.read(root) is None and res.settled is None and not res.ended
    rows = json.loads((root / "game" / "meta" / "deaths.json").read_text(encoding="utf-8"))
    assert rows == [{"who": soul.id, "name": soul.name, "kind": "companion", "turn": 4, "cause": "dead"}]
    sdk.apply(root, [], load_registry(root), turn=5)
    assert len(json.loads((root / "game" / "meta" / "deaths.json").read_text(encoding="utf-8"))) == 1, "recorded once"
    _kill(root, "player")
    sdk.apply(root, [], load_registry(root), turn=6)
    assert [d["kind"] for d in settlement.read(root)["deaths"]] == ["companion", "player"]


def test_in_a_romance_the_beloveds_death_ends_the_route(tmp_path):
    root = _run(tmp_path, "romance-companion@1", endings=FAIL)
    soul = next(e for e in load_registry(root).of_class("soul"))
    _kill(root, soul.id)
    sdk.apply(root, [], load_registry(root), turn=2)
    assert settlement.read(root)["exit"] == {"kind": "death", "id": "E9", "turn": 2}


def test_an_ending_trigger_settles_with_its_cg_and_only_once(tmp_path):
    root = _run(tmp_path, "mystery-trpg@1", endings={"E1": {"title": "真相", "kind": "true", "text": "雾散了。", "assets": {"image": "e1.png"}}},
                trigger_end="E1")
    res = sdk.apply(root, [], load_registry(root), turn=7)
    s = settlement.read(root)
    assert res.ended and s["exit"] == {"kind": "ending", "id": "E1", "turn": 7} and s["cg_unlocked"] == ["E1"] and s["epilogue"] == "雾散了。"
    before = (root / "game" / "meta" / "settlement.json").read_text(encoding="utf-8")
    _kill(root, "player")
    res2 = sdk.apply(root, [], load_registry(root), turn=8)
    assert res2.settled is None and (root / "game" / "meta" / "settlement.json").read_text(encoding="utf-8") == before


def test_the_downed_rule_rolling_to_death_settles(tmp_path):
    """hp 0 → down → the pack's down rule each Resolve → dead (or stable) — dead settles the run."""
    root = _run(tmp_path, "mystery-trpg@1", endings=FAIL)
    sdk.apply(root, [{"op": "set", "var": "player.hp", "value": 0}], load_registry(root), turn=1)
    for t in range(2, 14):
        sdk.apply(root, [], load_registry(root), turn=t)
        st = json.loads((root / "game" / "states" / "player.json").read_text(encoding="utf-8"))
        if st.get("dead") or st.get("stable"):
            break
    s = settlement.read(root)
    if st.get("dead"):
        assert s and s["exit"]["kind"] == "death" and s["exit"]["id"] == "E9"
    else:
        assert s is None, "stable: no exit"


def test_insanity_exits_when_the_contract_says_so(tmp_path):
    root = _run(tmp_path, "mystery-trpg@1", endings=FAIL)
    reg = load_registry(root)
    (root / "game" / "player" / "san.json").write_text(json.dumps({"san": 0}), encoding="utf-8")
    reg.variables["player.san"] = VarSpec("player.san", "int", "game/player/san.json", "san", 0, min=0)
    res = sdk.ApplyResult(turn=3)
    out = settlement.after_apply(root, reg, res, turn=3)
    assert out and out["exit"] == {"kind": "insanity", "id": "E9", "turn": 3}


def test_an_open_adventure_day_is_a_segment_not_an_exit(tmp_path):
    root = _run(tmp_path, "open-adventure@1")
    reg = load_registry(root)
    d0 = int(reg.variables["time.day"].value)
    sdk.apply(root, [{"op": "add", "var": "time.day", "delta": 1}], reg, turn=2)
    assert (root / "game" / "meta" / "segments" / f"day-{d0}.json").exists() and settlement.read(root) is None
