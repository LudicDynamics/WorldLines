import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any
import tempfile


def atomic_write_json(path: Path, data: Any, indent: int = 2):
    """Write dictionary to JSON file using write-to-temp-then-rename pattern."""
    path = Path(path)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)

    # Create temp file in the same directory to ensure atomic move on file system
    # We use delete=False then manually close, to allow os.replace on Windows
    fd, tmp_path = tempfile.mkstemp(dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, default=str, ensure_ascii=False)

        # Atomic replacement
        os.replace(tmp_path, path)
    except Exception:
        # Cleanup on failure
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def atomic_write_text(path: Path, content: str) -> None:
    """Write text content to file using write-to-temp-then-rename pattern.

    Args:
        path: Target file path
        content: Text content to write

    This function:
    - Creates parent directories if they don't exist
    - Uses atomic temp file + rename for crash safety
    - Cleans up temp file on failure
    """
    path = Path(path)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory for atomic move
    fd, tmp_path = tempfile.mkstemp(dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)

        # Atomic replacement
        os.replace(tmp_path, path)
    except Exception:
        # Cleanup on failure
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Write bytes content to file using write-to-temp-then-rename pattern."""
    path = Path(path)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def atomic_copy_file(src: Path, dst: Path) -> None:
    """Atomically copy src file to dst using temp file + replace."""
    src = Path(src)
    data = src.read_bytes()
    atomic_write_bytes(dst, data)


def atomic_write_dir(target: Path, source: Path):
    """
    Atomically overwrite target directory with source directory.
    Strategy:
    1. Move source to target.tmp (if on same filesystem) or copy.
    2. Rename target to target.old (backup).
    3. Rename target.tmp to target.
    4. Delete target.old.

    Actually os.replace (rename) is atomic for directories on POSIX and modern Windows
    if they are on the same volume.
    """
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)

    # We essentially want "install source as target".
    # But source might be a temp dir.

    # 1. Prepare temp path on same volume
    tmp_target = target.with_suffix(f".{uuid.uuid4().hex}.tmp")

    # Copy source content to tmp location to ensure it's on same volume and independent
    if source.exists():
        shutil.copytree(source, tmp_target, dirs_exist_ok=True)

    # 2. Atomic Swap
    try:
        # Windows: os.replace cannot replace existing directory sometimes?
        # Python 3.3+ os.replace supports directory replacement on POSIX.
        # On Windows, it might retain the old one or fail if not empty?
        # Let's try os.replace first.
        # Check docs: "On Windows, if dst exists and is a file, OSError will be raised...
        # if dst is a directory, OSError will be raised."
        # Wait, Python docs say os.replace is platform independent?
        # "On Windows, if dst exists, it will be replaced..." implies files.
        # For directories on Windows, we might need a workaround.

        # Robust approach for M0: atomic rename if target doesn't exist,
        # else move target aside, rename new, del old.

        old_target = target.with_suffix(f".{uuid.uuid4().hex}.bak")

        if target.exists():
            os.rename(target, old_target)

        try:
            os.rename(tmp_target, target)
        except Exception:
            # Rollback
            if old_target.exists():
                os.rename(old_target, target)
            raise

        # Success, cleanup old
        if old_target.exists():
            shutil.rmtree(old_target)

    except Exception:
        if tmp_target.exists():
            shutil.rmtree(tmp_target)
        raise


def ensure_dirs(root: Path):
    """Ensure standard M0 directory structure exists."""
    from .paths import get_game_dir, get_neonrp_dir, get_rules_dir

    neonrp_dir = get_neonrp_dir(root)
    neonrp_dir.mkdir(exist_ok=True)

    (neonrp_dir / "events").mkdir(exist_ok=True)
    (neonrp_dir / "saves").mkdir(exist_ok=True)
    (neonrp_dir / "branches").mkdir(exist_ok=True)  # For branch isolation
    (neonrp_dir / "logs").mkdir(exist_ok=True)
    get_game_dir(root).mkdir(exist_ok=True)
    get_rules_dir(root).mkdir(exist_ok=True)
