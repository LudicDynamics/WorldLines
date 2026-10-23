"""What the TUI knows about the two beats, fed by the engine's ``engine/beat`` events (core/beat_events, 10-08).

``BeatState`` is plain data — no widgets — so the renderer and the slash commands (``/plan``, ``/dice``, ``/status``) read
the same thing and tests can drive it without an app:

    node            the graph node the world is in (plan · resolve · combat · dungeon · a phase …)
    board / checks  the planning beat's board and agreed checks (the latest plan.beat)
    dice            every die this session rolled, newest last ({turn, request, answer})
    changes         the state changes of the latest resolve ({turn, applied, created, refused})
    settled         the run's settlement once it exits (run.settled)

Colors for the two beats (planning and resolving should read apart at a glance — e.g. green / red).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PLAN_COLOR = "#4ade80"     # planning: green — talk, nothing in the world moves yet
RESOLVE_COLOR = "#f87171"  # resolving: red — the dice fall, the world changes
LAYER_COLOR = "#fbbf24"    # a mode layer (combat / dungeon …)

BEAT_COLORS = {"plan": PLAN_COLOR, "resolve": RESOLVE_COLOR}


NEUTRAL_COLOR = "#9ca3af"
TONE_COLORS = {"plan": PLAN_COLOR, "res": RESOLVE_COLOR}  # the tones a beat declaration may ask for (ui.beats … tone)


def color_of(node: str | None) -> str:
    return BEAT_COLORS.get(str(node or ""), LAYER_COLOR if node else NEUTRAL_COLOR)


def tone_color(tone: str | None) -> str:
    """A declared beat's colour (``ui.beats.kinds.<node>.tone``); an unknown / missing tone is neutral."""
    return TONE_COLORS.get(str(tone or ""), NEUTRAL_COLOR)


@dataclass
class BeatState:
    node: str | None = None
    turn: int | None = None
    board: dict[str, Any] = field(default_factory=dict)
    checks: list[Any] = field(default_factory=list)
    mic: list[Any] = field(default_factory=list)
    dice: list[dict[str, Any]] = field(default_factory=list)
    changes: dict[str, Any] = field(default_factory=dict)
    settled: dict[str, Any] | None = None
    away: dict[str, dict[str, Any]] = field(default_factory=dict)  # name → {iid, name, where, text}: who acted elsewhere this beat
    max_dice: int = 200

    def feed(self, ev: dict[str, Any]) -> str | None:
        """Take one event; returns the node just entered (the renderer draws a beat marker), else None."""
        kind = str(ev.get("kind") or "")
        if ev.get("turn") is not None:
            self.turn = ev.get("turn")
        if kind == "node.enter":
            self.node = str(ev.get("node") or "") or None
            return self.node
        if kind == "plan.beat":
            self.board = dict(ev.get("board") or {})
            self.checks = list(ev.get("checks") or [])
            self.mic = list(ev.get("mic") or [])
        elif kind == "resolve.beat":
            self.checks = []  # the agreed checks were rolled; the next talk starts a new board
        elif kind == "dice":
            self.dice.append({k: v for k, v in ev.items() if k != "kind"})  # the numbers too: /status dice redraws the box
            del self.dice[: -self.max_dice]
        elif kind == "state.changed":
            self.changes = {k: ev.get(k) for k in ("turn", "applied", "created", "refused")}
        elif kind == "run.settled":
            self.settled = {k: v for k, v in ev.items() if k != "kind"}
        elif kind == "away":
            self.away = {str(a.get("name")): dict(a) for a in ev.get("items") or [] if isinstance(a, dict) and a.get("name")}
        return None


# ── what a resolve changed / called, as one compact row each (10-08: tags, not Markdown) ─────────────────────────────

CHIP_UP, CHIP_DOWN, CHIP_NEW, CHIP_GONE, CHIP_MOVE, CHIP_EDIT, CHIP_NO = (
    "#4ade80", "#f87171", "#60a5fa", "#9ca3af", "#fbbf24", "#c084fc", "#6b7280")
SYNC_COLOR, ASYNC_COLOR = "#38bdf8", "#a78bfa"


def _short(s: Any, n: int = 28) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _place(to: Any) -> str:
    return str(to or "").rsplit("/", 1)[-1]


