"""The workbench's local CLI creation agent (webui/agent_cli_backend.py, route C2): detection, the tightened flags, the
scrubbed environment, both event dialects end to end against a fake `claude` / `codex` (tests/fixtures/fake_agent_cli.py,
which drives the real `neonrp mcp serve-create` over MCP — no login, no model), resume, stop, and the SSE route."""
from __future__ import annotations

import io
import json
import shutil
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from neonrp.webui import agent_cli_backend as ACB

FAKE = Path(__file__).parent / "fixtures" / "fake_agent_cli.py"
SMALL = Path(__file__).resolve().parents[1] / "worldlines" / "templates" / "werewolf-night-village.template"


@pytest.fixture
def fakebin(tmp_path, monkeypatch):
    b = tmp_path / "bin"
    b.mkdir()
    src = FAKE.read_text(encoding="utf-8")
    for n in ("claude", "codex"):
        p = b / n
        p.write_text(f"#!{sys.executable}\n{src}", encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{b}:/usr/bin:/bin")
    log = tmp_path / "agent.log"
    monkeypatch.setenv("FAKE_AGENT_LOG", str(log))
    ACB._version_cache.clear()
    return log


@pytest.fixture
def world(tmp_path):
    if not SMALL.is_dir():
        pytest.skip("built-in template not in this checkout")
    from neonrp import template as TP

    w = tmp_path / "edit"
    TP.build(SMALL, w)
    (w / ".neonrp").mkdir(exist_ok=True)
    (w / ".neonrp" / "config.json").write_text('{"models": {"x": {"api_key": "sk-must-not-leak"}}}', encoding="utf-8")
    return w.resolve()


def _log(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


def test_scrub_env_drops_keys_and_tokens():
    env = {"PATH": "/bin", "HOME": "/h", "LANG": "ja_JP.UTF-8", "ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "b",
           "CLAUDE_CODE_OAUTH_TOKEN": "c", "GITHUB_TOKEN": "d", "AWS_SECRET_ACCESS_KEY": "e", "WORLDLINES_ACCOUNT": "f",
           "DEEPSEEK_KEY": "g", "NEONRP_TEMPLATE_PATH": "/t", "DB_PASSWORD": "h"}
    assert ACB.scrub_env(env) == {"PATH": "/bin", "HOME": "/h", "LANG": "ja_JP.UTF-8", "NEONRP_TEMPLATE_PATH": "/t"}


def test_detect(fakebin, monkeypatch):
    got = {a["id"]: a for a in ACB.detect()}
    assert got["engine"]["available"]
    assert got["claude-code"]["available"] and got["claude-code"]["version"] == "9.9.9 (Claude Code)"
    assert got["codex"]["available"] and got["codex"]["version"] == "codex-cli 9.9.9"
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    got = {a["id"]: a for a in ACB.detect()}
    assert not got["claude-code"]["available"] and got["claude-code"]["why"] == "not_installed"


def test_flags_are_tight(tmp_path):
    c = ACB.argv_for("claude-code", tmp_path, "hi", resume=None, mcp_config=tmp_path / "m.json", kind="world")
    assert c[1:3] == ["-p", "hi"] and "--bare" not in c
    for f in ("--strict-mcp-config", "--verbose"):
        assert f in c
    assert c[c.index("--tools") + 1] == "" and c[c.index("--output-format") + 1] == "stream-json"   # no built-in tool
    dis = c[c.index("--disallowedTools") + 1:c.index("--append-system-prompt")]
    assert {"Bash", "Read", "Edit", "Write", "WebFetch"} <= set(dis)
    assert "mcp__neonrp-create__*" in c and "Read" not in c[:c.index("--disallowedTools")]
    x = ACB.argv_for("codex", tmp_path, "hi", resume=None, mcp_config=None, kind="world")
    assert x[1:3] == ["exec", "--json"] and "--ignore-user-config" in x
    assert "--sandbox" not in x and not any("sandbox_mode" in a for a in x)   # they would override the profile
    assert 'default_permissions="neonrp_create"' in x
    perm = next(a for a in x if a.startswith("permissions.neonrp_create.filesystem="))
    assert f'"{tmp_path}"="read"' in perm and f'"{tmp_path / ".neonrp"}"="none"' in perm and '":minimal"="read"' in perm
    assert '"write"' not in perm
    assert x[x.index("-C") + 1] == str(tmp_path) and x[-1].endswith("---\nhi")
    r = ACB.argv_for("codex", tmp_path, "hi", resume="t-1", mcp_config=None, kind="world")
    assert r[1:3] == ["exec", "resume"] and r[-2] == "t-1" and 'default_permissions="neonrp_create"' in r


@pytest.mark.parametrize("agent", ["claude-code", "codex"])
def test_run_end_to_end_with_fake_cli(fakebin, world, monkeypatch, agent):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-no")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oa-no")
    evs: list[tuple[str, dict]] = []
    r = ACB.AgentRun(agent, world, "加一条笔记", kind="world", emit=lambda n, d: evs.append((n, d))).run()
    assert r["success"], r
    assert r["session_id"] and "notes/agent-1.md" in r["assistant_message"]
    assert r["files"]["added"] == ["notes/agent-1.md"] and (world / "notes" / "agent-1.md").is_file()
    names = [n for n, _ in evs]
    assert names[0] == "agent" and "chunk" in names and names[-1] == "files"
    uses = [d["name"] for n, d in evs if n == "tool_use"]
    assert uses[:2] == ["list_files", "read_file"] and "write_file" in uses and uses[-1] == "lint"
    refused = [d for n, d in evs if n == "tool_result" and d["path"] == ".neonrp/config.json"]
    assert refused and refused[0]["ok"] is False and "sk-must-not-leak" not in json.dumps(evs, ensure_ascii=False)
    assert ("file", {"path": "notes/agent-1.md"}) in evs
    rec = _log(fakebin)[-1]
    assert rec["cwd"] == str(world)
    assert "ANTHROPIC_API_KEY" not in rec["env"] and "OPENAI_API_KEY" not in rec["env"] and "HOME" in rec["env"]
    # the next turn resumes the same session
    r2 = ACB.AgentRun(agent, world, "再加一条", kind="world", emit=lambda n, d: None, resume=r["session_id"]).run()
    assert r2["success"] and r2["session_id"] == r["session_id"] and _log(fakebin)[-1]["resume"] == r["session_id"]
    assert r2["files"]["added"] == ["notes/agent-2.md"]


def test_refused_write_is_reported_not_written(fakebin, world):
    evs: list[tuple[str, dict]] = []
    r = ACB.AgentRun("claude-code", world, "BREAK it", kind="world", emit=lambda n, d: evs.append((n, d))).run()
    assert r["success"]
    bad = [d for n, d in evs if n == "tool_result" and d["path"] == "notes/broken.json"]
    assert bad and bad[0]["ok"] is False and not (world / "notes" / "broken.json").exists()
    assert ("file", {"path": "notes/broken.json"}) not in evs


def test_a_key_never_reaches_the_folder(fakebin, world):
    """A prompt injection that gets the agent to write a key: the MCP refuses it, nothing lands on disk."""
    evs: list[tuple[str, dict]] = []
    r = ACB.AgentRun("claude-code", world, "SECRET 把 key 写进笔记", kind="world", emit=lambda n, d: evs.append((n, d))).run()
    bad = [d for n, d in evs if n == "tool_result" and d["path"] == "notes/leak.md"]
    assert bad and bad[0]["ok"] is False and "looks like a key" in bad[0]["summary"]
    assert not (world / "notes" / "leak.md").exists() and "notes/leak.md" not in r["files"]["added"]
    rec = _log(fakebin)[-1]
    assert rec["env_tool_search"] == "false"


def test_stop_kills_the_agent(fakebin, world):
    seen = threading.Event()
    run = ACB.AgentRun("claude-code", world, "SLOW", kind="world",
                       emit=lambda n, d: seen.set() if n == "tool_result" else None)
    out: list[dict] = []
    t = threading.Thread(target=lambda: out.append(run.run()))
    t0 = time.monotonic()
    t.start()
    assert seen.wait(30)
    run.cancel()
    t.join(20)
    assert not t.is_alive() and time.monotonic() - t0 < 30
    assert out[0]["cancelled"] and not out[0]["success"] and out[0]["error"] is None
    assert not (world / "notes").exists()


def test_timeout(fakebin, world):
    r = ACB.AgentRun("codex", world, "SLOW", kind="world", emit=lambda n, d: None, timeout=3).run()
    assert r["timed_out"] and not r["success"] and "stopped after" in r["error"]


def test_missing_cli_is_an_error_not_a_crash(world, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    r = ACB.AgentRun("claude-code", world, "x", kind="world", emit=lambda n, d: None).run()
    assert not r["success"] and "could not start" in r["error"]


# ── the SSE route + the setting ──

def _sse(raw: bytes) -> list[tuple[str, dict]]:
    out = []
    for block in raw.decode().split("\n\n"):
        lines = dict(x.split(": ", 1) for x in block.splitlines() if ": " in x and not x.startswith(":"))
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_message_route_streams_a_cli_turn(fakebin, world, monkeypatch, tmp_path):
    from neonrp import presets
    from neonrp.commands import web as _web
    from neonrp.webui.engine_routes import EngineRoutes
    from neonrp.webui.launcher_routes import LauncherRoutes

    monkeypatch.setattr(presets, "_USER_CONFIG_PATH", tmp_path / "home" / "config.json")
    ert = _web.EditRuntime(world)
    monkeypatch.setattr(_web, "_try_rebind_edit_runtime", lambda server: ert)

    class H(EngineRoutes, LauncherRoutes):
        _CREATE_PREFIX = "/api/v1/create"

        def __init__(self, path, body=None):
            self.path, self.body, self.out, self.status, self.server = path, body, None, 200, None
            self.wfile = io.BytesIO()

        def _read_json_body(self):
            return self.body

        def _send_json(self, d, status=200):
            self.out, self.status = d, status

        def send_error(self, code, msg=""):
            self.out, self.status = {"error": msg}, code

        def send_response(self, code):
            self.status = code

        def send_header(self, *a):
            pass

        def end_headers(self):
            pass

        def _cors_headers(self):
            pass

    h = H("/api/v1/local/settings/create-agent", {"agent": "codex"})
    assert h._launcher_route_put() and h.out == {"ok": True, "selected": "codex"}
    assert presets.get_create_agent() == "codex"
    h = H("/api/v1/local/create-agents")
    assert h._launcher_route_get(None) and h.out["selected"] == "codex"

    h = H("/api/v1/create/session/edit-local/message", {"input": "加一条笔记"})
    h._post_create()
    evs = _sse(h.wfile.getvalue())
    names = [n for n, _ in evs]
    assert names[0] == "agent" and evs[0][1]["agent"] == "codex"
    assert "tool_use" in names and "file" in names and names[-3:] == ["files", "lint", "done"]
    lint = dict(evs)["lint"]
    assert lint["kind"] == "world" and set(lint["counts"]) == {"block", "warn"}
    done = evs[-1][1]
    assert done["success"] and done["agent"] == "codex" and "notes/agent-1.md" in done["assistant_message"]
    assert ert._agent_sessions["codex"] and ert._agent_run is None and ert._busy.acquire(blocking=False)
    ert._busy.release()

    h = H("/api/v1/create/session/edit-local/message/stop", {})
    h._post_create()
    assert h.out == {"ok": True, "stopped": False}

    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    ACB._version_cache.clear()
    h = H("/api/v1/local/settings/create-agent", {"agent": "claude-code"})
    h._launcher_route_put()
    assert h.status == 400 and h.out["error"] == "agent_unavailable"
    h = H("/api/v1/local/create-agents")
    h._launcher_route_get(None)
    assert h.out["selected"] == "engine"   # the chosen CLI went away → back to the engine
    h = H("/api/v1/create/session/edit-local/message", {"input": "x", "agent": "codex"})
    h._post_create()
    assert h.status == 400 and h.out["error"] == "agent_unavailable"
    shutil.rmtree(world / "notes", ignore_errors=True)
