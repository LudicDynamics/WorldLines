"""Commit blob/ref STORAGE layer for the M17 commit-versioning subsystem.

This module is the *storage IO* leaf only. It does NOT compose commits and
does NOT derive `commit_id`s — that is `core/turn_commit.py`'s job (built in
parallel). Here we only:

  * pack/unpack a directory into a deterministic, content-hashed blob,
  * read/write blobs, world commit objects and soul commit objects,
  * read/write/list refs (HEAD + named branches),
  * garbage-collect unreachable commit objects and orphan blobs.

Storage layout (M17 design §4), rooted at ``COMMITS_HOME``::

    ~/.worldlines/commits/
    ├── worlds/<world_commit_id>.json   # world commit objects
    ├── refs/
    │   ├── <wid>/HEAD                  # tip of "main" for this wid
    │   ├── <wid>/branches/<name>       # tip of named branches
    │   └── tags/<name>                 # user tags → commit_id
    └── blobs/<blob_hash>.tar.xz        # deduplicated packed dirs

Soul commit objects live outside this tree, under the soul instance's own
``.commits/`` dir (design §2.2); callers pass that path explicitly.

Stdlib only: ``tarfile`` + ``lzma``. The design (§4.1) specifies ``.tar.zst``
(zstandard), but adding ``zstandard`` would violate the no-new-deps rule, so
we use stdlib ``lzma`` and emit ``.tar.xz``. zstd remains a deferred
dependency decision (see module report).
"""

from __future__ import annotations

import hashlib
import gzip
import io
import json
import lzma
import shutil
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

# Default storage root. Injectable per-call via the ``root`` argument so tests
# (and a future relocatable install) never touch the real home directory.
COMMITS_HOME: Path = Path.home() / ".worldlines" / "commits"

# Fixed tar member metadata. Zeroing mtime/uid/gid and clearing owner names is
# what makes "same dir → same bytes → same hash" hold across machines and
# clock states; without this the tar header would smear in volatile metadata.
_TAR_MTIME = 0
_TAR_UID = 0
_TAR_GID = 0
_TAR_UNAME = ""
_TAR_GNAME = ""

# lzma preset: deterministic by construction (no timestamp in the xz stream),
# preset 6 is the stdlib default — a reasonable size/speed tradeoff for blobs.
_LZMA_PRESET = 6

_BLOB_SUFFIX = ".tar.xz"


# --------------------------------------------------------------------------- #
# Path helpers
# --------------------------------------------------------------------------- #

def _worlds_dir(root: Path) -> Path:
    return Path(root) / "worlds"


def _blobs_dir(root: Path) -> Path:
    return Path(root) / "blobs"


def _refs_dir(root: Path) -> Path:
    return Path(root) / "refs"


def _wid_refs_dir(root: Path, wid: str) -> Path:
    return _refs_dir(root) / wid


def _branches_dir(root: Path, wid: str) -> Path:
    return _wid_refs_dir(root, wid) / "branches"


def _ref_path(root: Path, wid: str, name: str) -> Path:
    """Resolve a ref name to its on-disk file.

    ``HEAD`` is the bare tip file; everything else is a named branch under
    ``<wid>/branches/<name>`` (design §4 layout).
    """
    if name == "HEAD":
        return _wid_refs_dir(root, wid) / "HEAD"
    return _branches_dir(root, wid) / name


def _blob_path(root: Path, blob_hash: str) -> Path:
    return _blobs_dir(root) / f"{blob_hash}{_BLOB_SUFFIX}"


def _world_commit_path(root: Path, commit_id: str) -> Path:
    return _worlds_dir(root) / f"{commit_id}.json"


def _soul_commits_dir(soul_instance_path: Path) -> Path:
    return Path(soul_instance_path) / ".commits"


def _soul_commit_path(soul_instance_path: Path, commit_id: str) -> Path:
    return _soul_commits_dir(soul_instance_path) / f"{commit_id}.json"


# --------------------------------------------------------------------------- #
# Blob pack / unpack
# --------------------------------------------------------------------------- #

