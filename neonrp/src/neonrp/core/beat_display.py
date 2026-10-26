"""What the player sees of a beat when the beat display is on (dice and tool calls drawn in their own line
styles; each kind of beat looks different). A node-kind plugin draws its own beat; this module draws a landing beat.

Plain text in the line conventions the TUI already colours (``ConversationView._semantic_line_class``):
``// …`` a scene header · ``[…`` a tool line · ``[name: expr >= n] → outcome`` a dice line · ``[state_update] …`` a state
change · ``1. …`` a choice. The stored history stays the plain prose — this is display only, never fed back to a model.

On with ``turn.display.beats`` = on (engine.json) or ``NEONRP_SHOW_BEATS=1``.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


def enabled(root: Path) -> bool:
    if os.environ.get("NEONRP_SHOW_BEATS", "").strip() in ("1", "true", "on"):
        return True
    from neonrp.core import engine_config

    return str(engine_config.get(root, "turn.display.beats", "off") or "off").lower() in ("on", "1", "true")


def _short(text: str, n: int = 60) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


LEVELS = ("critical", "special", "success", "fail", "fumble")  # core.dice.Outcome values; dice.outcome.<level> labels them
_LEVEL_ALIAS = {"crit": "critical", "critical_success": "critical", "failure": "fail", "failed": "fail",
                "critical_failure": "fumble", "extreme": "special", "hard": "special"}


def outcome_level(t: dict[str, Any]) -> str | None:
    """The tier a checked roll landed on — critical / special / success / fail / fumble — one name for every pack:
    the tool's own ``level`` (pct writes ``crit``; read as ``critical``), else a lone d20's natural 20 / 1 (SRD),
    else plain success / fail from ``passed``. None for a roll with no target. A ``level`` that says the opposite of
    ``passed`` (a contest: his own success, the other side won — 10-25) gives way to ``passed``."""
    lv = str(t.get("level") or "").strip().lower()
    lv = _LEVEL_ALIAS.get(lv, lv)
    if lv in LEVELS:
        if t.get("passed") is not None and (lv in ("critical", "special", "success")) != bool(t.get("passed")):
            return "success" if t.get("passed") else "fail"
        return lv
    if t.get("vs") is None or t.get("passed") is None:
        return None
    rolls = t.get("rolls") or []
    if not t.get("under") and len(rolls) == 1 and "d20" in str(t.get("dice") or t.get("request") or "").lower():
        try:
            nat = int(rolls[0])
        except (TypeError, ValueError):
            nat = 0
        if nat == 20:
            return "critical"
        if nat == 1:
            return "fumble"
    return "success" if t.get("passed") else "fail"


def _lang(root: Path) -> str:
    from neonrp.core.output_lang import prompt_lang

    return prompt_lang(root)


def _dice_line(t: dict[str, Any], lang: str = "zh") -> str | None:
    """A die rolled mid-prose ([dice 1d20+2 vs 12]撬锁) as the TUI's dice line — the outcome in the run's language and
    with the engine's tier (``level``: 大成功 / 成功 / 失败 / 大失败; 10-17 it was always 「成功 / 失败」 in Chinese)."""
    if t.get("total") is None or t.get("vs") is None:
        return None

    ok = bool(t.get("passed"))
    name = _short(str(t.get("reason") or str(t.get("request") or "dice").split(" ")[0]), 24)
    if t.get("under"):  # a percentile check (pct): [找暗门: 37 ≤ 60] → 成功
        roll = int(t.get("total") or 0)
        head = f"{roll} {'≤' if roll <= int(t.get('vs') or 0) else '>'} {t.get('vs')}"
    else:
        rolls = t.get("rolls") or []
        nat = rolls[0] if len(rolls) == 1 else "+".join(map(str, rolls))
        try:
            mod = int(t.get("total")) - sum(int(r) for r in rolls)
        except (TypeError, ValueError):
            mod = 0
        head = f"{nat}{mod:+d}={t.get('total')} {'>=' if ok else '<'} {t.get('vs')}"
    from neonrp import prompts as _prompts

    W = _prompts.strings("beat_display", lang)

    def said(x: dict[str, Any], passed: bool) -> str:
        lv = {"critical": "crit", "special": "success"}.get(outcome_level(x) or "", outcome_level(x) or "")  # one tier name for every pack
        return (W.get(f"dice_{lv}") if lv in ("crit", "fumble", "success", "fail") else None) or W["dice_success" if passed else "dice_fail"]
    word = said(t, ok)
    tail = contest_said(t, lang, word)
    return f"[{name}: {head}] → {tail or word}"


