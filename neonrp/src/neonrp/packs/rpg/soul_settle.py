"""Soul settle — the closed-schema write-back after the turn resolved.

In ② a soul only *speaks* (LLM). What it should *remember and feel* depends on
what the world finally did with the turn — the landed narration, not the
soul's own proposal (its move may have been refused, the player may have
walked off). So the closed schema (mood / trust / important / intention) is
judged **after ③–⑤**, from the final narration, by Jev, and written by the
engine as a typed memo entry. No LLM writes memo.

Every question has a deterministic fallback (backend ``off``): mood unchanged,
trust 0, important False, intention unchanged — the typed event line is still
appended, so a no-Jev build keeps a complete, typed ``D_soul``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from neonrp.core import system_one as s1
from neonrp.core.registry import Registry, load_registry

logger = logging.getLogger(__name__)

MOODS: list[str] = ["calm", "warm", "curious", "hopeful", "alert", "anxious", "guarded", "angry", "hurt", "sad", "tired"]
TRUST_STEPS: list[str] = ["-2", "-1", "0", "1", "2"]


@dataclass
class SoulPatch:
    iid: str
    name: str
    mood: str | None
    mood_before: str | None
    trust_delta: int
    important: bool
    intention: str | None
    my_reaction: str
    event: str
    source: str  # jev | proxy | stub | off
    confidence: float = 0.0
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _soul_dir(root: Path, reg: Registry, iid: str) -> Path | None:
    env = reg.entries.get(iid)
    if env is None or env.cls != "soul":
        return None
    sid = str(env.props.get("sid") or "")
    d = root / "souls" / f"{sid}-{iid}"
    return d if d.is_dir() else None


def _goals(soul_dir: Path) -> list[str]:
    m = _read(soul_dir / "persona" / "motivations.json")
    out = [str(x) for x in (m.get("motivations") or m.get("goals") or []) if isinstance(x, str) and x.strip()]
    return out[:6]


def _event_line(narration: str, name: str) -> str:
    """The narration sentence(s) around the soul's name, else the opening."""
    text = " ".join(narration.split())
    i = text.find(name) if name else -1
    if i < 0:
        return text[:200]
    start = max(0, i - 80)
    return text[start : start + 200]


def questions_for(name: str, mood_before: str | None, goals: list[str]) -> dict[str, s1.Q]:
    qs: dict[str, s1.Q] = {
        "mood": s1.choice(f"{name} 在这一回合结束时的情绪最接近哪一个?", {m: m for m in sorted(set(MOODS) | ({mood_before} if mood_before else set()))}),
        "trust": s1.choice(f"经过这一回合,{name} 对玩家的信任变化(-2 大降 … +2 大升)", {t: t for t in TRUST_STEPS}),
        "important": s1.noul(f"这一回合对 {name} 来说是值得长期记住的重要事件吗?"),
    }
    if len(goals) >= 2:
        qs["intention"] = s1.choice(f"这一回合之后,{name} 最想推进的目标是哪一个?", {g: g for g in goals})
    return qs


def settle_souls(
    root: Path,
    *,
    reports: list[dict[str, Any]],
    narration: str,
    turn: int,
    registry: Registry | None = None,
    ask: Callable[..., dict[str, s1.Answer] | None] | None = None,
) -> list[dict[str, Any]]:
    """Judge + write the closed schema for every soul that took part (not failed)."""
    reg = registry or load_registry(root)
    ask_fn = ask or s1.ask
    jobs: list[tuple[str, Path, dict[str, Any]]] = []
    seen: set[str] = set()
    for r in reports:
        iid = str(r.get("iid") or "")
        if not iid or iid in seen or r.get("ok") is False or not str(r.get("text") or "").strip():
            continue
        sd = _soul_dir(root, reg, iid)
        if sd is None:
            continue
        seen.add(iid)
        jobs.append((iid, sd, r))
    if not jobs:
        return []
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=min(4, len(jobs)), thread_name_prefix="neonrp-settle") as ex:
        return [d for d in ex.map(lambda j: _settle_one(root, reg, ask_fn, narration, turn, *j), jobs) if d]


def _settle_one(root: Path, reg: Registry, ask_fn: Any, narration: str, turn: int, iid: str, sd: Path, r: dict[str, Any]) -> dict[str, Any] | None:
    try:
        name = reg.entries[iid].name
        rs = _read(sd / "run_state.json")
        status = rs.get("status") if isinstance(rs.get("status"), dict) else {}
        mood_before = status.get("mood") if isinstance(status.get("mood"), str) else None
        goals = _goals(sd)
        my_reaction = " ".join(str(r.get("text") or "").split())[:200]
        event = _event_line(narration, name)
        state = {
            "soul": name, "mood_before": mood_before, "goals": goals,
            "my_reaction": my_reaction, "what_happened": " ".join(narration.split())[-800:],
        }
        t0 = time.monotonic()
        answers = None
        try:
            answers = ask_fn(state, questions_for(name, mood_before, goals))
        except Exception:  # noqa: BLE001 — a judge failure is the fallback
            logger.debug("soul settle ask failed for %s", iid, exc_info=True)
        src = s1.backend_name() if answers is not None else "off"
        patch = SoulPatch(iid, name, mood_before, mood_before, 0, False, None, my_reaction, event, src)
        if answers:
            a = answers.get("mood")
            if a is not None and s1.confidence_ok(a) and str(a.value) in MOODS + ([mood_before] if mood_before else []):
                patch.mood = str(a.value)
                patch.confidence = float(a.confidence)
            a = answers.get("trust")
            if a is not None and s1.confidence_ok(a):
                try:
                    patch.trust_delta = max(-2, min(2, int(str(a.value))))
                except ValueError:
                    pass
            a = answers.get("important")
            if a is not None and s1.confidence_ok(a):
                patch.important = a.yes >= 0.5
            a = answers.get("intention")
            if a is not None and s1.confidence_ok(a) and str(a.value) in goals:
                patch.intention = str(a.value)
        _apply_patch(sd, rs, patch, turn)
        patch.applied = True
        d = patch.to_dict()
        d["ms"] = round((time.monotonic() - t0) * 1000, 1)
        return d
    except Exception:  # noqa: BLE001 — one soul's memo failing never blocks the others
        logger.debug("soul settle failed for %s", iid, exc_info=True)
        return None


def _apply_patch(sd: Path, rs: dict[str, Any], p: SoulPatch, turn: int) -> None:
    changed = False
    status = rs.get("status") if isinstance(rs.get("status"), dict) else {}
    if p.mood and p.mood != p.mood_before:
        status["mood"] = p.mood
        changed = True
    if p.trust_delta:
        t = status.get("trust") if isinstance(status.get("trust"), dict) else {}
        t["player"] = max(-10, min(10, int(t.get("player", 0) or 0) + p.trust_delta))
        status["trust"] = t
        changed = True
    if p.intention:
        status["intention"] = p.intention
        changed = True
    if changed:
        rs["status"] = status
        _write(sd / "run_state.json", rs)
    path = sd / "short-term-memo" / "recent_events.json"
    memo = _read(path)
    events = memo.get("events") if isinstance(memo.get("events"), list) else []
    events.append({
        "turn": turn, "event": p.event, "my_reaction": p.my_reaction, "affect": p.mood or p.mood_before or "",
        **({"important": True} if p.important else {}), **({"trust_delta": p.trust_delta} if p.trust_delta else {}),
        "by": "engine.settle",
    })
    memo["events"] = events[-40:]
    _write(path, memo)