def pack_dir(src_dir: Path) -> tuple[str, bytes]:
    """Pack ``src_dir`` into a deterministic ``.tar.xz`` blob.

    Returns ``(blob_hash, blob_bytes)``. The hash is sha256 of the *packed
    bytes* (not the directory tree). We hash the packed bytes — not the dir —
    because the blob's identity for dedup/GC is the artefact stored on disk;
    determinism of pack guarantees the dir→bytes map is stable, so the bytes
    hash is an equivalent content key while also detecting blob corruption.

    Determinism guarantees (so the same dir always yields the same bytes):
      * entries enumerated and emitted in sorted POSIX-path order,
      * mtime/uid/gid zeroed, owner/group names cleared,
      * directory entries themselves are NOT emitted (only files), so empty
        vs. pruned dirs cannot perturb the stream,
      * lzma stream carries no timestamp.
    """
    src_dir = Path(src_dir)

    files: list[tuple[str, Path]] = []
    if src_dir.exists():
        for path in src_dir.rglob("*"):
            if path.is_file():
                arcname = path.relative_to(src_dir).as_posix()
                files.append((arcname, path))
    files.sort(key=lambda item: item[0])

    raw = io.BytesIO()
    # format=GNU_FORMAT is stable across Python versions for our field set.
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for arcname, path in files:
            info = tar.gettarinfo(name=str(path), arcname=arcname)
            info.mtime = _TAR_MTIME
            info.uid = _TAR_UID
            info.gid = _TAR_GID
            info.uname = _TAR_UNAME
            info.gname = _TAR_GNAME
            # Normalise mode so a file's executable bit on one machine does not
            # change the blob hash on another; regular-file rw-r--r--.
            info.mode = 0o644
            with open(path, "rb") as fh:
                tar.addfile(info, fh)

    blob_bytes = _compress(raw.getvalue())
    blob_hash = _sha256_bytes(blob_bytes)
    return blob_hash, blob_bytes


# Blob codec. xz preset 6 costs ≈1 s/MB and the worlds carry 2 MB portrait
# PNGs (incompressible): E1 09-25 measured 1.8 s per folder, ×3 folders, every
# turn — the single largest engine-side cost of a landed turn. gzip level 1
# is ≈50 ms/MB and still deterministic (mtime pinned). Old blobs stay xz;
# ``unpack_dir`` sniffs the magic so both restore.
_CODEC = "gzip1"


def _compress(raw: bytes) -> bytes:
    if _CODEC == "xz":
        return lzma.compress(raw, preset=_LZMA_PRESET)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=1, mtime=0) as gz:
        gz.write(raw)
    return buf.getvalue()


def _decompress(blob_bytes: bytes) -> bytes:
    if blob_bytes[:2] == b"\x1f\x8b":
        return gzip.decompress(blob_bytes)
    return lzma.decompress(blob_bytes)


