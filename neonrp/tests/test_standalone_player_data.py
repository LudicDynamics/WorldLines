"""角色可单独出场 standalone · 玩家自己的记录(10-15)。

① soul.json 的 standalone: true = 作者同意这个角色离开世界单独聊 / 单独发布;主角(game/player/profile.json)同样可标。
  模板 meta(/api/v1/local/templates)带 standalone 列表;/api/v1/local/souls 每个角色带 standalone;lint 只认 true / false
② 玩家数据 ~/.worldlines/player-data/<玩家>.json:已获得角色 · 已解锁结局 · 成就(id + 时间 + 来源世界);
  GET /api/v1/local/player-data;结局落地写结局;获得角色只有一条路:takeable 的角色满足 take_when(companion_at_ending
  默认 · ending:<id>)就带走,带完整记忆;standalone 角色聊过只记进 talked,不算获得(10-15,PLATFORM-PLAY-RULES §3 §5)

stub,不调模型;wuwu · spice-witch · stoneford-town · neon-rebirth。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from pathlib import Path
from unittest.mock import patch

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import player_data, sdk
from neonrp.core.registry import load_registry
from neonrp.template import builder


def test_templates_list_their_standalone_characters():
    want = {"wuwu": {"vera", "player"}, "spice-witch": {"maestro", "player"}, "stoneford-town": {"elena", "player"}, "last-train": {"player"}}
    for name, sids in want.items():
        t = TP.load(PRODUCT_TEMPLATES / f"{name}.template")
        assert set(t.standalone) == sids and set(t.meta()["standalone"]) == sids, name
    assert "severin" not in TP.load(PRODUCT_TEMPLATES / "spice-witch.template").standalone, "only where the author said yes"


def test_the_soul_library_carries_it_and_keeps_it(tmp_path):
    from neonrp.core import souls

    d = souls.SOUL_HOME / "vera-si-vera0001"
    shutil.copytree(PRODUCT_TEMPLATES / "wuwu.template" / "world" / "souls" / "vera-si-vera0001", d)
    row = next(s for s in souls.list_souls() if s["sid"] == "vera")
    assert row["standalone"] is True
    assert row["takeable"] is True and row["take_when"] == "companion_at_ending"
    meta = souls.read_soul_json(d)
    meta.takeable, meta.take_when = True, "ending:E01"
    souls.write_soul_json(d, meta)  # a rewrite of soul.json does not drop them
    sj = json.loads((d / "soul.json").read_text(encoding="utf-8"))
    assert sj["standalone"] is True and sj["take_when"] == "ending:E01" and "takeable" not in sj


def test_lint_takes_true_or_false_only(tmp_path):
    d = tmp_path / "wuwu.template"
    shutil.copytree(PRODUCT_TEMPLATES / "wuwu.template", d)
    p = d / "world" / "souls" / "vera-si-vera0001" / "soul.json"
    sj = json.loads(p.read_text(encoding="utf-8"))
    sj["standalone"] = "yes"
    p.write_text(json.dumps(sj, ensure_ascii=False), encoding="utf-8")
    probs = [x for x in TP.lint(TP.load(d), i18n=False)["problems"] if x["code"] == "soul.standalone"]
    assert probs and probs[0]["level"] == "block"
    assert "vera" not in TP.load(d).standalone


def _wuwu(tmp_path: Path) -> Path:
    dest = tmp_path / "wuwu-run"
    TP.build(TP.load(PRODUCT_TEMPLATES / "wuwu.template"), dest)
    return dest


def test_talking_is_noted_but_not_gained(tmp_path):
    root = _wuwu(tmp_path)
    souls = player_data.standalone_souls(root)
    vera = next(i for i, s in souls.items() if s["sid"] == "vera")
    assert set(s["sid"] for s in souls.values()) == {"vera"}
    other = next(e.id for e in load_registry(root).of_class("soul") if e.id != vera)
    got = player_data.after_turn(root, [{"iid": vera, "kind": "speak", "text": "「嗯。」"}, {"iid": other, "kind": "speak", "text": "「……」"},
                                        {"iid": vera, "kind": "gesture", "text": ""}])
    assert got == [vera], "only a standalone character who answered in words"
    assert player_data.after_turn(root, [{"iid": vera, "kind": "speak", "text": "「又见面了。」"}]) == [], "once"
    assert player_data.gain(root, vera, "talked") is False, "talking twice is still only talking"
    d = player_data.read()
    assert d["characters"] == [], "talking does not gain her"
    assert d["player"] == "local" and [(c["sid"], c["world"]) for c in d["talked"]] == [("vera", "wuwu")] and d["talked"][0]["at"]


def _neon(tmp_path: Path, tag: str, **kuon: object) -> Path:
    tpl = tmp_path / "neon-rebirth.template"
    if not tpl.exists():
        shutil.copytree(PRODUCT_TEMPLATES / "neon-rebirth.template", tpl)
    t = TP.load(tpl)
    draft = {"fields": {"name": "早濑", "look": "黑色雨衣", "origin": "hacker", "past": "旧地铁网", "regret": "那通电话",
                        "attrs": {"体": 4, "技": 5, "识": 4, "魂": 4, "运": 3}}, "companion": "kuon"}
    errs, norm = builder.check(t, draft)
    assert not errs, errs
    t = builder.select_cast(t, norm)
    dest = tmp_path / f"neon-{tag}"
    TP.build(t, dest)
    builder.apply(t, dest, norm)
    if kuon:  # this run's copy of 久远 says so (the template's own keeps the defaults)
        p = next((dest / "souls").glob("kuon-*/soul.json"))
        p.write_text(json.dumps({**json.loads(p.read_text(encoding="utf-8")), **kuon}, ensure_ascii=False), encoding="utf-8")
    return dest


def _end_e04(root: Path) -> None:
    r = sdk.apply(root, [], load_registry(root), turn=1, player_says="我用一枚书签写下:回到你的书里去吧", narration="……")
    assert r.ended and r.ended["id"] == "E04"


def test_by_default_the_companion_at_the_ending_comes_home_with_full_memory(tmp_path):
    _end_e04(_neon(tmp_path, "default"))
    d = player_data.read()
    assert [(e["id"], e["world"]) for e in d["endings"]] == [("E04", "neon-rebirth")] and d["endings"][0]["title"]
    assert [(c["sid"], c["how"], c.get("memory")) for c in d["characters"]] == [("kuon", "companion_at_ending", "full")]
    _end_e04(_neon(tmp_path, "again"))
    assert len(player_data.read()["endings"]) == 1 and len(player_data.read()["characters"]) == 1, "once per world"


def test_the_author_can_keep_a_character_or_tie_it_to_one_ending(tmp_path, monkeypatch):
    _end_e04(_neon(tmp_path, "kept", takeable=False))
    assert player_data.read()["characters"] == [], "takeable: false — stays in its world"
    monkeypatch.setenv("WORLDLINES_PLAYER_ID", "p2")
    _end_e04(_neon(tmp_path, "other-ending", take_when="ending:E01"))
    assert player_data.read()["characters"] == [], "taken only on E01"
    monkeypatch.setenv("WORLDLINES_PLAYER_ID", "p3")
    _end_e04(_neon(tmp_path, "this-ending", take_when="ending:E04"))
    assert [(c["sid"], c["how"]) for c in player_data.read()["characters"]] == [("kuon", "ending:E04")]


def test_talked_then_taken_only_when_the_condition_holds(tmp_path):
    root = _neon(tmp_path, "talk", standalone=True)
    kuon = next(i for i, s in player_data.run_souls(root).items() if s["sid"] == "kuon")
    assert player_data.after_turn(root, [{"iid": kuon, "kind": "speak", "text": "「嗯。」"}]) == [kuon]
    d = player_data.read()
    assert d["characters"] == [] and [c["sid"] for c in d["talked"]] == ["kuon"]
    _end_e04(root)
    d = player_data.read()
    assert [(c["sid"], c["how"], c["memory"]) for c in d["characters"]] == [("kuon", "companion_at_ending", "full")]
    assert [c["sid"] for c in d["talked"]] == ["kuon"], "the talked note stays as it was"


def test_take_rules_show_in_the_template_and_are_linted(tmp_path):
    t = TP.load(PRODUCT_TEMPLATES / "neon-rebirth.template")
    assert t.take["kuon"] == "companion_at_ending" and t.meta()["take"]["kuon"] == "companion_at_ending"
    d = tmp_path / "wuwu.template"
    shutil.copytree(PRODUCT_TEMPLATES / "wuwu.template", d)
    p = d / "world" / "souls" / "vera-si-vera0001" / "soul.json"
    base = json.loads(p.read_text(encoding="utf-8"))
    ends = sorted({e for rel in TP.load(d).plots for e in (json.loads((d / rel / "plot.json").read_text(encoding="utf-8")).get("endings") or {})})

    def codes(**kw):
        p.write_text(json.dumps({**base, **kw}, ensure_ascii=False), encoding="utf-8")
        return {x["code"] for x in TP.lint(TP.load(d), i18n=False)["problems"] if x["level"] == "block" and x["code"].startswith("soul.")}

    assert codes(takeable="no") == {"soul.takeable"}
    assert codes(take_when="when_she_smiles") == {"soul.take_when"}
    assert codes(take_when="ending:NOPE") == {"soul.take_when"}, "an ending this world has"
    assert codes(take_when=f"ending:{ends[0]}") == set()
    assert TP.load(d).take["vera"] == f"ending:{ends[0]}"
    assert codes(takeable=False) == set() and TP.load(d).take["vera"] is None


def test_achievements_and_players_are_separate(monkeypatch):
    assert player_data.unlock_achievement("first_night", "neon-rebirth", "ending:E01")
    assert not player_data.unlock_achievement("first_night", "neon-rebirth", "ending:E01")
    monkeypatch.setenv("WORLDLINES_PLAYER_ID", "acct-42")
    assert player_data.read()["player"] == "acct-42" and player_data.read()["achievements"] == []
    monkeypatch.delenv("WORLDLINES_PLAYER_ID")
    assert [a["id"] for a in player_data.read()["achievements"]] == ["first_night"]


def test_http_player_data_and_template_rows(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "wuwu.template", store / "wuwu.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    player_data.unlock_achievement("a1", "wuwu")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/api/v1/local/player-data", timeout=60) as r:
                d = json.loads(r.read())
            assert d["player"] == "local" and [a["id"] for a in d["achievements"]] == ["a1"] and d["endings"] == []
            with urllib.request.urlopen(base + "/api/v1/local/templates", timeout=120) as r:
                rows = {x["id"]: x for x in json.loads(r.read())["templates"]}
            assert set(rows["wuwu"]["standalone"]) == {"vera", "player"}
        finally:
            server.shutdown()