def contest_said(t: dict[str, Any], lang: str = "zh", result: str | None = None) -> str | None:
    """A contest's verdict in plain words (niko 10-25), the result first so a line read as it streams never shows his own
    success before the loss: 「失败:你掷 59(目标 60)成功,<她>掷 44(目标 55)也成功;同样成功时比谁赢得多,<她>多 11,你多 1 →
    <她>赢」. ``t`` is the dice event: his side at the top (``own_level`` his own tier, ``passed`` who won), the other side in
    ``contest`` (``by``: tier / margin / tie / both_fail for a percentile roll, total for a d20 — which rule decided it).
    None when it is no contest."""
    c = t.get("contest")
    if not isinstance(c, dict) or c.get("total") is None or t.get("total") is None:
        return None
    from neonrp import prompts as _prompts

    W = _prompts.strings("beat_display", lang)
    if not W.get("dice_contest_side"):
        return None
    ok = bool(t.get("passed"))

    def who(i: Any, name: Any) -> str:
        return str(W.get("dice_you") or "") if str(i or "") == "player" else str(name or i or "")
    me, them = who(t.get("who"), t.get("name")), who(c.get("who"), c.get("name"))
    won = t.get("who") if ok else c.get("who")
    winner = W["dice_contest_you_win"] if str(won or "") == "player" else W["dice_contest_win"].format(who=me if ok else them)
    ra, rb = int(t.get("total") or 0), int(c.get("total") or 0)
    if t.get("under") and c.get("vs") is not None and t.get("vs") is not None:  # percentile: roll under each side's own skill
        ta, tb = int(t.get("vs") or 0), int(c.get("vs") or 0)
        la = outcome_level({"level": t.get("own_level") or t.get("level"), "vs": ta}) or ("success" if ra <= ta else "fail")
        lb = outcome_level({"level": c.get("level"), "vs": tb}) or ("success" if rb <= tb else "fail")
        if t.get("own_level") is None and la in LEVELS and (la in ("critical", "special", "success")) != (ra <= ta):
            la = "success" if ra <= ta else "fail"  # an old event: ``level`` was rewritten to who won; his own roll says his tier
        word = lambda lv: W.get(f"dice_{ {'critical': 'crit'}.get(lv, lv)}") or lv  # noqa: E731
        pa, pb = la in ("critical", "special", "success"), lb in ("critical", "special", "success")
        sides = W["dice_contest_sides"].format(
            a=W["dice_contest_side"].format(who=me, roll=ra, target=ta, also="", word=word(la)),
            b=W["dice_contest_side"].format(who=them, roll=rb, target=tb, also=W["dice_contest_also"] if pa == pb else "", word=word(lb)))
        ma, mb = ta - ra, tb - rb
        by = c.get("by") or ("tier" if la != lb else "both_fail" if not pa else "margin" if ma != mb else "tie")
        if by == "tier":
            why = W["dice_contest_by_tier"].format(hi=word(la if ok else lb), lo=word(lb if ok else la))
        elif by == "margin":
            why = W["dice_contest_by_margin"].format(w=me if ok else them, mw=ma if ok else mb, l=them if ok else me, ml=mb if ok else ma)
        else:
            why = W.get(f"dice_contest_{by}") or W["dice_contest_tie"]
    else:  # a d20 contest: the one acting against the other's total
        sides = W["dice_contest_sides"].format(a=W["dice_contest_side_total"].format(who=me, roll=ra),
                                               b=W["dice_contest_side_total"].format(who=them, roll=rb))
        why = W["dice_contest_by_total"]
    res = result or W["dice_success" if ok else "dice_fail"]
    return W["dice_contest"].format(result=res, sides=sides, why=why, winner=winner)


def _state_line(ar: Any, reg: Any) -> str | None:
    """The beat's landed changes, read from the ApplyResult: variables from → to, moves, created and patched things."""
    def nm(i: Any) -> str:
        e = reg.entries.get(str(i)) if reg is not None else None
        return e.name if e is not None else str(i)

    parts: list[str] = []
    for a in getattr(ar, "applied", None) or []:
        op = a.get("op")
        if op in ("set", "add") and a.get("var"):
            parts.append(f"{a['var']} {a.get('from')}→{a.get('to')}")
        elif op == "move_to":
            parts.append(f"{nm(a.get('who'))} → {nm(a.get('to'))}")
        elif op == "patch":
            props = a.get("props") or {}
            parts.append(f"{nm(a.get('who'))} " + " ".join(f"{k}={(v or {}).get('to') if isinstance(v, dict) else v}" for k, v in props.items()))
        elif op in ("write", "rm", "flag", "remove"):
            parts.append(f"{op} {a.get('path') or a.get('key') or nm(a.get('who'))}")
    for c in getattr(ar, "created", None) or []:
        if isinstance(c, dict):
            parts.append(f"新 {c.get('class')} {nm(c.get('id')) if c.get('id') else c.get('name') or ''}".strip())
    return ("[state_update] " + " · ".join(_short(p, 40) for p in parts)) if parts else None


