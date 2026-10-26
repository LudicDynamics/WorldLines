"""neonrp.create_mcp (`neonrp mcp serve-create --root`): the path boundary, the write rules, lint for each folder kind, and
the stdio server end to end (a real MCP client starts the CLI)."""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest

from neonrp import create_mcp as M

REPO = Path(__file__).resolve().parents[1]
SMALL = REPO / "worldlines" / "templates" / "werewolf-night-village.template"


@pytest.fixture
def tpl(tmp_path):
    if not SMALL.is_dir():
        pytest.skip("built-in template not in this checkout")
    d = tmp_path / "wnv.template"
    shutil.copytree(SMALL, d)
    return d.resolve()


def test_paths_stay_inside_the_folder(tmp_path):
    root = tmp_path / "t.template"
    (root / "world").mkdir(parents=True)
    (root / "template.json").write_text("{}", encoding="utf-8")
    (tmp_path / "secret.json").write_text("{}", encoding="utf-8")
    (root / "link.json").symlink_to(tmp_path / "secret.json")
    (root / "inner.json").symlink_to(root / "template.json")   # a symlink that stays inside is refused too
    (root / "lnk").symlink_to(root / "world")
    root = root.resolve()
    for bad in ("../secret.json", "world/../../secret.json", "link.json", "inner.json", "lnk/x.json", ".neonrp/config.json",
                ".git/config", "world/.env", "角色.json"):
        with pytest.raises(M.PathRefused):
            M.resolve(root, bad)
    assert M.resolve(root, "/etc/hosts") == root / "etc" / "hosts"   # absolute → read as relative to the folder
    assert M.read_file(root, "template.json") == "{}"
    files = [f["path"] for f in M.list_files(root)["files"]]
    assert files == ["template.json"]   # symlinks are not listed


def test_writes_are_text_and_json_must_parse(tmp_path):
    root = tmp_path.resolve()
    with pytest.raises(M.PathRefused, match="not valid JSON"):
        M.write_file(root, "a.json", "{oops")
    with pytest.raises(M.PathRefused):
        M.write_file(root, "a.png", "x")
    with pytest.raises(M.PathRefused):
        M.write_file(root, "big.md", "x" * (M.MAX_WRITE + 1))
    r = M.write_file(root, "world/notes.md", "# 笔记")
    assert r["ok"] and r["created"]
    assert M.write_file(root, "world/notes.md", "# 笔记 2")["created"] is False
    assert (root / "world" / "notes.md").read_text(encoding="utf-8") == "# 笔记 2"
    assert not (root / "a.json").exists() and not list(root.rglob("*.tmp"))


def test_kind_and_lint_template(tpl):
    assert M.kind_of(tpl) == "template"
    r = M.lint(tpl)
    assert r["kind"] == "template" and set(r["counts"]) == {"block", "warn"}
    assert r["ok"] == (r["counts"]["block"] == 0)
    assert all(set(p) == {"level", "code", "where", "message"} for p in r["problems"])
    # break the card → a block shows up
    data = json.loads((tpl / "template.json").read_text(encoding="utf-8"))
    data.setdefault("card", {})["title"] = ""
    M.write_file(tpl, "template.json", json.dumps(data, ensure_ascii=False))
    r2 = M.lint(tpl)
    assert not r2["ok"] and any(p["where"] == "card.title" for p in r2["problems"])


def test_template_slots_and_build_preview(tpl):
    s = M.slots(tpl)
    assert s and all(set(x) == {"slot", "label", "need", "have", "stale"} for x in s)
    b = M.build_preview(tpl)
    assert b["ok"] and b["pack"]


def test_lint_world_and_soul(tpl, tmp_path):
    from neonrp import template as TP

    world = tmp_path / "w"
    TP.build(tpl, world)
    assert M.kind_of(world.resolve()) == "world"
    r = M.lint(world.resolve())
    assert r["kind"] == "world" and isinstance(r["ok"], bool)
    (world / "game" / "broken.json").write_text("{nope", encoding="utf-8")
    assert not M.lint(world.resolve())["ok"]

    soul = tmp_path / "s"
    soul.mkdir()
    (soul / "soul.json").write_text(json.dumps({"sid": "s", "name": "阿雾"}), encoding="utf-8")
    soul = soul.resolve()
    assert M.kind_of(soul) == "soul"
    r = M.lint(soul)
    assert r["ok"] and r["counts"]["warn"] == 1   # no soul.md
    (soul / "persona").mkdir()
    (soul / "persona" / "kernel.json").write_text("[1,", encoding="utf-8")
    assert M.lint(soul)["counts"]["block"] == 1


