"""Tests for the M17 commit blob/ref storage layer (`core/commit_store.py`).

Storage IO only — no commit_id derivation, no turn loop. Commit objects are
hand-built fixtures since composition lives in `turn_commit.py` (not here).
"""

from __future__ import annotations

from pathlib import Path

from neonrp.core.commit_store import (
    GcReport,
    create_branch,
    gc,
    list_branches,
    pack_dir,
    read_blob,
    read_ref,
    read_soul_commit,
    read_world_commit,
    unpack_dir,
    write_blob,
    write_ref,
    write_soul_commit,
    write_world_commit,
)


# --------------------------------------------------------------------------- #
# Fixtures helpers
# --------------------------------------------------------------------------- #

def _make_tree(base: Path) -> Path:
    """Build a small nested directory tree to pack/restore."""
    src = base / "game"
    (src / "events").mkdir(parents=True)
    (src / "location").mkdir(parents=True)
    (src / "events" / "a.json").write_text('{"id": "a"}\n', encoding="utf-8")
    (src / "events" / "b.json").write_text('{"id": "b"}\n', encoding="utf-8")
    (src / "location" / "carriage-1.json").write_text("c1\n", encoding="utf-8")
    (src / "meta.json").write_bytes(b"\x00\x01binary\xff")
    return src


