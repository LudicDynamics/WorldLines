"""标准前端第四批引擎接口(10-15,docs/planning/STANDARD-FRONTEND-1014.md §5 第 18–20 条)。

⑱ 阶段目标:plot.json 的 stages 可写 {name, goal}(goal 本局语言 / 四语);GET /api/v1/play/engine/objective 给当前阶段的
   目标、走过的阶段(没到的不给名字)、委托(状态词收成 offered · active · done · failed · abandoned + 本局语言 label;
   locked 不列;没碰到过的委托不列)、这一局怎么结束(合约 exit 的说法)
⑲ 线索:条目(plot.json entries 的 clue: true)或类(clue: true)是线索;gained[].kind = clue;entities?clue=1 只给已发现的
⑳ 地图:各层 pos100(0–100);没有位置 / 和别人叠在一起的地点按连着的邻居或空位摆(pos_guess),钉子带 hotspot_guess;
   place.discovered {addr, name, parent, by: grow | arrive | reveal} 进 /beats(第一次看这一局不刷屏)

stub / 不调模型;pct-house · stoneford-town · kagura-island · last-train。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from pathlib import Path
from unittest.mock import patch

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import beat_events, holdings, objective, sdk, stages, worldmap
from neonrp.core.output_lang import write_output_lang
from neonrp.core.registry import load_registry

GOALS = [{"name": "来访", "goal": {"zh": "在宅子里找到失踪者留下的痕迹", "en": "Find what the missing man left behind"}},
         {"name": "日记", "goal": "弄清日记里说的「下面」是哪里"}, "钥匙", {"name": "地窖", "goal": "下去"}]


def _copy(name: str, tmp_path: Path) -> Path:
    d = tmp_path / "store" / f"{name}.template"
    shutil.copytree(PRODUCT_TEMPLATES / f"{name}.template", d)
    return d


def _build(tdir: Path, tmp_path: Path, tag: str = "run") -> Path:
    dest = tmp_path / tag
    TP.build(TP.load(tdir), dest)
    return dest


def _pct_with_goals(tmp_path: Path) -> Path:
    d = _copy("pct-house", tmp_path)
    p = d / "plots" / "P01" / "plot.json"
    pj = json.loads(p.read_text(encoding="utf-8"))
    pj["stages"] = GOALS
    pj["entries"]["I801"]["clue"] = True
    p.write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


# ── ⑱ objective ──────────────────────────────────────────────────────────────────────────────────────────────────────

def test_stage_goals_and_hidden_stages(tmp_path):
    root = _build(_pct_with_goals(tmp_path), tmp_path)
    o = objective.objective(root)
    assert o["now"] == {"plot": "P01", "stage": 0, "name": "来访", "goal": "在宅子里找到失踪者留下的痕迹"}
    steps = o["plots"][0]["steps"]
    assert [s["state"] for s in steps] == ["current", "hidden", "hidden", "hidden"] and steps[1]["name"] == "" and steps[1]["goal"] == ""
    assert o["exit"] == {"on": "ending", "label": "走到一个结局"}
    (root / "game" / "meta" / "plot_vars.json").write_text(json.dumps({"P01": {"stage": 1}}), encoding="utf-8")
    o = objective.objective(root)
    assert [s["state"] for s in o["plots"][0]["steps"]][:2] == ["done", "current"] and o["now"]["goal"] == "弄清日记里说的「下面」是哪里"
    write_output_lang(root, "en")
    assert objective.objective(root)["plots"][0]["steps"][0]["goal"] == "Find what the missing man left behind"
    assert TP.run_view(root)["plots"][0]["stages"] == ["来访", "日记", "钥匙", "地窖"], "run_view keeps names (strings)"
    ch = stages.changes(root, {"P01.stage": 1}, {"P01.stage": 3})
    assert ch[0]["name"] == "地窖"


def test_stage_objects_are_linted(tmp_path):
    from neonrp.packs.rpg import plot as rplot

    ok = rplot.lint({"id": "X", "stages": GOALS})
    assert not [p for p in ok if p.where.startswith("stages[")]
    bad = rplot.lint({"id": "X", "stages": [{"goal": "无名"}, 3, {"name": "a", "goal": 5}]})
    assert {p.where for p in bad if p.level == "error"} >= {"stages[0]", "stages[1]", "stages[2].goal"}
    assert not [p for p in TP.lint(TP.load(_pct_with_goals(tmp_path)), i18n=False)["problems"] if p["level"] == "block" and "stages" in p["where"]]


def test_jobs_fold_into_one_state_word(tmp_path):
    root = _build(PRODUCT_TEMPLATES / "stoneford-town.template", tmp_path)
    reg = load_registry(root)
    raw = {e.id: str(e.props.get("state")) for e in reg.of_class("job")}
    jobs = {j["id"]: j for j in objective.objective(root)["jobs"]}
    for jid, word in raw.items():
        if word == "locked":
            assert jid not in jobs, "a locked commission is not on any board yet"
        elif word == "in_progress":
            assert jobs[jid]["state"] == "active" and jobs[jid]["active"] and jobs[jid]["state_label"] == "进行中"
    offers = [i for i, w in raw.items() if w == "available" and i not in jobs]
    assert offers, "offers the player has not come across are not listed"
    name = reg.entries[offers[0]].name
    sdk.apply(root, [], load_registry(root), turn=1, narration=f"布告板上贴着「{name}」。")
    assert objective.job_state("Accepted") == "active" and objective.job_state("完成") == "done" and objective.job_state("locked") is None
    assert objective.job_state("whatever") == "offered"
    assert offers[0] in {j["id"] for j in objective.objective(root)["jobs"]}, "an offer the prose showed is listed"
    assert objective.objective(root)["exit"]["on"] == "segment"


# ── ⑲ clues ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_clues_are_their_own_kind(tmp_path):
    root = _build(_pct_with_goals(tmp_path), tmp_path)
    reg = load_registry(root)
    assert reg.is_clue(reg.entries["I801"]) and not reg.is_clue(reg.entries["I802"])
    before = holdings.snapshot(reg)
    reg.entries["I801"].parent = "player"
    g, _ = holdings.diff(before, holdings.snapshot(reg))
    assert g[0]["id"] == "I801" and g[0]["kind"] == "clue"
    from neonrp.core.registry import ClassSpec, class_from_dict

    assert class_from_dict("rumor", {"clue": True}).clue and not ClassSpec("x").clue


def test_entities_lists_found_clues_only(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    _pct_with_goals(tmp_path)
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
            call("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
            root = Path(server.runtime.root)
            assert call("/api/v1/play/engine/entities?clue=1")["entities"] == [], "the diary is in the study: not found yet"
            sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T001/study"}], load_registry(root), turn=1)
            got = call("/api/v1/play/engine/entities?clue=1")["entities"]
            assert [e["id"] for e in got] == ["I801"]
            assert [e["id"] for e in call("/api/v1/play/engine/entities?cls=item&clue=1")["entities"]] == ["I801"]
            ob = call("/api/v1/play/engine/objective")
            assert ob["now"]["goal"] and ob["lang"] == "zh"
            assert "place.discovered" in call("/api/v1/play/engine/beats")["names"]
        finally:
            server.shutdown()


# ── ⑳ map ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_unplaced_places_get_a_spot_and_every_level_is_0_to_100():
    tree = {"nodes": {
        "T": {"children": ["T/a", "T/b", "T/c", "T/d"], "edges": [{"from": "T/c", "to": "T/a"}]},
        "T/a": {"pos": {"x": 400, "y": 300}, "children": []},
        "T/b": {"pos": {"x": 800, "y": 700}, "children": []},
        "T/c": {"pos": {"x": 400, "y": 300}, "children": []},  # on top of a
        "T/d": {"children": []},                                # no position at all
        "D": {"children": ["D/r1", "D/r2", "D/r3"], "edges": []},
        "D/r1": {"pos": {"x": 0, "y": 0}, "children": []}, "D/r2": {"pos": {"x": 0, "y": 0}, "children": []},
        "D/r3": {"pos": {"x": 0, "y": 0}, "children": []}}}
    g = worldmap.place_unplaced(tree)
    assert g == {"T/c", "T/d", "D/r2", "D/r3"}
    n = tree["nodes"]
    assert n["T/c"]["pos_guess"] and n["T/c"]["pos"] != n["T/a"]["pos"] and "pos_guess" not in n["T/a"]
    import math

    assert math.dist((n["T/c"]["pos"]["x"], n["T/c"]["pos"]["y"]), (400, 300)) < math.dist((n["T/c"]["pos"]["x"], n["T/c"]["pos"]["y"]), (800, 700)), \
        "placed beside the place it links to"
    worldmap.pos100(tree)
    for c in ("T/a", "T/b", "T/c", "T/d", "D/r1", "D/r2", "D/r3"):
        p = n[c]["pos100"]
        assert 0 <= p["x"] <= 100 and 0 <= p["y"] <= 100, (c, p)
    assert len({(n[c]["pos100"]["x"], n[c]["pos100"]["y"]) for c in ("D/r1", "D/r2", "D/r3")}) == 3, "rooms no longer on one dot"


def test_map_view_carries_pos100_and_guessed_pins(tmp_path):
    root = _build(PRODUCT_TEMPLATES / "stoneford-town.template", tmp_path)
    v = worldmap.map_view(root, lens="play")
    lv = next(lv for lv, L in v["levels"].items() if L["hotspots"])
    L = v["levels"][lv]
    assert isinstance(L["hotspot_guess"], list) and all(2 <= x <= 98 and 2 <= y <= 98 for x, y in L["hotspots"].values())
    kids = [a for a, n in v["nodes"].items() if n.get("parent") == lv and n.get("pos100")]
    assert kids and all(0 <= v["nodes"][a]["pos100"]["x"] <= 100 for a in kids)


def test_place_discovered_events(tmp_path):
    root = _build(PRODUCT_TEMPLATES / "kagura-island.template", tmp_path)
    first = sdk.apply(root, [], load_registry(root), turn=1)
    assert first.discovered == [], "the first look at a run notes what is known, no flood"
    reg = load_registry(root)
    to = reg.exits(reg.player_location)[0]
    moved = sdk.apply(root, [{"op": "move_to", "who": "player", "to": to.id}], load_registry(root), turn=2)
    assert moved.discovered == [{"turn": 2, "addr": to.id, "name": to.name, "parent": to.parent, "by": "arrive"}]
    again = sdk.apply(root, [], load_registry(root), turn=3)
    assert again.discovered == []
    grown = sdk.apply(root, [{"op": "new_location", "name": "海边的小屋", "near": to.id}], load_registry(root), turn=4)
    rec = next(d for d in grown.discovered if d["name"] == "海边的小屋")
    assert rec["by"] == "grow"
    evs, _ = beat_events.from_traces([{"turn_seq": 4, "apply": {"beat": {"kind": "resolve"}, **grown.to_dict()}}], root=root)
    assert any(k == "place.discovered" and d["by"] == "grow" for k, d in evs)
