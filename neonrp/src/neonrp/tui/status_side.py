"""The right-hand status column: a toggle at its top — 「玩家」 shows the player's own state, 「Agent」 the
characters' — rendered field by field (hp bar · down / stable / dead · effects with their countdown · carried items),
not as Markdown.

``collect(root)`` reads the registry (any pack: rpg · pct · werewolf …) into plain dicts — testable without an app;
``render_player`` / ``render_agents`` turn them into rich Text; ``StatusSide`` is the widget.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static

from neonrp.tui.i18n import get_message

HP_OK, HP_LOW, HP_OUT = "#4ade80", "#fbbf24", "#f87171"
EFFECT_COLOR, ITEM_COLOR, MUTED = "#c084fc", "#e5e7eb", "#9ca3af"
DOWN_COLOR, DEAD_COLOR, STABLE_COLOR = "#fb923c", "#ef4444", "#60a5fa"


def _owner(reg: Any, e: Any) -> str | None:
    """Whose an entry is — the registry's own answer (`on` as a name, `{{user}}`, `{{char}}`, a carrying parent …);
    the old `player:<id>` spelling still read as that id."""
    try:
        who = reg.owner_of(e)
    except Exception:  # noqa: BLE001 — a registry stand-in without the API: the raw field
        who = str(e.props.get("on") or "player")
    if isinstance(who, str) and who.startswith("player:") and who[7:] in getattr(reg, "entries", {}):
        return who[7:]
    if who in ("me", "self") or (who in (None, "") and getattr(e, "cls", "") == "status"):  # an effect with no `on`: the player's
        return "player"
    return who


def _effects_on(reg: Any, who: str) -> list[dict[str, Any]]:
    out = []
    for e in reg.of_class("status") if "status" in getattr(reg, "classes", {}) else []:
        if _owner(reg, e) == who:
            p = e.props
            out.append({"name": e.name, "turns": p.get("turns"), "until": p.get("until_text"), "rule": p.get("rule") or p.get("note") or ""})
    return out


def _vital(e: Any) -> dict[str, Any]:
    p = e.props
    hp, mx = p.get("hp"), p.get("max_hp")
    return {"hp": hp if isinstance(hp, (int, float)) else None, "max_hp": mx if isinstance(mx, (int, float)) else None,
            "down": int(p.get("down") or 0), "stable": int(p.get("stable") or 0), "dead": int(p.get("dead") or 0)}


def collect(root: Path) -> dict[str, Any]:
    """{"player": {...}, "agents": [...]} from the run's registry; empty parts when the world has none."""
    from neonrp.core.registry import load_registry

    try:
        reg = load_registry(Path(root))
    except Exception:  # noqa: BLE001 — a world that does not load shows an empty column
        return {"player": {}, "agents": []}
    out: dict[str, Any] = {"player": {}, "agents": []}
    pl = reg.entries.get("player")
    here = getattr(reg, "player_location", None)
    if pl is not None:
        p = pl.props
        san = reg.variables.get("player.san")
        items = [{"name": e.name, "qty": e.props.get("qty")} for e in reg.of_class("carry") if _owner(reg, e) == "player"] \
            if "carry" in reg.classes else []
        if not items:
            items = [{"name": str(x.get("name")), "qty": x.get("qty")} for x in p.get("inventory") or [] if isinstance(x, dict)]
        out["player"] = {"name": pl.name, **_vital(pl), "gold": p.get("gold"), "level": p.get("level"),
                         "san": san.value if san is not None else None, "san_label": p.get("san_label") or "SAN", "effects": _effects_on(reg, "player"), "items": items,
                         "judge": judge_status(root) if judge_matters(root) else None}
    try:
        from neonrp.packs import resolve as _resolve_pack

        cast = str(getattr(_resolve_pack(Path(root)), "cast_class", "") or "")
    except Exception:  # noqa: BLE001
        cast = ""
    for cls in [c for c in ("soul", cast) if c and c in reg.classes]:
        for e in reg.of_class(cls):
            where = reg.entries.get(e.parent) if e.parent else None
            out["agents"].append({"id": e.id, "name": e.name, **_vital(e), "here": bool(here and e.parent == here),
                                  "where": (where.name if where is not None else e.parent) or "", "alive": e.props.get("alive"),
                                  "effects": _effects_on(reg, e.id)})
    return out


# ── rendering ────────────────────────────────────────────────────────────────

def _t(locale: str, key: str) -> str:
    return get_message(locale, key)


def _bar(hp: float, mx: float, width: int = 12) -> Text:
    frac = max(0.0, min(1.0, hp / mx)) if mx else 0.0
    color = HP_OK if frac > 0.5 else HP_LOW if frac > 0 else HP_OUT
    n = round(frac * width)
    t = Text()
    t.append("█" * n, style=color)
    t.append("░" * (width - n), style=MUTED)
    t.append(f" {int(hp)}/{int(mx)}", style=color)
    return t


