"""Local tests for `neonrp.core.worldhub` — exercise zip + extract +
bootstrap without touching S3.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from neonrp.core.worldhub import (
    HASH_LEN,
    HUB_KINDS,
    WORLDHUB_META_FILENAME,
    WorldHubError,
    _bootstrap_neonrp,
    _zip_world_for_upload,
    compute_hash,
    parse_query,
    read_worldhub_meta,
    registry_url,
    slugify,
)
from neonrp.core.world_export import load_world_zip
from neonrp.core import worldhub as _wh


def _make_template_world(root: Path, name: str = "test-world") -> Path:
    """Create a minimal template-style world directory (no .neonrp/)."""
    world = root / name
    (world / "game" / "player").mkdir(parents=True)
    (world / "game" / "player" / "player.json").write_text(
        json.dumps({"id": "player", "name": "Test"}), encoding="utf-8"
    )
    (world / "runtime_contract.json").write_text(
        json.dumps({"router": {"execution_mode": "orchestrator"}}), encoding="utf-8"
    )
    return world


def test_bootstrap_adds_neonrp_to_template_world(tmp_path: Path) -> None:
    world = _make_template_world(tmp_path)
    assert not (world / ".neonrp").exists()

    _bootstrap_neonrp(world)

    assert (world / ".neonrp" / "manifest.json").is_file()
    manifest = json.loads((world / ".neonrp" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("current_branch") == "main"
    # Runtime contract at root should be mirrored into .neonrp/
    assert (world / ".neonrp" / "runtime_contract.json").is_file()


def test_zip_world_handles_template_style_source(tmp_path: Path) -> None:
    world = _make_template_world(tmp_path)

    zip_path = _zip_world_for_upload(world)
    try:
        assert zip_path.is_file()
        assert zip_path.suffix == ".zip"
        # Hash should be deterministic 12 hex chars
        h = compute_hash(zip_path)
        assert len(h) == HASH_LEN
        assert all(c in "0123456789abcdef" for c in h)
    finally:
        shutil.rmtree(zip_path.parent, ignore_errors=True)


def test_zip_extract_roundtrip(tmp_path: Path) -> None:
    """Upload-side zip + download-side extract should give a working game dir."""
    world = _make_template_world(tmp_path, name="test-roundtrip")

    zip_path = _zip_world_for_upload(world)
    try:
        # Simulate the download side: extract into a fresh games dir.
        games_dir = tmp_path / "games"
        target = load_world_zip(zip_path, games_dir=games_dir)

        # Extracted folder has the expected shape.
        assert (target / ".neonrp" / "manifest.json").is_file()
        assert (target / "game" / "player" / "player.json").is_file()
        assert (target / "runtime_contract.json").is_file()
    finally:
        shutil.rmtree(zip_path.parent, ignore_errors=True)


def test_load_world_zip_does_not_overwrite_existing_target(tmp_path: Path) -> None:
    """Downloading a zip when a same-named game dir already exists must
    not silently overwrite the existing dir — the new extract should
    land at the timestamped `<name>-restored-<ts>` target.
    """
    world = _make_template_world(tmp_path, name="dup-world")
    zip_path = _zip_world_for_upload(world)
    try:
        games_dir = tmp_path / "games"
        # First extract — lands at games/dup-world
        first = load_world_zip(zip_path, games_dir=games_dir)
        assert first.name == "dup-world"
        # Plant a sentinel so we can detect overwrite
        sentinel = first / "SENTINEL.txt"
        sentinel.write_text("original-content", encoding="utf-8")

        # Second extract — should NOT clobber the sentinel
        second = load_world_zip(zip_path, games_dir=games_dir)
        assert second.name.startswith("dup-world-restored-")
        assert first.exists(), "original dup-world was destroyed"
        assert sentinel.exists(), "original sentinel was overwritten"
        assert sentinel.read_text(encoding="utf-8") == "original-content"
    finally:
        shutil.rmtree(zip_path.parent, ignore_errors=True)


def test_zip_existing_game_preserves_neonrp(tmp_path: Path) -> None:
    """A source with `.neonrp/` already should be zipped as-is, not re-bootstrapped."""
    world = _make_template_world(tmp_path, name="test-existing")
    # Pre-existing .neonrp with a custom marker
    (world / ".neonrp").mkdir()
    (world / ".neonrp" / "manifest.json").write_text(
        json.dumps({"version": "0.2", "current_branch": "feature-x", "branches": {}, "entities": {}}),
        encoding="utf-8",
    )

    zip_path = _zip_world_for_upload(world)
    try:
        games_dir = tmp_path / "games"
        target = load_world_zip(zip_path, games_dir=games_dir)
        manifest = json.loads((target / ".neonrp" / "manifest.json").read_text(encoding="utf-8"))
        # The custom branch should be preserved, not overwritten.
        assert manifest["current_branch"] == "feature-x"
    finally:
        shutil.rmtree(zip_path.parent, ignore_errors=True)


def _make_hosted_save_zip(root: Path, slug: str = "dark-train", name: str = "Dark Train") -> Path:
    """Build a save zip shaped exactly like the play gateway's
    ``GET /session/{sid}/zip`` output: a single top-level dir named after
    the slug, containing a complete NeonRP session workdir with
    ``.neonrp/manifest.json``, a session transcript, and ``.session-meta.json``
    (the hosted-save marker — NOT ``.worldhub.json``).
    """
    import zipfile

    work = root / "session-workdir"
    (work / ".neonrp" / "sessions").mkdir(parents=True)
    (work / ".neonrp" / "manifest.json").write_text(
        json.dumps({"version": "0.2", "current_branch": "main", "branches": {}, "entities": {}}),
        encoding="utf-8",
    )
    (work / ".neonrp" / "sessions" / "main.jsonl").write_text(
        json.dumps({"role": "narrator", "content": "a played turn"}) + "\n",
        encoding="utf-8",
    )
    (work / "game").mkdir()
    (work / "game" / "run_state.json").write_text(json.dumps({"turn_count": 3}), encoding="utf-8")
    (work / ".session-meta.json").write_text(
        json.dumps({"uid": "u", "sid": "abc12345", "kind": "worlds", "slug": slug, "name": name, "started": 111}),
        encoding="utf-8",
    )

    zip_path = root / f"{slug}-abc12345.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in work.rglob("*"):
            if entry.is_file():
                zf.write(entry, arcname=str(Path(slug) / entry.relative_to(work)))
    return zip_path


def test_downloaded_hosted_save_is_visible_in_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Round-trip: a save downloaded from hosted play (web) and restored
    with ``load-world`` must appear in the launcher's continue list and
    register as already-played. The session workdir carries
    ``.session-meta.json`` (not ``.worldhub.json``); before the fix
    ``list_saved_games()`` silently skipped it.
    """
    import neonrp.worlds as W

    # A restored hosted-play save is a RUN → it lives under PLAYS_HOME.
    zip_path = _make_hosted_save_zip(tmp_path)
    plays_dir = tmp_path / "plays"
    target = load_world_zip(zip_path, games_dir=plays_dir)

    # The hosted-save marker is read straight off the restored dir.
    assert W.read_session_meta(target) is not None
    assert W.resolve_wid(target) == "dark-train"

    monkeypatch.setattr(W, "PLAYS_HOME", plays_dir)
    saved = W.list_saved_games()
    assert len(saved) == 1, "downloaded hosted save did not appear in the continue list"
    entry = saved[0]
    assert entry["display_name"] == "Dark Train"
    assert entry["wid"] == "dark-train"
    assert entry["world_id"] == "hub:dark-train"
    assert entry["started"] is True, "restored save with a session transcript should read as played"


