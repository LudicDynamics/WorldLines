"""标准前端要的引擎侧槽位与事件(10-14,docs/planning/STANDARD-FRONTEND-1014.md §5)。

① 开场 CG / 阶段过场槽位 opening.cg:<n> · stage.cg:<plot>.<n>:列进 asset_slots、能填、能取(含视频)、lint 认识(可选)
② plot 里非 item 条目的图(归乡 G101–G105)列进 asset_slots / slot_file 取得到;主持 [~show …] 只能展示模板里有的槽位;
   玩家第一次走进挂图的地点 → show(by: arrive)
③ party.join / party.leave:捏人带进来的同伴开局就在队里,跟着玩家走 = 入队,玩家走了没跟 = 离队
④ state.changed 带 gained / lost(谁、什么、从哪来、怎么来)
⑤ resolve.beat / plan.beat 带 mentions(id · cls · name · span)
⑥ inspect / pick 结构化玩家动作:不过模型、不替玩家说话,按世界自己的规则落地(末班车的「笔记本」规则照样触发)
⑦ stage.changed:剧情阶段变量变了 → 事件(带阶段名和过场槽位)

全部 stub / 不调模型,用 last-train · guixiang · pct-house · neon-rebirth 四个产品模板。"""
from __future__ import annotations

import json
import shutil
import threading
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import beat_events, holdings, mentions, player_action, sdk, show, stages
from neonrp.core.registry import load_registry

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _run(name: str, tmp_path: Path, tdir: Path | None = None) -> Path:
    dest = tmp_path / f"run-{name}"
    TP.build(TP.load(tdir or PRODUCT_TEMPLATES / f"{name}.template"), dest)
    return dest


def _copy(name: str, tmp_path: Path) -> Path:
    d = tmp_path / "store" / f"{name}.template"
    shutil.copytree(PRODUCT_TEMPLATES / f"{name}.template", d)
    return d


def _apply(root: Path, turn: int, ops: list | None = None, says: str = ""):
    return sdk.apply(root, list(ops or []), load_registry(root), turn=turn, player_says=says, narration=says)


def _events(root: Path, ap: dict, turn: int = 1, kind: str = "resolve"):
    tr = {"turn_seq": turn, "apply": {"beat": {"kind": kind}, **ap}}
    return beat_events.from_traces([tr], root=root)[0]


# ── ① opening / stage CG ─────────────────────────────────────────────────────────────────────────────────────────────

