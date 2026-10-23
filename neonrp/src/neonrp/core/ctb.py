"""CTB tick scheduler — prototype (exp/jev-system-one, TODO #4).

"CTB" as in FFX's Conditional Turn-Based order: every actor carries an
*action gauge*; the gauge fills at the actor's *speed*; whoever fills first
acts next, then pays a *cost* (its gauge drops back) and the world clock
advances to that moment. Nothing here calls an LLM — it only decides **who
should act next and when**, so the engine (or a hosted/auto mode) can drive
off-scene characters between player turns without running everyone every
turn.

How the pieces map:

- ``speed``  ← S1's ``away.<iid>.stir`` (0–1) blended with the character's
  own urgency from its last report; a character nobody expects to move sits
  at speed ≈ 0.1 and only surfaces every few world-hours.
- ``cost``   ← what the action took (a heartbeat = 1, a light exchange = 2,
  a full engage that moved = 4) in *world minutes* units below.
- ``tick``   ← the world clock's Δ each player turn (``tick_world``), or a
  timer in hosted/auto mode (e.g. one tick per real minute).

The player is *not* an actor here: the player acts whenever they type; a
player turn is what advances the clock and lets the gauges fill.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GAUGE_FULL = 100.0
DEFAULT_SPEED = 0.15
COST_HEARTBEAT = 25.0
COST_SPEAK = 50.0
COST_ACT = 100.0


@dataclass
class Actor:
    iid: str
    name: str = ""
    speed: float = DEFAULT_SPEED  # 0–1 → gauge units per world minute
    gauge: float = 0.0
    last_acted_at: float = 0.0  # world minutes

    def to_dict(self) -> dict[str, Any]:
        return {"iid": self.iid, "name": self.name, "speed": round(self.speed, 3), "gauge": round(self.gauge, 2), "last_acted_at": self.last_acted_at}


@dataclass
class CTBScheduler:
    """Deterministic, replayable: same speeds + same ticks ⇒ same order."""

    actors: dict[str, Actor] = field(default_factory=dict)
    now: float = 0.0  # world minutes since the run started

    # ── roster ───────────────────────────────────────────────────────
    def upsert(self, iid: str, *, name: str = "", speed: float | None = None) -> Actor:
        a = self.actors.get(iid)
        if a is None:
            a = Actor(iid=iid, name=name)
            self.actors[iid] = a
        if name:
            a.name = name
        if speed is not None:
            a.speed = max(0.0, min(1.0, float(speed)))
        return a

    def remove(self, iid: str) -> None:
        self.actors.pop(iid, None)

    def set_speed_from_plan(self, stirs: dict[str, float], *, floor: float = 0.05, ceiling: float = 1.0) -> None:
        """Feed S1's ``away.<iid>.stir`` answers: p(should act now) → speed."""
        for iid, p in stirs.items():
            if iid in self.actors:
                self.actors[iid].speed = max(floor, min(ceiling, float(p)))

    # ── time ─────────────────────────────────────────────────────────
    def tick(self, minutes: float) -> list[Actor]:
        """Advance the clock; return actors whose gauge is full, soonest first."""
        if minutes <= 0:
            return self.ready()
        self.now += minutes
        for a in self.actors.values():
            a.gauge = min(GAUGE_FULL * 4, a.gauge + a.speed * minutes * (GAUGE_FULL / 60.0))
        return self.ready()

    def ready(self) -> list[Actor]:
        full = [a for a in self.actors.values() if a.gauge >= GAUGE_FULL]
        # Fuller first; ties → who waited longest.
        return sorted(full, key=lambda a: (-a.gauge, a.last_acted_at, a.iid))

    def eta(self, iid: str) -> float | None:
        """World minutes until this actor's gauge is full (None if it never will)."""
        a = self.actors.get(iid)
        if a is None or a.speed <= 0:
            return None
        missing = max(0.0, GAUGE_FULL - a.gauge)
        return missing / (a.speed * (GAUGE_FULL / 60.0))

    def next_up(self) -> tuple[Actor, float] | None:
        """Who acts next and in how many world minutes (without mutating)."""
        best: tuple[Actor, float] | None = None
        for a in self.actors.values():
            e = self.eta(a.iid)
            if e is None:
                continue
            if best is None or e < best[1] or (e == best[1] and a.iid < best[0].iid):
                best = (a, e)
        return best

    def after_action(self, iid: str, cost: float = COST_ACT) -> None:
        a = self.actors.get(iid)
        if a is None:
            return
        a.gauge = max(0.0, a.gauge - cost)
        a.last_acted_at = self.now

    # ── persistence (game/meta/ctb.json) ─────────────────────────────
    @staticmethod
    def path(root: Path) -> Path:
        try:
            from neonrp.core.paths import get_game_dir

            return get_game_dir(root) / "meta" / "ctb.json"
        except Exception:
            return root / "game" / "meta" / "ctb.json"

    def save(self, root: Path) -> Path:
        p = self.path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"now": self.now, "actors": [a.to_dict() for a in self.actors.values()]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return p

    @classmethod
    def load(cls, root: Path) -> CTBScheduler:
        p = cls.path(root)
        s = cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return s
        s.now = float(data.get("now") or 0.0)
        for row in data.get("actors") or []:
            if isinstance(row, dict) and row.get("iid"):
                a = s.upsert(str(row["iid"]), name=str(row.get("name") or ""), speed=row.get("speed"))
                a.gauge = float(row.get("gauge") or 0.0)
                a.last_acted_at = float(row.get("last_acted_at") or 0.0)
        return s


def plan_offscene_actions(
    scheduler: CTBScheduler,
    *,
    minutes: float,
    stirs: dict[str, float] | None = None,
    budget: int = 2,
) -> list[tuple[str, str]]:
    """One player turn passed (``minutes`` of world time). Update speeds from
    S1, advance, and return up to ``budget`` ``(iid, depth)`` actions for
    off-scene characters — ``depth`` is what the engine should run for them
    (``speak`` for a mild gauge overflow, ``act`` when the gauge is far past
    full, i.e. they have been waiting to move for a while)."""
    if stirs:
        scheduler.set_speed_from_plan(stirs)
    ready = scheduler.tick(minutes)
    out: list[tuple[str, str]] = []
    for a in ready[:budget]:
        depth = "act" if a.gauge >= GAUGE_FULL * 1.5 else "speak"
        out.append((a.iid, depth))
        scheduler.after_action(a.iid, COST_ACT if depth == "act" else COST_SPEAK)
    return out
