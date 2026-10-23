"""Tests for the soul library (neonrp.core.souls).

SOUL_HOME / PLAYER_HOME are monkeypatched onto tmp dirs so nothing
touches the developer's real ~/.worldlines.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp.core import souls
from neonrp.core.souls import (
    SOUL_CHARTER_FILENAME,
    SOUL_SUBFOLDERS,
    SoulMeta,
    SoulSource,
    create_soul_dir,
    list_souls,
    migrate_players_to_souls,
    read_soul_json,
    write_soul_json,
)


@pytest.fixture
def soul_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "souls"
    monkeypatch.setattr(souls, "SOUL_HOME", home)
    return home


@pytest.fixture
def player_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "players"
    monkeypatch.setattr(souls, "PLAYER_HOME", home)
    return home


class TestCreateSoulDir:
    def test_creates_all_subfolders_soul_json_and_charter(self, soul_home: Path):
        soul_dir = create_soul_dir("elena", name="Elena Voss", name_local="艾莲娜")

        assert soul_dir.parent == soul_home
        assert soul_dir.name.startswith("elena-")
        for sub in SOUL_SUBFOLDERS:
            assert (soul_dir / sub).is_dir(), f"missing subfolder {sub}"
        assert (soul_dir / SOUL_CHARTER_FILENAME).is_file()
        assert "Soul Charter" in (soul_dir / SOUL_CHARTER_FILENAME).read_text(encoding="utf-8")

        meta = read_soul_json(soul_dir)
        assert meta is not None
        assert meta.sid == "elena"
        assert meta.name == "Elena Voss"
        assert meta.name_local == "艾莲娜"
        assert meta.schema_version == 1
        assert meta.source.kind == "local-create"
        assert meta.created_at.endswith("Z")

    def test_seeded_source_and_tags(self, soul_home: Path):
        soul_dir = create_soul_dir(
            "mira",
            name="Mira",
            source=SoulSource(kind="soulhub", hash="abc123", version="2.0"),
            tags=["companion", "mage"],
        )
        meta = read_soul_json(soul_dir)
        assert meta is not None
        assert meta.source.kind == "soulhub"
        assert meta.source.hash == "abc123"
        assert meta.tags == ["companion", "mage"]


class TestSoulJsonRoundTrip:
    def test_round_trip(self, tmp_path: Path):
        meta = SoulMeta(
            sid="elena",
            name="Elena Voss",
            name_local="艾莲娜",
            version="2.1-beta",
            created_at="2026-05-15T10:00:00Z",
            source=SoulSource(kind="soulhub", hash="b54b307b50ef", version="1.0"),
            agent_template="heroine-classic",
            tags=["companion", "mage"],
        )
        write_soul_json(tmp_path, meta)

        on_disk = json.loads((tmp_path / "soul.json").read_text(encoding="utf-8"))
        assert list(on_disk.keys())[0] == "schema_version"

        reloaded = read_soul_json(tmp_path)
        assert reloaded == meta

    def test_read_missing_returns_none(self, tmp_path: Path):
        assert read_soul_json(tmp_path) is None

    def test_read_invalid_json_returns_none(self, tmp_path: Path):
        (tmp_path / "soul.json").write_text("{not json", encoding="utf-8")
        assert read_soul_json(tmp_path) is None

    def test_read_missing_required_keys_returns_none(self, tmp_path: Path):
        (tmp_path / "soul.json").write_text(
            json.dumps({"schema_version": 1, "name": "x"}), encoding="utf-8"
        )
        assert read_soul_json(tmp_path) is None


class TestListSouls:
    def test_empty_when_no_home(self, soul_home: Path):
        assert list_souls() == []

    def test_shape(self, soul_home: Path):
        create_soul_dir("elena", name="Elena Voss", name_local="艾莲娜")
        entries = list_souls()
        assert len(entries) == 1
        e = entries[0]
        assert set(e) >= {
            "sid",
            "name",
            "name_local",
            "version",
            "source",
            "display_name",
        }
        assert e["sid"] == "elena"
        assert e["display_name"] == "Elena Voss (艾莲娜)"
        assert e["source"]["kind"] == "local-create"

    def test_display_name_without_local(self, soul_home: Path):
        create_soul_dir("bob", name="Bob")
        assert list_souls()[0]["display_name"] == "Bob"

    def test_mtime_sort_newest_first(self, soul_home: Path):
        soul_home.mkdir(parents=True, exist_ok=True)
        old = soul_home / "old-20200101-000000"
        old.mkdir()
        write_soul_json(old, SoulMeta(sid="old", name="Old"))
        new = soul_home / "new-20260101-000000"
        new.mkdir()
        write_soul_json(new, SoulMeta(sid="new", name="New"))

        # Force a deterministic mtime ordering.
        import os

        os.utime(old, (1_000_000, 1_000_000))
        os.utime(new, (2_000_000, 2_000_000))

        sids = [s["sid"] for s in list_souls()]
        assert sids == ["new", "old"]

    def test_skips_invalid_dirs(self, soul_home: Path):
        soul_home.mkdir(parents=True, exist_ok=True)
        (soul_home / "junk").mkdir()  # no soul.json
        (soul_home / "broken").mkdir()
        (soul_home / "broken" / "soul.json").write_text("garbage", encoding="utf-8")
        (soul_home / "loose-file.txt").write_text("x", encoding="utf-8")
        create_soul_dir("valid", name="Valid")

        entries = list_souls()
        assert [e["sid"] for e in entries] == ["valid"]


class TestMigration:
    def _make_player(self, player_home: Path, name: str) -> Path:
        p = player_home / name
        p.mkdir(parents=True)
        (p / "profile.json").write_text(json.dumps({"name": name}), encoding="utf-8")
        (p / "stats.json").write_text(json.dumps({"hp": 10}), encoding="utf-8")
        (p / "inventory.json").write_text(json.dumps([]), encoding="utf-8")
        (p / "journal.md").write_text("# log\n", encoding="utf-8")
        return p

    def test_no_players_dir(self, soul_home: Path, player_home: Path):
        assert migrate_players_to_souls() == []

    def test_creates_souls_from_players(self, soul_home: Path, player_home: Path):
        self._make_player(player_home, "hero")

        created = migrate_players_to_souls()
        assert len(created) == 1
        soul_dir = created[0]

        meta = read_soul_json(soul_dir)
        assert meta is not None
        assert meta.sid == "hero"
        assert meta.source.kind == "builtin"
        assert "migrated" in meta.tags

        # Legacy state mapped into character/.
        character = soul_dir / "character"
        assert (character / "profile.json").exists()
        assert (character / "stats.json").exists()
        assert (character / "journal.md").read_text(encoding="utf-8") == "# log\n"
        assert (soul_dir / SOUL_CHARTER_FILENAME).exists()

        # And it shows up via the normal listing API.
        assert [s["sid"] for s in list_souls()] == ["hero"]

    def test_idempotent(self, soul_home: Path, player_home: Path):
        self._make_player(player_home, "hero")

        first = migrate_players_to_souls()
        assert len(first) == 1

        # Marker present → second run is a no-op even though players/ still exists.
        second = migrate_players_to_souls()
        assert second == []
        assert len(list_souls()) == 1

        # A newly added legacy player is NOT re-imported (one-shot by design).
        self._make_player(player_home, "latecomer")
        assert migrate_players_to_souls() == []
        assert len(list_souls()) == 1
