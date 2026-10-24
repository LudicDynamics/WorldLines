"""回放包 worldlines.replay/1(10-15 / 10-18:打完一局主动分享):
- 引擎 core/replay_pack:从一局的回合轨迹只抄展示要的(叙事 · 台词 · 骰子 · 结局 · 角色 / 地点引用),计划 / 角色打算 / 提议 / 计时 / 用量一律不进;密钥形状的串打码;老局没轨迹拍点就读 story.md
- 回放包 zip:timeline.json 进、原始轨迹 orchestration.jsonl 不进;v3 局没有 story.md 也能导出(从 timeline 渲染)
- 本机回放库 core/replay_library + 本地接口 /api/v1/local/replays(列表 · 导出 · 文档 · 封面 · 分享 · 删除)"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp.core import replay_export as RE
from neonrp.core import replay_library as RL
from neonrp.core import replay_pack as RP
from _paths import PRODUCT

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
KEY = "sk-" + "a" * 40


def _rec(n, kind, *, said="", script=None, narration="", rolled=None, loc="T1/hall", ended=None, **extra):
    beat = {"kind": kind, "script": script or [], "rolled": rolled or [], "board": {"Mira": "secret plan"}, "checks": [{"text": "check text"}]}
    apply = {"narration_plain": narration, "beat": beat, "variables": {"location": loc, "time.day": 1, "time.clock": f"2{n}:00"},
             "proposals": [{"raw": "<lines>RAW PROPOSAL</lines>"}], "ended": ended}
    return {"schema_version": 1, "turn_seq": n, "player": {"input": said}, "world_location": loc.rsplit("/", 1)[-1],
            "plan": {"tension": 0.9, "souls": {"x": {"reacts": 0.5}}}, "timing": {"v3": {"usage": {"prompt_tokens": 9}}},
            "bus_messages": [{"topic": "engine/event"}], "notes": "NOTE", "world_agent": {"tool_calls": [{"name": "op:set"}]},
            "apply": apply, **extra}


def _run(root: Path, *, story: bool = False, ending: bool = True) -> Path:
    (root / ".neonrp" / "orchestration").mkdir(parents=True)
    (root / ".neonrp" / "config.json").write_text(json.dumps({"api_key": KEY}), encoding="utf-8")
    (root / ".neonrp" / "manifest.json").write_text(json.dumps({"current_branch": "main"}), encoding="utf-8")
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "template.json").write_text(json.dumps({"id": "mist-house"}), encoding="utf-8")
    for area, node, nm in (("T1", "hall", "Hall"), ("T1", "study", "Study")):
        (root / "game" / "locations" / area / node).mkdir(parents=True, exist_ok=True)
        (root / "game" / "locations" / area / node / "location.json").write_text(json.dumps({"id": node, "name": nm}), encoding="utf-8")
    (root / "game" / "locations" / "T1" / "location.json").write_text(json.dumps({"id": "T1", "name": "Mist House"}), encoding="utf-8")
    (root / "game" / "plots" / "P01").mkdir(parents=True)
    (root / "game" / "plots" / "P01" / "plot.json").write_text(json.dumps({"endings": {"E1": {"title": "Fog", "kind": "true", "assets": {"image": "assets/ending-E1.webp"}}}}), encoding="utf-8")
    (root / "game" / "plots" / "P01" / "assets").mkdir()
    (root / "game" / "plots" / "P01" / "assets" / "ending-E1.webp").write_bytes(b"RIFFending")
    (root / "assets" / "places").mkdir(parents=True)
    (root / "assets" / "places" / "T1__study.webp").write_bytes(b"RIFFstudy")
    (root / "souls" / "mira-si-mira0001").mkdir(parents=True)
    (root / "souls" / "mira-si-mira0001" / "assets").mkdir()
    (root / "souls" / "mira-si-mira0001" / "assets" / "portrait.png").write_bytes(PNG)
    (root / "souls" / "mira-si-mira0001" / "soul.json").write_text(json.dumps({"sid": "mira", "name": "Mira", "name_local": "米拉"}), encoding="utf-8")
    recs = [
        _rec(0, "opening", said="Start the game.\n\nLanguage: English.", narration="Fog on the steps.",
             script=[{"who": "Host", "role": "host", "text": "Fog on the steps."}]),
        _rec(1, "plan", said="ask Mira", souls=[{"sid": "mira", "instance_id": "si-mira0001", "activated": True, "reason": "co-located"}], script=[
            {"who": "Ines", "role": "player", "text": "ask Mira"},
            {"who": "Host", "role": "handoff", "text": "mic to Mira: where first?"},
            {"who": "米拉", "role": "soul", "text": "“The study.”\n(intends: search the study before the butler wakes)"}]),
        _rec(1, "resolve", said="ask Mira", narration=f"[Ines Spot: 12 > 40] → fail\n\nThe study is cold. {KEY}",
             rolled=["Ines Spot 1d100 = 12 vs 40 → fail"], loc="T1/study",
             ended={"id": "E1", "title": "Out of the fog", "turn": 1, "trigger": "x"} if ending else None),
    ]
    (root / ".neonrp" / "orchestration" / "main.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
    if story:
        (root / "story.md").write_text("# log\n\n## T0 · Hall · Day1 08:00\n\n> look\n\n**world-agent**：Dust.\n", encoding="utf-8")
    (root / "cover.png").write_bytes(PNG)
    return root


def test_doc_keeps_only_what_the_player_saw(tmp_path):
    doc = RP.build_replay_doc(_run(tmp_path / "mist-house-20261018-101010"), world_id="mist-house", world_name="Mist House", lang="en", has_cover=True)
    assert doc["format"] == "worldlines.replay/1" and doc["cover"] == "cover.png" and doc["world"] == {"id": "mist-house", "name": "Mist House"}
    t0, t1 = doc["turns"]
    assert t0["beats"][0]["kind"] == "opening" and "input" not in t0["beats"][0], "the opening's input is the engine's start line"
    plan, resolve = t1["beats"]
    assert plan["input"] == "ask Mira" and "input" not in resolve, "said once, shown once"
    assert [ln["role"] for ln in plan["lines"]] == ["soul"], "the player's own line is the input; the handoff is scaffolding"
    assert plan["lines"][0] == {"who": "米拉", "role": "soul", "text": "“The study.”", "cast": "mira"}, "her draft stays backstage"
    assert resolve["dice"] == [{"text": "Ines Spot 1d100 = 12 vs 40 → fail"}]
    assert resolve["lines"][0]["role"] == "narrator" and resolve["lines"][0]["text"].startswith("The study is cold."), "roll header moves to dice"
    assert t1["place"] == "T1/study" and t1["time"] == {"day": 1, "clock": "21:00"}
    assert doc["places"] == [{"id": "T1/hall", "name": "Hall", "area": "Mist House"}, {"id": "T1/study", "name": "Study", "area": "Mist House"}]
    assert doc["cast"] == [{"id": "mira", "name": "米拉", "role": "soul"}]
    assert doc["ending"] == {"id": "E1", "title": "Out of the fog", "kind": "true", "turn": 1}, "kind from the world's plot"
    blob = json.dumps(doc, ensure_ascii=False)
    for leak in ("secret plan", "check text", "RAW PROPOSAL", "tension", "prompt_tokens", "engine/event", "NOTE", "op:set", "intends", "mic to Mira", KEY):
        assert leak not in blob, leak
    assert "[redacted]" in blob
    assert RP.turn_count(doc) == 1


def test_old_runs_fall_back_to_story_md(tmp_path):
    run = _run(tmp_path / "w", story=True)
    (run / ".neonrp" / "orchestration" / "main.jsonl").write_text(json.dumps({"turn_seq": 0, "souls": []}) + "\n", encoding="utf-8")
    doc = RP.build_replay_doc(run)
    assert doc["turns"] == [{"n": 0, "beats": [{"kind": "turn", "input": "look", "lines": [{"who": "world-agent", "role": "host", "text": "Dust."}], "dice": []}],
                             "place": "Hall", "time": {"clock": "Day1 08:00"}}]
    assert RP.has_content(run)


def test_bundle_has_timeline_not_the_raw_trace(tmp_path):
    run = _run(tmp_path / "mist-house-20261018-101010")
    assert not (run / "story.md").exists() and RE.validate_replay_source(run).ok, "a v3 run without story.md is replayable"
    meta = RE.build_replay_bundle(run, tmp_path / "r.zip", lang="en")
    with zipfile.ZipFile(tmp_path / "r.zip") as zf:
        names = {n.split("/", 1)[1] for n in zf.namelist()}
        story = zf.read("mist-house-replay/story.md").decode()
        doc = json.loads(zf.read("mist-house-replay/timeline.json"))
    assert names == {"replay.json", "timeline.json", "story.md", "cover.png", "assets/ending/E1.webp", "assets/soul.portrait/mira.png", "assets/place.scene/T1__study.webp"}
    assert meta["format"] == "worldlines.replay/1" and meta["schema_version"] == 3 and meta["turns"] == 1 and meta["ending"]["id"] == "E1"
    assert meta["world_ref"] == "hub/template/mist-house" and doc["world"]["id"] == "mist-house" and doc["world"]["ref"] == meta["world_ref"]
    assert "## T1 · Study · Day1 21:00" in story and "> ask Mira" in story


def test_library_export_list_get_share_delete(tmp_path):
    plays = tmp_path / "plays"
    run = _run(plays / "mist-house-20261018-101010")
    with patch.object(RL, "HOME", tmp_path / "replays"):
        e = RL.export(run, lang="en")
        assert e["tpl"] == "mist-house" and e["title"] and e["updated"] and e["ending"]["kind"] == "true"
        assert e["world"]["id"] == "mist-house" and e["turns"] == 1 and e["ending"]["id"] == "E1" and e["has_cover"] and e["shared"] is None
        assert RL.export(run, lang="en")["id"] == e["id"], "same run, same point → the copy already made"
        assert [x["id"] for x in RL.list_replays("mist-house")] == [e["id"]] and RL.list_replays("other") == []
        assert RL.get(e["id"])["turns"][1]["place"] == "T1/study" and RL.cover(e["id"]).read_bytes() == PNG
        sent = {}

        def fake_share(meta, files, *, text, lang):
            sent.update(names=set(files), text=text, meta=meta)
            return {"replay_id": "r1", "ref": "hub/replay/r1", "moment_url": "https://sns.example/m/1"}

        with patch("neonrp.core.replay_share.share_files", fake_share):
            out = RL.share(e["id"], text="hi", lang="en")
        assert out["ref"] == "hub/replay/r1" and sent["names"] == {"replay.json", "timeline.json", "story.md", "cover.png", "assets/ending/E1.webp", "assets/soul.portrait/mira.png", "assets/place.scene/T1__study.webp"}
        assert RL.list_replays()[0]["shared"]["ref"] == "hub/replay/r1"
        with pytest.raises(RL.ReplayLibraryError):
            RL.get("../etc")
        RL.delete(e["id"])
        assert RL.list_replays() == []


def test_library_refuses_a_run_with_nothing_to_replay(tmp_path):
    run = tmp_path / "empty-20261018-101010"
    (run / ".neonrp").mkdir(parents=True)
    with patch.object(RL, "HOME", tmp_path / "replays"), pytest.raises(RL.ReplayLibraryError) as ei:
        RL.export(run)
    assert ei.value.status == 422


def test_on_ending_keeps_the_run_and_never_raises(tmp_path):
    run = _run(tmp_path / "mist-house-20261018-101010")
    with patch.object(RL, "HOME", tmp_path / "replays"):
        RL.on_ending(run, {"id": "E1"})
        RL.on_ending(tmp_path / "missing", {"id": "E1"})
        assert len(RL.list_replays()) == 1


def test_http_local_replays(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    plays = tmp_path / "plays"
    _run(plays / "mist-house-20261018-101010")
    monkeypatch.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    with patch.object(RL, "HOME", tmp_path / "replays"), patch("neonrp.worlds.PLAYS_HOME", plays):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def call(path, body=None, method=None):
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(base + path, data=data, method=method or ("GET" if data is None else "POST"), headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                    return r.status, (json.loads(raw) if r.headers.get("Content-Type", "").startswith("application/json") else raw)
            except urllib.error.HTTPError as e:
                raw = e.read()
                try:
                    return e.code, json.loads(raw)
                except ValueError:
                    return e.code, raw

        try:
            assert call("/api/v1/local/replays") == (200, {"replays": []})
            st, e = call("/api/v1/local/replays", {"session_id": "mist-house-20261018-101010", "lang": "en"})
            assert st == 200 and e["cover_url"] == f"/api/v1/local/replays/{e['id']}/cover"
            st, body = call("/api/v1/local/replays?world=mist-house")
            assert [x["id"] for x in body["replays"]] == [e["id"]]
            st, doc = call(f"/api/v1/local/replays/{e['id']}")
            assert st == 200 and doc["format"] == "worldlines.replay/1" and doc["local"]["id"] == e["id"]
            assert call(f"/api/v1/local/replays/{e['id']}/cover") == (200, PNG)
            assert call("/api/v1/local/replays", {"session_id": "../x"})[0] == 400
            assert call("/api/v1/local/replays", {"session_id": "nope"})[0] == 404
            assert call("/api/v1/local/replays/nope")[0] == 404
            assert call(f"/api/v1/local/replays/{e['id']}", method="DELETE") == (200, {"ok": True})
            assert call("/api/v1/local/replays") == (200, {"replays": []})
        finally:
            server.shutdown()


def test_a_turn_that_ends_the_run_keeps_a_replay(tmp_path):
    """orchestration_trace.append_turn_trace: the trace line of an ending (or an exit) → a replay in the library, with that last beat."""
    import time

    from neonrp.core.orchestration_trace import TurnTrace, append_turn_trace

    run = _run(tmp_path / "mist-house-20261018-101010", ending=False)
    append_turn_trace(run, "main", TurnTrace(turn_seq=2, apply={"narration_plain": "No ending yet.", "beat": {"kind": "resolve"}}))
    time.sleep(0.3)
    assert RL.list_replays() == [], "no ending, no replay"
    append_turn_trace(run, "main", TurnTrace(turn_seq=3, apply={"narration_plain": "The fog lifts.", "beat": {"kind": "resolve"},
                                                                 "ended": {"id": "E1", "title": "Out of the fog", "turn": 3}}))
    for _ in range(50):
        if RL.list_replays():
            break
        time.sleep(0.1)
    (e,) = RL.list_replays()
    assert e["ending"]["id"] == "E1" and "The fog lifts." in json.dumps(RL.get(e["id"])["turns"][-1])


def test_doc_carries_the_stage_events_and_the_pictures(tmp_path):
    """For the player (10-18): each beat's contract events (backstage keys out), who is on the scene, and the run's
    own pictures — scene · portrait · the ending's art — as bundle members."""
    run = _run(tmp_path / "mist-house-20261018-101010")
    meta, files = RE.pack_replay(run, lang="en")
    doc = json.loads(files["timeline.json"])
    plan = doc["turns"][1]["beats"][0]
    assert plan["present"] == ["mira"]
    names = [e[0] for e in plan["events"]]
    assert "plan.beat" in names and "node.enter" not in names and "tool" not in names and "soul.mind" not in names
    pb = dict(plan["events"])["plan.beat"]
    assert "board" not in pb and "checks" not in pb and "mic" not in pb
    assert [x["role"] for x in pb["script"]] == ["player", "soul"] and "intends" not in json.dumps(pb), "handoff + her draft stay out"
    assert doc["assets"] == {"place.scene:T1/study": "assets/place.scene/T1__study.webp", "soul.portrait:mira": "assets/soul.portrait/mira.png",
                             "ending:E1": "assets/ending/E1.webp"}
    assert doc["ending"]["image"] == "assets/ending/E1.webp" and meta["ending"]["image"] == "assets/ending/E1.webp"
    assert files["assets/ending/E1.webp"] == b"RIFFending" and files["assets/soul.portrait/mira.png"] == PNG
    assert not any(n.endswith("config.json") or n.startswith(".neonrp") for n in files)