def change_text(ev: dict[str, Any]) -> Any:
    """state.changed → one row of tags: ``hp 24→23`` · ``＋ 小治疗药水`` · ``－ 罩灯`` · ``➜ shop_general`` · ``✎ Q001 detail`` ·
    ``✕ move_to`` (refused). Engine housekeeping (the clock ticking) stays out; background units are marked ⟳."""
    from rich.text import Text

    t = Text()

    def chip(label: str, color: str, *, strike: bool = False) -> None:
        if t.plain:
            t.append("  ")
        t.append(label, style=f"{color}{' strike' if strike else ''}")

    created_names = {str(c.get("id")): c.get("name") for c in ev.get("created") or [] if isinstance(c, dict)}
    for a in ev.get("applied") or []:
        if not isinstance(a, dict):
            continue
        op, tick = str(a.get("op") or ""), "⟳" if str(a.get("by") or "").startswith("tick:") else ""
        if op in ("set", "add"):
            var = str(a.get("var") or "")
            if var.startswith("time."):
                continue
            fr, to = a.get("from"), a.get("to")
            up = isinstance(fr, (int, float)) and isinstance(to, (int, float)) and to > fr
            down = isinstance(fr, (int, float)) and isinstance(to, (int, float)) and to < fr
            chip(f"{tick}{var.rsplit('.', 1)[-1] if var.startswith('player.') else var} {_short(fr, 10)}→{_short(to, 10)}",
                 CHIP_UP if up else CHIP_DOWN if down else CHIP_EDIT)
        elif op == "new":
            chip(f"{tick}＋ {_short(created_names.get(str(a.get('id'))) or a.get('id'))}", CHIP_NEW)
        elif op == "remove":
            chip(f"{tick}－ {_short(a.get('name') or a.get('who'))}", CHIP_GONE)
        elif op == "move_to":
            who = str(a.get("who") or "")
            chip(f"{tick}➜ {'' if who == 'player' else _short(who, 12) + ' '}{_place(a.get('to'))}", CHIP_MOVE)
        elif op == "patch":
            keys = ",".join(list((a.get("props") or {}).keys())[:3])
            chip(f"{tick}✎ {_short(_place(a.get('who')), 14)} {keys}", CHIP_EDIT)
        elif op == "write":
            chip(f"{tick}📝 {_short(_place(a.get('path')), 22)}", CHIP_EDIT)
        elif op == "event":
            chip(f"⚠ {_short(a.get('who'), 14)} {a.get('event')}", CHIP_DOWN)
    for r in ev.get("refused") or []:
        o = r.get("op") if isinstance(r, dict) else None
        name = (o.get("op") if isinstance(o, dict) else o) or "?"
        chip(f"✕ {name}", CHIP_NO, strike=True)
    return t if t.plain else None


def write_down_text(ev: dict[str, Any], locale: Any) -> Any:
    """The background write-down's news (core/write_down_async): pending · corrected · same · cut · timeout · failed."""
    from rich.text import Text

    from neonrp.tui.i18n import get_message

    state = str(ev.get("kind") or "").rsplit(".", 1)[-1]
    mark, color = {"pending": ("⋯", ASYNC_COLOR), "corrected": ("✎", CHIP_EDIT), "same": ("✓", CHIP_NO)}.get(state, ("·", CHIP_NO))
    t = Text()
    t.append(f"{mark} ", style=f"bold {color}")
    key = "wd.cut_busy" if state == "cut" and ev.get("why") == "busy" else f"wd.{state}"  # busy: the player did not move
    t.append(get_message(locale, key), style=color)
    return t


def tool_text(ev: dict[str, Any]) -> Any:
    """A tool the beat called: ``⇄ referee …`` (sync — the prose waited for it) / ``⇢ map`` (async — runs beside it)."""
    from rich.text import Text

    asyn = bool(ev.get("async"))
    req = str(ev.get("request") or "")
    t = Text()
    t.append("⇢ " if asyn else "⇄ ", style=f"bold {ASYNC_COLOR if asyn else SYNC_COLOR}")
    t.append(_short(req, 40), style=ASYNC_COLOR if asyn else SYNC_COLOR)
    if ev.get("ok") is False:
        t.append("  ✕", style=CHIP_DOWN)
    elif not asyn and ev.get("answer"):
        t.append(f"  → {_short(ev.get('answer'), 50)}", style="#9ca3af")
    return t


SETTLE_COLOR = "#f5c542"


def settlement_text(st: dict[str, Any], locale: str = "zh") -> Any:
    """run.settled / game/meta/settlement.json → the ending card: exit · epilogue · CG · deaths · accusations · truth."""
    from rich.text import Text

    from neonrp.tui.i18n import get_message

    def m(k: str) -> str:
        return get_message(locale, f"settle.{k}")

    t = Text()
    t.append(f"\n✦ {m('title')}\n", style=f"bold {SETTLE_COLOR}")
    ex = st.get("exit") if isinstance(st.get("exit"), dict) else {"id": st.get("exit")}
    if ex:
        t.append(f"{m('exit')}  ", style="#9ca3af")
        t.append(f"{ex.get('kind') or ''} {ex.get('id') or ''}".strip() + "\n", style=SETTLE_COLOR)
    if st.get("epilogue"):
        t.append(f"\n{st['epilogue']}\n", style="#f8fafc")
    if st.get("cg_unlocked"):
        t.append(f"\n{m('cg')}  {' · '.join(map(str, st['cg_unlocked']))}\n", style="#c084fc")
    for d in st.get("deaths") or []:
        if isinstance(d, dict):
            t.append(f"✝ {m('deaths')}  {d.get('name') or d.get('who')}  ({d.get('turn')})\n", style="#ef4444")
    acc = st.get("accusation") or []
    if acc:
        t.append(f"\n{m('accusation')}\n", style="bold #fbbf24")
        for a in acc:
            votes = len(a.get("votes") or []) if isinstance(a, dict) else 0
            t.append(f"  {a.get('round', '')} · {a.get('name') or a.get('target')} ({a.get('role') or '?'})  ×{votes}\n", style="#fbbf24")
    tr = st.get("truth_reveal") or {}
    if isinstance(tr, dict) and (tr.get("text") or tr.get("roles")):
        t.append(f"\n{m('truth')}\n", style="bold #60a5fa")
        if tr.get("text"):
            t.append(f"  {tr['text']}\n", style="#dbeafe")
        for r in tr.get("roles") or []:
            mark = "✝" if r.get("alive") is False else "·"
            t.append(f"  {mark} {r.get('name') or r.get('id')}  {r.get('role')}\n", style="#93c5fd")
    t.append(f"\n{m('hint')}", style="dim #9ca3af")
    return t