def test_open_root_refuses_other_folders(tmp_path):
    with pytest.raises(SystemExit):
        M.open_root(str(tmp_path))
    with pytest.raises(SystemExit):
        M.open_root(str(tmp_path / "nope"))


def test_spec_tools():
    names = [n["name"] for n in M.spec_list(Path("."))]
    assert "template" in names
    assert M.spec_read(Path("."), "template")
    with pytest.raises(M.PathRefused):
        M.spec_read(Path("."), "no-such-spec")


def _stdio(root: Path, cwd: Path, calls: list[tuple[str, dict]]) -> tuple[list[str], list[str]]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        p = StdioServerParameters(command=sys.executable, args=["-m", "neonrp", "mcp", "serve-create", "--root", str(root)],
                                  env={"PATH": "/usr/bin:/bin", "HOME": str(cwd)}, cwd=str(cwd))
        async with stdio_client(p) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = [t.name for t in (await s.list_tools()).tools]
                outs = [(await s.call_tool(n, a)).content[0].text for n, a in calls]
                return tools, outs

    return asyncio.run(go())


def test_stdio_server_end_to_end(tpl, tmp_path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    tools, outs = _stdio(tpl, cwd, [
        ("list_files", {}),
        ("read_file", {"path": "../../etc/passwd"}),
        ("read_file", {"path": ".neonrp/config.json"}),
        ("write_file", {"path": "notes/x.json", "content": "{oops"}),
        ("write_file", {"path": "notes/idea.md", "content": "# 想法\n"}),
        ("lint", {}),
        ("slots", {}),
        ("build_preview", {}),
    ])
    assert set(tools) == {"list_files", "read_file", "write_file", "lint", "spec_list", "spec_read", "slots", "build_preview"}
    assert len(json.loads(outs[0])["files"]) > 10
    assert json.loads(outs[1])["ok"] is False and json.loads(outs[2])["ok"] is False
    assert "not valid JSON" in json.loads(outs[3])["error"] and not (tpl / "notes" / "x.json").exists()
    assert json.loads(outs[4])["ok"] and (tpl / "notes" / "idea.md").read_text(encoding="utf-8") == "# 想法\n"
    assert json.loads(outs[5])["kind"] == "template"
    assert json.loads(outs[6]) and json.loads(outs[7])["ok"]
    assert not list(cwd.iterdir())   # the CLI left nothing (.neonrp/logs, .env load) in the agent's cwd
    assert not (tpl / ".neonrp").exists()


def test_stdio_world_has_no_template_tools(tpl, tmp_path):
    from neonrp import template as TP

    world = tmp_path / "w"
    TP.build(tpl, world)
    tools, _ = _stdio(world.resolve(), tmp_path, [])
    assert "lint" in tools and "slots" not in tools and "build_preview" not in tools


def test_write_refuses_key_shaped_text(tmp_path):
    root = tmp_path.resolve()
    for bad in ('{"api_key": "abcdefghijklmnop1234"}', "base_url: x\nkey: sk-abcdefghijklmnopqrstuv\n",
                "token Bearer abcdefghijklmnopqrstuvwxyz0123", "ANTHROPIC sk-ant-api03-abcdefghijklmnopqrstuvwx",
                "aws AKIAABCDEFGHIJKLMNOP", "ghp_abcdefghijklmnopqrstuvwxyz12"):
        name = "x.json" if bad.startswith("{") else "x.md"
        with pytest.raises(M.PathRefused, match="looks like a key"):
            M.write_file(root, f"notes/{name}", bad)
        assert not (root / "notes" / name).exists()
    with pytest.raises(M.PathRefused, match="credentials"):
        M.write_file(root, "world/credentials.json", "{}")
    # placeholders and ordinary prose pass (the publish scan's own exemptions)
    assert M.write_file(root, "notes/ok.json", '{"api_key": "${DEEPSEEK_API_KEY}", "note": "雾港的灯塔"}')["ok"]
    assert M.write_file(root, "notes/ok.md", "她把钥匙(key)藏在灯塔里。sk 是她的名字缩写。")["ok"]
