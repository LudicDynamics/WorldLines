"""The local workbench's creation agent can be the user's own Claude Code or Codex CLI instead of the engine's build
session (docs/planning/CREATE-MULTIMODEL-MCP-STUDY-1026.md, route C2). Local only, creation only — never hosting play.

The engine starts the CLI as a child process in the folder being edited, hands it ``neonrp mcp serve-create --root
<folder>`` as its only MCP server, and turns the CLI's JSON event stream into the workbench's stream (chunk · tool_use ·
tool_result · file). Tightened on purpose:

    Claude Code   claude -p … --output-format stream-json --verbose --strict-mcp-config --mcp-config <tmp>
                  --tools "" --allowedTools mcp__neonrp-create__* --disallowedTools Bash Read Edit Write …
                  (no built-in tool at all — only the MCP tools)
    Codex         codex exec --json --skip-git-repo-check --ignore-user-config -C <folder>
                  -c permissions.neonrp_create.filesystem={:minimal=read, <folder>=read, <folder>/.neonrp=none, …}
                  -c default_permissions="neonrp_create" -c mcp_servers.neonrp-create.command=… …
                  (its shell reads only the folder and writes nothing; files change through the MCP tools)

No ``--bare`` (it only takes ANTHROPIC_API_KEY, not the user's own login). The child's environment drops every variable
that looks like a key / token / secret; the CLI's own login (``~/.claude`` / ``~/.codex``) is its business — the engine
never reads it."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

ENGINE = "engine"
AGENTS: dict[str, dict[str, str]] = {
    "claude-code": {"bin": "claude", "label": "Claude Code"},
    "codex": {"bin": "codex", "label": "Codex"},
}
MCP_NAME = "neonrp-create"
TOOL_PREFIXES = (f"mcp__{MCP_NAME}__", f"{MCP_NAME}.", f"{MCP_NAME}/")
DEFAULT_TIMEOUT = 15 * 60
CLAUDE_BUILTINS = ("Bash", "Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Glob", "Grep", "WebFetch", "WebSearch", "Task")
CODEX_PROFILE = "neonrp_create"
_SECRETISH = re.compile(r"API_?KEY|_KEY$|^KEY$|TOKEN|SECRET|PASSW|CREDENTIAL|COOKIE|PRIVATE", re.I)
_version_cache: dict[tuple[str, float], str | None] = {}


def scrub_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """The parent's environment minus anything that looks like a key, token or secret (and the account variables)."""
    src = os.environ if env is None else env
    return {k: v for k, v in src.items() if not _SECRETISH.search(k) and not k.upper().startswith("WORLDLINES_")}


def _version(path: str) -> str | None:
    try:
        key = (path, os.stat(path).st_mtime)
    except OSError:
        return None
    if key not in _version_cache:
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=8, env=scrub_env(),
                                 stdin=subprocess.DEVNULL)
            _version_cache[key] = (out.stdout or out.stderr).strip().splitlines()[0][:80] if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, IndexError):
            _version_cache[key] = None
    return _version_cache[key]


def detect() -> list[dict[str, Any]]:
    """The creation backends on this machine: the engine's own (always) + each CLI found on PATH."""
    out: list[dict[str, Any]] = [{"id": ENGINE, "available": True}]
    for aid, a in AGENTS.items():
        path = shutil.which(a["bin"])
        ver = _version(path) if path else None
        out.append({"id": aid, "label": a["label"], "bin": a["bin"], "available": bool(path and ver),
                    "version": ver, "why": None if path and ver else ("not_installed" if not path else "not_runnable")})
    return out


def available(agent_id: str) -> bool:
    return any(a["id"] == agent_id and a["available"] for a in detect())


def system_prompt(root: Path, kind: str) -> str:
    return (
        "You are the creation agent of the NeonRP local workbench. You edit exactly one "
        f"{kind} folder ({root.name}) and you change files ONLY through the {MCP_NAME} MCP tools (write_file; read_file / "
        "list_files to look). You cannot run commands. Before adding a field read the spec (spec_read). After every change "
        "run lint and fix every block. Write content natively in the user's language; ids, field names and file names are "
        "ASCII. Never write keys, personal paths or internal addresses into any file. Finish with a short summary, in the "
        "user's language, of what you changed and what lint still says."
    )


