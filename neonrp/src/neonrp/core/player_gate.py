"""Player gate: the player's words pass a gate before the world reads them. A small model (the judge's)
reads them against what the player can actually know — the prose on screen, the places on the map, their own bag
and contracts — and hands the world an intent, plus whatever the words claim beyond that knowledge (「讨伐狼人」 when
the player has only heard of beasts). Those are the player's words or guesses, never facts the world must make true.
Sits on top of the P0 understanding (rule-only, who is here); no judge model → no gate, the turn runs as before.

Every part is the template's to change (「每个 template 或后续的里面可以修改提示词」): the prompt spec's
``player_gate`` key (pack.json < manifest.json["prompt"] < game/meta/prompt.json, merged per field) —
``enabled`` (false = off) · ``system`` (the whole gate prompt; str or {lang: str}; must still ask for the JSON shape) ·
``extra`` (rules appended, e.g. 「玩家是穿越者,知道原作剧情」) · ``rule`` (what the world does with names out of nothing) ·
``seen_rule`` (what it does with names the player met before: by default it lands them) ·
``visible_classes`` (the registry classes the player can see; default carry, job) · ``claim_rule`` (what the world does
with what the player states as a world fact — 「天已经黑了」; by default: their account, the world keeps its clock)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from neonrp import prompts as _prompts

logger = logging.getLogger(__name__)

_SYS = _prompts.by_lang("player_gate", "_SYS")
# (head, intent, unseen head, unseen rule, seen head, seen rule, turn label, rumours, lore, names) — what the
# player names is grounded if it appeared anywhere the player could have met it (the prose of this playthrough, the
# world's rumours and lore, the names the world has); then saying it is emergence and the world should land it. Named
# out of nothing it is unphysical: the world does not make it because it was said. Heading off somewhere new is not
# naming — the world may grow a place there and names it itself.
# 10-03 (suite B4: 「我进镇的时候天已经黑了」 moved the clock 08:30 → 21:40): what the player states as a world fact is
# their attempt or their account, never the fact — the world keeps its own clock and rules
_CLAIMS = _prompts.by_lang("player_gate", "_CLAIMS")
_HEAD = _prompts.by_lang("player_gate", "_HEAD")
_BODY = _prompts.by_lang("player_gate", "_BODY")  # recent prose · places · what the player sees · the player's line · list sep


def corpus(root: Path, reg: Any, branch: str = "main", lang: str = "zh") -> list[tuple[str, str]]:
    """Everything the player could have met, with where: every turn's prose / options / panels of this playthrough,
    the world's rumours and lore, the names the registry knows. Deterministic, text only."""
    from neonrp.core.orchestration_trace import read_turn_traces

    h = _HEAD.get(lang, _HEAD["zh"])
    out: list[tuple[str, str]] = []
    try:
        traces = read_turn_traces(root, branch or "main")
    except Exception:  # noqa: BLE001
        traces = []
    for i, tr in enumerate(traces):
        ap = tr.get("apply") or {}
        panels = ap.get("panels") or {}
        txt = "\n".join([str(ap.get("narration_plain") or ""), " ".join(str(o) for o in ap.get("options") or []),
                         *[str(v.get("text") if isinstance(v, dict) else v) for v in (panels.values() if isinstance(panels, dict) else [])]])
        if txt.strip():
            out.append((h[6].format(n=tr.get("turn") or i + 1), txt))
    texts = getattr(reg, "texts", {}) or {}
    if texts.get("rumors"):
        out.append((h[7], str(texts["rumors"])))
    if texts.get("lore"):
        out.append((h[8], str(texts["lore"])))
    names = [e.name for e in getattr(reg, "entries", {}).values() if not str(e.id).startswith("~")]
    if names:
        out.append((h[9], "\n".join(names)))
    return out


def source_of(term: str, corp: list[tuple[str, str]]) -> str | None:
    t = term.strip().casefold()
    if len(t) < 2:
        return None
    return next((label for label, txt in corp if t in txt.casefold()), None)


def spec(root: Path) -> dict[str, Any]:
    from neonrp.core.adv import prompt_spec

    try:
        g = prompt_spec(root).get("player_gate")
    except Exception:  # noqa: BLE001
        g = None
    return g if isinstance(g, dict) else {}


def _pick(v: Any, lang: str) -> str:
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("zh") or next(iter(v.values()), "") or "")
    return str(v or "")


def _enabled(root: Path) -> bool:
    from neonrp.core import engine_config
    from neonrp.core import system_one as s1

    mode = str(engine_config.get(root, "turn.player_gate", "auto") or "auto").lower()
    if mode in ("off", "0", "false") or spec(root).get("enabled") is False:
        return False
    return s1.LLM_ADAPTER_FACTORY is not None or bool(s1.fallback_judge_preset())


