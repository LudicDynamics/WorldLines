"""「再给几个选项」(10-15, player2): a few more things the player could do right now — the beat does not move.

    POST /api/v1/play/engine/choices {n?: 3, avoid?: [options already on screen]}
    → {lang, options: [str…], by: "more"}           409 while a turn is running

Read-only: no turn record, no state write. One model call on the run's own provider (the same adapter a turn uses, so
the call is metered the same way: Worldlines' usage allowance, or nothing with the player's own key), in the run's
language, from what the player can see — the last beat's prose, where they are, who is there, what they carry, their
skills (10-16: so a choice can be "@someone …" or "/skill …", the two moves players did not know they had) (no
host-only data, so no option can spoil). Each call is kept in the trace's side file
``.neonrp/orchestration/<branch>.side.jsonl`` ({kind: choices, ts, n, avoid, options, usage, ms, error?}) for debugging.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_N = 6


def _adapter(root: Path) -> Any:
    """The run's provider (the same one its turns use) — its own function so tests inject a stub."""
    from neonrp.core.config import load_config, resolve_provider
    from neonrp.core.llm import get_adapter_from_config

    return get_adapter_from_config(resolve_provider(load_config(root), None, None))


def scene(root: Path, branch: str = "main", lang: str | None = None) -> dict[str, Any]:
    """What the player can see now: the last beat's prose, the place, the people, the things on them, their skills."""
    from neonrp.core import people, play_menu
    from neonrp.core import sheet as _sheet
    from neonrp.core.orchestration_trace import read_turn_traces
    from neonrp.core.registry import load_registry

    last = (read_turn_traces(root, branch, last=1) or [{}])[-1]
    ap = last.get("apply") if isinstance(last.get("apply"), dict) else {}
    reg = load_registry(root)
    here = reg.entries.get(reg.player_location or "")
    who = [p["name"] for p in people.people(root)["people"] if p.get("here") and p.get("name")]
    held = [i["name"] for i in play_menu._items(reg) if i.get("held")]
    try:  # the names the engine takes after "/" (play_menu.catalog's cmd)
        skills = [str(r.get("label") or r.get("name")) for r in _sheet.sheet(root, lang, reg=reg).get("skills") or [] if r.get("label") or r.get("name")]
    except Exception:  # noqa: BLE001 — no sheet, no skills line
        skills = []
    return {"prose": str(ap.get("narration_plain") or "")[-1500:], "place": str(here.name or "") if here else "", "people": who,
            "items": held, "skills": skills, "options": [str(o) for o in ap.get("options") or []]}


def _parse(raw: str, n: int, avoid: set[str]) -> list[str]:
    out: list[str] = []
    for ln in str(raw or "").splitlines():
        t = re.sub(r"^\s*(?:[-*•·]|\d+[.)、.]|[（(]?\d+[)）])\s*", "", ln).strip().strip("「」\"'")
        if t and len(t) <= 80 and t not in avoid and t not in out:
            out.append(t)
        if len(out) >= n:
            break
    return out


def _side(root: Path, branch: str, rec: dict[str, Any]) -> None:
    try:
        p = Path(root) / ".neonrp" / "orchestration" / f"{(branch or 'main').replace('/', '-')}.side.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — the side file is for debugging; it never fails the call
        logger.debug("choices side record skipped", exc_info=True)


def more_choices(root: Path, *, n: int = 3, avoid: list[str] | None = None, branch: str = "main", adapter: Any = None) -> dict[str, Any]:
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang

    lang = prompt_lang(root)
    n = max(1, min(MAX_N, int(n or 3)))
    sc = scene(root, branch, lang)
    avoid_set = {str(a).strip() for a in (avoid or []) if str(a).strip()} | set(sc["options"])
    T = prompts.strings("choices", lang)
    none = str(T["none"])
    user = str(T["user"]).format(n=n, prose=sc["prose"] or none, place=sc["place"] or none,
                                 people=T["sep"].join(sc["people"]) or none, items=T["sep"].join(sc["items"]) or none,
                                 skills=T["sep"].join(sc["skills"]) or none,
                                 avoid="\n".join(f"- {a}" for a in sorted(avoid_set)) or none)
    t0 = time.monotonic()
    rec: dict[str, Any] = {"kind": "choices", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "n": n, "avoid": sorted(avoid_set)}
    try:
        out = (adapter or _adapter(root)).generate(str(T["system"]), user)
        err = getattr(out, "error", None)
        # 10-16: the adapter looks for a proposal JSON and flags plain lines as an error — but plain lines are what this
        # call asks for, so the model's text counts whenever there is some (an error with no text is a real one)
        raw = str(getattr(out, "raw_output", "") or ("" if err else getattr(out, "proposal_text", "")) or "")
        rec["usage"] = dict(getattr(out, "usage", None) or {})
        if err and not raw.strip():
            rec["error"] = str(err)[:300]
    except Exception as exc:  # noqa: BLE001 — a model error answers with no options, never a crash
        raw = ""
        rec["error"] = str(exc)[:300]
    options = _parse(raw, n, avoid_set)
    rec.update({"options": options, "ms": round((time.monotonic() - t0) * 1000, 1)})
    _side(root, branch, rec)
    return {"lang": lang, "options": options, "by": "more", **({"error": rec["error"]} if rec.get("error") and not options else {})}