def plan_text(ev: dict[str, Any]) -> Any:
    """plan.beat → the board under the talk: ``▣ 玩家 → 撬锁 · 艾琳娜 → 按住门框`` / ``🎲 player DEX normal 撬锁`` /
    ``🎙 → 艾琳娜`` (who the host passed the mic to). None when the beat set nothing."""
    from rich.text import Text

    t = Text()
    board = ev.get("board") or {}
    if board:
        t.append("▣ ", style=f"bold {PLAN_COLOR}")
        t.append(" · ".join(f"{k} → {_short(v, 30)}" for k, v in board.items()), style=PLAN_COLOR)
    for c in ev.get("checks") or []:
        if t.plain:
            t.append("\n")
        if isinstance(c, dict):
            head = " ".join(str(x) for x in (c.get("who"), c.get("attr"), c.get("dc")) if x)
            t.append("🎲 ", style="#e8a33d")
            t.append(head, style="bold #e8a33d")
            if c.get("adj"):
                t.append(f" {c.get('adj')}", style="#fbbf24")
            if c.get("why"):
                t.append(f"  {_short(c.get('why'), 40)}", style="#d6c7a1")
        else:
            t.append(f"🎲 {_short(c, 60)}", style="#e8a33d")
    for x in ev.get("mic") or []:
        who = x.get("who") if isinstance(x, dict) else x
        if who:
            if t.plain:
                t.append("\n")
            t.append(f"🎙 → {who}", style="#93c5fd")
    return t if t.plain else None


PANEL_COLORS = {"map": "#34d399", "sheet": "#60a5fa", "formation": "#f87171"}


def panel_renderable(panel: dict[str, Any]) -> Any:
    """A panel the beat drew (core/panels value) as a bordered box: text as written (the map / formation are monospace
    pictures), json via its fallback text or compactly, an image as its path."""
    import json as _json

    from rich.panel import Panel
    from rich.text import Text

    pid = str(panel.get("id") or "panel")
    fmt = str(panel.get("format") or "text")
    if fmt == "image":
        body = Text(f"🖼 {panel.get('text') or panel.get('data') or ''}", style="#d1d5db")
    elif fmt == "json":
        fb = panel.get("fallback") or panel.get("text")
        body = Text(str(fb) if fb else _json.dumps(panel.get("data"), ensure_ascii=False)[:600], style="#d1d5db")
    else:
        body = Text(str(panel.get("text") or ""), style="#e5e7eb")
    color = PANEL_COLORS.get(pid, "#9ca3af")
    return Panel(body, title=f"[bold {color}]{pid}[/]", title_align="left", border_style=color, expand=False)


ITEM_COLOR = "#fde68a"
_ITEM_SKIP = {"name", "qty", "id", "class", "on", "rule"}


def is_item_class(cls: str, spec: Any = None) -> bool:
    """An item = something carried: rpg's ``carry`` (the player's bag), a pack's ``item``, or any class kept in the
    player's inventory file."""
    folder = str(getattr(spec, "folder", "") or "")
    return cls in ("carry", "item") or "inventory" in folder


def item_card(name: str, props: dict[str, Any]) -> Any:
    """A picked-up item, field by field (10-08: not Markdown): ``🎒 小治疗药水 ×1`` then one line per prop it carries."""
    from rich.panel import Panel
    from rich.text import Text

    t = Text()
    qty = props.get("qty")
    t.append(f"🎒 {name}", style=f"bold {ITEM_COLOR}")
    if qty not in (None, "", 1):
        t.append(f"  ×{qty}", style="#d6c7a1")
    for k, v in props.items():
        if k in _ITEM_SKIP or v in (None, "", [], {}) or isinstance(v, (dict, list)):
            continue
        t.append(f"\n{k:10}", style="#9ca3af")
        t.append(_short(v, 60), style="#e5e7eb")
    return Panel(t, border_style="#a16207", expand=False, padding=(0, 1))