def test_pack_replay_writes_nothing(tmp_path, monkeypatch):
    """The browser build packs straight from its run: no zip, no temp dir, no replay library."""
    import tempfile

    run = _run(tmp_path / "mist-house-20261018-101010")
    monkeypatch.setattr(tempfile, "TemporaryDirectory", lambda *a, **k: (_ for _ in ()).throw(AssertionError("temp dir")))
    monkeypatch.setattr(zipfile, "ZipFile", lambda *a, **k: (_ for _ in ()).throw(AssertionError("zip")))
    before = sorted(p for p in tmp_path.rglob("*"))
    with patch.object(RL, "HOME", tmp_path / "nope"):
        meta, files = RE.pack_replay(run)
    assert sorted(p for p in tmp_path.rglob("*")) == before and "timeline.json" in files and meta["turns"] == 1


def test_share_uploads_the_pictures(tmp_path):
    from neonrp.core import replay_share as RS

    assert RS._uploadable("assets/ending/E1.webp") and RS._uploadable("cover.png") and RS._uploadable("timeline.json")
    assert not RS._uploadable("local.json") and not RS._uploadable("orchestration.jsonl")


@pytest.mark.skipif(not (PRODUCT / "ui" / "app" / "hub" / "play" / "wlweb.py").is_file(), reason="the Hub source (hub/play) is not in the open repo")
def test_browser_bridge_carries_bytes_as_base64():
    """hub/play/wlweb._body: text as it is; a picture (not UTF-8) as base64 + the flag the worker decodes (10-18)."""
    import base64
    import importlib.util

    spec = importlib.util.spec_from_file_location("wlweb_t", PRODUCT / "ui" / "app" / "hub" / "play" / "wlweb.py")
    W = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(W)
    assert W._body(None) == ("", 0) and W._body('{"a": "雾"}'.encode()) == ('{"a": "雾"}', 0)
    data, flag = W._body(PNG)
    assert flag == 1 and base64.b64decode(data) == PNG
    sent = {}
    W.HOST["xhr"] = lambda m, u, h, body, ms, binary: sent.update(body=body, binary=binary) or [200, "{}", ""]
    W._xhr("PUT", "https://storage.example/obj", {}, PNG)
    assert sent["binary"] == 1 and base64.b64decode(sent["body"]) == PNG


