"""Roll a run back to a past turn, git-style (10-08: one implementation for the web runtime and the TUI's /rollback).

The current line is kept (its ref + session log stay); a sandbox branch is forked at the turn's world commit (game +
souls restored, souls re-minted with their folders), the orchestration history up to the fork is carried over (the
replay bar / resume still show 1..N), and the new branch becomes the manifest's current branch. The caller drops its
cached session afterwards so the next turn runs on the new branch.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


def commit_for_turn(root: Path, turn: int, branch: str | None = None) -> str | None:
    """The world commit of ``turn`` on ``branch`` (default: the current one), newest first when several."""
    from neonrp.webui.commit_routes import commit_graph

    g = commit_graph(Path(root))
    br = branch or str(g.get("branch") or "main")
    hits = [n for n in g.get("nodes") or [] if n.get("turn_seq") == turn and str(n.get("branch") or "main") == br]
    if not hits:
        hits = [n for n in g.get("nodes") or [] if n.get("turn_seq") == turn]
    return str(hits[0]["id"]) if hits else None


def fork_orchestration(root: Path, source: str, dest: str, turn_seq: int | None) -> None:
    """Copy ``source``'s orchestration trace lines with ``turn_seq`` ≤ the fork point onto ``dest``. Best-effort."""
    if turn_seq is None:
        return
    src = Path(root) / ".neonrp" / "orchestration" / f"{source}.jsonl"
    if not src.exists():
        return
    kept: list[str] = []
    try:
        for line in src.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                if int(json.loads(line).get("turn_seq", 0)) <= turn_seq:
                    kept.append(line)
            except (ValueError, TypeError):
                continue
    except OSError:
        return
    dst = Path(root) / ".neonrp" / "orchestration" / f"{dest}.jsonl"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")


def rollback(root: Path, commit_id: str, source_branch: str) -> dict[str, Any]:
    """Fork ``rollback-xxxxxxxx`` at ``commit_id`` and make it current. {ok, branch, commit_id, turn_seq, souls} or
    {ok: False, error}."""
    from neonrp.core.commit_subsystem import CommitSubsystemError, rollback_to_commit
    from neonrp.core.manifest import BranchMetadata, Manifest
    from neonrp.core.paths import get_manifest_path
    from neonrp.core.storage import atomic_write_json

    root = Path(root)
    new_branch = f"rollback-{uuid.uuid4().hex[:8]}"
    try:
        out = rollback_to_commit(root, root / ".neonrp" / "commits", commit_id, new_branch)
    except CommitSubsystemError as exc:
        return {"ok": False, "error": str(exc)}
    turn_seq = out.get("turn_seq")
    fork_orchestration(root, source_branch, new_branch, turn_seq)
    try:
        mpath = get_manifest_path(root)
        m = Manifest(**json.loads(Path(mpath).read_text(encoding="utf-8")))
        src_meta = m.branches.get(source_branch)
        m.branches[new_branch] = BranchMetadata(head_event=-1, kind="sandbox", parent=source_branch,
                                                fork_event=(src_meta.head_event if src_meta else -1))
        m.current_branch = new_branch
        atomic_write_json(mpath, m.model_dump())
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": f"manifest update failed: {exc}"}
    return {"ok": True, "branch": new_branch, "commit_id": commit_id, "turn_seq": turn_seq, "souls": out.get("souls")}
