"""One-click turn-engine mode: `neonrp engine mode` + /engine/mode routes (webui/mode_routes.py)."""
from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import neonrp
from neonrp.commands.engine_cmd import engine_group
from neonrp.core import engine_config

TEMPLATE = Path(neonrp.__file__).parent / "templates" / "stoneford-elena"


@pytest.fixture
def world(tmp_path: Path) -> Path:
    dst = tmp_path / "w"
    shutil.copytree(TEMPLATE, dst)
    return dst


def test_cli_switch_keeps_other_keys(world: Path, monkeypatch):
    monkeypatch.delenv("NEONRP_TURN_V3", raising=False)
    p = world / "game" / "meta" / "engine.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"turn": {"solve": {"max_ops": 9}}}))
    r = CliRunner().invoke(engine_group, ["mode", "v3", "--world", str(world)])
    assert r.exit_code == 0, r.output
    assert engine_config.v3_enabled(world)
    assert json.loads(p.read_text())["turn"]["solve"]["max_ops"] == 9
    r = CliRunner().invoke(engine_group, ["mode", "v2b", "--world", str(world)])
    assert r.exit_code == 0 and not engine_config.v3_enabled(world)
    r = CliRunner().invoke(engine_group, ["mode", "--world", str(world)])
    assert "turn.mode = v2b" in r.output and "world" in r.output


def test_env_layer_still_wins_and_is_reported(world: Path, monkeypatch):
    monkeypatch.setenv("NEONRP_TURN_V3", "1")
    r = CliRunner().invoke(engine_group, ["mode", "v2b", "--world", str(world)])
    assert r.exit_code == 0
    assert "from env" in r.output and "overrides" in r.output


def _req(base: str, path: str, method="GET", body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{base}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, None


def test_mode_routes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("NEONRP_TURN_V3", raising=False)
    from neonrp.commands.web import make_server
    from neonrp.core.manifest import Manifest

    worlds = tmp_path / "lib" / "worlds"
    shutil.copytree(TEMPLATE, worlds / "stone")
    (worlds / "stone" / ".neonrp").mkdir(exist_ok=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (worlds / "stone" / ".neonrp" / "manifest.json").write_text(json.dumps(m.model_dump(), default=str))
    with (
        patch("neonrp.worlds.WORLDS_HOME", worlds),
        patch("neonrp.worlds.PLAYS_HOME", tmp_path / "lib" / "plays"),
        patch("neonrp.worlds.STUDIO_HOME", tmp_path / "lib" / "studio"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            assert _req(base, "/api/v1/play/engine/mode")[0] == 409
            assert _req(base, "/api/v1/create/session", "POST", {"world_id": "stone"})[0] == 200
            E = "/api/v1/create/session/edit-local/engine/mode"
            st, v = _req(base, E)
            assert st == 200 and v["mode"] in ("v2b", "v3") and v["modes"] == ["v2b", "v3"]
            st, v = _req(base, E, "POST", {"mode": "v3"})
            assert st == 200 and v["mode"] == "v3" and v["source"] == "world"
            assert _req(base, E)[1]["mode"] == "v3"
            st, v = _req(base, E, "POST", {"mode": "v1"})
            assert st == 400 and "v2b" in v["error"]
            st, v = _req(base, E, "POST", {"mode": "v2b"})
            assert st == 200 and v["mode"] == "v2b"
            st, meta = _req(base, "/api/v1/meta")
            assert meta["capabilities"]["engine_mode"] is True
        finally:
            server.shutdown()
