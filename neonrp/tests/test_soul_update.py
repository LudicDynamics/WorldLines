"""A taken character when its author ships a new version (10-20; docs/planning/SOUL-REFRESH-MERGE-1020.md,
core/soul_update): a diff the player chooses from item by item — nothing follows the author on its own.

The author's version lives in a copy of the template store (the tests edit it as an author would); the player's is the
snapshot (the tests edit it as the run / the phone would)."""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp import template
from neonrp.core import player_data, rewards, soul_chat, soul_update
from neonrp.core import soul_update as U
from _paths import PRODUCT

TEMPLATES = PRODUCT / "templates"
SOUL = "world/souls/chara-si-chara0001"


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = tmp_path / "store"
    for t in ("pct-house", "stoneford-town"):
        shutil.copytree(TEMPLATES / f"{t}.template", s / f"{t}.template", ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(s))
    monkeypatch.setattr(player_data, "HOME", tmp_path / "player-data")
    rewards._STORE.clear()
    U.clear_cache()
    return s


def _author(store: Path, rel: str) -> Path:
    return store / "pct-house.template" / SOUL / rel


def _bump(store: Path, v: str = "0.3") -> None:
    p = store / "pct-house.template" / "template.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["version"] = v
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _wj(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _rj(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _take(store: Path, tmp_path: Path, name: str = "run") -> Path:
    root = tmp_path / name
    template.build(template.load(store / "pct-house.template"), root)
    iid = next(i for i, s in player_data.run_souls(root).items() if s["sid"] == "chara")
    assert player_data.take(root, iid, "truth_quiz", memory="full")
    return soul_chat.snapshot_dir("pct-house", "chara")


def _items(d, **kw):
    return [it for it in d["items"] if all(it.get(k) == v for k, v in kw.items())]


# ── taking, nothing to decide ────────────────────────────────────────────────

def test_a_take_keeps_the_players_base_and_the_picture(store, tmp_path):
    snap = _take(store, tmp_path)
    m = _rj(snap / ".wl" / "snapshot.json")
    assert m["lang"] == "zh" and m["accepted_version"] == "0.2" and m["source"] == "template"
    assert m["author_files"] and not m["pending_base"], "the author's version of the day is the author's base"
    assert (snap / ".wl" / "accepted" / "soul.md").read_bytes() == (snap / "soul.md").read_bytes()
    assert U.diff("pct-house", "chara")["items"] == [], "the author has not changed anything"
    assert not U.has_update("pct-house", "chara")
    assert (snap / ".wl" / "author" / "soul.md").is_file() and (snap / ".wl" / "orchestration.json").is_file()


def test_the_world_the_run_keeps_is_not_in_the_diff(store, tmp_path):
    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    states = tmp_path / "run" / "game" / "states"
    _wj(states / "si-chara0001.json", {"hp": 1, "down": 1})
    _wj(tmp_path / "run" / "game" / "meta" / "party.json", {"members": []})
    (snap / "long-term-memo" / "important_events.md").write_text("# 重要事件\n\n- 我们一起下了地窖\n", encoding="utf-8")
    assert U.diff("pct-house", "chara")["items"] == [], "only the author's changes make items; the run's world never does"


# ── what appears, and its default ────────────────────────────────────────────

def test_the_four_cases_of_a_field(store, tmp_path):
    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    p = "persona/core_traits.json"
    a = _rj(_author(store, p))
    a["personality_type"] = "更沉稳的委托人"            # only the author
    a["fears"] = ["地窖", "钟声"]                        # both, differently
    a["quirks"] = ["紧张时拧扣子"]                       # both, the same
    _wj(_author(store, p), a)
    mine = _rj(snap / p)
    mine["fears"] = ["地窖", "管家的脚步声"]
    mine["quirks"] = ["紧张时拧扣子"]
    mine["sid_note"] = "only mine"                       # only the player
    _wj(snap / p, mine)
    _bump(store)
    d = U.diff("pct-house", "chara")
    got = {tuple(it["path"]): it for it in _items(d, file=p)}
    assert set(got) == {("personality_type",), ("fears",)}, got.keys()
    assert got[("personality_type",)]["default"] == "theirs" and not got[("personality_type",)]["both_changed"]
    assert got[("fears",)]["default"] == "mine" and got[("fears",)]["both_changed"] and got[("fears",)]["unit"] == "list", "a list without ids is one item"
    assert got[("personality_type",)]["category"] == "settings" and got[("personality_type",)]["label"].startswith("人设")
    assert U.has_update("pct-house", "chara")


def test_lists_with_ids_are_one_item_per_id(store, tmp_path):
    inv = "character/inventory.json"
    _wj(_author(store, inv), {"sid": "chara", "items": [{"id": "lamp", "name": "黄铜提灯"}, {"id": "letter", "name": "舅舅的旧信"}]})
    snap = _take(store, tmp_path)
    assert U.diff("pct-house", "chara")["items"] == []
    _wj(_author(store, inv), {"sid": "chara", "items": [{"id": "lamp", "name": "黄铜提灯(修好了)"}, {"id": "watch", "name": "停了的怀表"}]})
    mine = _rj(snap / inv)
    mine["items"].append({"id": "key", "name": "地窖钥匙"})
    _wj(snap / inv, mine)
    U.clear_cache()
    d = U.diff("pct-house", "chara")
    got = {it["path"][-1]["id"]: it for it in _items(d, file=inv)}
    assert set(got) == {"lamp", "letter", "watch"}, "the player's own key never appears"
    assert got["lamp"]["op"] == "change" and got["letter"]["op"] == "remove" and got["watch"]["op"] == "add"
    assert got["watch"]["after"] == {"id": "lamp"} and all(it["unit"] == "list_item" and it["category"] == "state" for it in got.values())
    U.apply("pct-house", "chara", token=d["token"], all_="theirs")
    assert [x["id"] for x in _rj(snap / inv)["items"]] == ["lamp", "watch", "key"] and _rj(snap / inv)["items"][0]["name"] == "黄铜提灯(修好了)"


def test_memory_and_long_text_come_entry_by_entry(store, tmp_path):
    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    mem = "long-term-memo/important_events.md"
    (snap / mem).write_text("# 重要事件\n\n## 舅舅\n\n- 舅舅失踪前一晚在书房烧过东西\n- 我自己记得的一件事\n", encoding="utf-8")
    U._copy_tree(snap, snap / ".wl" / "accepted")  # as if taken like that
    (snap / ".wl" / "author" / mem).write_text("# 重要事件\n\n## 舅舅\n\n- 舅舅失踪前一晚在书房烧过东西\n- 舅舅常去地窖\n", encoding="utf-8")
    m = _rj(snap / ".wl" / "snapshot.json")
    m["author_files"][mem] = U._sha((snap / ".wl" / "author" / mem).read_bytes())
    U._save_meta("pct-house", "chara", m)
    _author(store, mem).write_text("# 重要事件\n\n## 舅舅\n\n- 舅舅失踪前一晚,在书房烧过东西。\n- 舅舅常去地窖,半夜也去\n\n## 管家\n\n- 管家有地窖的钥匙\n", encoding="utf-8")
    U.clear_cache()
    d = U.diff("pct-house", "chara")
    got = _items(d, file=mem)
    assert {(it["op"], it["where"]) for it in got} == {("change", "舅舅"), ("add", "管家")}, got
    ch = next(it for it in got if it["op"] == "change")
    assert ch["author_before"] == "- 舅舅常去地窖" and ch["theirs"].startswith("- 舅舅常去地窖,半夜") and ch["unit"] == "entry" and ch["category"] == "memory"
    assert not any("我自己记得" in json.dumps(it, ensure_ascii=False) for it in got), "the player's own entry never appears"
    assert not any("书房烧过" in str(it.get("theirs")) for it in got), "only punctuation changed: the same entry"
    U.apply("pct-house", "chara", token=d["token"], all_="theirs")
    text = (snap / mem).read_text(encoding="utf-8")
    assert "- 舅舅常去地窖,半夜也去" in text and "- 我自己记得的一件事" in text and "## 管家\n\n- 管家有地窖的钥匙" in text
    assert "- 舅舅常去地窖\n" not in text


def test_entries_cut_by_top_level_items_and_second_level_headings():
    es = U.entries("# 标题\n\n开头一段。\n\n- 一\n  续行\n- 二\n\n## 甲\n\n正文 a\n\n### 小节\n更多正文\n\n- 三\n")
    got = [(e["section"], e["kind"], e["text"]) for e in es]
    assert ("", "item", "- 一\n  续行") in got and ("", "item", "- 二") in got and ("甲", "item", "- 三") in got
    assert ("", "body", "# 标题\n\n开头一段。") in got and ("甲", "body", "正文 a\n\n### 小节\n更多正文") in got
    same = U.entries("- 舅舅失踪前一晚,在书房烧过东西。\n")[0]["key"] == U.entries("-   舅舅失踪前一晚,在书房烧过东西\n")[0]["key"]
    assert same, "the same entry: marker, spacing and the final full stop do not count"


def test_prose_and_pictures_and_new_files(store, tmp_path):
    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    s = _author(store, "soul.md").read_text(encoding="utf-8")
    _author(store, "soul.md").write_text(s.replace("十九岁", "二十岁"), encoding="utf-8")
    pic = U.portrait(snap)
    assert pic is not None, "the portrait came along with the take"
    src = template.slot_file(template.load(store / "pct-house.template"), "soul.portrait:chara")  # where the author keeps it
    Path(src).write_bytes(b"\x89PNG\r\n\x1a\nNEW")
    (_author(store, "stickers") / "startled.png").write_bytes(b"\x89PNG\r\n\x1a\nSTICK")
    pic.write_bytes(b"\x89PNG\r\n\x1a\nMINE")  # even if the player's picture changed: the author's picture is the default
    U.clear_cache()
    d = U.diff("pct-house", "chara")
    soul = _items(d, file="soul.md")
    assert len(soul) == 1 and soul[0]["op"] == "change" and "二十岁" in soul[0]["theirs"] and soul[0]["default"] == "theirs"
    p = _items(d, file=f"assets/{pic.name}")[0]
    assert p["unit"] == "file" and p["default"] == "theirs" and p["theirs"]["url"].endswith(f"f=assets/{pic.name}")
    st = _items(d, file="stickers/startled.png")[0]
    assert st["op"] == "add" and st["default"] == "theirs" and st["category"] == "settings"


# ── the diff JSON, choosing, saving ──────────────────────────────────────────

def _author_changes(store: Path) -> None:
    p = "persona/core_traits.json"
    a = _rj(_author(store, p))
    a["personality_type"] = "更沉稳的委托人"
    a["fears"] = ["地窖", "钟声"]
    _wj(_author(store, p), a)
    _bump(store)
    U.clear_cache()


def test_the_diff_json_and_choosing_item_by_item(store, tmp_path):
    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    _author_changes(store)
    d = U.diff("pct-house", "chara", "en")
    assert d["schema"] == "worldlines.soul-update/1" and d["from_version"] == "0.2" and d["to_version"] == "0.3" and d["token"].startswith("u_")
    assert d["base"]["unknown"] is False and d["counts"]["settings"] == 2 and d["choices"] is None
    assert {it["id"] for it in d["items"]} == {it["id"] for it in U.diff("pct-house", "chara")["items"]}, "ids are stable"
    assert all(it["label"].startswith("Persona") for it in d["items"])
    before = (snap / "long-term-memo" / "important_events.md").read_bytes()
    with pytest.raises(U.UpdateError) as e:
        U.apply("pct-house", "chara", token="u_stale")
    assert e.value.status == 409
    pt = next(it for it in d["items"] if it["path"] == ["personality_type"])
    fe = next(it for it in d["items"] if it["path"] == ["fears"])
    r = U.apply("pct-house", "chara", token=d["token"], choices={pt["id"]: "mine", fe["id"]: "theirs"})
    assert r["ok"] and r["took"] == 1 and r["kept"] == 1 and r["version"] == "0.3"
    cur = _rj(snap / "persona/core_traits.json")
    assert cur["fears"] == ["地窖", "钟声"] and cur["personality_type"] == "倔强的委托人"
    assert (snap / "long-term-memo" / "important_events.md").read_bytes() == before, "memory untouched"
    saved = U.updates("pct-house", "chara")
    assert len(saved) == 1 and saved[0]["choices"] == {pt["id"]: "mine", fe["id"]: "theirs"} and saved[0]["decided_at"]
    assert (snap / ".wl" / "accepted" / "persona" / "core_traits.json").read_bytes() == (snap / "persona/core_traits.json").read_bytes(), "the next base"
    assert _rj(snap / ".wl" / "snapshot.json")["author_version"] == "0.3"
    assert next(c for c in player_data.read()["characters"] if c["sid"] == "chara")["version"] == "0.3"
    assert U.diff("pct-house", "chara")["items"] == [], "kept mine: this change of the author's is not asked again"
    a = _rj(_author(store, "persona/core_traits.json"))
    a["personality_type"] = "最沉稳的委托人"
    _wj(_author(store, "persona/core_traits.json"), a)
    U.clear_cache()
    again = U.diff("pct-house", "chara")["items"]
    assert [(it["path"], it["default"], it.get("kept_before")) for it in again] == [(["personality_type"], "mine", True)], "changed again: asked again"


def test_one_click_all_and_not_clicking(store, tmp_path):
    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    _author_changes(store)
    before = U._files(snap)
    d = U.diff("pct-house", "chara")
    assert U._files(snap) == before and U.has_update("pct-house", "chara"), "not clicking: as it was, the hint stays"
    assert "倔强的委托人" in soul_chat._docs(Path(soul_chat.resolve("pct-house", "chara")["folder"])), "the phone reads the player's version"
    U.apply("pct-house", "chara", token=d["token"], all_="mine")
    assert U._files(snap) == before and not U.has_update("pct-house", "chara")


def test_a_failed_write_changes_nothing(store, tmp_path, monkeypatch):
    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    _author_changes(store)
    (_author(store, "rules") / "interaction_rules.md").write_text("- 说话更短\n", encoding="utf-8")
    U.clear_cache()
    before = U._files(snap)
    real, n = U.os.replace, {"i": 0}

    def flaky(a, b):
        n["i"] += 1
        if n["i"] == 2:
            raise OSError("disk full")
        return real(a, b)
    monkeypatch.setattr(U.os, "replace", flaky)
    with pytest.raises(U.UpdateError):
        U.apply("pct-house", "chara", all_="theirs")
    assert U._files(snap) == before and U.updates("pct-house", "chara") == []


# ── the author's version gone, old snapshots, plot NPCs ──────────────────────

def test_the_template_gone_the_character_stays(store, tmp_path, monkeypatch):
    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    shutil.rmtree(store / "pct-house.template")
    real = template.discover  # (the repo's own copy is gone too)
    monkeypatch.setattr(template, "discover", lambda: {k: v for k, v in real().items() if k != "pct-house"})
    rewards._STORE.clear()
    U.clear_cache()
    c = soul_chat.resolve("pct-house", "chara")
    assert c["access"] == "obtained" and Path(c["folder"]) == snap and c.get("orphan")
    assert "温妮" in soul_chat._docs(Path(c["folder"]))
    assert soul_chat.graph_of(c)["schema"] and soul_chat.chat_node(c)
    row = next(r for r in soul_chat.souls("zh")["souls"] if r["sid"] == "chara")
    assert row["obtained"] and "/player-data/souls/pct-house/chara/file?side=mine&f=assets/portrait" in row["avatar_url"]
    assert U.diff("pct-house", "chara")["gone"] and not U.has_update("pct-house", "chara")
    assert soul_update.side_file("pct-house", "chara", "mine", row["avatar_url"].split("f=")[1]) is not None


def test_old_snapshots_migrate(store, tmp_path):
    snap = _take(store, tmp_path)
    shutil.rmtree(snap / ".wl")
    shutil.rmtree(snap / "assets")
    (snap / "assets").mkdir()  # 9ce2d8a3 … 69722ada: the folder without its pictures
    m = U.ensure("pct-house", "chara")
    assert m["migrated"] == "exact" and m["author_files"] and U.portrait(snap) is not None, "same version: the author's now is the base"
    assert U.diff("pct-house", "chara")["items"] == []
    assert U.ensure("pct-house", "chara") == _rj(snap / ".wl" / "snapshot.json"), "idempotent"
    shutil.rmtree(snap / ".wl")
    _author_changes(store)
    m = U.ensure("pct-house", "chara")
    assert m["migrated"] == "no_base" and m["author_files"] is None
    d = U.diff("pct-house", "chara")
    assert d["base"]["unknown"] and d["items"] and all(it["default"] == "mine" and it["both_changed"] for it in d["items"])
    U.apply("pct-house", "chara", token=d["token"], all_="defaults")
    m = _rj(snap / ".wl" / "snapshot.json")
    assert m["author_files"] and U.diff("pct-house", "chara")["items"] == [], "after one decision, the usual three-way"


def test_a_plot_npcs_update(store, tmp_path):
    def back(d):
        d["entries"]["N201"]["props"]["takeable"] = True
        d["entries"]["N201"]["props"]["persona"] = "探路队里最年轻的一个"
    p = store / "stoneford-town.template" / "plots" / "P20" / "plot.json"
    d = _rj(p)
    back(d)
    _wj(p, d)
    root = tmp_path / "run"
    template.build(template.load(store / "stoneford-town.template"), root)
    assert player_data.take(root, "N201", "truth_quiz", memory="full")
    snap = soul_chat.snapshot_dir("stoneford-town", "N201")
    assert _rj(snap / ".wl" / "snapshot.json")["source"] == "npc"
    assert U.diff("stoneford-town", "N201")["items"] == []
    d = _rj(p)
    d["entries"]["N201"]["props"]["persona"] = "探路队里最年轻的一个,怕黑"
    _wj(p, d)
    U.clear_cache()
    got = U.diff("stoneford-town", "N201")["items"]
    assert [it["file"] for it in got] == ["soul.md"] and "怕黑" in got[0]["theirs"]


# ── the engine's routes, the Hub's old 「pull」 ────────────────────────────────

def test_http_routes_and_the_hubs_pull(store, tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    snap = _take(store, tmp_path)
    U.diff("pct-house", "chara")
    _author_changes(store)
    assert next(c for c in rewards.listing("zh")["characters"] if c["sid"] == "chara")["upd"]
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/api/v1/local/player-data/souls/pct-house/chara"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read() if "/file" in path else json.loads(r.read())
        try:
            d = call("/update?lang=ja")
            assert d["items"] and d["items"][0]["label"].startswith("人物像")
            try:
                call("/update", {"token": "u_x", "all": "theirs"})
                raise AssertionError("409")
            except urllib.error.HTTPError as e:
                assert e.code == 409
            assert call("/update", {"token": d["token"], "all": "defaults"})["ok"]
            assert len(call("/updates")["updates"]) == 1
            assert call("/file?side=mine&f=soul.md").startswith("# 温妮".encode())
            try:
                call("/file?side=mine&f=../../player-data.json")
                raise AssertionError("404")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown()
    a = _rj(_author(store, "persona/core_traits.json"))
    a["quirks"] = ["新的小动作"]
    _wj(_author(store, "persona/core_traits.json"), a)
    U.clear_cache()
    r = rewards.refresh("characters", "pct-house", "chara")
    assert r["ok"] and r["took"] == 1 and _rj(snap / "persona/core_traits.json")["quirks"] == ["新的小动作"], "「pull」 = all as suggested"
