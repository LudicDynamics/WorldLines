"""A character acting on its own between chats — the foreground tick (10-16: 「有了角色编排就能做角色自由行动(tick):
暂时没有后台,tick 在前台打开时跑」). No server loop: the phone (chat.html) asks while it is open and visible, and once
when a thread is opened (catching up on the time away: one tick, never one per missed interval).

Who ticks: a character the player owns — the library's own, or one gained — whose graph has a ``tick`` node reached by
a ``{tick: …}`` edge (core/soul_orchestration), and whose switch the player turned on. **Off by default** (it spends the
player's credits). A character only tried out (standalone, not gained) never ticks: its folder is the template's.

One tick = one model call: its own documents · its simple world (core/soul_ambient: the routine row for this time of
day) · the last few messages · its last few doings → ``{"did", "mood", "message"}``. What lands, only in its own memory
(the soul agent's write area, documents/spec/soul §3.7): a line in ``trajectory/action_log.md`` and an event in
``short-term-memo/recent_events.json`` (``by: "soul.tick"``); and, at most ``proactive_daily`` a day, a message to the
player in the thread (``origin: "tick"``) — the phone shows it unread.

What starts it (the graph's edges into the tick node): ``{tick: …}`` = the clock, every ``interval_min`` while the phone is
open; ``{idle: <minutes>}`` alone = once per quiet stretch, when the player has written nothing for that long. The node's
fields set ``interval_min`` · ``daily_max`` · ``proactive_daily`` · ``prompt`` (empty = :data:`PROMPT`). A ``reflect`` node
with ``every`` ≥ 1 folds short-term memory into long-term after that many ticks (:func:`reflect`, one cheap call).

    settings + state: ~/.worldlines/player-data/<player>/ticks.json
      {"souls": {"<tpl>/<sid>": {"on": bool, "last_at": <epoch>, "day": "YYYY-MM-DD", "count": n, "sent": n}}}
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from neonrp.core.soul_orchestration import NODE_KINDS as _KINDS

# the tick node's fields (interval_min · daily_max · proactive_daily · prompt) — these are their defaults; the graph's node wins
INTERVAL_MIN = int(_KINDS["tick"]["params"]["interval_min"])     # wall-clock minutes between two ticks of one character
DAILY_MAX = int(_KINDS["tick"]["params"]["daily_max"])           # ticks a character gets a day
PROACTIVE_DAILY = int(_KINDS["tick"]["params"]["proactive_daily"])  # messages a character may send the player a day on its own
_LOCK = threading.Lock()

PROMPT = """You are {name}. Between conversations with the player you go on living your own small life.
It is {slot} ({clock}). Your simple world, your routine for this time of day, the people you know and your own documents follow.
Decide ONE small, ordinary thing you do now, in character. Answer with ONE JSON object, nothing else:
{"did": "<one sentence, first person, what you did>", "mood": "<one or two words>", "message": "<a short message to the player, or empty>"}
Write every text in the language "{lang}". Send a message only when you would really text them now (most of the time leave it empty).
Never invent plot, secrets or other people's actions; never contradict your documents."""

REFLECT_PROMPT = """You are {name}, looking back over the last while. Below are your recent events (short-term memory) and what you
already keep in long-term memory. Write the few things worth remembering for long — what changed, what you feel about the
player and the people around you, what you decided. Answer with ONE JSON object, nothing else:
{"keep": ["<one line, first person>", "..."]}
At most 5 lines, in the language "{lang}". Never invent anything that is not in the events; never repeat what you already keep."""


def _fill(tpl: str, **kw: Any) -> str:
    """{name} / {slot} / {clock} / {lang} filled in; every other brace (the JSON shape) left as written."""
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return tpl


def _key(c: dict[str, Any]) -> str:
    return f"{c['tpl']}/{c['sid']}"


def _path() -> Path:
    from neonrp.core.soul_chat import _player_dir

    return _player_dir() / "ticks.json"


