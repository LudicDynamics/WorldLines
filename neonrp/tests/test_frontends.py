"""前端台做实(10-17):template/frontends.py + webui/frontend_routes.py —— 内置前端只读的真文件夹、模板自己的 frontends/<name>/、
路径守卫、令牌只给本机、Godot 只关自己起的进程、前端 agent 只写这个文件夹、manifest lint。"""

from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from neonrp.template import frontends as FE
from _paths import PRODUCT

REPO = Path(__file__).resolve().parents[1]
HAVE_SRC = (PRODUCT / "examples" / "clients" / "godot" / "project.godot").is_file()
HAVE_CHAT = (PRODUCT / "ui" / "player" / "chat" / "index.html").is_file()   # the phone (ui/player) is not in the open repo


def _tpl(tmp_path: Path, monkeypatch, tid: str = "pct-house"):
    """A writable copy of a shipped template (the write store = tmp)."""
    from neonrp import template as TP

    store = tmp_path / "templates"
    store.mkdir(exist_ok=True)
    shutil.copytree(PRODUCT / "templates" / f"{tid}.template", store / f"{tid}.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    return TP.load(store / f"{tid}.template")


@pytest.mark.skipif(not HAVE_SRC, reason="no source checkout")
def test_builtin_frontends_are_real_read_only_folders():
    rows = {r["id"]: r for r in FE.listing(None)}
    assert set(rows) == set(FE.BUILTIN)
    assert all(not r["writable"] for r in rows.values())
    d, writable, info = FE.resolve(None, "builtin.godot")
    assert not writable and info["kind"] == "godot"
    paths = {f["path"] for f in FE.tree(d)}
    assert "tests/smoke.gd" in paths and "addons/worldlines/client.gd" in paths
    assert not any(p.startswith(".godot/") for p in paths)
    assert "class_name WorldLinesClient" in FE.read(d, "addons/worldlines/client.gd")
    ts, _, _ = FE.resolve(None, "builtin.ts")
    assert not any(p.startswith(("node_modules/", "dist/")) for p in (f["path"] for f in FE.tree(ts)))


def test_path_guard(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    for bad in ("../x", "a/../../x", "", ".git/config", "node_modules/x.js", "a\\b"):
        with pytest.raises(FE.FrontendError):
            FE._inside(tmp_path, bad)
    FE.write(tmp_path, "src/b.js", "ok")
    assert FE.read(tmp_path, "src/b.js") == "ok"
    with pytest.raises(FE.FrontendError):
        FE.write(tmp_path, "big.txt", "x" * (FE._MAX_WRITE + 1))


def test_create_web_and_chat_and_lint(tmp_path, monkeypatch):
    t = _tpl(tmp_path, monkeypatch)
    m = FE.create(t, "my-web", "web-ts", "我的网页")
    assert m["entry"] == "index.html" and m["targets"] == ["local"]
    d = t.dir / "frontends" / "my-web"
    assert {"frontend.json", "index.html", "main.js", "style.css", "contract.ts"} <= {p.name for p in d.iterdir()}
    assert "CONTRACT_HASH" in (d / "contract.ts").read_text(encoding="utf-8")
    assert FE.check(t, "my-web") == []
    FE.create(t, "phone", "chat")
    assert "pct-house" in (t.dir / "frontends" / "phone" / "main.js").read_text(encoding="utf-8")
    with pytest.raises(FE.FrontendError):
        FE.create(t, "my-web", "web-ts")
    with pytest.raises(FE.FrontendError):
        FE.create(t, "Bad Name", "web-ts")
    with pytest.raises(FE.FrontendError):
        FE.create(t, "x", "unity")
    # the manifest checks
    j = json.loads((d / "frontend.json").read_text(encoding="utf-8"))
    j.update(kind="unity", entry="nope.html", events=["plan.beat", "made.up"], targets=["local", "hub"])
    (d / "frontend.json").write_text(json.dumps(j), encoding="utf-8")
    codes = {(p["level"], p["code"]) for p in FE.check(t, "my-web")}
    assert codes == {("block", "frontend.manifest"), ("block", "frontend.entry"), ("warn", "frontend.events"), ("warn", "frontend.target")}
    (t.dir / "frontends" / "empty").mkdir()
    assert [p["code"] for p in FE.check(t, "empty")] == ["frontend.manifest"]
    assert {p["where"] for p in FE.lint(t)} == {"frontends/my-web", "frontends/empty"}
    rows = {r["id"]: r for r in FE.listing(t)}
    assert rows["phone"]["kind"] == "chat" and rows["phone"]["writable"] and rows["phone"]["problems"] == []


@pytest.mark.skipif(not HAVE_SRC, reason="no source checkout")
def test_create_godot_copies_the_client(tmp_path, monkeypatch):
    t = _tpl(tmp_path, monkeypatch)
    FE.create(t, "my-godot", "godot", "灰橡宅 Godot")
    d = t.dir / "frontends" / "my-godot"
    assert (d / "tests" / "smoke.gd").is_file() and (d / "addons" / "worldlines" / "client.gd").is_file()
    assert not (d / "tests" / "town_play.gd").exists() and not list(d.rglob("*.uid"))
    assert 'config/name="灰橡宅 Godot"' in (d / "project.godot").read_text(encoding="utf-8")
    assert FE.check(t, "my-godot") == []


def test_read_only_template_cannot_get_a_frontend(tmp_path, monkeypatch):
    t = _tpl(tmp_path, monkeypatch)
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(tmp_path / "elsewhere"))
    with pytest.raises(FE.FrontendError):
        FE.create(t, "x", "web-ts")


class _Stub:
    """A model that writes one file — and tries to write outside the folder."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat_stream(self, msgs, tools=None):
        self.seen.append(msgs)
        text = self.replies.pop(0)
        for i in range(0, len(text), 7):
            yield SimpleNamespace(delta=text[i:i + 7], error=None)


def test_agent_writes_only_inside_the_folder(tmp_path, monkeypatch):
    t = _tpl(tmp_path, monkeypatch)
    FE.create(t, "w", "web-ts")
    d = t.dir / "frontends" / "w"
    stub = _Stub(['<read path="main.js"/>',
                  '加了一个背包按钮。\n<file path="bag.js">export const bag = 1</file>\n<file path="../evil.js">x</file>\n<delete path="style.css"/>'])
    evs = list(FE.agent(d, {"kind": "web-ts", "title": "w"}, t, "加一个背包按钮", adapter=stub))
    kinds = [e for e, _ in evs]
    assert kinds[0] == "chunk" and kinds[-1] == "done"
    assert ("tool_use", {"name": "read_file", "path": "main.js"}) in evs
    assert (d / "bag.js").read_text(encoding="utf-8") == "export const bag = 1\n"
    assert not (t.dir / "frontends" / "evil.js").exists()
    assert not (d / "style.css").exists()
    done = evs[-1][1]
    assert done["wrote"] == ["bag.js"] and "[写了 bag.js]" in done["assistant_message"]
    sysm = stub.seen[0][0].content
    assert "WorldLines 的前端 agent" in sysm and '<file path="index.html">' in sysm and "beat_events" in sysm
    assert "main.js" in stub.seen[1][-1].content   # the read came back as the next message


def test_godot_stop_touches_only_our_processes():
    assert FE.godot_stop(1) is False   # launchd: not ours, never touched


# ── over HTTP ──

@pytest.fixture()
def server(tmp_path, monkeypatch):
    from neonrp.commands.web import make_server

    _tpl(tmp_path, monkeypatch)
    with (
        patch("neonrp.worlds.WORLDS_HOME", tmp_path / "worlds"),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "studio"),
    ):
        srv = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            yield srv, f"http://127.0.0.1:{srv.server_address[1]}"
        finally:
            srv.shutdown()


def _call(base, path, body=None, headers=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()), dict(r.headers)


def test_routes(server):
    srv, base = server
    from neonrp.net.host import hub_of

    c, h = _call(base, "/api/v1/local/frontends/_/connect")
    assert c["token"] == hub_of(srv).token and c["protocol"] == "worldlines.net/1"
    assert "Access-Control-Allow-Origin" not in h
    _, h = _call(base, "/api/v1/local/frontends/_/connect", headers={"Origin": "http://localhost:5180"})
    assert "Access-Control-Allow-Origin" not in h   # no CORS: another local page cannot read the token
    with pytest.raises(urllib.error.HTTPError) as e:   # a DNS-rebound / proxied name is not localhost
        _call(base, "/api/v1/local/frontends/_/connect", headers={"Host": "evil.example"})
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        _call(base, "/api/v1/local/frontends/pct-house/new", {"name": "x", "kind": "web-ts"}, headers={"Host": "tailnet.example"})
    assert e.value.code == 403
    lst, _ = _call(base, "/api/v1/local/frontends/pct-house")
    assert lst["tpl"] == "pct-house" and lst["writable"] and lst["bound"] is None
    assert [r["id"] for r in lst["frontends"]][:4] == list(FE.BUILTIN)
    made, _ = _call(base, "/api/v1/local/frontends/pct-house/new", {"name": "site", "kind": "web-ts", "title": "站"})
    assert made["id"] == "site"
    tr, _ = _call(base, "/api/v1/local/frontends/pct-house/site/tree")
    assert tr["writable"] and "index.html" in {f["path"] for f in tr["files"]}
    _call(base, "/api/v1/local/frontends/pct-house/site/file", {"path": "extra.js", "content": "// hi"})
    f, _ = _call(base, "/api/v1/local/frontends/pct-house/site/file?path=extra.js")
    assert f["content"] == "// hi"
    with urllib.request.urlopen(base + "/api/v1/local/frontends/pct-house/site/site/index.html") as r:
        assert r.headers["Content-Type"].startswith("text/html") and b"main.js" in r.read()
    with urllib.request.urlopen(base + "/api/v1/local/frontends/pct-house/site/site/main.js") as r:
        assert r.headers["Content-Type"].startswith("text/javascript")
    with pytest.raises(urllib.error.HTTPError) as e:
        _call(base, "/api/v1/local/frontends/pct-house/site/file", {"path": "../template.json", "content": "{}"})
    assert e.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(base + "/api/v1/local/frontends/pct-house/site/site/../../template.json")
    assert e.value.code in (400, 404)
    if HAVE_SRC:
        with pytest.raises(urllib.error.HTTPError) as e:
            _call(base, "/api/v1/local/frontends/pct-house/builtin.godot/file", {"path": "x.gd", "content": "x"})
        assert e.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as e:
            _call(base, "/api/v1/local/frontends/pct-house/builtin.godot/agent", {"input": "hi"})
        assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:   # no run bound: the smoke would have nothing to play
        _call(base, "/api/v1/local/frontends/pct-house/site/godot/smoke", {})
    assert e.value.code == 409
    with pytest.raises(urllib.error.HTTPError) as e:
        _call(base, "/api/v1/local/frontends/nope")
    assert e.value.code == 404
    st, _ = _call(base, "/api/v1/local/frontends/_/godot")
    assert set(st) == {"bin", "version", "running"}


def test_only_the_protocol_example_has_a_build_step():
    for fid in ("builtin.godot", "builtin.player", "builtin.chat", "nope"):
        with pytest.raises(FE.FrontendError):
            FE.build(fid)
    assert FE.BUILTIN["builtin.ts"]["site"] == "dist"


def test_web_starter_asks_the_real_connect_route():
    assert "fetch('/api/v1/local/frontends/_/connect')" in FE._WEB_JS


def test_frontends_stay_out_of_runs_and_packages_but_lint_sees_them(tmp_path, monkeypatch):
    import io
    import zipfile

    from neonrp import template as TP
    from neonrp.template import package

    t = _tpl(tmp_path, monkeypatch)
    FE.create(t, "w", "web-ts")
    names = zipfile.ZipFile(io.BytesIO(package.export_template(t, any_zone=True))).namelist()
    assert names and not any("/frontends/" in n for n in names)
    (t.dir / "frontends" / "w" / "frontend.json").write_text("{}", encoding="utf-8")
    probs = [p for p in TP.lint(t, i18n=False)["problems"] if p["code"].startswith("frontend.")]
    assert probs and {p["level"] for p in probs} == {"warn"}   # never blocks publishing


def test_words_follow_the_language(tmp_path, monkeypatch):
    t = _tpl(tmp_path, monkeypatch)
    FE.create(t, "w-en", "web-ts", lang="en")
    FE.create(t, "w-zh", "web-ts")
    d = t.dir / "frontends"
    assert 'lang="en"' in (d / "w-en" / "index.html").read_text(encoding="utf-8") and "Connected" in (d / "w-en" / "main.js").read_text(encoding="utf-8")
    assert "已连上" in (d / "w-zh" / "main.js").read_text(encoding="utf-8")
    assert not any("%%" in (d / n / f).read_text(encoding="utf-8") for n in ("w-en", "w-zh") for f in ("index.html", "main.js"))
    assert {r["id"]: r["title"] for r in FE.listing(None, "ja")}["builtin.chat"] == "スマホ"
    stub = _Stub(['ok <file path="a.js">x</file>'])
    evs = list(FE.agent(d / "w-en", {"kind": "web-ts", "title": "w"}, t, "hi", adapter=stub, lang="en"))
    assert evs[-1][1]["assistant_message"] == "ok [wrote a.js]"
    assert stub.seen[0][0].content.startswith("You are the WorldLines front-end agent")


# ── 10-19: copy · export · import ──

def _zip(entries: dict[str, bytes | str]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in entries.items():
            z.writestr(k, v)
    return buf.getvalue()


@pytest.mark.skipif(not HAVE_SRC, reason="no source checkout")
def test_fork_a_builtin_then_it_can_change(tmp_path, monkeypatch):
    t = _tpl(tmp_path, monkeypatch)
    m = FE.fork(t, "builtin.ts", "my-ts", "我的协议示例")
    d = t.dir / "frontends" / "my-ts"
    assert m["from"] == "builtin.ts" and m["title"] == "我的协议示例" and m["site"] == "dist" and m["kind"] == "web-ts"
    assert (d / "src" / "client.ts").is_file() and not (d / "node_modules").exists() and not (d / "dist").exists()
    assert FE.check(t, "my-ts") == []
    _, writable, _ = FE.resolve(t, "my-ts")
    assert writable
    FE.fork(t, "my-ts", "my-ts-2")   # a world's own one copies too, keeping its manifest
    m2 = json.loads((t.dir / "frontends" / "my-ts-2" / "frontend.json").read_text(encoding="utf-8"))
    assert m2["from"] == "my-ts" and m2["title"] == "我的协议示例 · my-ts-2" and m2["site"] == "dist"
    for bad in ("my-ts", "new", "import", "Bad"):
        with pytest.raises(FE.FrontendError):
            FE.fork(t, "builtin.chat", bad)
    monkeypatch.setenv("NEONRP_TEMPLATE_WRITE_DIR", str(tmp_path / "elsewhere"))
    with pytest.raises(FE.FrontendError):   # a read-only world: copy the world first
        FE.fork(t, "builtin.chat", "phone")


def test_export_then_import_under_another_name(tmp_path, monkeypatch):
    import io
    import zipfile

    t = _tpl(tmp_path, monkeypatch)
    FE.create(t, "w", "web-ts")
    d = t.dir / "frontends" / "w"
    (d / "node_modules").mkdir()
    (d / "node_modules" / "x.js").write_text("junk")
    (d / "dist").mkdir()
    (d / "dist" / "index.html").write_text("built")
    data = FE.export_zip(d, "w")
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert "w/frontend.json" in names and "w/main.js" in names and not any("node_modules" in n or "/dist/" in n for n in names)
    out = FE.import_zip(t, "w-copy", data)
    assert out["id"] == "w-copy" and (t.dir / "frontends" / "w-copy" / "main.js").read_text(encoding="utf-8") == (d / "main.js").read_text(encoding="utf-8")
    flat = _zip({"frontend.json": (d / "frontend.json").read_text(encoding="utf-8"), "index.html": "<p>hi</p>"})   # no top folder
    FE.import_zip(t, "flat", flat)
    assert (t.dir / "frontends" / "flat" / "index.html").is_file()
    with pytest.raises(FE.FrontendError):
        FE.import_zip(t, "w-copy", data)   # taken


@pytest.mark.parametrize("entries,code", [
    ({"../evil.js": "x", "frontend.json": "{}"}, "imp_unsafe"),
    ({"/abs.js": "x"}, "imp_unsafe"),
    ({"a/b.txt": "x"}, "chk_no_manifest"),
    ({"frontend.json": json.dumps({"schema": "worldlines.frontend/1", "kind": "unity", "entry": "nope.html"})}, "chk_kind"),
])
def test_import_refuses_and_writes_nothing(tmp_path, monkeypatch, entries, code):
    t = _tpl(tmp_path, monkeypatch)
    with pytest.raises(FE.FrontendImportRefused) as e:
        FE.import_zip(t, "x", _zip(entries), "en")
    want = str(FE.words("en")[code]).split("{")[0].strip()
    assert any(want in p["message"] for p in e.value.problems), e.value.problems
    assert not (t.dir / "frontends" / "x").exists() and not (t.dir / "evil.js").exists() and not (t.dir / "frontends" / "evil.js").exists()
    with pytest.raises(FE.FrontendImportRefused):
        FE.import_zip(t, "x", b"not a zip")


def test_import_refuses_a_big_package(tmp_path, monkeypatch):
    t = _tpl(tmp_path, monkeypatch)
    monkeypatch.setattr(FE, "_ZIP_MAX", 100)
    with pytest.raises(FE.FrontendImportRefused):
        FE.import_zip(t, "big", _zip({"frontend.json": "{}", "big.txt": "x" * 200}))


@pytest.mark.skipif(not HAVE_CHAT, reason="forks the builtin phone, whose source (ui/player) is not in the open repo")
def test_fork_export_import_over_http(server):
    srv, base = server
    made, _ = _call(base, "/api/v1/local/frontends/pct-house/builtin.chat/fork", {"name": "phone", "title": "小手机 · 灰橡宅"})
    assert made["id"] == "phone" and made["from"] == "builtin.chat"
    with urllib.request.urlopen(base + "/api/v1/local/frontends/pct-house/phone/export") as r:
        assert r.headers["Content-Type"] == "application/zip" and 'phone.frontend.zip' in r.headers["Content-Disposition"]
        data = r.read()
    req = urllib.request.Request(base + "/api/v1/local/frontends/pct-house/import?name=phone-2", data=data, method="POST", headers={"Content-Type": "application/zip"})
    with urllib.request.urlopen(req) as r:
        assert json.loads(r.read())["id"] == "phone-2"
    bad = urllib.request.Request(base + "/api/v1/local/frontends/pct-house/import?name=bad&lang=en", data=_zip({"../x.js": "x"}), method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(bad)
    assert e.value.code == 422 and json.loads(e.value.read())["problems"][0]["code"] == "frontend.import"
    if HAVE_SRC:
        with urllib.request.urlopen(base + "/api/v1/local/frontends/pct-house/builtin.godot/export") as r:   # builtin ones export too
            assert len(r.read()) > 1000
    for path, body in (("/api/v1/local/frontends/pct-house/builtin.chat/fork", {"name": "z"}),):
        with pytest.raises(urllib.error.HTTPError) as e:
            _call(base, path, body, headers={"Host": "tailnet.example"})
        assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(urllib.request.Request(base + "/api/v1/local/frontends/pct-house/phone/export", headers={"Host": "evil.example"}))
    assert e.value.code == 403