def test_freshly_created_world_is_in_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A world authored via the TUI ``_write_bundle`` world branch is a
    library SOURCE: it lands under ``WORLDS_HOME/<slug>`` (a stable world-id,
    no timestamp) and surfaces in ``list_worlds()`` as an owned world — the
    founder bug was the launcher still showing only the OLD worlds after
    create. Playing it later instantiates a run elsewhere (PLAYS_HOME).
    """
    import neonrp.worlds as W

    worlds_dir = tmp_path / "worlds"
    world_dir = worlds_dir / "my-new-world"
    (world_dir / "game" / "meta").mkdir(parents=True)
    (world_dir / ".neonrp").mkdir()
    (world_dir / "game" / "meta" / "game-start.json").write_text(
        json.dumps({"name": "我的新世界"}, ensure_ascii=False), encoding="utf-8"
    )

    monkeypatch.setattr(W, "WORLDS_HOME", worlds_dir)
    owned = W.list_owned_worlds()
    assert [w["id"] for w in owned] == ["my-new-world"]
    entry = owned[0]
    assert entry["owned"] is True
    assert entry["origin"] == "created"
    assert entry["display_name"] == "我的新世界"
    # And it shows up in the full world list (the 世界库 grows).
    listed = {w["id"] for w in W.list_worlds()}
    assert "my-new-world" in listed


def test_download_world_lands_in_worlds_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A downloaded WORLD is a library SOURCE → WORLDS_HOME; a downloaded
    hosted-play SAVE (carries ``.session-meta.json``) is a RUN → PLAYS_HOME.
    """
    import neonrp.worlds as W
    from neonrp.core import worldhub as wh

    worlds_dir = tmp_path / "worlds"
    plays_dir = tmp_path / "plays"
    monkeypatch.setattr(W, "WORLDS_HOME", worlds_dir)
    monkeypatch.setattr(W, "PLAYS_HOME", plays_dir)

    # --- world download ---
    world = _make_template_world(tmp_path, name="dark-train")
    world_zip = _zip_world_for_upload(world)
    try:
        world_hash = compute_hash(world_zip)
        entry = {"hash": world_hash, "slug": "dark-train", "name": "Dark Train",
                 "version": "1.0", "url": "file://world", "uploaded_at": "..."}
        monkeypatch.setattr(wh, "resolve", lambda q, *, kind="worlds": entry)
        monkeypatch.setattr(
            wh.urllib.request, "urlretrieve",
            lambda url, dst: shutil.copy(str(world_zip), str(dst)),
        )
        target = wh.download("dark-train")
        assert target.parent == worlds_dir, "downloaded world must land in WORLDS_HOME"
        assert (target / ".worldhub.json").is_file()
    finally:
        shutil.rmtree(world_zip.parent, ignore_errors=True)

    # --- hosted-play save download ---
    save_zip = _make_hosted_save_zip(tmp_path, slug="dark-train")
    save_hash = compute_hash(save_zip)
    save_entry = {"hash": save_hash, "slug": "dark-train", "name": "Dark Train",
                  "version": "1.0", "url": "file://save", "uploaded_at": "..."}
    monkeypatch.setattr(wh, "resolve", lambda q, *, kind="worlds": save_entry)
    monkeypatch.setattr(
        wh.urllib.request, "urlretrieve",
        lambda url, dst: shutil.copy(str(save_zip), str(dst)),
    )
    save_target = wh.download("dark-train")
    assert save_target.parent == plays_dir, "hosted-play save must land in PLAYS_HOME"
    assert (save_target / ".session-meta.json").is_file()


