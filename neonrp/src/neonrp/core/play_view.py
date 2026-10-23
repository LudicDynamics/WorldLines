"""What the play side may hand a page, and what only the debug side may (10-15, the standard front end §5.14 follow-up).

The turn record, the hello, the schema and the live stream were written for the test bench: they carry the host's
working — soul personas and rules, relationship truths, plot triggers with their narration, every soul's turn (also the
ones far from the player), the planning board's hidden notes, the bus messages, the model's thinking. A page a player
uses gets the player's view of each; the full one is the debug read:

    play (any page)                       debug (``debug_enabled()``: the local engine; off in the browser build)
    /trace?i=N            trace()         /api/v1/play/engine/debug/trace?i=N
    /state  (+ /events hello, positions)  /api/v1/play/engine/debug/state
    /api/v1/play/schema   schema()        /api/v1/play/engine/debug/schema
    entities?cls=<person> core/people     /api/v1/play/engine/debug/entities?cls=…
    /events               sse()           /events?debug=1

``NEONRP_DEBUG_ROUTES=1|0`` decides; unset = on for a local engine, off under Pyodide (the Hub's browser engine) — a
shipped app that embeds the local engine (iOS) sets it to 0.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

APPLY_KEYS = ("turn", "beat", "narration_plain", "mentions", "options", "panels", "applied", "created", "gained", "lost",
              "joined", "left", "stages", "shows", "discovered", "settled", "ended", "action", "mode",
              "achievements", "milestones", "audio")
TOOL_KEYS = ("request", "text", "ok", "async", "why", "rolls", "total", "vs", "passed", "under", "level", "label", "reason", "dice",
             "show", "panel")
JUDGMENT_KEYS = ("attitude", "thought", "follow", "stay", "want_move", "move_to")
SOUL_AFTER_KEYS = ("iid", "name", "trust_delta", "intention", "mood")


def debug_enabled() -> bool:
    v = os.environ.get("NEONRP_DEBUG_ROUTES", "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    return sys.platform != "emscripten"


def _present(ap: dict[str, Any]) -> set[str]:
    """The characters this beat had on stage: whoever the beat judged (their turn ran where the player is)."""
    return {str(r.get("iid")) for r in ap.get("reports") or [] if isinstance(r, dict) and r.get("iid")}


def trace(t: dict[str, Any]) -> dict[str, Any]:
    """A turn record as a player may read it: what was said and shown, what landed, the dice; not the host's work."""
    ap = t.get("apply") if isinstance(t.get("apply"), dict) else {}
    here = _present(ap)
    out_ap: dict[str, Any] = {k: ap[k] for k in APPLY_KEYS if k in ap}
    out_ap["tool_returns"] = [{k: x[k] for k in TOOL_KEYS if k in x} for x in ap.get("tool_returns") or [] if isinstance(x, dict)]
    out_ap["reports"] = [{"iid": r.get("iid"), "name": r.get("name"), "kind": r.get("kind"), "text": r.get("text"),
                          "proposed_move": r.get("proposed_move"),
                          "judgment": {k: (r.get("judgment") or {}).get(k) for k in JUDGMENT_KEYS if (r.get("judgment") or {}).get(k) is not None}}
                         for r in ap.get("reports") or [] if isinstance(r, dict)]
    out_ap["souls"] = [{k: s[k] for k in SOUL_AFTER_KEYS if k in s} for s in ap.get("souls") or []
                       if isinstance(s, dict) and str(s.get("iid") or "") in here]
    if not ap.get("narration_plain") and ap.get("proposals"):  # an old record: the prose only in the last proposal
        last = (ap.get("proposals") or [])[-1]
        if isinstance(last, dict) and last.get("narration"):
            out_ap["proposals"] = [{"narration": last["narration"]}]
    souls = [{k: s[k] for k in ("sid", "instance_id", "speech") if k in s} for s in t.get("souls") or []
             if isinstance(s, dict) and str(s.get("instance_id") or "") in here]
    player = t.get("player") if isinstance(t.get("player"), dict) else {}
    return {"schema_version": t.get("schema_version"), "turn_seq": t.get("turn_seq"), "ts": t.get("ts"),
            "player": {"input": player.get("input")}, "world_location": t.get("world_location"), "souls": souls, "apply": out_ap,
            "land": {k: v for k, v in (t.get("land") or {}).items() if k in ("ok", "commit_id")} if isinstance(t.get("land"), dict) else None}


