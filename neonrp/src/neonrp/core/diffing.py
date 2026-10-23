"""Diff rendering for NeonRP proposals and for direct build-mode writes.

Two audiences:

- ``render_diff`` / ``render_diff_summary`` — sandbox proposals, reviewed
  before they land.
- ``summarize_write`` (M31) — build mode's *direct* writes, where there is
  no review step: the file is already on disk by the time anyone looks.
  The agent surface still has to answer "what changed, and how", so every
  write hands back a compact change record the TUI folds into its tool
  card. Cheap on purpose: the old content is in hand at write time, while
  diffing landed commits would mean unpacking two tarballs.
"""

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from neonrp.core.proposal import Proposal, UpsertTextOp, DeleteOp

# A preview is for glancing, not for reading the file back. Anything past
# this lands in the file itself, which is one `read_file` away.
_PREVIEW_MAX_LINES = 24
_PREVIEW_MAX_LINE_CHARS = 160


@dataclass
class WriteSummary:
    """What one direct write did, in the terms a reviewer thinks in."""

    path: str
    kind: str = "modified"  # created | modified | deleted | unchanged
    added: int = 0
    removed: int = 0
    preview: str = ""
    truncated: bool = False

    @property
    def headline(self) -> str:
        """One-line form for a collapsed tool card: ``created +12``."""
        if self.kind == "unchanged":
            return "unchanged"
        parts = [self.kind]
        if self.added:
            parts.append(f"+{self.added}")
        if self.removed:
            parts.append(f"-{self.removed}")
        return " ".join(parts)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "added": self.added,
            "removed": self.removed,
            "headline": self.headline,
            "preview": self.preview,
            "truncated": self.truncated,
        }


def _split(text: str) -> list[str]:
    return text.splitlines()


def summarize_write(
    path: str,
    old_content: str | None,
    new_content: str | None,
) -> WriteSummary:
    """Describe a direct write: created / modified / deleted, ± lines, preview.

    ``old_content is None`` means the file did not exist; ``new_content is
    None`` means it was deleted. Binary or undecodable content should be
    passed as ``None``-free empty strings by the caller — this function
    only ever sees text.
    """
    if new_content is None:
        old_lines = _split(old_content or "")
        return WriteSummary(
            path=path,
            kind="deleted",
            removed=len(old_lines),
            preview="",
        )

    if old_content is None:
        new_lines = _split(new_content)
        preview, truncated = _preview_lines(f"+{line}" for line in new_lines)
        return WriteSummary(
            path=path,
            kind="created",
            added=len(new_lines),
            preview=preview,
            truncated=truncated,
        )

    if old_content == new_content:
        return WriteSummary(path=path, kind="unchanged")

    old_lines = _split(old_content)
    new_lines = _split(new_content)
    diff = list(
        difflib.unified_diff(old_lines, new_lines, lineterm="", n=2)
    )
    # Drop the ---/+++ header lines; the path is already on the card.
    body = [line for line in diff[2:] if not line.startswith("@@")] if len(diff) > 2 else []
    added = sum(1 for line in body if line.startswith("+"))
    removed = sum(1 for line in body if line.startswith("-"))
    preview, truncated = _preview_lines(iter(body))
    return WriteSummary(
        path=path,
        kind="modified",
        added=added,
        removed=removed,
        preview=preview,
        truncated=truncated,
    )


def _preview_lines(lines) -> tuple[str, bool]:
    """Clip a diff body to something a tool card can hold."""
    kept: list[str] = []
    truncated = False
    for line in lines:
        if len(kept) >= _PREVIEW_MAX_LINES:
            truncated = True
            break
        if len(line) > _PREVIEW_MAX_LINE_CHARS:
            line = line[:_PREVIEW_MAX_LINE_CHARS] + "…"
        kept.append(line)
    return "\n".join(kept), truncated