def test_compute_hash_stable_for_same_content(tmp_path: Path) -> None:
    blob = tmp_path / "a.zip"
    blob.write_bytes(b"deterministic content")
    h1 = compute_hash(blob)
    h2 = compute_hash(blob)
    assert h1 == h2
    # Same content via SHA256 first 12 hex
    expected = hashlib.sha256(b"deterministic content").hexdigest()[:HASH_LEN]
    assert h1 == expected


def test_read_worldhub_meta_missing_returns_none(tmp_path: Path) -> None:
    assert read_worldhub_meta(tmp_path) is None


def test_read_worldhub_meta_parses_file(tmp_path: Path) -> None:
    (tmp_path / WORLDHUB_META_FILENAME).write_text(
        json.dumps({"hash": "abc123def456", "name": "Test World", "version": "1.0"}),
        encoding="utf-8",
    )
    meta = read_worldhub_meta(tmp_path)
    assert meta is not None
    assert meta["hash"] == "abc123def456"
    assert meta["name"] == "Test World"


def test_read_worldhub_meta_bad_json_returns_none(tmp_path: Path) -> None:
    (tmp_path / WORLDHUB_META_FILENAME).write_text("not json", encoding="utf-8")
    assert read_worldhub_meta(tmp_path) is None


# ---------------------------------------------------------------------------
# v2: kind parameterization, slug, version resolution.
# ---------------------------------------------------------------------------

def test_hub_kinds_set() -> None:
    assert HUB_KINDS == ("worlds", "souls")


def test_registry_url_per_kind() -> None:
    worlds = registry_url("worlds")
    souls = registry_url("souls")
    assert worlds.endswith("/worlds/index.json")
    assert souls.endswith("/souls/index.json")
    assert worlds != souls


def test_registry_url_rejects_unknown_kind() -> None:
    with pytest.raises(WorldHubError):
        registry_url("characters")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Dark Train", "dark-train"),
        ("Dark Train (CoC 7e)", "dark-train-coc-7e"),
        ("  Trailing  Spaces  ", "trailing-spaces"),
        ("Already-slug", "already-slug"),
    ],
)
def test_slugify(name: str, expected: str) -> None:
    assert slugify(name) == expected


@pytest.mark.parametrize(
    "q,expected",
    [
        ("dark-train", ("dark-train", None)),
        ("dark-train@2.0", ("dark-train", "2.0")),
        ("dark-train@", ("dark-train", None)),
        ("e38aff4819a0", ("e38aff4819a0", None)),
        ("  Dark-Train@1.0  ", ("dark-train", "1.0")),
    ],
)
def test_parse_query(q: str, expected: tuple[str, str | None]) -> None:
    assert parse_query(q) == expected


def _fake_registry(entries: list[dict]) -> dict:
    return {"schema_version": 1, "kind": "worlds", "worlds": entries}