def known_souls(root: Path) -> set[str]:
    """Instance ids of the souls the player knows: standing with them, or met (core/people)."""
    from neonrp.core import people

    try:
        return {str(r["id"]) for r in people.people(root)["people"] if r.get("kind") == "soul"}
    except Exception:  # noqa: BLE001
        return set()


def visible_entries(root: Path, reg: Any = None) -> set[str]:
    """The entries whose names the player may see: places on their map (or been to), the people they know, the things
    they have come across (core/people.seen + what is in view now), what is on them; the world's own levels."""
    from neonrp.core import people
    from neonrp.core.holdings import PLACE_CLASSES
    from neonrp.core.registry import load_registry

    reg = reg if reg is not None else load_registry(root)
    seen = people.seen(root) | people.visible_now(reg)
    try:
        from neonrp.core import worldmap

        tree = worldmap.build_map_tree(root)
        mapped = {a for a, n in tree["nodes"].items() if worldmap._known(n)}
    except Exception:  # noqa: BLE001
        mapped = set()
    knows = known_souls(root)
    out: set[str] = set()
    for e in reg.entries.values():
        if e.id == "player" or e.cls in ("world", "level", "town", "region"):
            out.add(e.id)
        elif e.cls in PLACE_CLASSES:
            if e.id in mapped or e.id in seen:
                out.add(e.id)
        elif e.cls == "soul":
            if e.id in knows:
                out.add(e.id)
        elif e.cls == "npc":
            st = e.props.get("state") if isinstance(e.props.get("state"), dict) else {}
            if st.get("met") or e.id in seen:
                out.add(e.id)
        elif e.id in seen or reg.owner_of(e) == "player":
            out.add(e.id)
    return out


def schema(view: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    """The five tables as a player may read them: no triggers (they are the plot), no variable docs (the host's notes),
    no entries the player has not come across (an undiscovered clue keeps its name to itself)."""
    out = dict(view)
    out["triggers"] = []
    out["variables"] = [{k: v for k, v in row.items() if k != "doc"} for row in view.get("variables") or []]
    if root is not None and isinstance(view.get("entries"), dict):
        vis = visible_entries(root)
        out["entries"] = {cls: [r for r in rows if r.get("id") in vis] for cls, rows in view["entries"].items()}
        out["classes"] = [{**c, "count": len(out["entries"].get(c.get("name"), []))} for c in view.get("classes") or []]
    return out


def sse(event: dict[str, Any], root: Path, known: set[str] | None = None) -> dict[str, Any] | None:
    """One live event for a player's page: the turn record trimmed, the host's thinking dropped, characters the player
    does not know left out. None = do not send."""
    kind = str(event.get("kind") or "")
    if kind == "thinking":
        return None
    if kind == "trace" and isinstance(event.get("trace"), dict):
        return {**event, "trace": trace(event["trace"])}
    if kind in ("hello", "positions", "soul_psyche", "soul_status"):
        known = known if known is not None else known_souls(root)
        if kind == "soul_psyche":
            return event if str(event.get("instance_id") or "") in known else None
        if kind == "soul_status":
            st = event.get("statuses") if isinstance(event.get("statuses"), dict) else {}
            return {**event, "statuses": {k: v for k, v in st.items() if k in known}}
        return {**event, "souls": [s for s in event.get("souls") or [] if str(s.get("instance_id") or "") in known]}
    return event


def safe_sse(event: dict[str, Any], root: Path, known: set[str] | None = None) -> dict[str, Any] | None:
    """:func:`sse` that never raises: a filter that breaks sends only the event's name (never its unfiltered body), and
    the turn that published it goes on (10-15: in the browser engine the filter runs inside the turn's own publish — an
    exception there ended the turn before its record and its turn_done)."""
    try:
        return sse(event, root, known)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("player-view filter failed for %s", event.get("kind") if isinstance(event, dict) else event,
                                            exc_info=True)
        return {"kind": event.get("kind")} if isinstance(event, dict) else None
