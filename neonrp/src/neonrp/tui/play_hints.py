"""The play hints the standard front end shows, in the TUI (10-23): `/` lists the sheet's skills with their value and line
next to the commands, `/skill ` the people, things and places to use it on, `@` the people here, `#` (inside a line —
a line that starts with `#` talks to the room) the places and things; a quick bar above the input; the sheet on the
/status player tab; the dice card's why / for. Everything reads the engine's own menu (core/play_menu.catalog, the one
behind GET /api/v1/play/engine/actions) — nothing a world declares twice.

A skill whose name is also one of our commands (or a world action) completes to the engine's marker ``[skill name]`` so
it still reaches the engine; ours keep the slash.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from rich.text import Text

from neonrp.tui.i18n import get_message

MUTED, SKILL, PERSON, THING, PLACE = "#9ca3af", "#4ade80", "#7dd3fc", "#fde68a", "#c4b5fd"
# Our commands that act on the run being played — listed right after the world's own actions in play
PLAY_COMMANDS = ("status", "undo", "redo", "save", "load", "who", "lang")

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def menu(root: Path | None, ttl: float = 5.0) -> dict[str, Any]:
    """The engine's play menu for this run (cached ``ttl`` s; :func:`invalidate` after a beat lands). {} without a run."""
    if root is None:
        return {}
    key = str(root)
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    try:
        from neonrp.core.play_menu import catalog

        m = catalog(Path(root))
    except Exception:  # noqa: BLE001 — a world without a sheet / registry: no hints, never an error
        m = {}
    _CACHE[key] = (time.monotonic(), m)
    return m


def invalidate() -> None:
    _CACHE.clear()


def _t(locale: str, key: str, **kw: Any) -> str:
    s = get_message(locale or "zh", key)
    return s.format(**kw) if kw else s


def _esc(s: Any) -> str:
    from rich.markup import escape

    return escape(str(s))


def skill_label(row: dict[str, Any]) -> str:
    return str(row.get("label") or row.get("name") or row.get("key") or "")


def skill_completion(row: dict[str, Any], taken: set[str]) -> str:
    """`/侦查`, or the engine's marker when the name is one of our commands / a world action (it would never reach the
    engine as a slash)."""
    name = skill_label(row)
    if name.casefold() in taken or " " in name and name.split()[0].casefold() in taken:
        return f"[skill {name}]"
    return f"/{name}"


def skill_rows(m: dict[str, Any], prefix: str, taken: set[str], locale: str) -> list[tuple[str, str]]:
    """`/` + what was typed → the sheet's skills (highest first) as (markup, completion)."""
    p = prefix.casefold()
    tag = _t(locale, "hint.skill")
    rows: list[tuple[str, str]] = []
    for r in m.get("skills") or []:
        names = [skill_label(r), str(r.get("name") or ""), str(r.get("key") or "")]
        if p and not any(n.casefold().startswith(p) for n in names if n):
            continue
        val = r.get("value")
        desc = str(r.get("desc") or "")
        line = f"[{SKILL}]/{_esc(skill_label(r))}[/]" + (f" [bold]{_esc(val)}[/]" if val not in (None, "") else "")
        line += f" [dim]- {_esc(desc)} · {tag}[/]" if desc else f" [dim]· {tag}[/]"
        rows.append((line, skill_completion(r, taken)))
    return rows


def skill_typed(m: dict[str, Any], command_text: str) -> tuple[dict[str, Any], str] | None:
    """`/侦查 井` → (the 侦查 row, "井"): the longest skill name the line starts with, then a space."""
    body = command_text.casefold()
    best: tuple[dict[str, Any], str] | None = None
    for r in m.get("skills") or []:
        for n in {skill_label(r), str(r.get("name") or ""), str(r.get("key") or "")}:
            if n and body.startswith(n.casefold() + " ") and (best is None or len(n) > len(skill_label(best[0]))):
                best = (r, command_text[len(n) + 1:])
    return best


def _targets(m: dict[str, Any], locale: str) -> list[tuple[str, str, str]]:
    """(name, colour, tag) for everything a line can point at: people here, things held / here, places."""
    out: list[tuple[str, str, str]] = []
    for p in m.get("people") or []:
        out.append((str(p.get("name") or ""), PERSON, _t(locale, "hint.person")))
    for i in m.get("items") or []:
        out.append((str(i.get("name") or ""), THING, _t(locale, "hint.held" if i.get("held") else "hint.thing_here")))
    for pl in m.get("places") or []:
        tag = "hint.here" if pl.get("here") else "hint.near" if pl.get("near") else "hint.place"
        out.append((str(pl.get("name") or ""), PLACE, _t(locale, tag)))
    return [t for t in out if t[0]]