def _read_all(dir_: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for p in sorted(dir_.rglob("*")):
        if p.is_file():
            out[p.relative_to(dir_).as_posix()] = p.read_bytes()
    return out


def _world_commit(cid: str, parent: str | None, turn_seq: int, *, blob: str) -> dict:
    """Minimal §2.1-shaped world commit object referencing one game blob."""
    return {
        "schema_version": 2,
        "world_commit_id": cid,
        "parent": parent,
        "branch": "main",
        "turn_seq": turn_seq,
        "world": {"wid": "dark-train", "instance_id": "wi-1", "version_hash": "v1"},
        "game_folder": {"hash": blob, "bundle_url": f"file:///blobs/{blob}.tar.xz"},
        "session_log": {"hash": f"l-{cid}", "bundle_url": "file:///x"},
        "world_agent_snapshot": {"conversation_hash": f"wa-{cid}", "bundle_url": "x"},
        "soul_scene_index": [],
        "labels": [],
        "message": f"turn {turn_seq}",
        "archived_at": None,
    }


# --------------------------------------------------------------------------- #
# Blob pack / write / read / unpack
# --------------------------------------------------------------------------- #

class TestBlobRoundTrip:
    def test_roundtrip_restores_byte_identical_tree(self, tmp_path: Path):
        src = _make_tree(tmp_path / "src")
        original = _read_all(src)

        blob_hash, data = pack_dir(src)
        root = tmp_path / "commits"
        write_blob(root, blob_hash, data)

        loaded = read_blob(root, blob_hash)
        dest = tmp_path / "restored"
        unpack_dir(loaded, dest)

        assert _read_all(dest) == original

    def test_pack_is_deterministic(self, tmp_path: Path):
        """Same content in two different paths → identical bytes and hash."""
        src1 = _make_tree(tmp_path / "one")
        src2 = _make_tree(tmp_path / "two")

        h1, b1 = pack_dir(src1)
        h2, b2 = pack_dir(src2)

        assert h1 == h2
        assert b1 == b2

    def test_different_content_differs(self, tmp_path: Path):
        src1 = _make_tree(tmp_path / "one")
        src2 = _make_tree(tmp_path / "two")
        (src2 / "events" / "a.json").write_text("CHANGED\n", encoding="utf-8")

        h1, _ = pack_dir(src1)
        h2, _ = pack_dir(src2)
        assert h1 != h2

    def test_write_blob_is_idempotent_dedup(self, tmp_path: Path):
        src = _make_tree(tmp_path / "src")
        blob_hash, data = pack_dir(src)
        root = tmp_path / "commits"

        p1 = write_blob(root, blob_hash, data)
        mtime1 = p1.stat().st_mtime_ns
        p2 = write_blob(root, blob_hash, data)  # second write must be no-op

        assert p1 == p2
        assert p2.stat().st_mtime_ns == mtime1

    def test_unpack_rejects_path_escape(self, tmp_path: Path):
        # A hand-crafted malicious tar member must not escape dest.
        import io
        import lzma
        import tarfile

        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w") as tar:
            info = tarfile.TarInfo(name="../escape.txt")
            payload = b"pwn"
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        blob = lzma.compress(raw.getvalue())

        try:
            unpack_dir(blob, tmp_path / "dest")
            raise AssertionError("expected ValueError on path escape")
        except ValueError:
            pass
        assert not (tmp_path / "escape.txt").exists()


# --------------------------------------------------------------------------- #
# Refs + branches
# --------------------------------------------------------------------------- #

class TestRefs:
    def test_absent_ref_is_none(self, tmp_path: Path):
        assert read_ref(tmp_path, "dark-train") is None
        assert read_ref(tmp_path, "dark-train", "nope") is None

    def test_write_then_read_head(self, tmp_path: Path):
        write_ref(tmp_path, "dark-train", "c0001")
        assert read_ref(tmp_path, "dark-train") == "c0001"
        write_ref(tmp_path, "dark-train", "c0002")
        assert read_ref(tmp_path, "dark-train") == "c0002"

    def test_create_and_list_branches(self, tmp_path: Path):
        assert list_branches(tmp_path, "dark-train") == []
        create_branch(tmp_path, "dark-train", "alt-elena", "c0005")
        create_branch(tmp_path, "dark-train", "alt-conductor", "c0006")

        assert list_branches(tmp_path, "dark-train") == ["alt-conductor", "alt-elena"]
        assert read_ref(tmp_path, "dark-train", "alt-elena") == "c0005"

    def test_create_branch_no_clobber(self, tmp_path: Path):
        create_branch(tmp_path, "dark-train", "alt", "c1")
        try:
            create_branch(tmp_path, "dark-train", "alt", "c2")
            raise AssertionError("expected FileExistsError")
        except FileExistsError:
            pass
        assert read_ref(tmp_path, "dark-train", "alt") == "c1"


# --------------------------------------------------------------------------- #
# Commit object IO
# --------------------------------------------------------------------------- #

class TestCommitObjectIO:
    def test_world_commit_roundtrip(self, tmp_path: Path):
        obj = _world_commit("c12af3b9e7d2", None, 0, blob="g-aaa")
        write_world_commit(tmp_path, obj)
        assert read_world_commit(tmp_path, "c12af3b9e7d2") == obj

    def test_soul_commit_roundtrip(self, tmp_path: Path):
        soul_path = tmp_path / "souls" / "elena-si-a1"
        obj = {
            "schema_version": 2,
            "soul_commit_id": "s9b71e22a4f8",
            "parent": None,
            "branch": "main",
            "soul": {"sid": "elena", "instance_id": "si-a1", "version_hash": "v"},
            "folder_hash": "sf812",
            "bundle_url": "file:///x",
            "agent_snapshot": {"conversation_hash": "ca55", "bundle_url": "y"},
            "turn_seq": 87,
            "archived_at": None,
        }
        write_soul_commit(soul_path, obj)
        assert read_soul_commit(soul_path, "s9b71e22a4f8") == obj

    def test_missing_commit_id_rejected(self, tmp_path: Path):
        try:
            write_world_commit(tmp_path, {"parent": None})
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


# --------------------------------------------------------------------------- #
# Garbage collection
# --------------------------------------------------------------------------- #

class TestGc:
    def _seed_chain(self, root: Path) -> None:
        # c0 -> c1 -> c2 (linear, main HEAD at c2). Each commit owns a blob.
        for i, parent in enumerate([None, "c0", "c1"]):
            cid = f"c{i}"
            write_world_commit(root, _world_commit(cid, parent, i, blob=f"g-{cid}"))
            write_blob(root, f"g-{cid}", b"blob-" + cid.encode())
            write_blob(root, f"l-{cid}", b"log")
            write_blob(root, f"wa-{cid}", b"conv")
        write_ref(root, "dark-train", "c2")

    def test_orphan_blob_dropped_reachable_kept(self, tmp_path: Path):
        self._seed_chain(tmp_path)
        write_blob(tmp_path, "orphan-xyz", b"nobody references me")

        report = gc(tmp_path, keep_tagged=True, keep_last=100)

        assert isinstance(report, GcReport)
        assert "orphan-xyz" in report.deleted_blobs
        assert "g-c2" in report.kept_blobs
        assert "g-c0" in report.kept_blobs  # ancestor reachable from HEAD
        # Reachable commits all retained under a generous keep_last.
        assert set(report.kept_commits) == {"c0", "c1", "c2"}
        assert report.deleted_commits == []

    def test_keep_last_drops_old_reachable(self, tmp_path: Path):
        self._seed_chain(tmp_path)

        report = gc(tmp_path, keep_tagged=True, keep_last=1)

        # Only the newest by turn_seq (c2) survives; older ancestors collected.
        assert report.kept_commits == ["c2"]
        assert set(report.deleted_commits) == {"c0", "c1"}
        # Their now-unreferenced blobs go too; c2's stay.
        assert "g-c0" in report.deleted_blobs
        assert "g-c2" in report.kept_blobs

    def test_tag_overrides_keep_last(self, tmp_path: Path):
        self._seed_chain(tmp_path)
        # Tag the oldest commit; it must survive even with keep_last=1.
        tags = tmp_path / "refs" / "tags"
        tags.mkdir(parents=True)
        (tags / "checkpoint").write_text("c0\n", encoding="utf-8")

        report = gc(tmp_path, keep_tagged=True, keep_last=1)

        assert "c0" in report.kept_commits
        assert "g-c0" in report.kept_blobs
        assert "c2" in report.kept_commits  # HEAD-newest still kept too

    def test_keep_tagged_false_ignores_tags(self, tmp_path: Path):
        self._seed_chain(tmp_path)
        tags = tmp_path / "refs" / "tags"
        tags.mkdir(parents=True)
        (tags / "checkpoint").write_text("c0\n", encoding="utf-8")

        report = gc(tmp_path, keep_tagged=False, keep_last=1)

        assert "c0" in report.deleted_commits
        assert report.kept_commits == ["c2"]

    def test_gc_empty_store_is_noop(self, tmp_path: Path):
        report = gc(tmp_path)
        assert report.deleted_commits == []
        assert report.deleted_blobs == []
