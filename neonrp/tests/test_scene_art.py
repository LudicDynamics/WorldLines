"""「画这一幕」(10-16,core/scene_art):一拍 → 平台今天收的字段(scene ≤ 600 · caption ≤ 200 · style ≤ 200 · world_ref)+ 结构化的 context;
只用玩家看到的(玩家视角的回合记录 · 在场的人的外貌 · 世界锁定的画风),记号 / op / 引擎消息 / 场外话 / 选项都拿掉,不碰灵魂的秘密;
作者的图先(开场 CG / show → cg,免费);参考图不用 -cNN 候选;这一局画过的图(记 / 删 / 内联的那张留在局里);本机的平台门(没登录 = signin)。"""
from __future__ import annotations

import base64
import json
import shutil
import threading
import urllib.request
from pathlib import Path
from unittest.mock import patch

from _paths import PRODUCT_TEMPLATES
from neonrp import template as TP
from neonrp.core import scene_art as SA


def _run(tmp_path: Path, name: str = "pct-house", art: str | None = "full") -> Path:
    """A built run; ``art`` = the template's realtime_art (None = left out = off)."""
    src = tmp_path / f"{name}.template"
    shutil.copytree(PRODUCT_TEMPLATES / f"{name}.template", src)
    if art is not None:
        d = json.loads((src / "template.json").read_text(encoding="utf-8"))
        d["realtime_art"] = art
        (src / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    dest = tmp_path / "run"
    TP.build(TP.load(src), dest)
    return dest


def _beats(root: Path, *beats: dict) -> None:
    p = root / ".neonrp" / "orchestration" / "main.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(b, ensure_ascii=False) + "\n" for b in beats), encoding="utf-8")


OPENING = {"turn_seq": 0, "player": {"input": "开始游戏。"}, "world_location": "hall",
           "apply": {"beat": {"kind": "opening", "script": [{"role": "host", "text": "雾从巷口一路漫到灰橡宅的台阶上。"}]}}}
TURN = {"turn_seq": 1, "player": {"input": "我看看灯下的托盘"}, "world_location": "hall",
        "apply": {"narration_plain": "你走到0油灯旁,银托盘上留着一圈水渍。[~show plot:x] <引擎:旁白> (OOC: 主持备注)\n① 问管家\n② 上楼",
                  "reports": [{"iid": "si-chara0001", "name": "温妮", "text": "「别碰它。」", "judgment": {"thought": "她其实知道舅舅在地窖"}}]},
        "souls": [{"sid": "chara", "instance_id": "si-chara0001", "speech": "「别碰它。」"}]}


def test_a_beat_becomes_the_platforms_fields(tmp_path):
    root = _run(tmp_path)
    _beats(root, OPENING, TURN)
    b = SA.brief(root, i=1)
    f = b["fields"]
    assert b["i"] == 1 and b["latest"] and b["cg"] is None
    assert f["world_ref"] == "hub/template/pct-house" and f["size"] == "1536x1024" and f["kind"] == "place"
    assert len(f["scene"]) <= 600 and len(f["style"]) <= 200 and len(f.get("caption") or "") <= 200
    assert f["style"].startswith("二次元插画"), "the template's locked style (ui.recipe.style)"
    assert "Place: 门厅" in f["scene"] and "银托盘上留着一圈水渍" in f["scene"]
    assert "温妮" in f["scene"] and "深棕微卷短发" in f["scene"], "who is on stage, and how she looks"
    for bad in ("", "[~show", "<引擎", "OOC", "主持备注", "① 问管家", "地窖", "知道舅舅"):
        assert bad not in json.dumps(b, ensure_ascii=False), bad
    secrets = (root / "souls" / "chara-si-chara0001" / "background" / "secrets.md").read_text(encoding="utf-8")
    assert not any(line.strip() and line.strip() in json.dumps(b, ensure_ascii=False) for line in secrets.splitlines() if len(line.strip()) > 12)
    ext = b["extended"]
    assert ext["style_locked"] and ext["characters"][0] == {"name": "温妮", "role": "", "look": ext["characters"][0]["look"], "ref": "soul.portrait:chara"}
    kinds = [r["kind"] for r in ext["references"]]
    assert kinds[0] == "place" and "character" in kinds and all(r["sha256"] for r in ext["references"])


def test_the_authors_picture_comes_first_and_candidates_are_never_references(tmp_path):
    root = _run(tmp_path)
    _beats(root, OPENING, TURN)
    first = SA.brief(root, i=0)
    assert first["cg"] and first["cg"]["slot"].startswith("opening.cg:") and first["cg"]["by"] == "opening"
    assert SA.listing(root)["cg"].keys() == {"0"}
    a = root / "souls" / "chara-si-chara0001" / "assets"
    for p in a.glob("portrait.*"):
        p.unlink()
    for p in a.glob("sprite.*"):
        p.rename(a / f"sprite-c01{p.suffix}")
    (a / "base-c02.png").write_bytes(b"\x89PNG")
    refs = SA.brief(root, i=1)["extended"]["references"]
    assert not [r for r in refs if "chara" in r["path"]], "a -cNN candidate is never a reference"
    assert SA.CANDIDATE.search("stand-c01") and not SA.CANDIDATE.search("stand")


def test_the_worlds_switch_defaults_to_off(tmp_path):
    root = _run(tmp_path, art=None)
    _beats(root, OPENING, TURN)
    assert SA.mode(root) == "off" and SA.listing(root)["realtime_art"] == "off"
    off = SA.brief(root, i=1)
    assert off["disabled"] and off["reason"] == "realtime_art_off" and "fields" not in off and off["cg"] is None
    assert SA.brief(root, i=0)["cg"]["slot"].startswith("opening.cg:"), "the author's picture still shows"


def test_scene_only_draws_nobody(tmp_path):
    root = _run(tmp_path, art="scene_only")
    _beats(root, OPENING, TURN)
    b = SA.brief(root, i=1)
    assert not b["disabled"] and b["realtime_art"] == "scene_only"
    assert "No people in the picture" in b["fields"]["scene"] and "深棕微卷短发" not in b["fields"]["scene"]
    assert b["extended"]["characters"] == [] and not b["extended"]["people"] and "caption" not in b["fields"]
    assert [r["kind"] for r in b["extended"]["references"]] == ["place"]


def test_lint_knows_the_switch(tmp_path):
    for v, bad in (("full", False), ("scene_only", False), ("off", False), ("on", True), (True, True)):
        src = tmp_path / f"t-{v}.template"
        shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", src)
        d = json.loads((src / "template.json").read_text(encoding="utf-8"))
        d["realtime_art"] = v
        (src / "template.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        t = TP.load(src)
        codes = {p["code"] for p in TP.lint(t, i18n=False)["problems"] if p["level"] == "block"}
        assert ("meta.realtime_art" in codes) == bad, (v, codes)
        assert t.meta().get("realtime_art") == (None if bad else v)


def test_the_runs_pictures(tmp_path):
    root = _run(tmp_path)
    _beats(root, OPENING, TURN)
    iid = "si-0f2c4e1a-1111-4a5b-9c3d-123456789abc"
    row = SA.record(root, {"id": iid, "i": 1, "caption": "「别碰它。」", "credits": 126})
    assert row["stored"] and not row["local"]
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 32).decode()
    own = SA.record(root, {"b64_png": png, "i": 1})
    assert own["id"].startswith("si-") and own["local"] and SA.inline_file(root, own["id"]) is not None
    items = SA.listing(root)["items"]
    assert [x["id"] for x in items] == [iid, own["id"]] and items[1]["local"]
    assert SA.forget(root, own["id"]) and SA.inline_file(root, own["id"]) is None
    assert not SA.forget(root, own["id"])
    for bad in ({"id": "../x", "i": 1}, {"id": iid}, {"b64_png": base64.b64encode(b"GIF89a").decode(), "i": 1}):
        try:
            SA.record(root, bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def test_the_platform_door_signed_out_and_signed_in(tmp_path, monkeypatch):
    monkeypatch.delenv("WORLDLINES_API_KEY", raising=False)
    monkeypatch.setattr("neonrp.core.worldlines_auth.access_token", lambda: None)
    assert SA.platform("status") == (200, {"signed_in": False, "available": False, "reason": "signin"})
    assert SA.platform("generate", {})[0] == 401
    calls = []

    def fake(method, url, token, body=None, timeout=30):
        calls.append((method, url))
        if url.endswith("/v1/me/balance?product=hub"):
            return 200, {"features": {"realtime_images": {"available": True}}}
        if url.endswith("/v1/images/generate/price"):
            return 200, {"credits": {"1536x1024": 126}, "daily_left": 20}
        return 201, {"id": "si-x"}
    monkeypatch.setattr("neonrp.core.worldlines_auth.access_token", lambda: "tok")
    monkeypatch.setattr(SA, "_call", fake)
    monkeypatch.setattr("neonrp.core.worldlines_auth.API_BASE", "https://ai.example/v1")
    st, body = SA.platform("status")
    assert body["available"] and body["price"]["credits"]["1536x1024"] == 126
    assert ("GET", "https://ai.example/v1/images/generate/price") in calls, "the OpenAI-style base's /v1 is not doubled"
    assert SA.platform("url", iid="../../etc")[0] == 404


def test_http_routes(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    store = tmp_path / "store"
    shutil.copytree(PRODUCT_TEMPLATES / "pct-house.template", store / "pct-house.template")
    tj = store / "pct-house.template" / "template.json"
    tj.write_text(json.dumps({**json.loads(tj.read_text(encoding="utf-8")), "realtime_art": "full"}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    monkeypatch.setattr("neonrp.core.worldlines_auth.access_token", lambda: None)
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
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET",
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        try:
            call("/api/v1/play/session", {"slug": "tpl--pct-house", "output_lang": "zh"})
            _beats(server.runtime.root, OPENING, TURN)
            st, b = call("/api/v1/play/engine/scene-art/brief?i=1")
            assert st == 200 and b["fields"]["world_ref"] == "hub/template/pct-house"
            assert call("/api/v1/play/engine/scene-art/brief?i=9")[0] == 404
            assert call("/api/v1/play/engine/scene-art/platform/status") == (200, {"signed_in": False, "available": False, "reason": "signin"})
            assert call("/api/v1/play/engine/scene-art/record", {"id": "si-0f2c4e1a-1111-4a5b-9c3d-123456789abc", "i": 1})[0] == 201
            st, L = call("/api/v1/play/engine/scene-art")
            assert st == 200 and len(L["items"]) == 1 and "0" in L["cg"]
            assert call("/api/v1/play/engine/scene-art/forget", {"id": "si-0f2c4e1a-1111-4a5b-9c3d-123456789abc"}) == (200, {"forgotten": True})
            assert call("/api/v1/play/engine/scene-art/platform/generate", {"scene": "x"})[0] == 401, "on: the door is open (signed out here)"
            tpl = SA._meta(server.runtime.root) / "template.json"
            tpl.write_text(json.dumps({**json.loads(tpl.read_text(encoding="utf-8")), "realtime_art": "off"}, ensure_ascii=False), encoding="utf-8")
            st, b = call("/api/v1/play/engine/scene-art/brief?i=1")
            assert st == 200 and b["disabled"] and b["reason"] == "realtime_art_off"
            st, e = call("/api/v1/play/engine/scene-art/platform/generate", {"scene": "x"})
            assert st == 403 and e["error"]["code"] == "realtime_art_off"
        finally:
            server.shutdown()