def target_rows(m: dict[str, Any], head: str, prefix: str, locale: str) -> list[tuple[str, str]]:
    """After `/侦查 `: what to use it on — the completion is the whole line."""
    p = prefix.strip().casefold()
    return [(f"[{SKILL}]{_esc(head)}[/] [{col}]{_esc(n)}[/] [dim]· {tag}[/]", f"{head} {n}")
            for n, col, tag in _targets(m, locale) if not p or n.casefold().startswith(p)]


def token_rows(m: dict[str, Any], value: str, locale: str, *, at_head_people: bool = False) -> list[tuple[str, str]]:
    """The line ends in `@…` / `#…` (inside the line) → the people / the places and things it can name; the completion is
    the line with that name filled in. Names may hold spaces (「@Clara S」→ Clara Shaw)."""
    v = value.replace("\r", "").replace("\n", "")
    if not v or v[-1] in "\r\n":
        return []
    at = max(v.rfind(c) for c in "@＠#＃")
    if at < 0:
        return []
    before, word = v[:at], v[at:]
    if before and not before[-1].isspace():
        return []  # mail@host, issue#3 — not a name
    if word[0] in "#＃" and not before.strip():
        return []  # a line that starts with # talks to the room (core/address)
    if word[0] in "@＠" and not before.strip() and not at_head_people:
        return []
    p = word[1:].casefold()
    if p.endswith((" ", "　")) and not any(n.casefold().startswith(p) for n, _c, _t in _targets(m, locale)):
        return []  # a name finished, the line goes on
    sigil = "@" if word[0] in "@＠" else "#"
    rows: list[tuple[str, str]] = []
    for n, col, tag in _targets(m, locale):
        is_person = col == PERSON
        if (sigil == "@") != is_person or (p and not n.casefold().startswith(p)) or n.casefold() == p:
            continue
        rows.append((f"[{col}]{sigil}{_esc(n)}[/] [dim]· {tag}[/]", f"{before}{sigil}{n}"))
    return rows


def quick(m: dict[str, Any]) -> list[tuple[str, str]]:
    """The quick bar: (label, text to put in the input) — people (@), common skills (/), things held (#)."""
    out = []
    for q in m.get("quick") or []:
        text, label = str(q.get("text") or ""), str(q.get("label") or "")
        if text:
            sig = {"person": "@", "skill": "/", "item": "#"}.get(str(q.get("kind")), "")
            out.append((f"{sig}{label}" if sig and not label.startswith(sig) else label or text, text))
    return out


def sheet_text(m: dict[str, Any], locale: str) -> Text | None:
    """The attributes and skills (value + line) under the player on /status."""
    attrs, skills = m.get("attrs") or [], m.get("skills") or []
    if not attrs and not skills:
        return None
    t = Text()
    if attrs:
        t.append(f"{_t(locale, 'hint.attrs')}\n", style=f"bold {MUTED}")
        t.append("  " + "  ".join(f"{r.get('label') or r.get('key')} {r.get('value')}" for r in attrs) + "\n", style="#e5e7eb")
    if skills:
        t.append(f"{_t(locale, 'hint.skills')}\n", style=f"bold {MUTED}")
        for r in skills:
            t.append(f"  /{skill_label(r)}", style=SKILL)
            if r.get("value") not in (None, ""):
                t.append(f" {r['value']}", style="bold #f8fafc")
            if r.get("desc"):
                t.append(f"  {r['desc']}", style=MUTED)
            t.append("\n")
        t.append(_t(locale, "hint.skills_use"), style=MUTED)
    return t


def dice_detail(ev: dict[str, Any], locale: str) -> Text | None:
    """Under the dice row, as the web's dice card: what was rolled for which skill, why it landed on that tier, what for."""
    total, vs = ev.get("total"), ev.get("vs")
    if total is None:
        return None
    label, reason = str(ev.get("label") or ""), str(ev.get("reason") or "")
    lv = str(ev.get("level") or "")
    if vs is None or ev.get("passed") is None:
        why = _t(locale, "hint.dice.plain", n=total)
    elif lv == "crit" and isinstance(ev.get("crit_max"), (int, float)):
        why = _t(locale, "hint.dice.crit", n=total, m=ev["crit_max"])
    elif lv == "fumble" and isinstance(ev.get("fumble_min"), (int, float)):
        why = _t(locale, "hint.dice.fumble", n=total, m=ev["fumble_min"])
    elif ev.get("under"):
        why = _t(locale, "hint.dice.under" if ev.get("passed") else "hint.dice.over", n=total, v=vs)
    else:
        why = _t(locale, "hint.dice.meet" if ev.get("passed") else "hint.dice.short", n=total, v=vs)
    t = Text("   ")
    if label:
        t.append(f"{label}  ", style=f"bold {SKILL}")
    t.append(f"{_t(locale, 'hint.dice.why')} ", style=MUTED)
    t.append(why, style="#d1d5db")
    if reason and reason != label:
        t.append(f"\n   {_t(locale, 'hint.dice.for')} ", style=MUTED)
        t.append(reason, style="#d1d5db")
    return t