@dataclass
class TurnChangeLedger:
    """Every file a single build turn touched (M31 B2).

    The per-write cards scroll past; this is the turn-level answer to
    "so what did it actually do".
    """

    writes: list[WriteSummary] = field(default_factory=list)

    def record(self, summary: WriteSummary) -> None:
        if summary.kind == "unchanged":
            return
        self.writes.append(summary)

    @property
    def is_empty(self) -> bool:
        return not self.writes

    def counts(self) -> dict[str, int]:
        out = {"created": 0, "modified": 0, "deleted": 0}
        for w in self.writes:
            if w.kind in out:
                out[w.kind] += 1
        return out

    def common_prefix(self) -> str:
        """Shared directory of everything touched, for a compact headline."""
        if not self.writes:
            return ""
        parts = [Path(w.path).parent.as_posix() for w in self.writes]
        if len(set(parts)) == 1:
            return parts[0]
        first = parts[0].split("/")
        for other in parts[1:]:
            other_parts = other.split("/")
            keep = 0
            for a, b in zip(first, other_parts):
                if a != b:
                    break
                keep += 1
            first = first[:keep]
            if not first:
                return ""
        return "/".join(first)

    def headline(self) -> str:
        """``3 created · 1 modified · souls/luowen`` — empty when nothing moved.

        The location is only worth printing when it actually locates
        something: a shallow common ancestor like ``.neonrp`` is true but
        tells the reader nothing, so it is left off.
        """
        if not self.writes:
            return ""
        counts = self.counts()
        bits = [f"{n} {kind}" for kind, n in counts.items() if n]
        where = self.common_prefix()
        line = " · ".join(bits)
        if where and len(where.split("/")) >= 2:
            return f"{line} · {where}"
        return line

    def to_dict(self) -> dict[str, object]:
        return {
            "counts": self.counts(),
            "headline": self.headline(),
            "files": [w.to_dict() for w in self.writes],
        }


def render_diff(proposal: Proposal, game_root: Path) -> str:
    """Render a proposal as unified diff output.

    Args:
        proposal: The proposal containing operations
        game_root: Path to the game directory

    Returns:
        Unified diff string, sorted by path for stability
    """
    diff_sections = []

    # Sort ops by path for stable output
    sorted_ops = sorted(proposal.ops, key=lambda op: op.path)

    for op in sorted_ops:
        section = _render_op_diff(op, game_root)
        if section:
            diff_sections.append(section)

    return "\n".join(diff_sections)


def _render_op_diff(op: UpsertTextOp | DeleteOp, game_root: Path) -> str:
    """Render diff for a single operation.

    Args:
        op: The operation to render
        game_root: Path to the game directory

    Returns:
        Diff string for this operation
    """
    file_path = game_root / op.path

    if isinstance(op, DeleteOp):
        return _render_delete_diff(op.path, file_path)
    elif isinstance(op, UpsertTextOp):
        return _render_upsert_diff(op.path, file_path, op.content)

    return ""


def _render_delete_diff(path: str, file_path: Path) -> str:
    """Render diff for a delete operation.

    Args:
        path: Relative path of the file
        file_path: Absolute path to the file

    Returns:
        Diff showing file deletion
    """
    old_lines = []

    # Read old content if file exists
    if file_path.exists():
        try:
            old_content = file_path.read_text(encoding="utf-8")
            old_lines = old_content.splitlines(keepends=False)
        except (IOError, UnicodeDecodeError):
            old_lines = ["[binary or unreadable file]"]

    # Compute hunk header with correct line count
    old_line_count = len(old_lines)
    hunk_header = f"@@ -1,{old_line_count} +0,0 @@"

    lines = [
        f"--- a/{path}",
        "+++ /dev/null",
        hunk_header,
    ]

    for line in old_lines:
        lines.append(f"-{line}")

    return "\n".join(lines)


def _render_upsert_diff(path: str, file_path: Path, new_content: str) -> str:
    """Render diff for an upsert operation.

    Args:
        path: Relative path of the file
        file_path: Absolute path to the file
        new_content: New content to write

    Returns:
        Unified diff showing changes
    """
    # Get old content if file exists
    if file_path.exists():
        try:
            old_content = file_path.read_text(encoding="utf-8")
        except (IOError, UnicodeDecodeError):
            old_content = ""
        from_file = f"a/{path}"
    else:
        old_content = ""
        from_file = "/dev/null"

    # Generate unified diff
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Ensure lines end with newlines for proper diff
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] += "\n"
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    diff = difflib.unified_diff(old_lines, new_lines, fromfile=from_file, tofile=f"b/{path}", lineterm="")

    result = "\n".join(line.rstrip() for line in diff)

    # If no changes, return empty
    if not result:
        return ""

    return result


def render_diff_summary(proposal: Proposal, game_root: Path) -> dict:
    """Generate a summary of changes in a proposal.

    Args:
        proposal: The proposal containing operations
        game_root: Path to the game directory

    Returns:
        Dictionary with lists of added, modified, and deleted files
    """
    added = []
    modified = []
    deleted = []

    for op in proposal.ops:
        file_path = game_root / op.path

        if isinstance(op, DeleteOp):
            deleted.append(op.path)
        elif isinstance(op, UpsertTextOp):
            if file_path.exists():
                modified.append(op.path)
            else:
                added.append(op.path)

    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
        "total": len(added) + len(modified) + len(deleted),
    }