def visible(reg: Any, history: list[Any] | None, n: int = 3, classes: list[str] | None = None, lang: str = "zh") -> str:
    """What the player can see: the last prose on screen (marks stripped), the map's places, their bag, their contracts."""
    from neonrp.core.sdk import strip_marks

    prose = []
    for h in (history or [])[-n:]:
        a = h.get("assistant", "") if isinstance(h, dict) else ""
        if a:
            prose.append(strip_marks(str(a))[-1500:])
    places = [e.name for e in reg.of_class("place") if not reg.current_town or e.id.startswith(reg.current_town + "/")]
    b = _BODY.get(lang) or _BODY["zh"]
    parts = [b[0] + "\n" + "\n---\n".join(prose) if prose else "", b[1] + "\n" + b[4].join(places[:40]) if places else ""]
    for c in classes if classes is not None else ["carry", "job"]:  # what the player can see, per template
        cs = reg.classes.get(c)
        if cs is None:
            continue
        rows = [f"{e.name}" + (f":{e.props['summary']}" if e.props.get("summary") else "") for e in reg.of_class(c)][:30]
        if rows:
            from neonrp.core.sdk import _loc

            parts.append(f"## {_loc(getattr(cs, 'title', ''), lang) or c}\n" + "\n".join(rows))
    return "\n\n".join(p for p in parts if p)


def gate(root: Path, reg: Any, user_text: str, history: list[Any] | None = None, *, branch: str = "main") -> dict[str, Any] | None:
    """{"intent", "named": [{said, source}], "block", "ms"} or None (off / no judge model / the model failed).
    The model only names; whether each name has a source is the engine's text search (``corpus`` / ``source_of``)."""
    import time

    if not (user_text or "").strip() or not _enabled(root):
        return None
    from neonrp.core import system_one as s1
    from neonrp.core.llm import Message
    from neonrp.core.output_lang import prompt_lang

    lang = prompt_lang(root)
    lang = lang if lang in _SYS else "zh"
    sp = spec(root)
    from neonrp.core.soul_view import player_name

    system = (_pick(sp.get("system"), lang) or _SYS[lang]).replace("{player}", player_name(reg))
    if sp.get("extra"):
        system += "\n" + _pick(sp["extra"], lang)
    vc = sp.get("visible_classes")
    t0 = time.monotonic()
    b = _BODY.get(lang) or _BODY["zh"]
    body = f"{b[2]}\n{visible(reg, history, classes=list(vc) if isinstance(vc, list) else None, lang=lang)}\n\n{b[3]}\n{user_text.strip()[:900]}"
    try:
        res = s1._llm_adapter().chat([Message(role="system", content=system), Message(role="user", content=body)])
        text = (getattr(getattr(res, "message", None), "content", None) or "").strip()
        i, j = text.find("{"), text.rfind("}")
        d = json.loads(text[i : j + 1]) if 0 <= i < j else {}
    except Exception:  # noqa: BLE001 — the gate never blocks a turn
        logger.debug("player gate failed", exc_info=True)
        return None
    intent = str(d.get("intent") or "").strip()
    raw = d.get("named") if isinstance(d.get("named"), list) else [b.get("said") if isinstance(b, dict) else b for b in d.get("beyond") or []]
    corp = corpus(root, reg, branch, lang)
    named: list[dict[str, Any]] = []
    for w in raw or []:
        w = str(w or "").strip()
        if w and w in user_text and w not in [x["said"] for x in named]:  # only words the player really used
            named.append({"said": w, "source": source_of(w, corp)})
    claims = [str(c).strip() for c in (d.get("claims") if isinstance(d.get("claims"), list) else []) if str(c or "").strip() and str(c).strip() in user_text]
    if not intent and not named and not claims:
        return None
    h = _HEAD[lang]
    lines = [h[0]]
    if intent:
        lines.append(f"{h[1]}:{intent}")
    unseen = [x for x in named if not x["source"]]
    seen = [x for x in named if x["source"]]
    if unseen:
        lines += [f"{h[2]}:", *[f"- 「{x['said']}」" for x in unseen], _pick(sp.get("rule"), lang) or h[3]]
    if seen:
        lines += [f"{h[4]}:", *[f"- 「{x['said']}」({x['source']})" for x in seen], _pick(sp.get("seen_rule"), lang) or h[5]]
    if claims:
        ch = _CLAIMS[lang]
        lines += [f"{ch[0]}:", *[f"- 「{c}」" for c in claims], _pick(sp.get("claim_rule"), lang) or ch[1]]
    seen = str(d.get("seen") or "").strip()
    return {"intent": intent, "named": named, "claims": claims, "seen": seen, "block": "\n".join(lines), "ms": round((time.monotonic() - t0) * 1000, 1),
            "custom": sorted(k for k in sp if k != "enabled")}