def _load() -> dict[str, Any]:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return d if isinstance(d, dict) and isinstance(d.get("souls"), dict) else {"souls": {}}


def _save(d: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _graph(c: dict[str, Any]) -> dict[str, Any]:
    from neonrp.core.soul_chat import graph_of

    return graph_of(c)


def tick_node(c: dict[str, Any], g: dict[str, Any] | None = None) -> dict[str, Any]:
    """The graph's tick node: the target of a ``{tick: …}`` or ``{idle: <minutes>}`` edge, else any node of kind ``tick``;
    {} = it does not tick. ``trigger``: clock (a tick edge, or no edge: every interval_min) · idle (only idle edges: when
    the player has said nothing for ``idle_min``)."""
    g = _graph(c) if g is None else g
    nodes = g.get("nodes") or {}
    into = [e for e in g.get("edges") or [] if isinstance(e, dict) and (nodes.get(str(e.get("to"))) or {}).get("kind") == "tick"
            and isinstance(e.get("on"), dict) and ("tick" in e["on"] or "idle" in e["on"])]
    nid = str(into[0]["to"]) if into else next((k for k, v in nodes.items() if (v or {}).get("kind") == "tick"), "")
    if not nid:
        return {}
    from neonrp.core.soul_orchestration import IDLE_RANGE, node_params

    mine = [e["on"] for e in into if str(e.get("to")) == nid]
    idle = [v for o in mine for v in [o.get("idle")] if isinstance(v, int) and not isinstance(v, bool) and IDLE_RANGE[0] <= v <= IDLE_RANGE[1]]
    clock = any("tick" in o for o in mine) or not idle
    return {"id": nid, **nodes[nid], **node_params(nodes[nid], "tick"), "trigger": "clock" if clock else "idle", "idle_min": min(idle) if idle else None}


def reflect_node(g: dict[str, Any]) -> dict[str, Any]:
    """The graph's reflect node with its parameters ({} = none); ``every`` 0 = off (the default)."""
    from neonrp.core.soul_orchestration import node_params

    nodes = g.get("nodes") or {}
    nid = next((k for k, v in nodes.items() if (v or {}).get("kind") == "reflect"), "")
    return {"id": nid, **nodes[nid], **node_params(nodes[nid], "reflect")} if nid else {}


def _ts(at: Any) -> float | None:
    try:
        from datetime import datetime

        return datetime.strptime(str(at), "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except (TypeError, ValueError):
        return None


def _last_heard(c: dict[str, Any]) -> float | None:
    """When the player last wrote to it (epoch), None = never."""
    from neonrp.core.soul_chat import read_thread

    return next((t for m in reversed(read_thread(c["tpl"], c["sid"])) if m.get("from") == "me" for t in [_ts(m.get("at"))] if t), None)


def status(c: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    """{can, why, on, due, wait_s, today, sent_today, interval_min, daily_max, proactive_daily, trigger, idle_min} —
    ``why``: trial · locked · no_tick_node · off · daily_max · wait · idle_wait (the player wrote less than idle_min ago)
    · idle_done (already ticked in this quiet stretch: waits for the player's next message)."""
    now = time.time() if now is None else now
    st = (_load()["souls"].get(_key(c)) or {})
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    count = int(st.get("count") or 0) if st.get("day") == day else 0
    sent = int(st.get("sent") or 0) if st.get("day") == day else 0
    owned = c["access"] in ("library", "obtained")
    node = tick_node(c) if owned else {}
    k = node or {"interval_min": INTERVAL_MIN, "daily_max": DAILY_MAX, "proactive_daily": PROACTIVE_DAILY, "trigger": "clock", "idle_min": None}
    out = {"on": bool(st.get("on")), "today": count, "sent_today": sent, "last_at": st.get("last_at"), "interval_min": k["interval_min"],
           "daily_max": k["daily_max"], "proactive_daily": k["proactive_daily"], "trigger": k["trigger"], "idle_min": k["idle_min"]}
    why = ("trial" if c["access"] == "standalone" else "locked") if not owned else "no_tick_node" if not node else "off" if not out["on"] \
        else "daily_max" if count >= k["daily_max"] else ""
    wait = max(0, int((float(st.get("last_at") or 0) + k["interval_min"] * 60) - now)) if not why else 0
    if not why and wait:
        why = "wait"
    if not why and k["trigger"] == "idle":
        heard = _last_heard(c)
        if heard is not None and now - heard < k["idle_min"] * 60:
            why, wait = "idle_wait", int(heard + k["idle_min"] * 60 - now)
        elif st.get("last_at") and (heard is None or float(st["last_at"]) >= heard):
            why = "idle_done"
    return {**out, "can": owned and bool(node), "why": why, "due": not why, "wait_s": wait}


def set_on(c: dict[str, Any], on: bool) -> dict[str, Any]:
    with _LOCK:
        d = _load()
        d["souls"].setdefault(_key(c), {})["on"] = bool(on)
        _save(d)
    return status(c)


def _slot(now: float) -> tuple[str, str]:
    h = time.localtime(now).tm_hour
    return ("morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 17 else "evening" if 17 <= h < 22 else "night"), time.strftime("%H:%M", time.localtime(now))


def _tail(p: Path, n: int) -> str:
    try:
        return "\n".join(p.read_text(encoding="utf-8").splitlines()[-n:])
    except OSError:
        return ""


_RUNNING: set[str] = set()  # characters whose tick is under way (the tick and what a plugin runs after it, 10-21)


def run(c: dict[str, Any], *, lang: str | None = None, adapter: Any = None, catchup: bool = False, now: float | None = None,
        force: bool = False, did: str | None = None) -> dict[str, Any]:
    """One tick if it is due; ``{ran: false, why}`` otherwise. A model failure lands nothing and is not counted.
    One at a time per character (``why: running`` while hers is under way, a plugin's step after it included).
    ``force`` = a plugin's own schedule decided it (a catch-up, a chat that decided to go): the clock is not asked, the
    character must still be the player's own. ``did`` = what she does is already known (no model call for it).
    A plugin may give the context instead of the simple world (``tick_context``) and, claiming the message
    (``tick_owns_message``), send it itself after its step (``soul_ticked`` → ``message``: text or {text, attach})."""
    key = _key(c)
    with _LOCK:
        if key in _RUNNING:
            return {"ran": False, "why": "running"}
        _RUNNING.add(key)
    try:
        return _run(c, lang=lang, adapter=adapter, catchup=catchup, now=now, force=force, did=did)
    finally:
        with _LOCK:
            _RUNNING.discard(key)


def _run(c: dict[str, Any], *, lang: str | None, adapter: Any, catchup: bool, now: float | None, force: bool, did: str | None) -> dict[str, Any]:
    from neonrp.core import node_kinds, soul_ambient, soul_chat as C
    from neonrp.core.llm import Message

    now = time.time() if now is None else now
    s = status(c, now)
    if force and c["access"] not in ("library", "obtained"):
        return {"ran": False, "why": s["why"], "status": s}
    if not force and not s["due"]:
        return {"ran": False, "why": s["why"], "status": s}
    lg = C._lang(lang, c["lang"])
    name = C._name(c["sj"], lg)
    slot, clock = _slot(now)
    world = soul_ambient.read(c, lg) or {}
    row = next((r for r in world.get("routine") or [] if r.get("at") == slot), {})
    place = next((p for p in world.get("places") or [] if p.get("id") == row.get("place")), {})
    folder = Path(c["folder"])
    hist = C.read_thread(c["tpl"], c["sid"])[-6:]
    where = "".join(str(x) for x in node_kinds.call_all("tick_context", c, lg))  # a plugin: where she is in her world now
    ctx = "\n\n".join(x for x in (
        f"## simple world\n{json.dumps({k: world.get(k) for k in ('setting', 'places', 'people')}, ensure_ascii=False)}" if world and not where else "",
        where or f"## now\n{slot} {clock} · routine: {json.dumps(row, ensure_ascii=False)} · place: {json.dumps(place, ensure_ascii=False)}",
        "## while the player was away (catching up: what you did meanwhile)" if catchup else "",
        f"## your last doings\n{_tail(folder / 'trajectory' / 'action_log.md', 5)}",
        "## the last messages\n" + "\n".join(f"{'player' if m.get('from') == 'me' else name}: {m.get('text') or m.get('sticker')}" for m in hist),
        f"## your documents\n{C._docs(folder)}") if x)
    system = _fill(str(tick_node(c).get("prompt") or "").strip() or PROMPT, name=name, slot=slot, clock=clock, lang=lg)
    system += "".join(str(x) for x in node_kinds.call_all("tick_system", c, lg))  # a plugin's own rule for a tick (10-19)
    owns = any(node_kinds.call_all("tick_owns_message", c))  # a plugin sends the message itself, after its step
    if did:  # what she does is already known (a plugin's: a chat that decided to go)
        did, d = str(did).strip()[:240], {}
    else:
        try:
            out = (adapter or C._adapter()).chat([Message(role="system", content=system), Message(role="user", content=ctx)])
        except Exception as exc:  # noqa: BLE001
            return {"ran": False, "why": "model", "error": str(exc)[:300], "status": s}
        if getattr(out, "error", None):
            return {"ran": False, "why": "model", "error": str(out.error)[:300], "status": s}
        raw = str(getattr(getattr(out, "message", None), "content", None) or "")
        try:
            from neonrp.core.json_repair import loads_repaired

            d = loads_repaired(raw[raw.find("{"): raw.rfind("}") + 1])
        except Exception:  # noqa: BLE001
            d = None
        did = str((d or {}).get("did") or "").strip()[:240] if isinstance(d, dict) else ""
        if not did:
            return {"ran": False, "why": "model", "error": "no doing in the answer", "status": s}
    mood = str(d.get("mood") or "").strip()[:40]
    msg = "" if owns else str(d.get("message") or "").strip()[:400]
    at = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now))
    (folder / "trajectory").mkdir(parents=True, exist_ok=True)
    with (folder / "trajectory" / "action_log.md").open("a", encoding="utf-8") as fh:
        fh.write(f"- [tick {at[:16].replace('T', ' ')} · {slot}{' · ' + str(place.get('name')) if place.get('name') else ''}] {did}\n")
    ev_p = folder / "short-term-memo" / "recent_events.json"
    try:
        ev = json.loads(ev_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ev = {}
    ev = ev if isinstance(ev, dict) else {}
    events = [e for e in ev.get("events") or [] if isinstance(e, dict)] + [{"turn": None, "event": did, "my_reaction": mood, "by": "soul.tick", "at": at}]
    ev_p.parent.mkdir(parents=True, exist_ok=True)
    ev_p.write_text(json.dumps({**ev, "events": events[-40:]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    sent = None
    with _LOCK:
        db = _load()
        st = db["souls"].setdefault(_key(c), {})
        if st.get("day") != day:
            st.update(day=day, count=0, sent=0)
        st["count"] = int(st.get("count") or 0) + 1
        st["last_at"] = now
        st["since_reflect"] = int(st.get("since_reflect") or 0) + 1
        if msg and int(st.get("sent") or 0) < int(s["proactive_daily"]):
            st["sent"] = int(st.get("sent") or 0) + 1
            sent = C._append(c["tpl"], c["sid"], [{"from": "soul", "kind": "text", "text": msg, "origin": "tick"}])[0]
        since = st["since_reflect"]
        _save(db)
    out = {"ran": True, "did": did, "mood": mood, "message": sent}
    rn = reflect_node(_graph(c))
    if rn and rn["every"] and since >= rn["every"]:
        out["reflected"] = reflect(c, lang=lg, adapter=adapter, now=now, node=rn)
    for r in node_kinds.call_all("soul_ticked", c, dict(out), adapter=adapter, lang=lg):  # a plugin's step after the tick (10-18)
        if isinstance(r, dict):
            m = r.pop("message", None)
            out.update(r)
            if owns and m:  # the plugin's message, after its step (it may carry what came of it)
                rec = {"from": "soul", "kind": "text", "text": str(m.get("text") if isinstance(m, dict) else m)[:400], "origin": "tick",
                       **({"attach": m["attach"]} if isinstance(m, dict) and m.get("attach") else {})}
                with _LOCK:
                    db = _load()
                    st = db["souls"].setdefault(_key(c), {})
                    st["sent"] = int(st.get("sent") or 0) + 1
                    out["message"] = C._append(c["tpl"], c["sid"], [rec])[0]
                    _save(db)
    return {**out, "status": status(c, now)}


def reflect(c: dict[str, Any], *, lang: str | None = None, adapter: Any = None, now: float | None = None,
            node: dict[str, Any] | None = None) -> dict[str, Any]:
    """The reflect node: one cheap model call folds short-term memory into long-term — a few lines appended to
    ``long-term-memo/reflections.md``; ``short-term-memo/recent_events.json`` keeps only its last ``keep`` events.
    Runs after a tick once ``every`` ticks went by (core/soul_orchestration ``reflect`` params; every 0 = off).
    A model failure folds nothing (the counter stays, the next tick tries again)."""
    from neonrp.core import soul_chat as C
    from neonrp.core.llm import Message

    now = time.time() if now is None else now
    rn = node if node is not None else reflect_node(_graph(c))
    if not rn:
        return {"ran": False, "why": "no_reflect_node"}
    lg = C._lang(lang, c["lang"])
    folder = Path(c["folder"])
    ev_p = folder / "short-term-memo" / "recent_events.json"
    try:
        ev = json.loads(ev_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ev = {}
    ev = ev if isinstance(ev, dict) else {}
    events = [e for e in ev.get("events") or [] if isinstance(e, dict)]
    if not events:
        return {"ran": False, "why": "nothing_to_fold"}
    lt_p = folder / "long-term-memo" / "reflections.md"
    ctx = "\n\n".join((
        "## recent events (short-term memory)\n" + "\n".join(f"- {e.get('event')}{' (' + str(e['my_reaction']) + ')' if e.get('my_reaction') else ''}" for e in events),
        f"## what you already keep\n{_tail(lt_p, 20) or '—'}"))
    ad = adapter or C._adapter()
    if hasattr(ad, "max_tokens"):
        try:
            ad.max_tokens = min(int(ad.max_tokens or 400), 400)  # a few lines; a cheap call
        except (TypeError, ValueError):
            pass
    try:
        out = ad.chat([Message(role="system", content=_fill(REFLECT_PROMPT, name=C._name(c["sj"], lg), lang=lg)), Message(role="user", content=ctx)])
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "why": "model", "error": str(exc)[:300]}
    if getattr(out, "error", None):
        return {"ran": False, "why": "model", "error": str(out.error)[:300]}
    raw = str(getattr(getattr(out, "message", None), "content", None) or "")
    try:
        from neonrp.core.json_repair import loads_repaired

        d = loads_repaired(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception:  # noqa: BLE001
        d = None
    keep = [str(x).strip()[:240] for x in ((d or {}).get("keep") or [] if isinstance(d, dict) else []) if str(x).strip()][:5]
    if not keep:
        return {"ran": False, "why": "model", "error": "nothing to keep in the answer"}
    at = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
    lt_p.parent.mkdir(parents=True, exist_ok=True)
    with lt_p.open("a", encoding="utf-8") as fh:
        fh.write("".join(f"- [reflect {at}] {x}\n" for x in keep))
    ev_p.write_text(json.dumps({**ev, "events": events[-int(rn["keep"]):]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with _LOCK:
        db = _load()
        st = db["souls"].setdefault(_key(c), {})
        st["since_reflect"] = 0
        st["reflected_at"] = now
        _save(db)
    return {"ran": True, "kept": keep, "folded": max(0, len(events) - int(rn["keep"]))}
