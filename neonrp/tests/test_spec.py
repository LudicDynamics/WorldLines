"""spec 让 agent 直接读:neonrp spec · GET /api/v1/spec[/<name>] · GET /llms.txt —— 同一份文本。
写的 spec 来自 documents/spec(wheel 里带一份 neonrp/_spec);生成的(ops / authoring / contracts / http)每次从代码现读。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest
from click.testing import CliRunner


def test_every_listed_spec_reads():
    from neonrp import spec

    got = {n["name"]: n for n in spec.names()}
    assert {"world", "soul", "template", "contract", "player", "ops", "authoring", "contracts", "http"} <= set(got)
    assert got["player"]["langs"] == ["zh", "en"]
    for n in got.values():
        for lg in n["langs"]:
            assert spec.read(n["name"], lang=lg).startswith("#"), n
    assert "`set_cast`" in spec.read("authoring") or "set_cast" in spec.read("authoring")
    assert "`roll_check`" in spec.read("ops", pack="pct") or "| `" in spec.read("ops", pack="pct")
    assert "mystery-trpg@" in spec.read("contracts")
    with pytest.raises(KeyError):
        spec.read("nope")


def test_cli():
    from neonrp.commands.spec_cmd import spec_cmd

    r = CliRunner().invoke(spec_cmd, [])
    assert r.exit_code == 0 and "template" in r.output
    r = CliRunner().invoke(spec_cmd, ["template", "--lang", "en"])
    assert r.exit_code == 0 and r.output.startswith("#")
    assert "/api/v1/spec/world" in CliRunner().invoke(spec_cmd, ["--llms"]).output
    assert CliRunner().invoke(spec_cmd, ["nope"]).exit_code != 0


def test_http(tmp_path):
    from neonrp.commands.web import make_server

    with patch("neonrp.worlds.WORLDS_HOME", tmp_path / "w"), patch("neonrp.worlds.PLAYS_HOME", tmp_path / "p"):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/llms.txt", timeout=30) as r:
                body = r.read().decode()
            assert f"{base}/api/v1/spec/template" in body
            with urllib.request.urlopen(base + "/api/v1/spec", timeout=30) as r:
                assert any(x["name"] == "contract" for x in json.loads(r.read())["specs"])
            with urllib.request.urlopen(base + "/api/v1/spec/soul?lang=en", timeout=30) as r:
                assert r.headers["Content-Type"].startswith("text/markdown") and r.read().startswith(b"#")
            with urllib.request.urlopen(base + "/api/v1/spec/ops?pack=werewolf", timeout=30) as r:
                assert "werewolf" in r.read().decode()
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + "/api/v1/spec/nope", timeout=30)
            assert e.value.code == 404
        finally:
            server.shutdown()


def test_read_spec_tool_is_for_the_authoring_side_only(tmp_path):
    """内置创作 agent 没有命令行:build 模式给它 read_spec 工具;游玩 / 沙盒 / 旧执行路径都不带(不多占每回合的工具说明)。"""
    from neonrp.core.conversation import _get_tool_schemas
    from neonrp.core.skill_loader import SkillLoader
    from neonrp.core.skills import SkillRegistry, get_skill_schemas

    loader = SkillLoader(tmp_path)
    names = lambda mode: {s["name"] for s in _get_tool_schemas(mode, loader, tmp_path)}  # noqa: E731
    assert "read_spec" in names("build")
    assert "read_spec" not in names("play") and "read_spec" not in names("sandbox")
    assert "read_spec" not in {s["name"] for s in get_skill_schemas()}
    reg = SkillRegistry(tmp_path, "r", "a", ["**"], [], ["**"])
    r = reg.invoke("read_spec", {"name": "template", "lang": "en"})
    assert r.success and r.data["spec"].startswith("# Template")
    assert not reg.invoke("read_spec", {"name": "nope"}).success
