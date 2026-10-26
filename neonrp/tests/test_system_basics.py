"""System test of the basic features, end to end over the web API the 1.0 UI uses (「测试主要包括…约定了里面需要
有的一些功能,比如说 Vault…Obsidian 那部分功能,还有其他一些基础功能」).

One run of the stoneford-elena template, stub model (no network, deterministic), in an isolated HOME. In order:
    ① bind a fresh run → the opening lands, the run is listed as a save (plan_loop off: the stub never fills a plan board)
    ② play turns → each lands a trace and a world commit
    ③ Vault: project the run into Obsidian notes (souls · places · canvas), links between them, the user's own notes kept,
       re-projected automatically after the next turn
    ④ Obsidian: register the vault in the app's vault list (a temp copy of it) and seed .obsidian/
    ⑤ worldlines: roll back to an earlier commit → a new branch, the old line kept
    ⑥ export the run to a zip and load it back (secrets and engine internals stay out)
    ⑦ the 1.0 UI's reads: map (layers · pins), schema, orchestration graph, template lint, contract, settlement
    ⑧ settings + delete a save
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from _paths import PRODUCT_TEMPLATES

pytestmark = pytest.mark.timeout(300) if hasattr(pytest.mark, "timeout") else []


@pytest.fixture(scope="module")
def web(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("sys")
    store = tmp / "store"
    for tid in ("stoneford-elena", "stoneford-three-towns"):
        shutil.copytree(PRODUCT_TEMPLATES / f"{tid}.template", store / f"{tid}.template")
    mp = pytest.MonkeyPatch()
    mp.setenv("NEONRP_TEMPLATE_PATH", str(store))
    mp.setenv("NEONRP_DISABLE_CLAUDE_CODE", "1")
    from neonrp.commands.web import make_server

    plays = tmp / "lib" / "plays"
    patches = [patch("neonrp.worlds.WORLDS_HOME", tmp / "lib" / "worlds"), patch("neonrp.worlds.PLAYS_HOME", plays),
               patch("neonrp.worlds.STUDIO_HOME", tmp / "lib" / "studio"),
               patch("neonrp.commands.web.WebRuntime.gateway_start", lambda self: {"sid": "local", "root": self.root.name})]
    for p in patches:
        p.start()
    server = make_server(None, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None, method=None, raw=False):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     method=method or ("GET" if body is None else "POST"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read()
            return b if raw else (json.loads(b) if b else {})

    ns = {"call": call, "server": server, "tmp": tmp}
    yield ns
    server.shutdown()
    for p in patches:
        p.stop()
    mp.undo()


def _traces(call) -> list:
    return call("/traces").get("turns", [])


def _say(web, text: str, timeout: float = 120) -> dict:
    call = web["call"]
    before = len(_traces(call))
    t0 = time.time()
    while True:  # 409 = the previous turn is still finishing its after-steps
        try:
            call("/cmd", {"text": text})
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 409 or time.time() - t0 > 60:
                raise
            time.sleep(0.5)
    t0 = time.time()
    while time.time() - t0 < timeout:
        rows = _traces(call)
        if len(rows) > before:
            return call(f"/trace?i={rows[-1]['i']}")
        time.sleep(0.3)
    raise AssertionError(f"turn did not land: {text!r}")


def test_01_bind_opening_and_save(web):
    call = web["call"]
    r = call("/api/v1/play/session", {"slug": "tpl--stoneford-elena", "output_lang": "zh"})
    web["root"] = Path(web["server"].runtime.root)
    # stub model for this run: zero cost, deterministic
    (web["root"] / ".neonrp" / "config.json").write_text(json.dumps({"llm": {"provider": "stub", "model": "stub-model"}}), encoding="utf-8")
    # this suite tests the basics, not the planning layer: every line resolves straight away (the stub never fills a plan board)
    eng = web["root"] / "game" / "meta" / "engine.json"
    cfg = json.loads(eng.read_text(encoding="utf-8")) if eng.exists() else {}
    cfg.setdefault("turn", {})["plan_loop"] = "off"
    eng.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    call("/start", {})  # the page fires the localized opening once on a fresh run
    t0 = time.time()
    while not _traces(call) and time.time() - t0 < 30:
        time.sleep(0.3)
    first = call(f"/trace?i={_traces(call)[0]['i']}")
    # the opening is the world's authored scene as its own beat, no model and nothing landed (8590ef87, 10-11: the
    # opening node, with or without the planning beat) — the turns after it land (test_02)
    beat = (first.get("apply") or {}).get("beat") or {}
    assert beat.get("kind") == "opening" and str((first.get("apply") or {}).get("narration_plain") or "").strip(), first.get("apply")
    saves = call("/api/v1/play/saves")["saves"]
    assert any(s.get("in_memory") for s in saves)
    web["slug"] = r.get("slug")


def test_02_turns_land_traces_and_commits(web):
    call = web["call"]
    for line in ("我四处看看。", "定。"):
        _say(web, line)
    rows = _traces(call)
    assert len(rows) >= 3
    commits = call("/api/v1/play/engine/commits")
    assert commits["nodes"], "a resolved turn lands a world commit"
    web["commits"] = commits


def test_03_vault_projection_links_and_user_notes(web):
    from neonrp.core.vault import VAULT_DIRNAME, project_vault

    root = web["root"]
    rep = project_vault(root)
    vault = rep.vault_dir or root / VAULT_DIRNAME
    notes = list(vault.rglob("*.md"))
    assert len(notes) >= 5
    text = "\n".join(p.read_text(encoding="utf-8") for p in notes)
    assert "艾琳娜" in text and "北门" in text          # one note per soul / place, named
    assert "[[" in text                                  # notes link to each other (Obsidian's graph)
    assert list(vault.rglob("*.canvas")), "who-is-where canvas"
    mine = vault / "我的笔记" / "我的.md"
    mine.parent.mkdir(parents=True, exist_ok=True)
    mine.write_text("我自己写的,不许动", encoding="utf-8")
    again = project_vault(root)
    assert mine.read_text(encoding="utf-8") == "我自己写的,不许动"
    assert not again.changed                             # deterministic: same state → same notes
    # a landed turn re-projects by itself once the vault exists
    stamp = {p: p.stat().st_mtime for p in vault.rglob("*.md") if "我的笔记" not in p.parts}
    _say(web, "我们往主街走。")
    _say(web, "定。")
    newer = [p for p in vault.rglob("*.md") if "我的笔记" not in p.parts and p.stat().st_mtime > stamp.get(p, 0)]
    assert newer, "the vault follows the world after a turn"
    assert mine.read_text(encoding="utf-8") == "我自己写的,不许动"
    web["vault"] = vault


def test_04_obsidian_register_and_seed(web, tmp_path):
    from neonrp.core import obsidian

    vault, reg = web["vault"], tmp_path / "obsidian.json"
    reg.write_text(json.dumps({"vaults": {}}), encoding="utf-8")
    assert obsidian.register_vault(vault, registry=reg)
    assert obsidian.is_registered(vault, registry=reg)
    assert not obsidian.register_vault(vault, registry=reg)          # second time is a no-op
    assert obsidian.open_uri(vault).startswith("obsidian://open?")
    seeded = obsidian.seed_config(vault)
    assert (vault / ".obsidian").is_dir() and isinstance(seeded, list)


def test_05_rollback_forks_a_branch(web):
    call = web["call"]
    commits = call("/api/v1/play/engine/commits")
    nodes = commits["nodes"]
    assert len(nodes) >= 2
    target = sorted(nodes, key=lambda n: n.get("turn_seq", 0))[0]["id"]
    before = commits["branch"]
    t0 = time.time()
    while True:  # the trace lands before the turn's after-steps finish; the engine refuses a rollback until then
        out = call("/rollback", {"commit": target})
        if out.get("error") != "a turn is in progress" or time.time() - t0 > 60:
            break
        time.sleep(0.5)
    assert out.get("ok") is not False, out
    after = call("/api/v1/play/engine/commits")
    assert after["branch"] != before and after["branch"].startswith("rollback-")
    assert before in after["branches"], "the old line is kept"


def test_06_export_and_load_back(web, tmp_path):
    from neonrp.core.world_export import export_world, load_world_zip, summarize_archive

    root = web["root"]
    z = export_world(root, tmp_path / "out.zip")
    names = zipfile.ZipFile(z).namelist()
    assert any(n.endswith("game/meta/run_state.json") for n in names)
    assert not any("/.neonrp/config.json" in n for n in names), "the run's model config (keys) never leaves"
    assert summarize_archive(z)
    back = load_world_zip(z, games_dir=tmp_path / "games")
    assert (back / "game" / "meta" / "run_state.json").exists()


def test_07_reads_the_ui_uses(web):
    call = web["call"]
    m = call("/api/v1/play/map")
    assert "T001" in m["levels"] and m["levels"]["T001"]["hotspots"]
    sc = call("/api/v1/play/schema")
    assert any(v["name"] == "player.gold" for v in sc["variables"]) and sc["actions"]
    g = call("/api/v1/play/engine/graph")
    # test_01 turned the talk beat off, and the graph is what the run plays (10-25): the plain turn, no talk node —
    # the same as the open engine, where the planning beat (the private layer's, 10-10) is not there at all
    assert "resolve" in g["graph"]["nodes"] and "plan" not in g["graph"]["nodes"]
    lint = call("/api/v1/local/templates/stoneford-elena/lint")
    assert "problems" in lint and "counts" in lint
    assert isinstance(call("/api/v1/play/engine/contract"), dict)
    assert isinstance(call("/api/v1/play/engine/settlement"), dict)
    slots = call("/api/v1/local/templates/stoneford-elena/assets")["slots"]
    assert any(s["slot"] == "card:cover" for s in slots)
    ts = call("/api/v1/local/templates/stoneford-elena/contract?fmt=ts", raw=True).decode()
    assert "CONTRACT_HASH" in ts


def test_08_settings_and_delete_save(web):
    call = web["call"]
    s = call("/api/v1/local/settings")
    assert s["presets"] and "image" in s
    saves = call("/api/v1/play/saves")["saves"]
    idle = [x for x in saves if not x.get("in_memory")]
    if not idle:  # make one: start another run, then delete the first
        call("/api/v1/play/session", {"slug": "tpl--stoneford-three-towns", "output_lang": "zh"})
        idle = [x for x in call("/api/v1/play/saves")["saves"] if not x.get("in_memory")]
    sid = idle[0]["session_id"]
    call(f"/api/v1/play/saves/{sid}", method="DELETE")
    assert all(x["session_id"] != sid for x in call("/api/v1/play/saves")["saves"])
