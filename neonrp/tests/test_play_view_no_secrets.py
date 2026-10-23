"""play 侧接口不带出主持才该知道的东西(10-15,STANDARD-FRONTEND §5.14 追加)。

/state(及 /events 的 hello · positions)只列玩家认识的角色;/trace 是玩家视角(没有 bus_messages / plan / spans /
异地角色的发言 / 计划板 / 变量全表);/api/v1/play/schema 没有触发器和变量的 doc;/events 不发 thinking、不发不认识的角色的
心象;完整数据只在 /api/v1/play/engine/debug/*(和 /events?debug=1),NEONRP_DEBUG_ROUTES=0 时没有。

kagura-island(卡卡尔是悠人的妹妹 · 67 次循环 · 结局触发器);stub,不调模型。"""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES
from neonrp.core import play_view

SECRETS = ("卡卡尔是悠人的妹妹", "灵魂设定", "decision rules", "已经第67次了")


def _trace(near: str, far: str) -> dict:
    return {"schema_version": 1, "turn_seq": 1, "ts": "t", "player": {"input": "你好", "intent": "act"}, "world_location": "T001/south_shore",
            "souls": [{"sid": "hane", "instance_id": near, "speech": "「嗯。」", "reason": "co-located"},
                      {"sid": "tsubasa", "instance_id": far, "speech": "(远处)我在等悠人", "reason": "away"}],
            "plan": {"secret": "主持的计划"}, "bus_messages": [{"prompt": "卡卡尔是悠人的妹妹"}], "spans": [{"x": 1}],
            "apply": {"beat": {"kind": "plan", "board": {"note": "主持的计划板"}, "script": [{"role": "host", "text": "雾来了。"}]},
                      "narration_plain": "雾来了。", "options": ["走"], "applied": [{"op": "set", "var": "flag.x"}],
                      "variables": {"P01.secret": 1}, "triggered": [{"id": "P01.end_truth"}], "annotated": "<host>…</host>",
                      "proposals": [{"narration": "雾来了。", "ops": [{"op": "set"}]}],
                      "tool_returns": [{"request": "dice 1d100 vs 60", "rolls": [12], "total": 12, "vs": 60, "passed": True, "raw": "x"}],
                      "reports": [{"iid": near, "name": "羽", "kind": "speak", "text": "「嗯。」",
                                   "judgment": {"attitude": "comfort", "follow": 0.8, "decision": {"chain": "…"}, "answers": {"a": 1}}}],
                      "souls": [{"iid": near, "name": "羽", "trust_delta": 1, "intention": "跟着他", "event": "提示词原文"},
                                {"iid": far, "name": "翼", "intention": "等悠人", "event": "…"}]}}


def test_trace_is_the_players_view():
    v = play_view.trace(_trace("si-hane0001", "si-tsubasa01"))
    s = json.dumps(v, ensure_ascii=False)
    for gone in ("bus_messages", "主持的计划\"", "spans", "P01.secret", "P01.end_truth", "annotated", "提示词原文", "我在等悠人", "等悠人",
                 "decision", "answers", "\"raw\"", "\"ops\""):
        assert gone not in s, gone
    ap = v["apply"]
    assert ap["narration_plain"] == "雾来了。" and ap["options"] == ["走"] and ap["beat"]["script"][0]["text"] == "雾来了。"
    assert ap["tool_returns"][0]["total"] == 12 and ap["reports"][0]["judgment"] == {"attitude": "comfort", "follow": 0.8}
    assert [x["iid"] for x in ap["souls"]] == ["si-hane0001"] and ap["souls"][0]["intention"] == "跟着他"
    assert [x["instance_id"] for x in v["souls"]] == ["si-hane0001"] and v["player"] == {"input": "你好"}


def test_live_events_for_a_player(tmp_path):
    root = tmp_path
    known = {"si-hane0001"}
    assert play_view.sse({"kind": "thinking", "text": "主持在想"}, root, known) is None
    assert play_view.sse({"kind": "soul_psyche", "instance_id": "si-tsubasa01", "inner_voice": "等悠人"}, root, known) is None
    assert play_view.sse({"kind": "soul_psyche", "instance_id": "si-hane0001", "inner_voice": "…"}, root, known)
    pos = play_view.sse({"kind": "positions", "souls": [{"instance_id": "si-hane0001"}, {"instance_id": "si-tsubasa01"}]}, root, known)
    assert [s["instance_id"] for s in pos["souls"]] == ["si-hane0001"]
    st = play_view.sse({"kind": "soul_status", "statuses": {"si-hane0001": {"state": "done"}, "si-tsubasa01": {"state": "done"}}}, root, known)
    assert list(st["statuses"]) == ["si-hane0001"]
    tr = play_view.sse({"kind": "trace", "trace": _trace("si-hane0001", "si-tsubasa01")}, root, known)
    assert "bus_messages" not in tr["trace"]
    assert play_view.sse({"kind": "resolve.beat", "text": "…"}, root, known) == {"kind": "resolve.beat", "text": "…"}


def test_schema_for_a_player():
    v = play_view.schema({"variables": [{"name": "loop.left", "doc": "主持说明", "value": 9}], "triggers": [{"id": "P01.end_truth"}], "classes": []})
    assert v["triggers"] == [] and v["variables"] == [{"name": "loop.left", "value": 9}]