def _condition(locale: str, v: dict[str, Any]) -> Text | None:
    if v.get("dead") or v.get("alive") is False:
        return Text(f"✝ {_t(locale, 'status.dead')}", style=f"bold {DEAD_COLOR}")
    if v.get("down"):
        if v.get("stable"):
            return Text(f"⚑ {_t(locale, 'status.stable')}", style=f"bold {STABLE_COLOR}")
        return Text(f"⚠ {_t(locale, 'status.down')}", style=f"bold {DOWN_COLOR}")
    return None


def _effect_lines(locale: str, effects: list[dict[str, Any]]) -> list[Text]:
    out = []
    for fx in effects:
        t = Text("  ◆ ", style=EFFECT_COLOR)
        t.append(str(fx["name"]), style=f"bold {EFFECT_COLOR}")
        if fx.get("turns") not in (None, ""):
            t.append(f"  ⏳{fx['turns']}", style=MUTED)
        elif fx.get("until"):
            t.append(f"  ⏳{fx['until']}", style=MUTED)
        if fx.get("rule"):
            t.append(f"\n     {str(fx['rule'])[:60]}", style=MUTED)
        out.append(t)
    return out


def render_player(locale: str, p: dict[str, Any]) -> Text:
    out = Text()
    if not p:
        return Text(_t(locale, "status.none"), style=MUTED)
    out.append(f"{p.get('name') or ''}\n", style="bold #f8fafc")
    cond = _condition(locale, p)
    if cond is not None:
        out.append_text(cond)
        out.append("\n")
    if p.get("hp") is not None and p.get("max_hp"):
        out.append("HP  ", style=MUTED)
        out.append_text(_bar(p["hp"], p["max_hp"]))
        out.append("\n")
    if p.get("san") is not None:
        out.append(f"{p.get('san_label') or 'SAN'} {p['san']}\n", style="#c084fc")
    if p.get("gold") is not None:
        out.append(f"{_t(locale, 'status.gold')} {p['gold']}\n", style="#fde68a")
    if p.get("effects"):
        out.append(f"\n{_t(locale, 'status.effects')}\n", style=f"bold {MUTED}")
        for line in _effect_lines(locale, p["effects"]):
            out.append_text(line)
            out.append("\n")
    if p.get("items"):
        out.append(f"\n{_t(locale, 'status.items')}\n", style=f"bold {MUTED}")
        for it in p["items"]:
            out.append("  ▪ ", style=MUTED)
            out.append(str(it["name"]), style=ITEM_COLOR)
            if it.get("qty") not in (None, "", 1):
                out.append(f" ×{it['qty']}", style=MUTED)
            out.append("\n")
    if p.get("judge"):  # who decides when the talk has settled (Jev) — and how to turn it on
        out.append("\n")
        out.append_text(judge_line(locale, p["judge"]))
    return out


LIFECYCLE = {"queued": ("…", MUTED), "running": ("✎", "#60a5fa"), "completed": ("✓", HP_OK), "degraded": ("!", HP_LOW),
             "offstage": ("·", MUTED), "error": ("✕", HP_OUT)}


def render_agents(locale: str, agents: list[dict[str, Any]], lifecycle: dict[str, dict[str, str]] | None = None) -> Text:
    if not agents:
        return Text(_t(locale, "status.none"), style=MUTED)
    out = Text()
    for a in sorted(agents, key=lambda a: (not a.get("here"), str(a.get("name")))):
        dot = "●" if a.get("here") else "○"
        out.append(f"{dot} ", style=HP_OK if a.get("here") else MUTED)
        out.append(str(a.get("name") or a.get("id")), style="bold #f8fafc")
        lc = (lifecycle or {}).get(str(a.get("id"))) or {}
        mark = LIFECYCLE.get(str(lc.get("state") or ""))
        if mark:
            out.append(f" {mark[0]}", style=f"bold {mark[1]}")
        out.append(f"  {_t(locale, 'status.here') if a.get('here') else a.get('where') or _t(locale, 'status.away')}\n", style=MUTED)
        cond = _condition(locale, a)
        if cond is not None:
            out.append("  ")
            out.append_text(cond)
            out.append("\n")
        if a.get("hp") is not None and a.get("max_hp"):
            out.append("  HP ", style=MUTED)
            out.append_text(_bar(a["hp"], a["max_hp"], width=10))
            out.append("\n")
        for line in _effect_lines(locale, a.get("effects") or []):
            out.append_text(line)
            out.append("\n")
        out.append("\n")
    return out