def test_library_keeps_and_serves_the_pictures(tmp_path):
    run = _run(tmp_path / "plays" / "mist-house-20261018-101010")
    with patch.object(RL, "HOME", tmp_path / "replays"):
        e = RL.export(run)
        assert RL.file(e["id"], "assets/ending/E1.webp").read_bytes() == b"RIFFending"
        assert RL.file(e["id"], "../local.json") is None and RL.file(e["id"], "local.json") is None and RL.file(e["id"], "assets/../local.json") is None
        sent = {}
        with patch("neonrp.core.replay_share.share_files", lambda meta, files, **k: sent.update(names=set(files)) or {"ref": "hub/replay/r"}):
            RL.share(e["id"])
        assert {"assets/ending/E1.webp", "assets/soul.portrait/mira.png", "assets/place.scene/T1__study.webp"} <= sent["names"]


def test_ending_turn_in_the_browser_build_never_starts_a_thread(tmp_path, monkeypatch):
    """Pyodide has no threads (and no replay library): the trace line of an ending is written, nothing else happens."""
    import sys
    import threading

    from neonrp.core.orchestration_trace import TurnTrace, append_turn_trace

    run = _run(tmp_path / "mist-house-20261018-101010", ending=False)
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setattr(threading.Thread, "start", lambda self: (_ for _ in ()).throw(RuntimeError("can't start new thread")))
    append_turn_trace(run, "main", TurnTrace(turn_seq=3, apply={"beat": {"kind": "resolve"}, "ended": {"id": "E1"}}))
    assert '"E1"' in (run / ".neonrp" / "orchestration" / "main.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    assert RL.list_replays() == []


def test_pictures_fall_back_to_the_template(tmp_path, monkeypatch):
    """A run without its own copies (the browser build keeps pictures in the template): the template's slot files go in —
    scene · portrait · ending art · the card cover as the replay's cover."""
    from neonrp.core import replay_pack as RPk

    run = _run(tmp_path / "mist-house-20261018-101010")
    for f in [run / "cover.png", run / "assets" / "places" / "T1__study.webp", run / "souls" / "mira-si-mira0001" / "assets" / "portrait.png",
              run / "game" / "plots" / "P01" / "assets" / "ending-E1.webp"]:
        f.unlink()
    tdir = tmp_path / "tpl"
    (tdir / "a").mkdir(parents=True)
    pics = {"card:cover": "cover.jpg", "place.scene:T1/study": "study.webp", "soul.portrait:mira": "mira.png", "ending:E1": "end.webp"}
    for name in pics.values():
        (tdir / "a" / name).write_bytes(b"\xff\xd8\xff\xe0" + name.encode())
    monkeypatch.setattr(RPk, "_template_files", lambda tid: {k: tdir / "a" / v for k, v in pics.items()} if tid == "mist-house" else {})
    meta, files = RE.pack_replay(run, lang="en")
    doc = json.loads(files["timeline.json"])
    assert doc["cover"] == "assets/card/cover.jpg" and files["assets/card/cover.jpg"].startswith(b"\xff\xd8")
    assert doc["ending"]["image"] == "assets/ending/E1.webp" and "assets/soul.portrait/mira.png" in files and "assets/place.scene/T1__study.webp" in files
    assert "cover.png" not in files
    with patch.object(RL, "HOME", tmp_path / "replays"):
        e = RL.export(run)
        assert e["has_cover"] and RL.cover(e["id"]).read_bytes().startswith(b"\xff\xd8")
