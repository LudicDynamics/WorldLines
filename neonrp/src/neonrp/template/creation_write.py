"""The creation desk's AI on every text box (niko 10-25 「所有提示词请都能自动填写」): an empty box gets a draft written from
what the form already says and the world around it; a box with text can be rewritten / completed on request. One call
writes any number of boxes, so 「AI 填空着的栏」 is consistent across them (a new character's name in the ending text).

    POST …/<template>/creation/write {addition, card?, targets: [{key, sec, name, i?}], lang?}
      → {ok, fields: {key: text}, missing: [key]}

The boxes it may write are the form's own: the text / longtext fields of the sections the template opens (a character's
name · persona · appearance, a plot's title · stages · prompt, a clue, an ending, a rule's note), the reveal, and the card's
title / pitch in the desk language (the other languages are creation_translate's). Ids, enums and triggers are not text
(the trigger is 「用一句话说」's). The desk decides which boxes (never the creator's own unless they asked); this module only
writes them, and writes nothing to disk. Nothing in here knows a world: the world's names come from its files.
"""
from __future__ import annotations

import json
import re
from typing import Any

from neonrp.template.creation_translate import TranslateError, ask

MAX_TARGETS = 40
NOT_TEXT = ("collect_flag",)   # a flag key: an id, not prose
_REFS = 60                     # world names per kind in the prompt


def writable(t: Any) -> dict[str, set[str]]:
    """sec → the names of the text boxes the form opens (``reveal`` · ``card`` included)."""
    from neonrp.template import creation

    f = creation.form(t)
    out = {s["key"]: {x["name"] for x in s["fields"] if x.get("type") in ("text", "longtext", "list") and x["name"] not in NOT_TEXT}
           for s in f["sections"]}
    if f.get("reveal"):
        out["reveal"] = {"reveal"}
    if f.get("card"):
        out["card"] = set(f["card"])
    return {k: v for k, v in out.items() if v}


def _now(addition: dict[str, Any], card: dict[str, Any], lang: str, sec: str, name: str, i: int) -> str:
    if sec == "reveal":
        v = addition.get("reveal")
    elif sec == "card":
        v = (card.get(lang) or {}).get(name) if isinstance(card.get(lang), dict) else ""
    else:
        rows = addition.get(sec) if isinstance(addition.get(sec), list) else []
        v = rows[i].get(name) if 0 <= i < len(rows) and isinstance(rows[i], dict) else ""
    return "、".join(map(str, v)) if isinstance(v, list) else str(v or "").strip()


def norm(t: Any, addition: Any, card: Any, targets: Any, lang: str) -> list[dict[str, Any]]:
    """The asked boxes the form really opens → [{key, field, row?, now, lang}] (``now`` = its text, '' = write a draft).
    ``lang`` = what the box is written in: the card's box in the desk language (the other languages are
    creation_translate's), everything else in the work's own language — the plot holds one language, the one its
    template is authored in (an i18n/<lang>/plots layer is not written here: the run's narrator already speaks the run's
    language over the authored plot, and a layer per save would go stale with every edit)."""
    from neonrp.template import i18n as I

    work = I.source_lang(t)
    if not isinstance(addition, dict) or not isinstance(targets, list) or (card is not None and not isinstance(card, dict)):
        raise TranslateError("bad_body", "addition must be an object, targets a list")
    ok, out, seen = writable(t), [], set()
    for x in targets:
        if not isinstance(x, dict):
            continue
        key, sec, name = str(x.get("key") or ""), str(x.get("sec") or ""), str(x.get("name") or "")
        try:
            i = int(x.get("i") or 0)
        except (TypeError, ValueError):
            continue
        if not key or key in seen or name not in ok.get(sec, set()):
            continue
        seen.add(key)
        out.append({"key": key, "field": f"{sec}.{name}", **({"row": i} if sec not in ("reveal", "card") else {}),
                    "now": _now(addition, card or {}, lang, sec, name, i), "lang": lang if sec == "card" else work})
    if len(out) > MAX_TARGETS:
        raise TranslateError("too_long", f"at most {MAX_TARGETS} boxes")
    return out


def _world(t: Any, lang: str) -> dict[str, Any]:
    """What the world already is, as far as a box needs: its card in the desk language, the names of its places and
    characters, and the truth the template itself wrote (the creator is its author too — the desk shows it)."""
    from neonrp.template import creation, creation_assist as CA, i18n as I

    c = I.card(t, lang)
    refs = CA.world_refs(t)
    rv = creation.template_reveal(t)
    return {"title": str(c.get("title") or ""), "pitch": str(c.get("pitch") or ""),
            "places": [r["name"] for r in refs["places"][:_REFS]], "characters": [r["name"] for r in refs["characters"][:_REFS]],
            **({"truth": str(rv.get(lang) or next(iter(rv.values()), ""))[:3000]} if rv else {})}


def parse(raw: str, keys: list[str]) -> dict[str, str] | None:
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else None
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    d = d.get("fields") if isinstance(d.get("fields"), dict) else d
    return {k: str(d[k]).strip() for k in keys if isinstance(d.get(k), (str, int, float)) and str(d[k]).strip()}


def write(t: Any, addition: Any, targets: Any, *, card: Any = None, lang: str = "", adapter: Any = None) -> dict[str, Any]:
    """Write the asked boxes → {ok, fields, missing}. Nothing writable asked = no model call."""
    from neonrp import prompts
    from neonrp.template import creation_translate as CT, i18n as I

    lang = I.norm_lang(lang) or I.source_lang(t)
    items = norm(t, addition, card, targets, lang)
    if not items:
        return {"ok": True, "fields": {}, "missing": []}
    S = prompts.strings("creation_write", lang)
    guide = {f: S["fields"][f] for f in sorted({x["field"] for x in items}) if f in S["fields"]}
    draft = {"addition": {k: v for k, v in addition.items() if k not in ("orchestration",)}, "card": (card or {}).get(lang) or {}}
    user = str(S["user"]).format(world=json.dumps(_world(t, lang), ensure_ascii=False), draft=json.dumps(draft, ensure_ascii=False),
                                 guide=json.dumps(guide, ensure_ascii=False, indent=1),
                                 items="\n".join(json.dumps(x, ensure_ascii=False) for x in items))
    got = parse(ask(adapter or CT._adapter(), str(S["system"]), user), [x["key"] for x in items])
    if got is None:
        raise TranslateError("model", "the model did not answer in JSON")
    return {"ok": bool(got), "fields": got, "missing": [x["key"] for x in items if x["key"] not in got]}
