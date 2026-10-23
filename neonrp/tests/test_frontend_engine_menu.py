"""标准前端第二批引擎接口(10-14,docs/planning/STANDARD-FRONTEND-1014.md §5 第 9 / 11 / 12 / 13 条)。

⑨ 技能说明:GET /api/v1/play/engine/sheet —— 每个属性 / 技能的本局语言显示名 + 一句说明 + 当前值(pct 还带检定线)
⑪ 行动接口:GET /api/v1/play/engine/actions —— 世界登记的行动 · 技能 · 道具 · 地点 · 在场的人 · 快捷条(常用的标出来)
⑫ 输出语言:run_view(/api/v1/play/engine/template)带 lang
⑬ 技能命令:「/侦查 井口」或 {action: skill, skill, target} —— pct 引擎当场检定、把结果交给主持;没有对应规则 → 一句话交给主持;
   「/go 3车」→ 世界行动的 prompt

全部 stub / 不调模型,用 last-train · guixiang · pct-house · neon-rebirth 四个产品模板。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import beat_events, play_menu, player_action, sheet
from neonrp.core.output_lang import write_output_lang
from neonrp.template import i18n as TI


def _run(name: str, tmp_path: Path, lang: str | None = None, tdir: Path | None = None) -> Path:
    dest = tmp_path / f"run-{name}-{lang or 'src'}"
    t = TP.load(tdir or PRODUCT_TEMPLATES / f"{name}.template")
    with TI.localized(t, lang) as lt:
        TP.build(lt, dest)
    if lang:
        write_output_lang(dest, lang)
    return dest


def _row(rows: list[dict], key: str) -> dict:
    return next(r for r in rows if r.get("key") == key)


# ── ⑨ sheet ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_pct_sheet_names_describes_and_gives_the_check(tmp_path):
    zh = sheet.sheet(_run("last-train", tmp_path))
    assert zh["lang"] == "zh" and zh["system"] == "pct" and zh["hp"] == {"current": 10, "max": 10}
    pow_ = _row(zh["attrs"], "pow")
    assert (pow_["label"], pow_["value"], pow_["check"]) == ("意志", 12, 60) and pow_["desc"]
    spot = _row(zh["skills"], "侦查")
    assert (spot["label"], spot["value"], spot["check"], spot["id"]) == ("察觉", 60, 60, "search") and "藏" in spot["desc"], "the sheet's old name shows by its BRP name, with its line"
    assert _row(zh["skills"], "定力")["label"] == "定力", "a skill the world's own table adds keeps its row"
    en = sheet.sheet(_run("last-train", tmp_path, "en"))
    assert en["lang"] == "en"
    assert _row(en["attrs"], "pow")["label"] == "POW" and _row(en["attrs"], "pow")["desc"].startswith("Will")
    s = _row(en["skills"], "侦查")  # keys stay as authored; the label is the run's language
    assert s["label"] == "Spot" and s["desc"].startswith("Spot")
    assert _row(en["skills"], "定力")["label"] == "Composure" and _row(en["skills"], "机械维修")["label"] == "Mechanical Repair"


def test_guixiang_world_skills_and_pct_house_list_shape(tmp_path):
    gx = sheet.sheet(_run("guixiang", tmp_path, "ja"))
    hk = _row(gx["skills"], "客家话")["label"]
    assert hk and hk != "客家话" and _row(gx["skills"], "侦查")["label"] == "発見", "the world's own skill shows its ja name"
    ph = sheet.sheet(_run("pct-house", tmp_path))  # skills as a [{name, value}] list
    lock = _row(ph["skills"], "开锁")
    assert lock["value"] == 30 and lock["check"] == 30 and lock["desc"]
    assert all(r["desc"] for r in ph["attrs"]), "every pct attribute has its line"


def test_a_pack_without_a_table_keeps_the_keys(tmp_path):
    nr = sheet.sheet(_run("neon-rebirth", tmp_path))
    assert "system" not in nr and nr["skills"] == []
    assert [(r["key"], r["label"], r["value"]) for r in nr["attrs"]] == [(k, k, 4) for k in ("体", "技", "识", "魂", "运")]
    assert all("check" not in r for r in nr["attrs"]), "no pct check line outside pct"


def test_a_world_table_row_can_name_and_describe(tmp_path):
    root = _run("neon-rebirth", tmp_path)
    rules = root / "game" / "rules" / "rules.json"
    d = json.loads(rules.read_text(encoding="utf-8"))
    d["attrs"] = {"识": {"zh": "识", "en": "Insight", "desc": {"zh": "看穿一个故事的来处。", "en": "See where a story comes from."}}}
    rules.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    r = _row(sheet.sheet(root, "en")["attrs"], "识")
    assert (r["label"], r["desc"]) == ("Insight", "See where a story comes from.")


# ── ⑪ actions ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_last_train_catalog(tmp_path):
    c = play_menu.catalog(_run("last-train", tmp_path))
    assert c["lang"] == "zh"
    assert [a["name"] for a in c["actions"]] == ["go", "talk", "search", "look", "report"]
    assert [a["common"] for a in c["actions"]] == [True, True, True, True, False], "no row marked → the first four"
    go = c["actions"][0]
    assert go["cmd"] == "/go" and go["args_hint"] == "<车厢>" and go["prompt"] == "我去{args}。"
    assert [v["kind"] for v in c["verbs"]] == ["skill", "inspect", "pick"] and all(v["label"] for v in c["verbs"])
    vals = [s["value"] for s in c["skills"]]
    assert vals == sorted(vals, reverse=True) and sum(s["common"] for s in c["skills"]) == play_menu.COMMON_SKILLS
    assert c["skills"][0]["cmd"].startswith("/") and c["skills"][0]["desc"]
    items = {i["id"]: i for i in c["items"]}
    assert items["ticket"]["held"] and not items["I701"]["held"], "carried + loose here"
    places = {p["id"]: p for p in c["places"]}
    assert places["T001/seated_car"]["here"] and places["T001/cab"]["near"] and places["T001/sleeper"]["near"]
    assert not places.get("T001/dining", {"near": False})["near"]
    people = {p["name"]: p for p in c["people"]}
    assert set(people) == {"夏澄", "周子航"} and people["夏澄"]["companion"] and people["夏澄"]["cmd"] == "@夏澄"
    kinds = [q["kind"] for q in c["quick"]]
    assert kinds == sorted(kinds, key=["person", "skill", "item"].index) and "@夏澄" in [q["text"] for q in c["quick"]]


def test_the_catalog_speaks_the_runs_language(tmp_path):
    c = play_menu.catalog(_run("last-train", tmp_path, "en"))
    assert c["lang"] == "en" and c["actions"][0]["help"] == "Go to another car" and c["actions"][0]["name"] == "go"
    assert c["verbs"][0]["label"] == "Use a skill"
    assert any(s["label"] == "Spot" and s["cmd"] == "/Spot" for s in c["skills"])


def test_marked_common_actions_and_labels(tmp_path):
    root = _run("pct-house", tmp_path)
    p = root / "game" / "meta" / "actions.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["actions"] = [{"name": "go", "help": "走到某个地点", "args_hint": "<地点>", "prompt": "我走向{args}。"},
                    {"name": "talk", "prompt": "我开口说话。"},
                    {"name": "look", "prompt": "我环顾四周。", "common": True, "label": "环顾"},
                    {"name": "bad name!", "prompt": "x"}]  # the bad one is skipped, never fatal
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    acts = play_menu.catalog(root)["actions"]
    assert [(a["name"], a["common"], a["label"]) for a in acts] == [("go", False, "前往"), ("talk", False, "交谈"), ("look", True, "环顾")]


def test_tui_reads_the_same_table(tmp_path):
    from neonrp.tui import commands as C

    acts = C.load_world_actions(_run("neon-rebirth", tmp_path))
    assert {"read", "bookmark", "nightfall"} <= set(acts) and acts["read"]["kind"] == "play"


# ── ⑫ lang ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_run_view_says_the_language(tmp_path):
    assert TP.run_view(_run("guixiang", tmp_path))["lang"] == "zh"
    assert TP.run_view(_run("guixiang", tmp_path, "ko"))["lang"] == "ko"


# ── ⑬ skill command ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_pct_skill_is_rolled_before_the_host_writes(tmp_path):
    root = _run("last-train", tmp_path)
    a = player_action.prepare(root, "/侦查 行李架", turn=3)
    b = player_action.prepare(root, player_action.skill_marker("侦查", "行李架"), turn=3)
    assert a["action"] == b["action"], "the text command and the structured one are the same move (seeded)"
    act = a["action"]
    assert act["kind"] == "skill" and act["skill"] == "察觉" and act["target"] == "行李架" and act["rolled"] and act["vs"] == 60
    assert a["say"] == "我用「察觉」:行李架。", "an old name typed: the line says the BRP name"
    tr = a["tool_returns"][0]
    assert tr["request"].startswith("dice ") and tr["rolls"] == [act["total"]] and tr["reason"] == "察觉 · 行李架"
    assert "引擎已经替这件事掷过了" in a["facts"] and str(act["total"]) in a["facts"]
    evs, _ = beat_events.from_traces([{"turn_seq": 3, "apply": {"beat": {"kind": "resolve"}, "narration_plain": "…", "action": act,
                                                              "tool_returns": a["tool_returns"]}}], root=root)
    d = dict(evs)
    assert d["dice"]["vs"] == 60 and d["dice"]["total"] == act["total"] and d["resolve.beat"]["action"]["kind"] == "skill"
    att = player_action.prepare(root, "/意志", turn=3)["action"]  # an attribute: × attr_x
    assert att["rolled"] and att["vs"] == 60 and att["target"] == ""


def test_multiword_names_and_the_runs_language(tmp_path):
    root = _run("pct-house", tmp_path, "en")
    r = player_action.prepare(root, "/First Aid the butler", turn=1)
    assert r["action"]["skill"] == "First Aid" and r["action"]["target"] == "the butler" and r["action"]["vs"] == 45
    assert r["say"] == "I use First Aid: the butler."


def test_no_rule_hands_it_to_the_host(tmp_path):
    nr = _run("neon-rebirth", tmp_path)
    r = player_action.prepare(nr, "/识 久远", turn=1)
    assert r["action"] == {"kind": "skill", "skill": "识", "key": "识", "target": "久远", "rolled": False}
    assert "tool_returns" not in r and "[dice" in r["facts"] and r["say"] == "我用「识」:久远。"
    # a structured skill the sheet does not know: still one line for the host, never refused
    r = player_action.prepare(_run("last-train", tmp_path), player_action.skill_marker("驾驶", "列车"), turn=1)
    assert r["action"]["rolled"] is False and r["say"] == "我用「驾驶」:列车。"
    assert player_action.prepare(nr, "/不是技能 x", turn=1) is None and player_action.prepare(nr, "我走过去", turn=1) is None


def test_world_actions_expand(tmp_path):
    root = _run("neon-rebirth", tmp_path)
    rows = {r["name"]: r for r in play_menu.world_actions(root)}
    assert player_action.prepare(root, "/read 久远", turn=1)["say"] == rows["read"]["prompt"].replace("{args}", "久远")
    assert player_action.prepare(root, "/nightfall", turn=1)["say"] == rows["nightfall"]["prompt"]


def test_body_shapes():
    assert player_action.from_body({"action": "skill", "skill": "/侦查", "target": "井口"}) == "[skill 侦查]井口"
    assert player_action.from_body({"action": "skill", "skill": "侦查"}) == "[skill 侦查]"
    assert player_action.from_body({"action": "skill"}) is None
    from neonrp.webui.engine_routes import _turn_input

    assert _turn_input({"input": "随便说", "action": "skill", "skill": "聆听"}) == "[skill 聆听]", "the action wins"
    assert _turn_input({"input": "/侦查 井口"}) == "/侦查 井口"


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


@pytest.mark.timeout(300)
def test_a_skill_turn_tells_the_host_and_leads_with_the_roll(tmp_path, monkeypatch):
    root = _session_run("pct-house", tmp_path, monkeypatch)
    from neonrp.core import turn_v3
    from neonrp.core.conversation import ConversationSession
    from neonrp.core.orchestration_trace import read_turn_traces

    seen: list[dict] = []
    real = turn_v3.solve_turn

    def spy(*a, **k):
        seen.append({"user_text": k.get("user_text"), "plan_facts": k.get("plan_facts")})
        return real(*a, **k)

    monkeypatch.setattr(turn_v3, "solve_turn", spy)
    s = ConversationSession(root, "world-agent", mode="play")
    r = s.send("/侦查 壁炉")
    assert r.success, r.error
    assert seen and seen[0]["user_text"] == "我用「察觉」:壁炉。" and "引擎已经替这件事掷过了" in seen[0]["plan_facts"]
    tr = read_turn_traces(root, "main")[-1]
    assert tr["apply"]["action"]["kind"] == "skill" and tr["apply"]["action"]["rolled"]
    first = tr["apply"]["tool_returns"][0]
    assert first["reason"] == "察觉 · 壁炉" and first["vs"] == 60
    assert "/侦查 壁炉" in [m.content for m in s.messages if m.role == "user"], "the history keeps what was sent"


def test_http_sheet_actions_and_lang(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "guixiang.template", store / "guixiang.template")
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
            call("/api/v1/play/session", {"slug": "tpl--guixiang", "output_lang": "en"})
            assert call("/api/v1/play/engine/template")["lang"] == "en"
            sh = call("/api/v1/play/engine/sheet")
            assert sh["lang"] == "en" and _row(sh["skills"], "客家话")["label"].isascii()
            acts = call("/api/v1/play/engine/actions")
            assert acts["lang"] == "en" and {"go", "talk", "look", "search", "push"} == {a["name"] for a in acts["actions"]}
            assert any(p["name"] for p in acts["people"]) and acts["quick"]
        finally:
            server.shutdown()
