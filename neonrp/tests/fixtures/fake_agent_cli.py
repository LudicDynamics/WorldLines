"""A stand-in for the `claude` / `codex` CLIs (tests + the C2 e2e): it speaks the real CLI's JSON event stream and drives
the MCP server it was handed (`neonrp mcp serve-create`) with a real MCP client — no login, no model.

Installed by copying it as <bin>/claude and <bin>/codex (its name picks the dialect). It writes what it was started with
(argv, env names, cwd) to $FAKE_AGENT_LOG as JSON lines. The prompt steers it:
    contains SLOW   → sleeps 60 s after the first tool call (to test stop)
    contains BREAK  → writes broken JSON first (refused), then a valid file
    contains SECRET → tries to write a key into notes/leak.md first (refused by the MCP)
otherwise it lists files, reads one, writes notes/agent-<n>.md with the prompt, and runs lint."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

NAME = Path(sys.argv[0]).name
CODEX = NAME.startswith("codex")


def out(ev: dict) -> None:
    sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def log(rec: dict) -> None:
    p = os.environ.get("FAKE_AGENT_LOG")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def parse() -> dict:
    a = sys.argv[1:]
    r: dict = {"prompt": "", "resume": None, "mcp": None}
    if CODEX:
        conf: dict = {}
        rest = []
        i = 0
        while i < len(a):
            if a[i] == "-c":
                k, _, v = a[i + 1].partition("=")
                try:
                    conf[k] = json.loads(v)
                except ValueError:
                    conf[k] = v
                i += 2
                continue
            if a[i] in ("-C", "--sandbox"):
                r[a[i]] = a[i + 1]
                i += 2
                continue
            rest.append(a[i])
            i += 1
        pos = [x for x in rest if not x.startswith("-") and x != "exec"]
        if "resume" in pos:
            pos.remove("resume")
            r["resume"] = pos.pop(0)
        r["prompt"] = pos[-1] if pos else ""
        cmd = conf.get("mcp_servers.neonrp-create.command")
        r["mcp"] = {"command": cmd, "args": conf.get("mcp_servers.neonrp-create.args") or []} if cmd else None
        r["conf"] = conf
    else:
        i = 0
        while i < len(a):
            if a[i] == "-p":
                r["prompt"] = a[i + 1]
                i += 2
                continue
            if a[i] == "--mcp-config":
                cfg = json.loads(Path(a[i + 1]).read_text(encoding="utf-8"))
                r["mcp"] = cfg["mcpServers"].get("neonrp-create")
                i += 2
                continue
            if a[i] == "--resume":
                r["resume"] = a[i + 1]
                i += 2
                continue
            i += 1
    return r


async def drive(r: dict, sid: str) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    m = r["mcp"]
    p = StdioServerParameters(command=m["command"], args=m["args"], env=dict(os.environ))
    async with stdio_client(p) as (rd, wr):
        async with ClientSession(rd, wr) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            if CODEX:
                out({"type": "thread.started", "thread_id": sid})
                out({"type": "turn.started"})
            else:
                out({"type": "system", "subtype": "init", "session_id": sid, "model": "fake",
                     "tools": ["Read", *(f"mcp__neonrp-create__{t}" for t in tools)],
                     "mcp_servers": [{"name": "neonrp-create", "status": "connected"}]})
            n = [0]

            async def call(tool: str, args: dict) -> str:
                n[0] += 1
                cid = f"call_{n[0]}"
                if CODEX:
                    out({"type": "item.started", "item": {"id": cid, "type": "mcp_tool_call", "server": "neonrp-create",
                                                          "tool": tool, "arguments": args, "status": "in_progress"}})
                else:
                    out({"type": "assistant", "message": {"content": [
                        {"type": "tool_use", "id": cid, "name": f"mcp__neonrp-create__{tool}", "input": args}]}})
                text = (await s.call_tool(tool, args)).content[0].text
                if CODEX:
                    out({"type": "item.completed", "item": {"id": cid, "type": "mcp_tool_call", "server": "neonrp-create",
                                                            "tool": tool, "arguments": args, "status": "completed",
                                                            "result": {"content": [{"type": "text", "text": text}]}}})
                else:
                    out({"type": "user", "message": {"content": [
                        {"type": "tool_result", "tool_use_id": cid, "content": [{"type": "text", "text": text}]}]}})
                return text

            say = (lambda t: out({"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": t}})) if CODEX \
                else (lambda t: out({"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}}))
            say("先看一下这个文件夹。")
            files = json.loads(await call("list_files", {}))["files"]
            if "SLOW" in r["prompt"]:
                time.sleep(60)
            first = next((f["path"] for f in files if f["path"].endswith(".json")), None)
            if first:
                await call("read_file", {"path": first})
            await call("read_file", {"path": ".neonrp/config.json"})   # refused by the server
            if "SECRET" in r["prompt"]:   # what an injected prompt would try: copy a key into the folder
                await call("write_file", {"path": "notes/leak.md", "content": "model: x\nkey: sk-abcdefghijklmnopqrstuvwxyz012345\n"})
            if "BREAK" in r["prompt"]:
                await call("write_file", {"path": "notes/broken.json", "content": "{oops"})
            k = len(list(Path(".").glob("notes/agent-*.md"))) + 1
            await call("write_file", {"path": f"notes/agent-{k}.md", "content": f"# 笔记 {k}\n\n{r['prompt']}\n"})
            lint = json.loads(await call("lint", {}))
            msg = f"写好了 notes/agent-{k}.md。lint:{lint['counts']['block']} block · {lint['counts']['warn']} warn。"
            say(msg)
            if CODEX:
                out({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})
            else:
                out({"type": "result", "subtype": "success", "is_error": False, "result": msg, "session_id": sid})


def main() -> None:
    if "--version" in sys.argv[1:]:
        print("codex-cli 9.9.9" if CODEX else "9.9.9 (Claude Code)")
        return
    r = parse()
    log({"name": NAME, "argv": sys.argv[1:], "cwd": os.getcwd(), "env": sorted(os.environ), "resume": r["resume"],
         "env_tool_search": os.environ.get("ENABLE_TOOL_SEARCH")})
    if not r["mcp"]:
        print("no neonrp-create MCP server given", file=sys.stderr)
        sys.exit(2)
    asyncio.run(drive(r, r["resume"] or str(uuid.uuid4())))


if __name__ == "__main__":
    main()
