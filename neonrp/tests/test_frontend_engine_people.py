"""标准前端第三批引擎接口(10-15,docs/planning/STANDARD-FRONTEND-1014.md §5 第 14–17 条)。

⑭ GET /api/v1/play/engine/people:玩家视角「认识的人」;play 侧 entities?cls=soul|npc 不再给 persona / rules / goals /
   relationships.truth(调试走 /api/v1/play/engine/debug/entities)
⑮ soul.mind 拍事件(态度 · 一句心思 · 意图 · 去向 · 跟不跟 · 信任变化);S-direct 的 <fields> 认可选的 thought
⑯ 枚举的显示词(mood / disposition / role,game/meta/labels.json;英文局退回成词,其它局 ASCII 键不显示);
   快捷条不拼「None」;世界行动没写 label 时给本局语言的常用动词名;label 可写四语
⑰ met_player:和玩家同处一地(这一拍前或后)就写进 souls/<…>/run_state.json,带 last_seen;分开后还在 people / 地图上

stub / 不调模型;kagura-island · spice-witch · pct-house · last-train。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from pathlib import Path
from unittest.mock import patch

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import beat_events, labels, people, play_menu, sdk
from neonrp.core.output_lang import write_output_lang
from neonrp.core.registry import load_registry


def _run(name: str, tmp_path: Path, lang: str | None = None) -> Path:
    dest = tmp_path / f"run-{name}-{lang or 'src'}"
    TP.build(TP.load(PRODUCT_TEMPLATES / f"{name}.template"), dest)
    if lang:
        write_output_lang(dest, lang)
    return dest


def _apply(root: Path, turn: int, ops: list):
    return sdk.apply(root, ops, load_registry(root), turn=turn)


def _by_name(rows: list[dict]) -> dict[str, dict]:
    return {r["name"]: r for r in rows if r["name"]}


# ── ⑭ ⑰ people · met_player ──────────────────────────────────────────────────────────────────────────────────────────

def test_people_are_the_ones_you_know(tmp_path):
    root = _run("kagura-island", tmp_path)
    reg = load_registry(root)
    start = reg.player_location
    present = {e.name for e in reg.of_class("soul") if e.parent == start}
    absent = {e.name for e in reg.of_class("soul") if e.parent != start}
    rows = _by_name(people.people(root)["people"])
    assert present and set(rows) >= present and not (set(rows) & absent), "only those you have seen"
    hane = rows["羽"]
    assert hane["here"] and hane["companion"] and hane["where"] == "就在这里" and hane["portrait_slot"] == "soul.portrait:hane"
    assert hane["role_label"] == "同伴" and hane["place"]
    for r in rows.values():
        assert not {"persona", "rules", "goals", "relationships", "truth"} & set(r), r
    trust = next((r["trust"] for r in people.people(root)["people"] if r.get("trust")), None)
    assert trust is None or (trust["label"] == "信任" and "value" in trust)


def test_met_survives_parting(tmp_path):
    root = _run("kagura-island", tmp_path)
    reg = load_registry(root)
    start = reg.player_location
    away = reg.exits(start)[0].id
    _apply(root, 1, [{"op": "move_to", "who": "player", "to": away}])  # the first beat already walks off
    rows = _by_name(people.people(root)["people"])
    yuto = rows["悠人"]
    assert not yuto["here"] and yuto["met"] and yuto["addr"] == start and yuto["last_seen"] == {"addr": start, "turn": 1}
    assert yuto["where"].startswith("在")
    rs = json.loads(next((root / "souls").glob("yuto-*/run_state.json")).read_text(encoding="utf-8"))
    assert rs["status"]["met_player"] is True
    from neonrp.core import worldmap

    ents = {e["id"]: e for e in worldmap.map_view(root, lens="play")["entities"]}
    assert "yuto" in ents, "a soul you met stays on your map after you part"


def test_npcs_without_a_name_yet_show_what_they_are(tmp_path):
    root = _run("spice-witch", tmp_path)
    reg = load_registry(root)
    npc = reg.of_class("npc")[0]
    town = npc.props["town"]
    p = root / "game" / "towns" / town / "npcs.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    rows = d["npcs"] if isinstance(d, dict) else d
    rec = next(r for r in rows if str(r["id"]) == npc.id.rsplit("/", 1)[-1])
    rec["location"] = reg.player_location.split("/", 1)[1]
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (root / "game" / "meta" / "labels.json").write_text(json.dumps({"role": {rec["role"]: {"zh": "守门人", "en": "gatekeeper"}}}, ensure_ascii=False), encoding="utf-8")
    row = next(r for r in people.people(root)["people"] if r["kind"] == "npc")
    assert row["name"] == "" and row["here"] and not row["met"] and row["role_label"] == "守门人"
    assert row["portrait_slot"] == f"npc.portrait:{rec['id']}"
    rec["state"] = {"met": True}
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert next(r for r in people.people(root)["people"] if r["kind"] == "npc")["name"] == npc.name


def test_play_reads_keep_secrets_out(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "kagura-island.template", store / "kagura-island.template")
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
            call("/api/v1/play/session", {"slug": "tpl--kagura-island", "output_lang": "zh"})
            play = json.dumps(call("/api/v1/play/engine/entities?cls=soul"), ensure_ascii=False)
            for secret in ("卡卡尔是悠人的妹妹", "persona", "\"rules\"", "relationships", "goals"):
                assert secret not in play, secret
            assert "\"trust\"" in play and "\"hp\"" in play
            assert "卡卡尔是悠人的妹妹" in json.dumps(call("/api/v1/play/engine/debug/entities?cls=soul"), ensure_ascii=False)
            assert "skills" in json.dumps(call("/api/v1/play/engine/entities?cls=player"), ensure_ascii=False), "the player's own sheet stays"
            ppl = call("/api/v1/play/engine/people")
            assert ppl["lang"] == "zh" and ppl["people"] and "卡卡尔是悠人的妹妹" not in json.dumps(ppl, ensure_ascii=False)
            assert "soul.mind" in call("/api/v1/play/engine/beats")["names"]
        finally:
            server.shutdown()


# ── ⑮ soul.mind ──────────────────────────────────────────────────────────────────────────────────────────────────────

def test_soul_mind_events(tmp_path):
    root = _run("kagura-island", tmp_path)
    ap = {"beat": {"kind": "resolve"}, "narration_plain": "……",
          "reports": [{"iid": "si-hane0001", "name": "羽", "kind": "speak", "text": "「走吧。」", "proposed_move": "T001/town",
                       "judgment": {"attitude": "comfort", "thought": "他好像在怕什么", "follow": 0.8, "stay": 0.1, "want_move": True}},
                      {"iid": "si-yuto0001", "name": "悠人", "kind": "gesture", "judgment": {"attitude": None}}],
          "applied": [{"op": "add", "var": "trust.hane", "from": 20, "to": 23}]}
    evs, _ = beat_events.from_traces([{"turn_seq": 4, "apply": ap}], root=root)
    minds = [d for k, d in evs if k == "soul.mind"]
    assert [m["iid"] for m in minds] == ["si-hane0001", "si-yuto0001"]
    h = minds[0]
    assert (h["sid"], h["attitude"], h["attitude_label"], h["thought"], h["intent"], h["move_to"], h["follow"]) == \
        ("hane", "comfort", "安抚 / 关心", "他好像在怕什么", "speak", "T001/town", 0.8)
    assert h["trust_delta"] == 3 and "trust_delta" not in minds[1] and minds[1]["attitude_label"] == ""
    kinds = [k for k, _ in evs]
    assert kinds.index("soul.mind") > kinds.index("resolve.beat")


def test_s_direct_reads_an_optional_thought(tmp_path):
    from neonrp.packs.rpg import soul_step

    root = _run("kagura-island", tmp_path)
    raw = "<lines>\n「嗯。」\n</lines>\n<fields>\nthought: 先别告诉他勾玉的事\nattitude: deflect\nfollow: 0.7\n</fields>"
    with patch("neonrp.core.light_chat.ask_soul_deliver", lambda *a, **k: {"ok": True, "answer": raw}):
        r = soul_step._soul_step_direct(root, "si-hane0001", situation="……", depth="speak", provider=None, mode="play", registry=None)
    assert r["judgment"]["thought"] == "先别告诉他勾玉的事" and r["judgment"]["attitude"] == "deflect"
    assert "thought:" in soul_step._S("zh")["direct_fmt"] and "thought:" in soul_step._S("ko")["direct_fmt"]


# ── ⑯ labels ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_enum_labels(tmp_path):
    root = _run("kagura-island", tmp_path)
    assert labels.label(root, "mood", "blank_then_violent", "en") == "blank then violent"
    assert labels.label(root, "mood", "blank_then_violent", "zh") == "", "an ASCII code is not a word for a zh player"
    assert labels.label(root, "role", "城门守卫", "zh") == "城门守卫"
    (root / "game" / "meta" / "labels.json").write_text(json.dumps({"mood": {"yearning": {"zh": "思念", "en": "longing"}},
                                                                    "disposition": {"lover": "恋人"}}, ensure_ascii=False), encoding="utf-8")
    assert labels.label(root, "mood", "yearning", "zh") == "思念" and labels.label(root, "mood", "yearning", "ja") == ""
    assert labels.label(root, "disposition", "lover", "ja") == "恋人"
    hane = next(r for r in people.people(root)["people"] if r.get("sid") == "hane")
    assert hane["mood_label"] == "思念"


def test_quick_bar_and_default_action_labels(tmp_path):
    root = _run("pct-house", tmp_path)
    st = root / "game" / "player" / "stats.json"
    d = json.loads(st.read_text(encoding="utf-8"))
    d["skills"] = [{"name": "生意口", "value": None}, {"name": "侦查", "value": 60}]
    st.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    acts = root / "game" / "meta" / "actions.json"
    a = json.loads(acts.read_text(encoding="utf-8"))
    a["actions"] = [{"name": "go", "prompt": "我走向{args}。"}, {"name": "brew", "prompt": "我熬一锅药。", "label": {"zh": "熬药", "en": "Brew"}},
                    {"name": "dance", "prompt": "我跳舞。"}]
    acts.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
    c = play_menu.catalog(root)
    assert all("None" not in q["label"] for q in c["quick"]), c["quick"]
    assert [(x["name"], x["label"]) for x in c["actions"]] == [("go", "前往"), ("brew", "熬药"), ("dance", "dance")]
    write_output_lang(root, "ja")
    assert [x["label"] for x in play_menu.catalog(root)["actions"]] == ["移動", "Brew", "dance"]