def _with_cg(tmp_path: Path) -> Path:
    d = _copy("pct-house", tmp_path)
    tj = json.loads((d / "template.json").read_text(encoding="utf-8"))
    tj["opening"] = {"cg": [{"image": "assets/opening/cg-1.png", "caption": {"zh": "雨夜,灰橡宅。", "en": "A rainy night."}, "camera": "slow push-in",
                             "video": "assets/opening/cg-1.mp4"},
                            {"image": "assets/opening/cg-2.png", "caption": "门开了。"}]}
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False, indent=2), encoding="utf-8")
    pj = json.loads((d / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))
    pj["stage_cg"] = {"1": {"image": "assets/stage-1.png", "caption": "日记里的那一页。"}, "地窖": {"image": "assets/stage-3.png"}}
    (d / "plots" / "P01" / "plot.json").write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "assets" / "opening").mkdir(parents=True, exist_ok=True)
    (d / "assets" / "opening" / "cg-1.png").write_bytes(PNG)
    (d / "assets" / "opening" / "cg-1.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (d / "plots" / "P01" / "assets").mkdir(parents=True, exist_ok=True)
    (d / "plots" / "P01" / "assets" / "stage-1.png").write_bytes(PNG)
    return d


def test_opening_and_stage_cg_are_optional_slots(tmp_path):
    d = _with_cg(tmp_path)
    t = TP.load(d)
    rows = {r["slot"]: r for r in TP.asset_slots(t)}
    o1, o2 = rows["opening.cg:1"], rows["opening.cg:2"]
    assert o1["have"] and o1["video_have"] and o1["camera"] == "slow push-in" and o1["need"] is False
    assert not o2["have"] and o2["label"] == "门开了。"
    s1, s3 = rows["stage.cg:P01.1"], rows["stage.cg:P01.3"]  # 「地窖」 is stage 3 by name
    assert s1["have"] and s1["plot"] == "P01" and s1["stage"] == 1 and not s3["have"]
    assert [r for r in rows if r.startswith("opening.cg:")] == ["opening.cg:1", "opening.cg:2"], "play order"
    assert TP.slot_file(t, "opening.cg:1").name == "cg-1.png" and TP.slot_file(t, "opening.cg:1", part="video").suffix == ".mp4"
    rep = TP.lint(t, i18n=False)
    probs = [p for p in rep["problems"] if "opening" in p["where"] or "stage_cg" in p["where"]]
    assert probs and all(p["level"] == "warn" for p in probs), probs  # not filled = optional, never a block
    # fill the empty ones through the slot protocol (upload) → recorded in template.json / plot.json
    TP.put_asset(t, "opening.cg:2", PNG)
    TP.put_asset(TP.load(d), "stage.cg:P01.3", PNG)
    t = TP.load(d)
    assert t.data["opening"]["cg"][1]["image"] == "assets/opening/cg-2.png" and t.data["opening"]["cg"][1]["caption"] == "门开了。"
    assert json.loads((d / "plots" / "P01" / "plot.json").read_text(encoding="utf-8"))["stage_cg"]["地窖"]["image"] == "assets/stage-3.png"
    assert all(r["have"] for r in TP.asset_slots(t) if r["slot"].startswith(("opening.cg:", "stage.cg:")))


def test_a_malformed_opening_blocks(tmp_path):
    d = _copy("pct-house", tmp_path)
    tj = json.loads((d / "template.json").read_text(encoding="utf-8"))
    tj["opening"] = {"cg": [{"caption": "no picture"}, {"image": "../outside.png"}]}
    (d / "template.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
    probs = [p for p in TP.lint(TP.load(d), i18n=False)["problems"] if p["code"] == "schema.opening"]
    assert len(probs) == 2 and all(p["level"] == "block" for p in probs)


def test_the_run_carries_its_opening_and_stage_cg(tmp_path):
    root = _run("pct-house", tmp_path, _with_cg(tmp_path))
    view = TP.run_view(root)
    assert [c["slot"] for c in view["opening"]["cg"]] == ["opening.cg:1", "opening.cg:2"] and view["opening"]["cg"][0]["camera"] == "slow push-in"
    p = view["plots"][0]
    assert p["stage_var"] == "P01.stage" and p["stage"] == 0 and p["dir"] == "plots/P01"
    assert [c["slot"] for c in p["stage_cg"]] == ["stage.cg:P01.1", "stage.cg:P01.3"]
    evs = _events(root, {"narration_plain": "雨夜。"}, turn=0, kind="opening")
    pb = next(d for k, d in evs if k == "plan.beat")
    assert pb["opening"] and [c["slot"] for c in pb["cg"]] == ["opening.cg:1", "opening.cg:2"] and pb["cg"][0]["template"] == "pct-house"


# ── ② plot pictures · show ───────────────────────────────────────────────────────────────────────────────────────────

def test_guixiang_illustrations_are_slots_and_files():
    t = TP.load(PRODUCT_TEMPLATES / "guixiang.template")
    rows = {r["slot"]: r for r in TP.asset_slots(t)}
    for g, parent in (("G101", "T001/y1947"), ("G102", "T001/backwell"), ("G105", "T001/well")):
        r = rows[f"plot:plots/P01:entry:{g}"]
        assert r["cls"] == "cg" and r["parent"] == parent and r["have"], r
        assert TP.slot_file(t, r["slot"]).is_file()
    assert not any(s.startswith("plot:plots/P01:entry:I") for s in rows), "items keep their item.icon slot (no duplicate)"


def test_show_op_only_where_the_template_has_pictures(tmp_path):
    gx = _run("guixiang", tmp_path)
    reg = load_registry(gx)
    spec = reg.actions["show"]
    assert spec.kind == "tool" and not spec.waits() and "G102" in spec.doc and "G102" in spec.doc_for("en")
    assert "show" not in load_registry(_run("last-train", tmp_path)).actions, "no pictures to show → prompt unchanged"
    ok = show.show_tool(gx, reg, {"slot": "井沿上的阿娣"})
    assert ok["ok"] and ok["show"]["slot"] == "plot:plots/P01:entry:G102" and ok["show"]["template"] == "guixiang"
    assert show.show_tool(gx, reg, {"slot": "plot:plots/P01:entry:G104"})["show"]["label"] == "闸门绞盘"
    assert not show.show_tool(gx, reg, {"slot": "a picture nobody drew"})["ok"]
    evs = _events(gx, {"narration_plain": "…", "tool_returns": [{"request": "show", "async": True, **ok},
                                                               {"request": "show", "async": True, "ok": False, "why": "no slot"}]})
    kinds = [k for k, _ in evs]
    assert kinds.count("show") == 1 and "tool" in kinds, "a refused show stays a tool event"
    assert next(d for k, d in evs if k == "show")["by"] == "host"


def test_walking_into_a_hung_picture_shows_it_once(tmp_path):
    gx = _run("guixiang", tmp_path)
    r = _apply(gx, 1, [{"op": "move_to", "who": "player", "to": "T001/y1947"}])
    assert [s["slot"] for s in r.shows] == ["plot:plots/P01:entry:G101"] and r.shows[0]["by"] == "arrive"
    evs = _events(gx, r.to_dict() | {"narration_plain": "…"})
    assert [d["inst"] for k, d in evs if k == "show"] == ["G101"]
    _apply(gx, 2, [{"op": "move_to", "who": "player", "to": "T001/hall"}])
    assert not _apply(gx, 3, [{"op": "move_to", "who": "player", "to": "T001/y1947"}]).shows, "once per run"


# ── ③ party ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_neon_rebirth_party_join_and_leave(tmp_path):
    root = _run("neon-rebirth", tmp_path)
    reg = load_registry(root)
    here = reg.player_location
    r = _apply(root, 1)
    assert {p["sid"] for p in r.joined} == {"isse", "yomi", "kuon", "akari"} and {p["why"] for p in r.joined} == {"companion"}
    assert sorted(holdings.members(root)) == sorted(p["iid"] for p in r.joined)
    other = next(e.id for e in reg.of_class("place") if e.id != here and e.id.startswith("T001/"))
    # two come along, two stay
    r = _apply(root, 2, [{"op": "move_to", "who": "player", "to": other}, {"op": "move_to", "who": "si-isse01", "to": other},
                         {"op": "move_to", "who": "si-yomi01", "to": other}])
    assert {p["sid"] for p in r.left} == {"kuon", "akari"} and {p["why"] for p in r.left} == {"stayed"} and not r.joined
    # back to the bookstore: akari (who stood there) is met again, but only joins when she walks on with the player
    _apply(root, 3, [{"op": "move_to", "who": "player", "to": here}, {"op": "move_to", "who": "si-isse01", "to": here},
                     {"op": "move_to", "who": "si-yomi01", "to": here}])
    r = _apply(root, 4, [{"op": "move_to", "who": "player", "to": other}, {"op": "move_to", "who": "si-akari01", "to": other},
                         {"op": "move_to", "who": "si-isse01", "to": other}, {"op": "move_to", "who": "si-yomi01", "to": other}])
    assert [p["sid"] for p in r.joined] == ["akari"] and r.joined[0]["why"] == "follow"
    r = _apply(root, 5, [{"op": "move_to", "who": "si-yomi01", "to": here}])
    assert [(p["sid"], p["why"]) for p in r.left] == [("yomi", "left")]
    evs = _events(root, r.to_dict() | {"narration_plain": "…"})
    assert [(k, d["sid"]) for k, d in evs if k.startswith("party.")] == [("party.leave", "yomi")]


def test_opening_puts_the_companions_in_the_party(tmp_path, monkeypatch):
    root = _session_run("last-train", tmp_path, monkeypatch)
    from neonrp.core.conversation import ConversationSession

    s = ConversationSession(root, "world-agent", mode="play")
    assert s.send("开始游戏").success
    from neonrp.core.orchestration_trace import read_turn_traces

    evs, _ = beat_events.from_traces(read_turn_traces(root, "main"), root=root)
    joins = [d for k, d in evs if k == "party.join"]
    assert [d["sid"] for d in joins] == ["xiacheng"] and joins[0]["turn"] == 0


# ── ④ gained / lost ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_gained_and_lost_say_who_what_where_how(tmp_path):
    root = _run("last-train", tmp_path)
    reg = load_registry(root)
    before = holdings.snapshot(reg)
    reg.entries["I701"].parent = "player"            # picked from the seat
    reg.entries["I702"].parent = "si-xiacheng01"     # the list goes to 夏澄 (from the seat: she picked it up)
    reg.entries["phone"].parent = "si-xiacheng01"    # the player hands over the phone
    reg.remove("ticket")                             # the ticket is used up
    gained, lost = holdings.diff(before, holdings.snapshot(reg))
    g = {x["id"]: x for x in gained}
    l_ = {x["id"]: x for x in lost}
    assert (g["I701"]["who"], g["I701"]["from"], g["I701"]["how"]) == ("player", "T001/seated_car", "picked")
    assert (g["I702"]["who"], g["I702"]["how"]) == ("si-xiacheng01", "picked")
    assert (g["phone"]["who"], g["phone"]["from"], g["phone"]["how"]) == ("si-xiacheng01", "player", "given")
    assert (l_["phone"]["who"], l_["phone"]["to"], l_["phone"]["how"]) == ("player", "si-xiacheng01", "given")
    assert (l_["ticket"]["who"], l_["ticket"]["how"], l_["ticket"]["kind"]) == ("player", "gone", "item")


def test_state_changed_carries_gained_from_a_landed_turn(tmp_path):
    root = _run("pct-house", tmp_path)
    _apply(root, 1, [{"op": "move_to", "who": "player", "to": "T001/study"}])
    r = player_action.perform(root, "pick", "I801", turn=2)["apply"]
    evs = _events(root, r.to_dict() | {"narration_plain": "…"}, turn=2)
    sc = next(d for k, d in evs if k == "state.changed")
    assert [(x["id"], x["who"], x["how"], x["from"]) for x in sc["gained"]] == [("I801", "player", "picked", "T001/study")] and sc["lost"] == []


# ── ⑤ mentions ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_mentions_name_ids_and_spans(tmp_path):
    root = _run("guixiang", tmp_path)
    text = "莲妹把族谱最后一页递给你。豫章堂里只剩一盏灯。"
    ms = mentions.find(load_registry(root), text)
    got = {(m["id"], m["cls"]) for m in ms}
    assert {("si-xiulian0001", "soul"), ("I101", "item"), ("T001/hall", "place")} <= got
    for m in ms:
        assert text[m["span"][0]:m["span"][1]] == m["name"]
    assert not any(m["id"] == "player" for m in ms)
    evs = _events(root, {"narration_plain": text})  # a trace recorded before mentions existed: the run's registry fills them
    rb = next(d for k, d in evs if k == "resolve.beat")
    assert {m["id"] for m in rb["mentions"]} >= {"si-xiulian0001", "I101"}
    kept = [{"id": "X", "cls": "item", "name": "莲妹", "span": [0, 2]}]
    assert next(d for k, d in _events(root, {"narration_plain": text, "mentions": kept}) if k == "resolve.beat")["mentions"] == kept


def test_mentions_keep_latin_words_whole(tmp_path):
    root = _run("guixiang", tmp_path)
    ms = mentions.find(load_registry(root), "Lianmei waves; lianmeiish is not her.")
    assert [m["name"] for m in ms] == ["Lianmei"]


# ── ⑥ inspect / pick ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_pick_runs_the_worlds_own_rules(tmp_path):
    root = _run("last-train", tmp_path)
    out = player_action.perform(root, "pick", "I701", turn=1)
    assert out["action"] == {"kind": "pick", "target": "I701", "ok": True}
    assert "got_notebook" in {k[5:] for k, v in load_registry(root).variables.items() if k.startswith("flag.") and v.value}, "the text rule saw it"
    assert load_registry(root).entries["I701"].parent == "player", "kept across a reload"
    assert player_action.perform(root, "pick", "I701", turn=2)["action"]["why"] == "have_it"
    far = player_action.perform(root, "inspect", "I703", turn=3)
    assert far["action"]["why"] == "not_here" and far["apply"].applied == []
    look = player_action.perform(root, "inspect", "夏澄的乘客名单", turn=4)
    assert look["action"]["ok"] and look["text"].startswith("一点十分的乘客名单")
    assert player_action.perform(root, "pick", "si-xiacheng01", turn=5)["action"]["why"] == "cannot_pick"
    assert player_action.perform(root, "pick", "nothing-like-it", turn=6)["action"]["why"] == "not_found"


def test_a_trigger_can_watch_a_pick(tmp_path):
    from neonrp.core.registry import register

    root = _run("pct-house", tmp_path)
    register(root, "triggers", "T.pick_key", {"when": {"entry": "I802", "event": "pick"}, "then": [{"to": "flag", "key": "took_key"},
                                                                                                    {"to": "narration", "text": "钥匙很冰。"}]})
    _apply(root, 1, [{"op": "move_to", "who": "player", "to": "T001/garden"}])
    out = player_action.perform(root, "pick", "I802", turn=2)
    assert load_registry(root).variables["flag.took_key"].value is True and out["text"].endswith("钥匙很冰。")


def _session_run(name: str, tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NEONRP_HOME", str(tmp_path / "home" / ".neonrp"))
    from neonrp.core.manifest import Manifest

    root = _run(name, tmp_path)
    neo = root / ".neonrp"
    (neo / "events").mkdir(parents=True, exist_ok=True)
    (neo / "sessions").mkdir(exist_ok=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (neo / "manifest.json").write_text(json.dumps(m.model_dump(), default=str), encoding="utf-8")
    (neo / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}), encoding="utf-8")
    return root


def test_an_action_is_its_own_beat_without_a_model(tmp_path, monkeypatch):
    root = _session_run("pct-house", tmp_path, monkeypatch)
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    _apply(root, 0, [{"op": "move_to", "who": "player", "to": "T001/study"}])
    s = ConversationSession(root, "world-agent", mode="play")
    with patch("neonrp.core.turn_v3.solve_turn", side_effect=AssertionError("no model for a click")):
        r = s.send(player_action.marker("pick", "I801"))
    assert r.success and r.route_decision == "action" and "烧了一半的日记" in r.assistant_message
    tr = read_turn_traces(root, "main")[-1]
    assert tr["apply"]["action"]["kind"] == "pick" and tr["apply"]["beat"]["advanced_by"] == "pick"
    evs, _ = beat_events.from_traces([tr], root=root)
    kinds = [k for k, _ in evs]
    assert kinds[:2] == ["node.enter", "resolve.beat"] and "state.changed" in kinds and "stage.changed" in kinds  # the diary moves the plot
    rb = dict(evs)["resolve.beat"]
    assert rb["action"]["target"] == "I801" and any(m["id"] == "I801" for m in rb["mentions"])
    st = dict(evs)["stage.changed"]
    assert (st["plot"], st["from"], st["to"], st["name"]) == ("P01", 0, 1, "日记")
    assert [m.content for m in s.messages if m.role == "user"][-1] == "[pick I801]", "the history says what the player did, not a line"


def test_cmd_takes_a_structured_action(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "last-train.template", store / "last-train.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else {"status": r.status}
        try:
            call("/api/v1/play/session", {"slug": "tpl--last-train", "output_lang": "zh"})
            root = Path(server.runtime.root)
            (root / ".neonrp" / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}), encoding="utf-8")
            q = server.runtime.broadcast.register()
            assert call("/cmd", {"action": "pick", "target": "I701"})["status"] == 202
            seen, t0 = [], time.time()
            while time.time() - t0 < 30:
                try:
                    m = q.get(timeout=1)
                except Exception:  # noqa: BLE001
                    continue
                seen.append(m)
                if m.get("kind") == "turn_done":
                    break
            kinds = [m.get("kind") for m in seen]
            assert "resolve.beat" in kinds and "state.changed" in kinds and kinds[-1] == "turn_done", kinds
            sc = next(m for m in seen if m["kind"] == "state.changed")
            assert sc["gained"][0]["id"] == "I701" and sc["gained"][0]["how"] == "picked"
            b = call("/api/v1/play/engine/beats")
            assert {"party.join", "stage.changed", "show"} <= set(b["names"])
        finally:
            server.shutdown()


# ── ⑦ stage ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_last_train_stage_changed_and_a_named_stage_var(tmp_path):
    root = _run("last-train", tmp_path)
    assert stages.stage_vars(root)["P01.stage"]["plot"] == "P01"
    _apply(root, 1, says="我拿起17号座上的笔记本看看")
    r = _apply(root, 2, [{"op": "add", "var": "departure.left", "delta": -1}, {"op": "flag", "key": "got_witness"}])
    assert [(s["var"], s["from"], s["to"]) for s in r.stages] == [("P01.stage", 0, 1)] and r.stages[0]["name"]
    assert "cg" not in r.stages[0], "no stage_cg declared → no slot"
    assert not _apply(root, 3).stages


def test_stage_var_may_name_another_variable():
    from neonrp.packs.rpg import plot as P

    assert P.stage_var_name({"id": "P01", "stages": ["a", "b"]}) == "P01.stage"
    assert P.stage_var_name({"id": "P01", "stages": ["a", "b"], "stage_var": "night"}) == "night"
    assert P.stage_var({"id": "P01", "stages": ["a", "b"], "stage_var": "night"}) is None, "declared where it lives"
    probs = P.lint({"id": "P01", "title": "t", "stages": ["a", "b"], "stage_var": "night"})
    assert any(p.where == "stage_var" for p in probs)


def test_stage_changed_points_at_its_cut_scene(tmp_path):
    root = _run("pct-house", tmp_path, _with_cg(tmp_path))
    r = _apply(root, 1, says="我翻开了那本日记")
    assert r.stages and r.stages[0]["cg"]["slot"] == "stage.cg:P01.1" and r.stages[0]["cg"]["caption"] == "日记里的那一页。"
    st = next(d for k, d in _events(root, r.to_dict() | {"narration_plain": "…"}) if k == "stage.changed")
    assert st["cg"]["slot"] == "stage.cg:P01.1" and st["name"] == "日记"


def test_contract_lists_the_new_beat_events():
    assert {"party.join", "party.leave", "stage.changed", "show"} <= set(beat_events.EVENTS)
    from neonrp.webui.engine_routes import EngineRoutes

    assert {"party.join", "party.leave", "stage.changed", "show"} <= set(EngineRoutes._STREAM_KINDS)


@pytest.mark.parametrize("name", ["last-train", "guixiang", "pct-house", "neon-rebirth"])
def test_templates_still_lint_without_new_blocks(name):
    rep = TP.lint(TP.load(PRODUCT_TEMPLATES / f"{name}.template"), i18n=False)
    new = [p for p in rep["problems"] if p["level"] == "block" and ("opening" in p["where"] or "stage_cg" in p["where"] or p["code"] == "schema.opening")]
    assert not new, new
