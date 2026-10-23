"""One character's context (TODO #3:「点角色名进它的 context,
像 Claude Code team mode:可以替它 RP,或看它的 RP 进度」).

Pure read: everything the TUI's soul-context screen shows comes from here so
a headless caller (tests, the web shell later) gets the same picture —
identity, where it stands, what it remembers, what it did in the last turns
(orchestration trace) and the private thread with the player.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def soul_progress(root: Path, iid: str, *, branch: str = "main", last: int = 8) -> list[dict[str, Any]]:
    """The turns in which this soul was awake, newest last:
    ``{turn_seq, ts, location, reason, speech, tool_calls, player_input}``."""
    from neonrp.core.orchestration_trace import read_turn_traces

    rows: list[dict[str, Any]] = []
    for trace in read_turn_traces(root, branch):
        souls = trace.get("souls") if isinstance(trace.get("souls"), list) else []
        mine = next((s for s in souls if isinstance(s, dict) and s.get("instance_id") == iid), None)
        if mine is None or not mine.get("activated"):
            continue
        player = trace.get("player") if isinstance(trace.get("player"), dict) else {}
        rows.append(
            {
                "turn_seq": trace.get("turn_seq"),
                "ts": trace.get("ts"),
                "location": mine.get("location") or trace.get("world_location"),
                "reason": mine.get("reason") or "",
                "speech": mine.get("speech") or "",
                "tool_calls": mine.get("tool_calls") or 0,
                "player_input": str(player.get("input") or "")[:120],
            }
        )
    return rows[-last:] if last else rows


def build_soul_context(root: Path, token: str, *, branch: str = "main") -> dict[str, Any]:
    """``token`` = name / alias / sid / instance_id (the roster resolves it)."""
    from neonrp.core.light_chat import _display_name, _persona_digest, _soul_memory_digest, _soul_node, read_thread
    from neonrp.core.ontology import _place_view, _resolve_soul, _soul_dir
    from neonrp.core.playthrough import read_playthrough

    root = Path(root)
    tok = str(token or "").strip()
    if not tok:
        return {"ok": False, "error": "empty"}
    pt, ref = _resolve_soul(root, tok)
    if ref is None:
        return {"ok": False, "error": f"unknown: {tok}"}
    sdir = _soul_dir(root, ref.sid, ref.instance_id)
    if not sdir.is_dir():
        return {"ok": False, "error": f"missing folder: {sdir.name}"}
    pt = pt or read_playthrough(root)
    active = set(getattr(pt, "active_souls", ()) or ()) if pt is not None else set()
    state = _read_json(sdir / "run_state.json")
    node = _soul_node(root, sdir)
    place = _place_view(root, node)
    status = state.get("status") if isinstance(state.get("status"), dict) else {}
    thread = []
    try:
        thread = read_thread(root, ref.instance_id, limit=6)
    except Exception:
        thread = []
    # TODO #6:能不能联系到 TA —— 同场直聊,或这个世界有电话/讯息。
    reachable, remote, medium = False, False, None
    try:
        from neonrp.core.light_chat import remote_comms, resolve_reachable_soul

        hit = resolve_reachable_soul(root, ref.instance_id)
        if hit is not None:
            reachable, remote = True, bool(hit[2])
            if remote:
                medium = (remote_comms(root) or {}).get("medium")
    except Exception:
        pass
    return {
        "ok": True,
        "sid": ref.sid,
        "iid": ref.instance_id,
        "name": _display_name(sdir, ref.sid),
        "role": str(getattr(ref, "role", "") or "npc"),
        "on_stage": ref.instance_id in active,
        "location": {"node": node, "name": place.get("name"), "town": place.get("town")},
        "status": {k: status.get(k) for k in ("hp", "max_hp", "mood") if k in status},
        "turn_count": state.get("turn_count"),
        "persona": _persona_digest(sdir)[:700],
        "memory": _soul_memory_digest(sdir),
        "progress": soul_progress(root, ref.instance_id, branch=branch),
        "thread": [
            {"ts": r.get("ts", ""), "role": r.get("role", ""), "text": str(r.get("text", ""))[:300]}
            for r in thread
            if isinstance(r, dict)
        ],
        "reachable": reachable,
        "remote": remote,
        "medium": medium,
        "folder": str(sdir),
    }
