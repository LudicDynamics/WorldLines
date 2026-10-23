"""Engine SPA assembly seam (two-repo split).

The engine wheel no longer embeds the web shell; `_spa_root` assembles one at
runtime. Resolution order under test:

  ① env NEONRP_SPA_DIR (unpacked WorldLines shell dist dir) — always wins
  ② packaged src/neonrp/webui/spa (transition compat: source checkout /
     pre-split wheel)
  ③ None → /local 404s pointing at the WorldLines shell (NOT sync_play_ui)

Hermetic: stdlib HTTP against a tmp project, no LLM, env restored by
monkeypatch.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from neonrp.commands.web import _spa_root, make_server
from neonrp.core.manifest import Manifest


def _init_project(root: Path) -> None:
    neon = root / ".neonrp"
    (neon / "sessions").mkdir(parents=True)
    (neon / "events").mkdir(parents=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (neon / "manifest.json").write_text(
        json.dumps(m.model_dump(), default=str), encoding="utf-8"
    )
    (root / "game").mkdir()


def _serve(root: Path):
    server = make_server(root, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _shell_dist(tmp_path: Path, marker: str) -> Path:
    """A minimal unpacked shell build (what the WorldLines repo ships)."""
    dist = tmp_path / "shell-dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        f"<!doctype html><div id='root'>{marker}</div>", encoding="utf-8"
    )
    (dist / "assets" / "app.js").write_text("console.log('ext')", encoding="utf-8")
    return dist


def test_env_spa_dir_wins_and_serves(tmp_path: Path, monkeypatch) -> None:
    """① NEONRP_SPA_DIR: /local serves the external dist's index.html (real
    resolution, no _spa_root patching) and its /assets bundle — even though
    the source checkout also carries a packaged webui/spa (env wins)."""
    dist = _shell_dist(tmp_path, "EXTERNAL WORLDLINES SHELL")
    monkeypatch.setenv("NEONRP_SPA_DIR", str(dist))
    _init_project(tmp_path / "run")
    server, base = _serve(tmp_path / "run")
    try:
        for path in ("/local", "/local/play/x", "/local?tpl=stoneford-elena"):  # history fallback + the UI's own query (10-05: was a 404)
            with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
                assert r.status == 200
                assert "EXTERNAL WORLDLINES SHELL" in r.read().decode("utf-8")
        with urllib.request.urlopen(f"{base}/assets/app.js", timeout=5) as r:
            assert "ext" in r.read().decode("utf-8")
    finally:
        server.shutdown()


def test_env_spa_dir_without_index_falls_through(tmp_path: Path, monkeypatch) -> None:
    """An env dir with no index.html is ignored → resolution falls through to
    the packaged copy (② — present in a source checkout)."""
    empty = tmp_path / "not-a-build"
    empty.mkdir()
    monkeypatch.setenv("NEONRP_SPA_DIR", str(empty))
    root = _spa_root()
    # Source checkout carries webui/spa → ② resolves; either way the broken
    # env dir must never be returned.
    assert root != empty
    if root is not None:
        assert root.joinpath("index.html").is_file()


def test_no_env_means_no_spa(monkeypatch) -> None:
    """② 形态 B (engine-only wheel): without the env var nothing resolves —
    the engine runs API-only and points at the WorldLines shell. The old
    "packaged webui/spa still resolves" compat path is gone."""
    monkeypatch.delenv("NEONRP_SPA_DIR", raising=False)
    assert _spa_root() is None


def test_no_shell_hint_points_at_worldlines(tmp_path: Path, monkeypatch) -> None:
    """③ neither env nor packaged copy → /local 404s with the two-repo hint:
    install the WorldLines shell / set NEONRP_SPA_DIR. The old
    scripts/sync_play_ui.sh advice is gone."""
    monkeypatch.delenv("NEONRP_SPA_DIR", raising=False)
    _init_project(tmp_path)
    with patch(
        "neonrp.commands.web.resources.files",
        side_effect=ModuleNotFoundError("no packaged webui"),
    ):
        assert _spa_root() is None  # real resolution: ③
        server, base = _serve(tmp_path)
        try:
            try:
                urllib.request.urlopen(f"{base}/local", timeout=5)
                raise AssertionError("expected 404")
            except urllib.error.HTTPError as e:
                assert e.code == 404
                body = e.read().decode("utf-8")
                assert "NEONRP_SPA_DIR" in body
                assert "WorldLines" in body
                assert "sync_play_ui" not in body
        finally:
            server.shutdown()