def mcp_command(root: Path) -> tuple[str, list[str]]:
    return sys.executable, ["-m", "neonrp", "mcp", "serve-create", "--root", str(root)]


def argv_for(agent_id: str, root: Path, prompt: str, *, resume: str | None, mcp_config: Path | None, kind: str) -> list[str]:
    exe = shutil.which(AGENTS[agent_id]["bin"]) or AGENTS[agent_id]["bin"]
    cmd, args = mcp_command(root)
    if agent_id == "claude-code":
        # no built-in tool at all (--tools ""): Read could open any file on the machine (~/.neonrp, ~/.ssh) and a prompt
        # injected through template text could carry a key into write_file. The MCP read_file covers the folder.
        argv = [exe, "-p", prompt, "--output-format", "stream-json", "--verbose",
                "--strict-mcp-config", "--mcp-config", str(mcp_config),
                "--tools", "",
                "--allowedTools", f"mcp__{MCP_NAME}__*", f"mcp__{MCP_NAME}",
                "--disallowedTools", *CLAUDE_BUILTINS,   # second layer, should a CLI version ignore --tools ""
                "--append-system-prompt", system_prompt(root, kind)]
        return argv + (["--resume", resume] if resume else [])
    over = ["-c", 'approval_policy="never"', *codex_permissions(root),
            "-c", f"mcp_servers.{MCP_NAME}.command={json.dumps(cmd)}",
            "-c", f"mcp_servers.{MCP_NAME}.args={json.dumps(args)}"]
    prompt = f"{system_prompt(root, kind)}\n\n---\n{prompt}"   # codex exec has no system-prompt flag: the rules ride on every turn
    if resume:
        return [exe, "exec", "resume", "--json", "--skip-git-repo-check", "--ignore-user-config", *over, resume, prompt]
    # no --sandbox: it overrides default_permissions, and the built-in read-only sandbox reads the whole disk
    return [exe, "exec", "--json", "--skip-git-repo-check", "--ignore-user-config", "-C", str(root), *over, prompt]


def codex_permissions(root: Path) -> list[str]:
    """A Codex permission profile for its shell: read the folder (minus .neonrp/ .git/) + the minimal system paths a
    command needs, write nothing. Checked with `codex sandbox -P` (0.162): a file outside the folder → Operation not
    permitted, while the built-in :read-only profile reads it."""
    fs = {":minimal": "read", str(root): "read", str(root / ".neonrp"): "none", str(root / ".git"): "none"}
    table = "{" + ",".join(f"{json.dumps(k)}={json.dumps(v)}" for k, v in fs.items()) + "}"
    return ["-c", f"permissions.{CODEX_PROFILE}.filesystem={table}", "-c", f'default_permissions="{CODEX_PROFILE}"']


def _short(name: str) -> str:
    for p in TOOL_PREFIXES:
        if name.startswith(p):
            return name[len(p):]
    return name


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
    if isinstance(content, dict):
        return _text_of(content.get("content")) or str(content.get("text") or "")
    return ""


def _ok_of(text: str) -> bool:
    try:
        v = json.loads(text)
    except (TypeError, ValueError):
        return True
    return not (isinstance(v, dict) and v.get("ok") is False)


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for p in root.rglob("*"):
        r = p.relative_to(root)
        if any(x.startswith(".") for x in r.parts) or p.is_symlink() or not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        out[r.as_posix()] = (st.st_size, st.st_mtime_ns)
        if len(out) > 20000:
            break
    return out


