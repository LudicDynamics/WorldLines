"""One world execution off the player's screen (10-21, TEMPLATE-LAYERS-1019 §2.3, stage B): a character does one thing
in her world, everyone else there takes her own turn elsewhere at the same time, and the world settles it — with the
player away. The same parts the player's own turn uses: the characters elsewhere run S2's away path
(core/turn_runner.away_turn: the fifth characters' orchestration — not a tick, so nothing here starts another world
execution), the world settles through turn_v3.solve_turn(player_present=False). A plugin calls it (the private phone
orchestration, after a subscribed character's tick); nothing here knows a world or a phone.

    run(root, {"iid", "name", "text", "where"?}, away=None | [iid, …], by="tick:<sid>", facts="", inbox_text=None)

Under the run's lock (core/run_lock.try_hold, never waits): busy = ``{"ok": False, "why": "busy"}`` — nothing written,
the caller keeps the action for later. What came of it is a world result (the 「世界卡」 on screens): one line per person
(``kind: act`` the one who acted · ``away`` everyone else) + what changed (the settling's applied ops), appended to
``<data>/meta/world_results.jsonl``; the host's inbox gets one ``<event world_result:<id>>`` (``inbox_text``, else the
narration); each person in it remembers her own line in this run (``by: world_result``, the result's id).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RESULTS = "world_results.jsonl"


def _meta(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(Path(root)) / "meta"


def _turn(root: Path) -> int:
    try:
        rs = json.loads((_meta(root) / "run_state.json").read_text(encoding="utf-8"))
        return int(rs.get("turn_count", 0) or 0)
    except (OSError, ValueError, TypeError):
        return 0


def results(root: Path, last: int = 20) -> list[dict[str, Any]]:
    """The run's latest world results, oldest first."""
    try:
        rows = [json.loads(x) for x in (_meta(root) / RESULTS).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []
    return rows[-last:] if last else rows


def elsewhere(root: Path, actor: str) -> list[str]:
    """Everyone of the run who can take a turn, but the one who acts: its souls, the dead left out."""
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    return [e.id for e in reg.of_class("soul") if e.id != actor and not int(e.props.get("dead") or 0)]


def _remember(root: Path, iid: str, text: str, turn: int, rid: str) -> None:
    from neonrp.core.soul_view import _soul_dir

    sdir = _soul_dir(Path(root), iid)
    if sdir is None or not text:
        return
    p = Path(sdir) / "short-term-memo" / "recent_events.json"
    try:
        memo = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        memo = {}
    memo = memo if isinstance(memo, dict) else {}
    evs = memo.get("events") if isinstance(memo.get("events"), list) else []
    evs.append({"turn": turn, "event": text[:200], "my_reaction": "", "affect": "", "by": "world_result", "result": rid})
    memo["events"] = evs[-40:]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(memo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def run(root: Path, actor: dict[str, Any], *, away: list[str] | None = None, provider: str | None = None, mode: str = "play",
        by: str = "", facts: str = "", inbox_text: str | None = None, locked: bool = False) -> dict[str, Any]:
    """``locked`` = the caller already writes this run (a seam at the start of the player's own turn): no lock taken."""
    from neonrp.core import run_lock

    if locked:
        return _run(Path(root), actor, away=away, provider=provider, mode=mode, by=by, facts=facts, inbox_text=inbox_text)
    with run_lock.try_hold(root) as ok:
        if not ok:
            return {"ok": False, "why": "busy"}
        return _run(Path(root), actor, away=away, provider=provider, mode=mode, by=by, facts=facts, inbox_text=inbox_text)


def _run(root: Path, actor: dict[str, Any], *, away: list[str] | None, provider: str | None, mode: str, by: str, facts: str,
         inbox_text: str | None) -> dict[str, Any]:
    from neonrp import prompts
    from neonrp.core import turn_v3
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.registry import load_registry
    from neonrp.core.turn_runner import away_turn

    iid = str(actor.get("iid") or "")
    cs = prompts.strings("conversation", prompt_lang(root))
    names = elsewhere(root, iid) if away is None else [x for x in away if x != iid]
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(names))), thread_name_prefix="neonrp-world-exec") as ex:
        outs = list(ex.map(lambda x: (x, away_turn(root, x, provider=provider, mode=mode, cs=cs)), names)) if names else []
    aways = [{"iid": x, "name": o.get("name") or x, "text": str(o.get("text") or ""), "move_to": o.get("proposed_move")}
             for x, o in outs if o.get("ok")]
    where = str(actor.get("where") or "")
    ops = ([{"op": "move_to", "who": iid, "to": where, "_from": "soul"}] if where else []) + [
        {"op": "move_to", "who": a["iid"], "to": a["move_to"], "_from": "soul"} for a in aways if a.get("move_to")]
    turn = _turn(root)
    res = turn_v3.solve_turn(root, user_text="", provider=provider, turn=turn,
                             soul_reports=[{"iid": iid, "name": actor.get("name") or iid,
                                            "text": str(actor.get("text") or "") + (f" @ {where}" if where else ""),
                                            **({"proposed_move": where} if where else {})}],
                             plan_facts=facts, soul_ops=ops, player_present=False)
    narration = " ".join(str(res.get("narration") or "").split())
    applied = list(getattr(res.get("apply"), "applied", None) or [])
    from neonrp.core.beat_display import away_items

    reg = load_registry(root)
    me = away_items(reg, [{"iid": iid, "name": actor.get("name") or iid, "text": str(actor.get("text") or "")}])
    rid = f"wr-{turn}-{uuid.uuid4().hex[:8]}"
    card = {"id": rid, "run": root.name, "turn": turn, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "by": by or f"act:{iid}",
            "items": [{**x, "kind": "act"} for x in me] + [{**x, "kind": "away"} for x in away_items(reg, aways)],
            "changes": [{k: v for k, v in o.items() if not str(k).startswith("_")} for o in applied if isinstance(o, dict)],
            "narration": narration[:600]}
    m = _meta(root)
    m.mkdir(parents=True, exist_ok=True)
    with (m / RESULTS).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(card, ensure_ascii=False) + "\n")
    from neonrp.core.triggers import _INBOX

    try:
        inbox = json.loads((m / _INBOX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        inbox = {}
    inbox = inbox if isinstance(inbox, dict) else {}
    items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
    items.append({"turn": turn, "trigger": "world_result", "kind": "event", "id": f"world_result:{rid}",
                  "text": (inbox_text if inbox_text is not None else narration)[:400]})
    inbox["items"] = items[-30:]
    (m / _INBOX).write_text(json.dumps(inbox, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for it in card["items"]:
        _remember(root, it["iid"], it["text"], turn, rid)
    return {"ok": True, "card": card, "narration": narration, "applied": len(applied), "away": aways}
