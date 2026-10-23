"""Game directory hashing for save/replay verification.

Provides a stable, deterministic hash over the entire game directory,
suitable for detecting changes between replay runs.
"""

import hashlib
from pathlib import Path


def compute_game_hash(game_dir: Path) -> str:
    """Compute a stable tree hash for the game directory.

    Algorithm:
    1. Enumerate all files under game_dir recursively
    2. Normalize paths to forward slash (relative to game_dir)
    3. Compute sha256 of each file's bytes
    4. Sort entries by normalized path
    5. Final hash = sha256(join_lines(sorted("{path}\\t{file_hash}")))
    6. Return "sha256:{hex_digest}"

    Args:
        game_dir: Path to the game directory.

    Returns:
        String in format "sha256:{hex_digest}".
        Returns "sha256:empty" if directory doesn't exist or is empty.
    """
    game_dir = Path(game_dir)

    if not game_dir.exists():
        return "sha256:empty"

    entries: list[str] = []

    for file_path in sorted(game_dir.rglob("*")):
        if file_path.is_file():
            # Compute relative path with forward slashes
            rel_path = file_path.relative_to(game_dir).as_posix()

            # Compute file hash
            file_hash = _hash_file(file_path)
            entries.append(f"{rel_path}\t{file_hash}")

    if not entries:
        return "sha256:empty"

    # Compute final hash over all entries
    combined = "\n".join(entries)
    final_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()

    return f"sha256:{final_hash}"


def compute_file_hash(file_path: Path) -> str:
    """Compute sha256 hash of a single file.

    Args:
        file_path: Path to the file.

    Returns:
        Hex-encoded sha256 hash.
    """
    return _hash_file(file_path)


def _hash_file(file_path: Path) -> str:
    """Hash file contents with sha256."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