def diff(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]) -> dict[str, list[str]]:
    return {"added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after)),
            "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k])}


class AgentRun:
    """One turn of a CLI agent over one folder. ``emit(name, data)`` gets the workbench events as they happen;
    ``run()`` blocks and returns the result; ``cancel()`` (another thread) stops the process group."""

    def __init__(self, agent_id: str, root: Path, prompt: str, *, kind: str, emit: Callable[[str, dict[str, Any]], None],
                 resume: str | None = None, timeout: float | None = None) -> None:
        if agent_id not in AGENTS:
            raise ValueError(f"unknown agent {agent_id!r}")
        self.agent_id, self.root, self.prompt, self.kind, self.emit = agent_id, root, prompt, kind, emit
        self.resume = resume
        self.timeout = timeout or float(os.environ.get("NEONRP_AGENT_CLI_TIMEOUT") or DEFAULT_TIMEOUT)
        self.proc: subprocess.Popen[str] | None = None
        self.cancelled = False
        self.timed_out = False
        self.session_id: str | None = None
        self.text: list[str] = []
        self.final: str | None = None
        self.error: str | None = None
        self._pending: dict[str, tuple[str, str]] = {}   # tool call id → (name, path)

    # ── the two event dialects ──
    def _tool_use(self, cid: str, name: str, args: Any) -> None:
        a = args if isinstance(args, dict) else {}
        if isinstance(args, str):
            try:
                a = json.loads(args)
            except ValueError:
                a = {}
        path = str(a.get("path") or a.get("file_path") or a.get("subdir") or a.get("name") or "")
        n = _short(name)
        self._pending[cid] = (n, path)
        self.emit("tool_use", {"name": n, "path": path})

    def _tool_result(self, cid: str, text: str, is_error: bool = False) -> None:
        n, path = self._pending.pop(cid, ("tool", ""))
        ok = not is_error and _ok_of(text)
        self.emit("tool_result", {"name": n, "path": path, "ok": ok, "summary": text[:300]})
        if ok and n == "write_file" and path:
            self.emit("file", {"path": path})

    def _claude(self, ev: dict[str, Any]) -> None:
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            self.session_id = ev.get("session_id") or self.session_id
            mcp = [s for s in ev.get("mcp_servers") or [] if isinstance(s, dict) and s.get("name") == MCP_NAME]
            self.emit("agent_status", {"mcp": (mcp[0].get("status") if mcp else "missing"), "model": ev.get("model")})
        elif t == "assistant":
            for c in (ev.get("message") or {}).get("content") or []:
                if c.get("type") == "text" and c.get("text"):
                    self.text.append(c["text"])
                    self.emit("chunk", {"text": c["text"]})
                elif c.get("type") == "thinking" and c.get("thinking"):
                    self.emit("thinking", {"text": c["thinking"]})
                elif c.get("type") == "tool_use":
                    self._tool_use(str(c.get("id")), str(c.get("name") or ""), c.get("input"))
        elif t == "user":
            for c in (ev.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    self._tool_result(str(c.get("tool_use_id")), _text_of(c.get("content")), bool(c.get("is_error")))
        elif t == "result":
            self.session_id = ev.get("session_id") or self.session_id
            if ev.get("is_error") or ev.get("subtype") not in (None, "success"):
                self.error = str(ev.get("result") or ev.get("subtype") or "agent error")[:500]
            else:
                self.final = str(ev.get("result") or "")

    def _codex(self, ev: dict[str, Any]) -> None:
        t = ev.get("type")
        item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
        it = item.get("type") or item.get("item_type")
        if t == "thread.started":
            self.session_id = ev.get("thread_id") or self.session_id
            self.emit("agent_status", {"mcp": "starting"})
        elif t == "item.started" and it == "mcp_tool_call":
            self._tool_use(str(item.get("id")), str(item.get("tool") or ""), item.get("arguments"))
        elif t == "item.started" and it == "command_execution":
            self._tool_use(str(item.get("id")), "shell", {"path": str(item.get("command") or "")[:120]})
        elif t == "item.completed":
            if it == "agent_message" and item.get("text"):
                self.text.append(item["text"])
                self.emit("chunk", {"text": item["text"]})
            elif it == "reasoning" and item.get("text"):
                self.emit("thinking", {"text": item["text"]})
            elif it == "mcp_tool_call":
                cid = str(item.get("id"))
                if cid not in self._pending:
                    self._tool_use(cid, str(item.get("tool") or ""), item.get("arguments"))
                res = item.get("result")
                err = item.get("error")
                text = _text_of(res) if res is not None else str((err or {}).get("message") if isinstance(err, dict) else err or "")
                self._tool_result(cid, text, bool(err) or item.get("status") == "failed")
            elif it == "command_execution":
                self._tool_result(str(item.get("id")), str(item.get("aggregated_output") or "")[:300],
                                  item.get("exit_code") not in (0, None))
        elif t == "turn.failed":
            self.error = str(((ev.get("error") or {}) if isinstance(ev.get("error"), dict) else {}).get("message") or "turn failed")[:500]
        elif t == "error":
            self.error = str(ev.get("message") or "agent error")[:500]

    # ── process ──
    def run(self) -> dict[str, Any]:
        before = snapshot(self.root)
        cfg_dir = Path(tempfile.mkdtemp(prefix="neonrp-agent-"))
        cfg = cfg_dir / "mcp.json"
        cmd, args = mcp_command(self.root)
        cfg.write_text(json.dumps({"mcpServers": {MCP_NAME: {"command": cmd, "args": args}}}), encoding="utf-8")
        stderr: list[str] = []
        try:
            argv = argv_for(self.agent_id, self.root, self.prompt, resume=self.resume, mcp_config=cfg, kind=self.kind)
            self.emit("agent", {"agent": self.agent_id, "label": AGENTS[self.agent_id]["label"], "resume": bool(self.resume)})
            try:
                env = scrub_env()
                if self.agent_id == "claude-code":
                    env["ENABLE_TOOL_SEARCH"] = "false"   # MCP tools in the list up front: there is no ToolSearch tool to find them
                self.proc = subprocess.Popen(argv, cwd=str(self.root), env=env, stdin=subprocess.DEVNULL,
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
                                             start_new_session=True)
            except OSError as e:
                self.error = f"could not start {AGENTS[self.agent_id]['bin']}: {e}"
                return self._result(before)
            if self.cancelled:   # stop pressed while it was starting
                self._kill()
            threading.Thread(target=lambda: stderr.extend(self.proc.stderr), daemon=True).start()  # type: ignore[union-attr,arg-type]
            timer = threading.Timer(self.timeout, self._on_timeout)
            timer.daemon = True
            timer.start()
            handle = self._claude if self.agent_id == "claude-code" else self._codex
            try:
                for line in self.proc.stdout:  # type: ignore[union-attr]
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(ev, dict):
                        handle(ev)
                self.proc.wait()
            finally:
                timer.cancel()
            if self.proc.returncode not in (0, None) and not (self.cancelled or self.timed_out) and not self.error:
                tail = "".join(stderr)[-400:].strip()
                self.error = f"{AGENTS[self.agent_id]['bin']} exited {self.proc.returncode}" + (f": {tail}" if tail else "")
            return self._result(before)
        finally:
            shutil.rmtree(cfg_dir, ignore_errors=True)

    def _result(self, before: dict[str, tuple[int, int]]) -> dict[str, Any]:
        files = diff(before, snapshot(self.root))
        self.emit("files", files)
        message = self.final if self.final else "".join(self.text)
        if self.cancelled:
            self.error = None
        elif self.timed_out:
            self.error = f"stopped after {int(self.timeout)} s"
        return {"success": not (self.error or self.cancelled or self.timed_out), "assistant_message": message,
                "error": self.error, "cancelled": self.cancelled, "timed_out": self.timed_out,
                "session_id": self.session_id, "files": files}

    def _kill(self) -> None:
        p = self.proc
        if p is None or p.poll() is not None:
            return
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return
        deadline = time.monotonic() + 3
        while p.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass

    def cancel(self) -> None:
        self.cancelled = True
        self._kill()

    def _on_timeout(self) -> None:
        self.timed_out = True
        self._kill()
