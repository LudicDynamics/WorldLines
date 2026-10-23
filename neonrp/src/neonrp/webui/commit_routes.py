"""The run's world lines over HTTP — the commit DAG the engine already keeps (core/commit_store.py), drawn by the UI.

    GET /api/v1/play/engine/commits
        {branch, head, branches: {name: {tip, kind, parent}}, nodes: [{id, parent, turn_seq, branch, label}]}

A node is one landed turn (a world commit). ``parent`` links make the graph; a rollback (POST /rollback)
forks a sandbox branch at that commit, so branches appear as the player tries another line. Labels are
the player's line for that turn, read from each branch's orchestration traces. Capped at MAX_NODES newest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_ROUTE = "/api/v1/play/engine/commits"
MAX_NODES = 400


def _read(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def commit_graph(root: Path) -> dict[str, Any]:
    cr = root / ".neonrp" / "commits"
    man = _read(root / ".neonrp" / "manifest.json")
    current = str(man.get("current_branch") or "main")
    nodes: dict[str, dict[str, Any]] = {}
    for f in (cr / "worlds").glob("*.json") if (cr / "worlds").is_dir() else []:
        d = _read(f)
        cid = str(d.get("world_commit_id") or f.stem)
        nodes[cid] = {"id": cid, "parent": d.get("parent"), "turn_seq": d.get("turn_seq"), "branch": d.get("branch") or "main",
                      "label": "", "mtime": f.stat().st_mtime}
    tips: dict[str, str] = {}
    refs = cr / "refs"
    if refs.is_dir():
        for wid_dir in refs.iterdir():
            head = wid_dir / "HEAD"
            if head.is_file():
                tips.setdefault("main", head.read_text(encoding="utf-8").strip())
            b = wid_dir / "branches"
            if b.is_dir():
                for r in b.iterdir():
                    if r.is_file():
                        tips[r.name] = r.read_text(encoding="utf-8").strip()
    # labels = the player's line, per branch's traces (a forked branch carries its history up to the fork)
    from neonrp.core.orchestration_trace import read_turn_traces
    branches: dict[str, dict[str, Any]] = {}
    for name, meta in (man.get("branches") or {}).items():
        branches[name] = {"tip": tips.get(name), "kind": (meta or {}).get("kind", "main"), "parent": (meta or {}).get("parent")}
        for t in read_turn_traces(root, name):
            cid = (t.get("land") or {}).get("commit_id")
            if cid in nodes and not nodes[cid]["label"]:
                nodes[cid]["label"] = ((t.get("player") or {}).get("input") or "").strip().split("\n")[0][:80]
    for name, tip in tips.items():
        branches.setdefault(name, {"tip": tip, "kind": "main" if name == "main" else "sandbox", "parent": None})
    head = branches.get(current, {}).get("tip")
    rows = sorted(nodes.values(), key=lambda n: (n["turn_seq"] if isinstance(n["turn_seq"], int) else -1, n["mtime"]))[-MAX_NODES:]
    for n in rows:
        n.pop("mtime", None)
    return {"branch": current, "head": head, "branches": branches, "nodes": rows}


class CommitRoutes:
    server: Any
    path: str

    def _commit_route_get(self, rt: Any) -> bool:
        if urlparse(self.path).path.rstrip("/") != _ROUTE:
            return False
        if rt is None:
            self.send_error(409, "no play session")
            return True
        self._send_json(commit_graph(rt.root))
        return True