def unpack_dir(blob_bytes: bytes, dest_dir: Path) -> None:
    """Restore a blob produced by :func:`pack_dir` into ``dest_dir``.

    ``dest_dir`` is created if absent. Extraction is filtered to regular files
    only and rejects any member whose resolved path escapes ``dest_dir``
    (defence against a tampered/hostile blob).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_root = dest_dir.resolve()

    raw = _decompress(blob_bytes)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            target = (dest_dir / member.name).resolve()
            if dest_root != target and dest_root not in target.parents:
                raise ValueError(f"blob member escapes destination: {member.name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            with extracted, open(target, "wb") as out:
                shutil.copyfileobj(extracted, out)


def has_blob(root: Path, blob_hash: str) -> bool:
    """True when a blob for this key is already stored (dedup check before packing)."""
    return _blob_path(root, blob_hash).exists()


def write_blob(root: Path, blob_hash: str, data: bytes) -> Path:
    """Write a blob to ``blobs/<blob_hash>.tar.xz``.

    Idempotent: identical content hashes the same, so re-writing an existing
    blob is a no-op (this is the dedup point — two unchanged turns share one
    blob, design §4.1). Returns the blob path.
    """
    path = _blob_path(root, blob_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return path


def read_blob(root: Path, blob_hash: str) -> bytes:
    """Read raw blob bytes by hash. Raises ``FileNotFoundError`` if absent."""
    return _blob_path(root, blob_hash).read_bytes()


# --------------------------------------------------------------------------- #
# Commit object IO
# --------------------------------------------------------------------------- #

def write_world_commit(root: Path, obj: dict) -> Path:
    """Persist a world commit object to ``worlds/<world_commit_id>.json``.

    The commit object is supplied fully-formed by ``turn_commit.py``; this
    layer only validates that an id is present and writes the file.
    """
    commit_id = _require_commit_id(obj, "world_commit_id")
    path = _world_commit_path(root, commit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, obj)
    return path


def read_world_commit(root: Path, commit_id: str) -> dict:
    """Load a world commit object. Raises ``FileNotFoundError`` if absent."""
    return _read_json(_world_commit_path(root, commit_id))


def write_soul_commit(soul_instance_path: Path, obj: dict) -> Path:
    """Persist a soul commit object under the soul instance's ``.commits/``.

    Soul commits are fully independent of the world commit tree (design §2.2),
    so they take an explicit soul-instance directory rather than ``root``.
    """
    commit_id = _require_commit_id(obj, "soul_commit_id")
    path = _soul_commit_path(soul_instance_path, commit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, obj)
    return path


def read_soul_commit(soul_instance_path: Path, commit_id: str) -> dict:
    """Load a soul commit object. Raises ``FileNotFoundError`` if absent."""
    return _read_json(_soul_commit_path(soul_instance_path, commit_id))


# --------------------------------------------------------------------------- #
# Refs
# --------------------------------------------------------------------------- #

def read_ref(root: Path, wid: str, name: str = "HEAD") -> str | None:
    """Read the commit_id a ref points at. Absent ref → ``None``.

    Absent is a normal state (a brand-new wid has no HEAD yet), so we return
    ``None`` rather than raising — callers branch on first-commit.
    """
    path = _ref_path(root, wid, name)
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def write_ref(root: Path, wid: str, commit_id: str, name: str = "HEAD") -> Path:
    """Point a ref (``HEAD`` or a named branch) at ``commit_id``."""
    path = _ref_path(root, wid, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{commit_id}\n", encoding="utf-8")
    return path


def list_branches(root: Path, wid: str) -> list[str]:
    """Return sorted named-branch names for ``wid`` (excludes bare HEAD)."""
    bdir = _branches_dir(root, wid)
    if not bdir.exists():
        return []
    return sorted(p.name for p in bdir.iterdir() if p.is_file())


def create_branch(root: Path, wid: str, name: str, at_commit: str) -> Path:
    """Create a named branch pointing at ``at_commit``.

    Raises ``FileExistsError`` if the branch already exists — branch creation
    is not idempotent on purpose, so a fork never silently clobbers an
    existing divergent line (design §3.2).
    """
    if name == "HEAD":
        raise ValueError("'HEAD' is reserved and is not a branch name")
    path = _ref_path(root, wid, name)
    if path.exists():
        raise FileExistsError(f"branch {name!r} already exists for {wid!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{at_commit}\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Garbage collection
# --------------------------------------------------------------------------- #

@dataclass
class GcReport:
    """Outcome of a :func:`gc` pass."""

    deleted_commits: list[str] = field(default_factory=list)
    deleted_blobs: list[str] = field(default_factory=list)
    kept_commits: list[str] = field(default_factory=list)
    kept_blobs: list[str] = field(default_factory=list)


def gc(root: Path, *, keep_tagged: bool = True, keep_last: int = 100) -> GcReport:
    """Reclaim unreachable world commit objects and orphan blobs.

    Reachability algorithm:
      1. **Roots** = every ref tip (HEAD + all named branches) and, if
         ``keep_tagged``, every tag under ``refs/tags/``.
      2. Walk each root's ``parent`` chain (the commit DAG, design §3) to build
         the full reachable-commit set. Walking ``parent`` from every tip
         covers the DAG because branches only ever fork *forward* — every
         historical node is an ancestor of some tip or tag.
      3. ``keep_last`` caps retention: of the reachable commits, only the most
         recent N by ``turn_seq`` (then commit_id, for a stable tiebreak) are
         kept; older reachable commits beyond N are dropped. Tagged commits are
         always retained when ``keep_tagged`` regardless of the cap, since a
         tag is an explicit "do not collect this" marker (design §4.2).
      4. Commit objects not in the keep set are deleted.
      5. A blob is kept iff it is referenced by a surviving commit object;
         every other blob is an orphan and is deleted.

    Returns a :class:`GcReport` of what was deleted vs. kept.
    """
    report = GcReport()

    all_commits = _all_world_commit_ids(root)
    if not all_commits:
        return report

    tag_targets = _tag_targets(root) if keep_tagged else {}
    roots = set(_all_ref_tips(root)) | set(tag_targets.values())

    reachable: set[str] = set()
    for start in roots:
        _walk_parents(root, start, reachable)

    # Apply keep_last: rank reachable commits newest-first. turn_seq is the
    # design's per-chain ordering breadcrumb; commit_id breaks ties so the
    # ordering is deterministic even if turn_seq collides across branches.
    ranked = sorted(
        reachable,
        key=lambda cid: (_commit_turn_seq(root, cid), cid),
        reverse=True,
    )
    keep: set[str] = set(ranked[:keep_last]) if keep_last >= 0 else set(ranked)
    if keep_tagged:
        keep |= set(tag_targets.values())

    # Delete commit objects outside the keep set.
    for cid in sorted(all_commits):
        if cid in keep:
            report.kept_commits.append(cid)
        else:
            _world_commit_path(root, cid).unlink(missing_ok=True)
            report.deleted_commits.append(cid)

    # Blob sweep: a blob survives only if a kept commit still references it.
    referenced: set[str] = set()
    for cid in report.kept_commits:
        try:
            obj = read_world_commit(root, cid)
        except FileNotFoundError:
            continue
        referenced |= _referenced_blob_hashes(obj)

    for blob_hash in sorted(_all_blob_hashes(root)):
        if blob_hash in referenced:
            report.kept_blobs.append(blob_hash)
        else:
            _blob_path(root, blob_hash).unlink(missing_ok=True)
            report.deleted_blobs.append(blob_hash)

    return report


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _sha256_bytes(data: bytes) -> str:
    """Content hash for blobs.

    ``core/hashing.py`` only exposes a *file/tree* hasher; the blob hash is
    over in-memory packed bytes, so there is no file to hand it. We use the
    identical sha256 hex digest that module uses (``hashlib.sha256``), so the
    algorithm stays the single shared one (design §5.2 "no second hash") — we
    just feed it bytes instead of a file path.
    """
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    # sort_keys + trailing newline so a re-serialised commit object is
    # byte-stable on disk (helps diffing and any future content addressing).
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_commit_id(obj: dict, key: str) -> str:
    cid = obj.get(key)
    if not cid or not isinstance(cid, str):
        raise ValueError(f"commit object missing string {key!r}")
    return cid


def _all_world_commit_ids(root: Path) -> list[str]:
    wdir = _worlds_dir(root)
    if not wdir.exists():
        return []
    return [p.stem for p in wdir.glob("*.json")]


def _all_blob_hashes(root: Path) -> list[str]:
    bdir = _blobs_dir(root)
    if not bdir.exists():
        return []
    out: list[str] = []
    for p in bdir.glob(f"*{_BLOB_SUFFIX}"):
        out.append(p.name[: -len(_BLOB_SUFFIX)])
    return out


def _all_ref_tips(root: Path) -> list[str]:
    """Every commit_id pointed at by HEAD or a named branch, any wid."""
    refs = _refs_dir(root)
    if not refs.exists():
        return []
    tips: list[str] = []
    for wid_dir in refs.iterdir():
        if not wid_dir.is_dir() or wid_dir.name == "tags":
            continue
        head = wid_dir / "HEAD"
        if head.is_file():
            v = head.read_text(encoding="utf-8").strip()
            if v:
                tips.append(v)
        bdir = wid_dir / "branches"
        if bdir.is_dir():
            for bp in bdir.iterdir():
                if bp.is_file():
                    v = bp.read_text(encoding="utf-8").strip()
                    if v:
                        tips.append(v)
    return tips


def _tag_targets(root: Path) -> dict[str, str]:
    """Map tag-name → commit_id from ``refs/tags/``."""
    tdir = _refs_dir(root) / "tags"
    if not tdir.exists():
        return {}
    out: dict[str, str] = {}
    for tp in tdir.iterdir():
        if tp.is_file():
            v = tp.read_text(encoding="utf-8").strip()
            if v:
                out[tp.name] = v
    return out


def _walk_parents(root: Path, start: str, seen: set[str]) -> None:
    """Add ``start`` and all its ancestors (via ``parent``) to ``seen``."""
    cursor: str | None = start
    while cursor and cursor not in seen:
        seen.add(cursor)
        try:
            obj = read_world_commit(root, cursor)
        except FileNotFoundError:
            return  # dangling parent (already GC'd / never written) — stop.
        cursor = obj.get("parent")


def _commit_turn_seq(root: Path, commit_id: str) -> int:
    try:
        obj = read_world_commit(root, commit_id)
    except FileNotFoundError:
        return -1
    seq = obj.get("turn_seq")
    return seq if isinstance(seq, int) else -1


def _referenced_blob_hashes(obj: dict) -> set[str]:
    """Collect every blob hash a world commit object points at.

    Per the §2.1 schema the blob-bearing sections are ``game_folder``,
    ``session_log`` and ``world_agent_snapshot``. We read the hash fields
    directly (``hash`` / ``conversation_hash``) rather than parsing
    ``bundle_url``, because the hash is the storage key and the URL is only a
    human/debug locator that may differ by machine (design §1.4: hash locates,
    not the path).
    """
    out: set[str] = set()
    gf = obj.get("game_folder")
    if isinstance(gf, dict) and isinstance(gf.get("hash"), str):
        out.add(gf["hash"])
    sl = obj.get("session_log")
    if isinstance(sl, dict) and isinstance(sl.get("hash"), str):
        out.add(sl["hash"])
    wa = obj.get("world_agent_snapshot")
    if isinstance(wa, dict) and isinstance(wa.get("conversation_hash"), str):
        out.add(wa["conversation_hash"])
    return out