class StatusSide(Vertical):
    """Right column: [玩家 | Agent] toggle on top, the chosen view below (scrolls)."""

    DEFAULT_CSS = """
    StatusSide { width: 36; height: 100%; border-left: solid #27272a; background: #0b0f0c; display: none; }
    StatusSide #status-toggle { height: 3; width: 100%; }
    StatusSide .status-tab { width: 1fr; min-width: 6; height: 3; background: #111827; color: #9ca3af; border: none; }
    StatusSide .status-tab.active { background: #1f2937; color: #f8fafc; text-style: bold; }
    StatusSide #status-scroll { height: 1fr; padding: 0 1; }
    """

    def __init__(self, *, locale: str = "zh", **kw: Any) -> None:
        super().__init__(**kw)
        self.locale = locale
        self.view = "player"
        self.root: Path | None = None
        self.data: dict[str, Any] = {"player": {}, "agents": []}
        self.lifecycle: dict[str, dict[str, str]] = {}  # instance id → {state: queued / running / completed …}

    def compose(self):  # type: ignore[override]
        yield Horizontal(
            Button(f"👤 {_t(self.locale, 'status.player')}", id="status-tab-player", classes="status-tab active"),
            Button(f"◎ {_t(self.locale, 'status.agents')}", id="status-tab-agents", classes="status-tab"),
            id="status-toggle",
        )
        yield VerticalScroll(Static("", id="status-body"), id="status-scroll")

    def set_root(self, root: Path | None) -> None:
        self.root = root
        self.refresh_state()

    def show(self, view: str) -> None:
        self.view = "agents" if view == "agents" else "player"
        for vid, name in (("player", "#status-tab-player"), ("agents", "#status-tab-agents")):
            try:
                self.query_one(name, Button).set_class(self.view == vid, "active")
            except Exception:  # noqa: BLE001
                pass
        self._paint()

    def set_lifecycle(self, snapshot: dict[str, dict[str, str]]) -> None:
        """The characters' in-turn lifecycle (queued → running → done), shown beside each name in the Agent view."""
        self.lifecycle = dict(snapshot or {})
        if self.view == "agents":
            self._paint()

    def refresh_state(self) -> None:
        if self.root is not None:
            self.data = collect(self.root)
        self._paint()

    def _paint(self) -> None:
        body = render_player(self.locale, self.data.get("player") or {}) if self.view == "player" \
            else render_agents(self.locale, self.data.get("agents") or [], self.lifecycle)
        try:
            self.query_one("#status-body", Static).update(body)
        except Exception:  # noqa: BLE001 — not mounted yet
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("status-tab-player", "status-tab-agents"):
            event.stop()
            self.show("agents" if event.button.id == "status-tab-agents" else "player")


# ── the judge (Jev) and the Worldlines account (10-08: /login is ours — the two-beat play leans on Jev) ──────────────

JUDGE_COLORS = {"jev": HP_OK, "proxy": HP_OK, "llm": HP_LOW, "own": HP_LOW, "off": MUTED, "stub": MUTED, "quota": HP_OUT}


def judge_matters(root: Path | None) -> bool:
    """The judge only has a job while a planning node runs (the talk that has to settle) — the same test the app uses to
    route a line to the planning beat. The public engine (NEONRP_PRIVATE=off) has none: no hint about Jev there."""
    if root is None:
        return False
    try:
        from neonrp.core import node_kinds

        return bool(node_kinds.call("plan", "active", Path(root), "·", default=False))
    except Exception:  # noqa: BLE001
        return False


def judge_status(root: Path | None = None) -> dict[str, Any]:
    """{"backend": jev | proxy | llm | own | stub | off | quota, "signed_in": bool} — who decides whether the talk has
    settled. ``own`` (10-24): no judge, the run's own model answers the planning beat's question."""
    from neonrp.core import system_one as s1

    try:
        backend = s1.backend_name()
        if backend in ("jev", "proxy") and s1.quota_blocked():
            backend = "quota"
        elif backend == "off" and s1.own_model_judge(root):
            backend = "own"
    except Exception:  # noqa: BLE001
        backend = "off"
    try:
        from neonrp.core import worldlines_auth as wa

        signed = bool(wa.status().get("signed_in"))
    except Exception:  # noqa: BLE001
        signed = False
    return {"backend": backend, "signed_in": signed}


def judge_line(locale: str, js: dict[str, Any] | None = None) -> Text:
    js = js or judge_status()
    b = str(js.get("backend") or "off")
    t = Text("⚖ ", style=JUDGE_COLORS.get(b, MUTED))
    t.append(_t(locale, f"judge.{b}"), style=JUDGE_COLORS.get(b, MUTED))
    if b in ("off", "quota", "llm", "own") and not js.get("signed_in"):
        t.append(f"  {_t(locale, 'judge.login')}", style=MUTED)
    return t