def resolve_text(root: Path, out: dict[str, Any], header: str, narration: str) -> str:
    """A landing beat: its header (the caller's: the beat's declared name, and why it came), the prose with each
    mid-prose tool and its answer where it happened, the landed state changes, and the options (a tool, so maybe none)."""
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    lines = [f"// {header}"]
    body = str(out.get("annotated") or narration or "")
    shown: list[str] = []
    for ln in body.splitlines():
        if re.fullmatch(r"\s*(\[~[^\]]+\]\s*)+", ln):
            continue  # the ops line annotate appends — the state line below says it readably
        m = re.match(r"^\[(?P<req>[^\]]+)\](?P<reason>[^\[<]*)(?:\[/[^\]]+\])?(?:<(?P<h>[\w.\-]+)>(?P<ans>.*?)</(?P=h)>)?\s*$", ln.strip())
        if m and m.group("req"):
            req = m.group("req")
            t = next((x for x in out.get("tool_returns") or [] if str(x.get("request") or "") == req), None)
            dl = _dice_line({**(t or {}), "reason": m.group("reason") or (t or {}).get("reason")}, _lang(root)) if t else None
            if dl:
                shown.append(dl)
            else:
                ans = (m.group("ans") or "").strip()
                shown.append(f"[{req}]" + (f" → {_short(ans, 70)}" if ans else ""))
            continue
        shown.append(ln)
    if narration and narration.split("\n", 1)[0].startswith("[") and narration.split("\n", 1)[0] not in shown:
        # the agreed checks' dice lines sit at the head of the plain narration
        head = [ln for ln in narration.splitlines() if ln.startswith("[") and "] →" in ln]
        shown = head + [x for x in shown if x not in head]
    lines += shown
    st = _state_line(out.get("apply"), reg)
    if st:
        lines.append(st)
    for i, o in enumerate(out.get("options") or [], 1):
        lines.append(f"{i}. {o}")
    return "\n".join(x for x in lines if x is not None)


def away_lines(reg: Any, turns: list[dict[str, Any]], lang: str = "zh") -> list[str]:
    """``// 异地 · 艾琳娜 @ 冒险者公会:……`` — one line per character elsewhere who took her own turn this beat
    (she is not in the player's prose, but the player sees that she is alive and where she went)."""
    from neonrp import prompts as _prompts

    label = str(_prompts.strings("beat_display", lang).get("away") or "elsewhere")  # the one label the player sees (C3-2)
    out: list[str] = []
    for a in away_items(reg, turns, lang):
        text = a["text"]
        out.append(f"// {label} · {a['name']}" + (f" @ {a['where']}" if a["where"] else "") + (f":{_short(text, 80)}" if text and text != "—" else ""))
    return out


def _names_town(place: str, town: str) -> bool:
    """「冒险者公会（碧石分部）」 already says 碧石镇; "Guild (Bishi branch)" already says Bishi Town — no suffix then."""
    stems = {town} | set(town.split()) | ({town[:-1]} if len(town) > 2 and " " not in town else set())
    return any(s and s in place for s in stems)


def away_items(reg: Any, turns: list[dict[str, Any]], lang: str = "zh") -> list[dict[str, str]]:
    """[{iid, name, where, text}] — each character elsewhere who took her own turn, with her WHOLE line (the prose line
    above is cut at 80; a renderer that folds it shows this one when opened, 10-08). A place in another town than the
    player's carries its town (10-23: 「冒险者公会」 read as the player's town's guild)."""
    from neonrp import prompts as _prompts

    in_town = str(_prompts.strings("beat_display", lang).get("away_place_in_town") or "{place} ({town})")
    out: list[dict[str, str]] = []
    for a in turns:
        text = " ".join(str(a.get("text") or "").split())
        env = reg.entries.get(a.get("iid")) if reg is not None else None
        where = ""
        if env is not None and env.parent:
            pe = reg.entries.get(env.parent)
            where = pe.name if pe is not None else str(env.parent)
            if pe is not None and pe.cls not in ("road", "town", "world") and pe.parent and pe.parent != getattr(reg, "current_town", None):
                tn = reg.entries.get(pe.parent)
                if tn is not None and tn.cls == "town" and not _names_town(pe.name, tn.name):
                    where = in_town.format(place=pe.name, town=tn.name)
        if not text and not where:
            continue
        out.append({"iid": str(a.get("iid") or ""), "name": str(a.get("name") or a.get("iid") or ""), "where": where, "text": text})
    return out