def test_debug_switch(monkeypatch):
    monkeypatch.setenv("NEONRP_DEBUG_ROUTES", "0")
    assert not play_view.debug_enabled()
    monkeypatch.setenv("NEONRP_DEBUG_ROUTES", "1")
    assert play_view.debug_enabled()
    monkeypatch.delenv("NEONRP_DEBUG_ROUTES")
    with patch("sys.platform", "emscripten"):
        assert not play_view.debug_enabled(), "the Hub's browser engine: off unless the bench turns it on"


@pytest.fixture
def server(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "kagura-island.template", store / "kagura-island.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    monkeypatch.delenv("NEONRP_DEBUG_ROUTES", raising=False)
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
        patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name}),
    ):
        srv = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            yield srv
        finally:
            srv.shutdown()


def _get(srv, path):
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return r.read().decode("utf-8")


def test_play_routes_keep_the_hosts_working_out(server, monkeypatch):
    base = f"http://127.0.0.1:{server.server_address[1]}"
    req = urllib.request.Request(base + "/api/v1/play/session", data=json.dumps({"slug": "tpl--kagura-island", "output_lang": "zh"}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=120).read()
    root = Path(server.runtime.root)
    trace_file = root / ".neonrp" / "orchestration" / "main.jsonl"
    trace_file.parent.mkdir(parents=True, exist_ok=True)
    with trace_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_trace("si-hane0001", "si-tsubasa01"), ensure_ascii=False) + "\n")
    i = json.loads(_get(server, "/traces"))["turns"][-1]["i"]

    state = json.loads(_get(server, "/state"))
    here = {s["instance_id"] for s in state["souls"]}
    full = json.loads(_get(server, "/api/v1/play/engine/debug/state"))
    assert here and here < {s["instance_id"] for s in full["souls"]}, "the play hello lists only the characters the player knows"
    play_trace = _get(server, f"/trace?i={i}")
    assert "bus_messages" not in play_trace and "我在等悠人" not in play_trace and "雾来了" in play_trace
    assert "bus_messages" in _get(server, f"/api/v1/play/engine/debug/trace?i={i}")
    schema = _get(server, "/api/v1/play/schema")
    for s in SECRETS:
        assert s not in schema, s
    assert json.loads(schema)["triggers"] == []
    assert "已经第67次了" in _get(server, "/api/v1/play/engine/debug/schema")
    for path in ("/api/v1/play/engine/entities?cls=soul", "/api/v1/play/engine/entities?cls=npc", "/api/v1/play/engine/people",
                 "/api/v1/play/map", "/api/v1/play/engine/template", "/api/v1/play/engine/beats", "/api/v1/play/engine/actions"):
        body = _get(server, path)
        for s in SECRETS:
            assert s not in body, (path, s)
    monkeypatch.setenv("NEONRP_DEBUG_ROUTES", "0")
    for path in ("/api/v1/play/engine/debug/state", f"/api/v1/play/engine/debug/trace?i={i}", "/api/v1/play/engine/debug/schema",
                 "/api/v1/play/engine/debug/entities?cls=soul"):
        with pytest.raises(urllib.error.HTTPError) as e:
            _get(server, path)
        assert e.value.code == 404, path


# ── 10-15 追加:没发现的线索不出名字 · 计划板保留 ─────────────────────────────────────────────────────────────────────

def _kagura(tmp_path: Path) -> Path:
    from neonrp import template as TP

    dest = tmp_path / "run"
    TP.build(TP.load(PRODUCT_TEMPLATES / "kagura-island.template"), dest)
    return dest


def _names(root: Path) -> set[str]:
    from neonrp.webui.schema_routes import schema_view

    v = play_view.schema(schema_view(root), root)
    return {r["name"] for rows in v["entries"].values() for r in rows}


def test_clues_keep_their_names_until_found(tmp_path):
    from neonrp.core import sdk
    from neonrp.core.registry import load_registry

    root = _kagura(tmp_path)
    assert "离岛的祭坛" not in _names(root) and "博物馆的空白年代" not in _names(root), "not found yet: no name"
    from neonrp.webui.schema_routes import schema_view

    assert "离岛的祭坛" in {r["name"] for rows in schema_view(root)["entries"].values() for r in rows}, "the debug read has everything"
    start = load_registry(root).player_location
    sdk.apply(root, [{"op": "move_to", "who": "player", "to": "T001/islet_surface"}], load_registry(root), turn=1)
    assert "离岛的祭坛" in _names(root), "standing by it"
    sdk.apply(root, [{"op": "move_to", "who": "player", "to": start}], load_registry(root), turn=2)
    assert "离岛的祭坛" in _names(root), "found once, known since"
    assert "博物馆的空白年代" not in _names(root)
    sdk.apply(root, [], load_registry(root), turn=3, narration="她说起博物馆的空白年代,声音压得很低。")
    assert "博物馆的空白年代" in _names(root), "what the prose named is known"
    assert "海底通道的壁画" not in _names(root)


def test_the_plan_board_is_the_tables_own():
    """The board is what each one at the table said they will do this round (the player and the people present — the
    talk itself shows each draft as 「打算」): it stays in the player's view."""
    t = _trace("si-hane0001", "si-tsubasa01")
    t["apply"]["beat"]["board"] = {"玩家": "撬开祠堂的门", "羽": "在门外望风"}
    t["apply"]["beat"]["checks"] = [{"who": "player", "text": "撬锁"}]
    b = play_view.trace(t)["apply"]["beat"]
    assert b["board"] == {"玩家": "撬开祠堂的门", "羽": "在门外望风"} and b["checks"]