def test_resolve_by_slug_latest_picks_newest_uploaded(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        {"hash": "aaaaaaaaaaaa", "slug": "dark-train", "name": "Dark Train", "version": "1.0",
         "uploaded_at": "2026-01-01T00:00:00+00:00", "url": "https://example/a.zip"},
        {"hash": "bbbbbbbbbbbb", "slug": "dark-train", "name": "Dark Train", "version": "2.0",
         "uploaded_at": "2026-05-13T00:00:00+00:00", "url": "https://example/b.zip"},
    ]
    monkeypatch.setattr(_wh, "read_registry", lambda kind="worlds": _fake_registry(entries))

    e = _wh.resolve("dark-train")
    assert e["version"] == "2.0"
    assert e["hash"] == "bbbbbbbbbbbb"


def test_resolve_by_slug_at_version(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        {"hash": "aaaaaaaaaaaa", "slug": "dark-train", "name": "Dark Train", "version": "1.0",
         "uploaded_at": "2026-01-01T00:00:00+00:00", "url": "https://example/a.zip"},
        {"hash": "bbbbbbbbbbbb", "slug": "dark-train", "name": "Dark Train", "version": "2.0",
         "uploaded_at": "2026-05-13T00:00:00+00:00", "url": "https://example/b.zip"},
    ]
    monkeypatch.setattr(_wh, "read_registry", lambda kind="worlds": _fake_registry(entries))

    e = _wh.resolve("dark-train@1.0")
    assert e["version"] == "1.0"
    assert e["hash"] == "aaaaaaaaaaaa"


def test_resolve_by_hash_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        {"hash": "e38aff4819a0", "slug": "dark-train", "name": "Dark Train",
         "version": "2.0", "uploaded_at": "...", "url": "https://example/b.zip"},
        {"hash": "538d19b9e55e", "slug": "dark-train", "name": "Dark Train",
         "version": "1.0", "uploaded_at": "...", "url": "https://example/a.zip"},
    ]
    monkeypatch.setattr(_wh, "read_registry", lambda kind="worlds": _fake_registry(entries))

    e = _wh.resolve("e38aff48")
    assert e["hash"] == "e38aff4819a0"


def test_resolve_unknown_slug_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_wh, "read_registry", lambda kind="worlds": _fake_registry([
        {"hash": "aaaaaaaaaaaa", "slug": "dark-train", "name": "Dark Train", "version": "1.0", "uploaded_at": "...", "url": "..."}
    ]))

    with pytest.raises(WorldHubError, match="no entry"):
        _wh.resolve("does-not-exist")


def test_resolve_unknown_version_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_wh, "read_registry", lambda kind="worlds": _fake_registry([
        {"hash": "aaaaaaaaaaaa", "slug": "dark-train", "name": "Dark Train", "version": "1.0", "uploaded_at": "...", "url": "..."}
    ]))

    with pytest.raises(WorldHubError, match="version .* not found"):
        _wh.resolve("dark-train@99")


def test_list_stories_groups_by_slug_newest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        {"hash": "a1", "slug": "dark-train", "name": "Dark Train", "version": "1.0",
         "uploaded_at": "2026-01-01T00:00:00+00:00", "url": "...", "size_bytes": 100},
        {"hash": "b2", "slug": "dark-train", "name": "Dark Train", "version": "2.0",
         "uploaded_at": "2026-05-13T00:00:00+00:00", "url": "...", "size_bytes": 200},
        {"hash": "c3", "slug": "neon-bay", "name": "Neon Bay", "version": "1.0",
         "uploaded_at": "2026-03-01T00:00:00+00:00", "url": "...", "size_bytes": 50},
    ]
    monkeypatch.setattr(_wh, "read_registry", lambda kind="worlds": _fake_registry(entries))

    stories = _wh.list_stories()
    assert [s["slug"] for s in stories] == ["dark-train", "neon-bay"]  # newest first
    dark = stories[0]
    assert dark["latest_version"] == "2.0"
    assert [v["version"] for v in dark["versions"]] == ["2.0", "1.0"]  # versions newest-first within story


def test_normalize_registry_backfills_slug_from_name(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = {"version": 1, "worlds": [
        {"hash": "abc", "name": "Dark Train (legacy d20)", "version": "1.0",
         "url": "...", "uploaded_at": "..."},
    ]}
    monkeypatch.setattr(
        _wh.urllib.request, "urlopen",
        lambda *a, **kw: _FakeURLOpen(json.dumps(legacy).encode())
    )
    reg = _wh.read_registry()
    assert reg["worlds"][0]["slug"] == "dark-train-legacy-d20"
    assert reg["worlds"][0]["changelog"] == ""


class _FakeURLOpen:
    """Minimal context-manager fake for urlopen."""
    def __init__(self, body: bytes):
        self._body = body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def read(self) -> bytes:
        return self._body
