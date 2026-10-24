"""The creation desk's "say it in one sentence" (10-18 · PLATFORM-PLAY-RULES-1015 §10, §5 "no if / else for the author").

The creator says a rule or an idea in their own words; a small agent turns it into rows of the creation form — fields,
trigger conditions, collect conditions — using only what the template opens (:func:`creation.form`). It never touches
a file or the template: it returns a patch (the ops it applied, a preview the creator reads, the whole addition after
the patch, what :func:`creation.check` says about it). The desk writes it into the form only when the creator confirms;
saving goes through ``creation/work`` as before.

The agent's tools (one JSON object per model reply, prompts/creation_assist.<lang>.md)::

    {"tool": "read_form"}                         → the open sections + fields, trigger kinds, collect conditions,
                                                    the world's places / characters / endings, the draft so far
    {"tool": "propose", "ops": [op, ...]}         → each op applied to the draft or rejected (with why)
    {"tool": "check"}                             → creation.check of the draft
    {"tool": "done", "reply": "…", "unsupported": [{"what": "…", "nearest": "…"}]}

    op = {"op": "add", "sec": "rule", "row": {...}}
       | {"op": "set", "sec": "soul", "i": 0, "field": "collect", "value": "ending"}   (sec "reveal": no i / field)
       | {"op": "del", "sec": "clue", "i": 1}

Something the template does not open is rejected by the engine whatever the model says, and comes back in
``unsupported`` ("this template does not open X" + the nearest thing it does open, when the model named one).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neonrp.template import creation

MAX_STEPS = 6
SAY_MAX = 600


class AssistError(ValueError):
    """No model to ask, or nothing to ask it."""

    def __init__(self, code: str, msg: str) -> None:
        super().__init__(msg)
        self.code = code


def _s(lang: str) -> dict[str, Any]:
    from neonrp.prompts import strings

    return strings("creation_assist_lines", lang)


# ── what the agent may see ────────────────────────────────────────────────────

def world_refs(t: Any) -> dict[str, list[dict[str, str]]]:
    """The names a rule may point at: places (entry ids ``<town>/<node>``), characters (soul ids / NPC ids), the template's
    own endings. Read straight from the world's files and the overlay (the overlay wins) — never a world build: a cold
    build can take minutes on a busy machine, and the desk's own slot request may be building the same template."""
    from neonrp import template as TP

    out: dict[str, list[dict[str, str]]] = {"places": [], "characters": [], "endings": []}
    got: dict[str, dict[str, str]] = {"places": {}, "characters": {}}
    bases = [b for b in (TP.world_dir(t), TP.overlay_dir(t)) if b is not None]
    for b in bases:
        loc = Path(b) / "game" / "locations"
        for f in sorted(loc.glob("*/*/**/location.json")):   # nodes nest (a room inside a yard): the entry id is <town>/<node>
            town = f.relative_to(loc).parts[0]
            got["places"][f"{town}/{f.parent.name}"] = str(_jread(f).get("name") or f.parent.name)
        for f in sorted((Path(b) / "game" / "towns").glob("*/npcs.json")):
            for n in _jread(f).get("npcs") or []:
                if isinstance(n, dict) and n.get("id"):
                    got["characters"][str(n["id"])] = str(n.get("name") or n["id"])
    try:
        for r in TP.draw_souls(t, seed="", everyone=True):
            if r.get("sid"):
                got["characters"].setdefault(str(r["sid"]), str(r.get("name") or r["sid"]))
        for sid, sd in (TP._world_souls(TP.world_dir(t)) if TP.world_dir(t) is not None else {}).items():
            got["characters"].setdefault(str(sid), str(sd.get("name") or sid))
        rows = TP.asset_slots(t, classes=False)   # the template's own slots: no build behind them
    except Exception:  # noqa: BLE001 — a template that does not load cleanly still gets a form
        rows = []
    for r in rows:
        slot = str(r.get("slot") or "")
        if r.get("cls") == "ending" and ":ending:" in slot and "@" not in slot:
            out["endings"].append({"id": slot.rsplit(":", 1)[-1], "name": str(r.get("label") or "")})
        elif r.get("cls") in ("npc", "soul", "character") and slot.startswith("plot:") and r.get("inst"):
            got["characters"].setdefault(str(r["inst"]), str(r.get("label") or r["inst"]))
    for k in ("places", "characters"):
        out[k] = [{"id": i, "name": n} for i, n in got[k].items()]
    return out


def _jread(f: Path) -> dict[str, Any]:
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def context(t: Any, draft: dict[str, Any]) -> dict[str, Any]:
    """read_form: the open layer as the agent needs it, with the draft's rows numbered."""
    f, s = creation.form(t), creation.spec(t)
    return {"template": getattr(t, "id", ""),
            "sections": [{"key": x["key"], "fields": x["fields"]} for x in f["sections"]],
            "closed": [a for a in creation.ADD if a not in s["add"]],
            "triggers": s["triggers"], "collect": s["collect"],
            **({"reveal": f["reveal"]} if f.get("reveal") else {}),
            "world": world_refs(t), "draft": draft}


# ── ops ───────────────────────────────────────────────────────────────────────

def _fields(f: dict[str, Any], sec: str) -> dict[str, dict[str, Any]]:
    return {x["name"]: x for x in next((s["fields"] for s in f["sections"] if s["key"] == sec), [])}


def _row_problems(t: Any, sec: str, row: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(closed, other): what check says about this one row — closed = names the template does not open."""
    probs = [p for p in creation.check(t, {sec: [row]}) if p.startswith(f"{sec}[0]")]
    closed = [p for p in probs if "is not open" in p or "must be one of" in p]
    return closed, [p for p in probs if p not in closed]


def apply_op(t: Any, f: dict[str, Any], draft: dict[str, Any], op: Any) -> tuple[dict[str, Any] | None, str]:
    """Apply one op to ``draft`` in place → (the change for the preview, "") or (None, why it was rejected).
    why = "closed:<sec>" (the template does not open the section) · "closed:<problem>" (a trigger kind / option it does
    not open) · anything else = the op itself is malformed."""
    if not isinstance(op, dict):
        return None, "an op must be an object"
    kind, sec = str(op.get("op") or ""), str(op.get("sec") or "")
    if sec == "reveal":
        if not f.get("reveal"):
            return None, "closed:reveal"
        if kind not in ("set", "del"):
            return None, "reveal takes set / del"
        before, after = str(draft.get("reveal") or ""), "" if kind == "del" else str(op.get("value") or "").strip()
        if after:
            draft["reveal"] = after
        else:
            draft.pop("reveal", None)
        return {"op": "set", "sec": "reveal", "before": before, "after": after}, ""
    if sec not in creation.ADD or sec not in _keys(f):
        return None, f"closed:{sec}" if sec in creation.ADD else f"unknown section {sec!r}"
    rows = draft.setdefault(sec, [])
    names = _fields(f, sec)
    if kind == "add":
        row = op.get("row")
        if not isinstance(row, dict):
            return None, "add needs a row object"
        dropped = [k for k in row if k not in names]
        row = {k: v for k, v in row.items() if k in names}
        closed, _ = _row_problems(t, sec, row)
        if closed:
            return None, "closed:" + "; ".join(closed)
        rows.append(row)
        return {"op": "add", "sec": sec, "i": len(rows) - 1, "after": row, **({"dropped": dropped} if dropped else {})}, ""
    i = op.get("i")
    if not isinstance(i, int) or not 0 <= i < len(rows):
        return None, f"{sec}: no row {i!r} (have {len(rows)})"
    if kind == "del":
        return {"op": "del", "sec": sec, "i": i, "before": rows.pop(i)}, ""
    if kind != "set":
        return None, f"unknown op {kind!r} (add / set / del)"
    name = str(op.get("field") or "")
    if name not in names:
        return None, f"{sec}: no field {name!r} (fields: {', '.join(names)})"
    row = {**rows[i], name: op.get("value")}
    if op.get("value") in (None, ""):
        row.pop(name)
    closed, _ = _row_problems(t, sec, row)
    if closed:
        return None, "closed:" + "; ".join(closed)
    before = rows[i].get(name)
    rows[i] = row
    return {"op": "set", "sec": sec, "i": i, "field": name, "before": before, "after": op.get("value")}, ""


def _keys(f: dict[str, Any]) -> set[str]:
    return {s["key"] for s in f["sections"]}


# ── the preview the creator reads ─────────────────────────────────────────────

def _when(tr: dict[str, Any], s: dict[str, Any]) -> str:
    from neonrp.core import triggers as T

    n = T.normalize(tr)
    w = n.get("when") or {}
    kind = next((k for k in T.WHEN_KINDS if k in w), "")
    nm = s.get("_names") or {}   # entry / soul id → the name the creator knows it by
    head = s.get(f"w_{kind}", kind).replace("{v}", str(nm.get(str(w.get(kind)), w.get(kind)) if kind not in ("text", "turn") else ""))
    conds = []
    for c in n.get("if") or []:
        if not isinstance(c, dict):
            continue
        if "text" in c:
            conds.append(s["c_text"].replace("{v}", " / ".join(c["text"]) if isinstance(c["text"], list) else str(c["text"])))
        elif "flag" in c:
            conds.append(s["c_flag_not" if c.get("is") is False else "c_flag"].replace("{v}", str(c["flag"])))
        elif "var" in c:
            op = next((k for k in T.CMP_OPS if k in c), "")
            conds.append(f"{c['var']} {op} {c.get(op, '')}".strip())
        else:
            conds.append(json.dumps(c, ensure_ascii=False))
    then = []
    for e in n.get("then") or []:
        if not isinstance(e, dict):
            continue
        to = str(e.get("to") or "")
        v = {"narration": e.get("text"), "soul": f"{nm.get(str(e.get('who')), e.get('who', ''))}: {e.get('text', '')}", "flag": e.get("key"),
             "var": f"{e.get('var', '')} {'+' + str(e['add']) if 'add' in e else '= ' + str(e.get('set'))}", "end": e.get("ending")}.get(to, "")
        then.append(s.get(f"t_{to}", to).replace("{v}", str(v or "")))
    return s["rule_line"].replace("{when}", head).replace("{if}", (s["and"].join(conds) and s["if_sep"] + s["and"].join(conds)))\
        .replace("{then}", s["and"].join(then))


def _summary(sec: str, row: Any, s: dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return str(row)
    if sec == "rule" and isinstance(row.get("trigger"), dict):
        return _when(row["trigger"], s)
    bits = [str(row.get(k)) for k in ("name", "title") if row.get(k)]
    if row.get("collect"):
        target = row.get("collect_ending") or row.get("collect_flag") or ""
        bits.append(s.get(f"collect_{row['collect']}", row["collect"]).replace("{v}", str(target)))
    if row.get("kind"):
        bits.append(s.get(f"kind_{row['kind']}", row["kind"]))
    return " · ".join(bits) or json.dumps(row, ensure_ascii=False)


def preview(changes: list[dict[str, Any]], lang: str, names: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """One line per change: {op, sec, i?, field?, text} — text in the creator's language; ``names`` = place / character
    ids → their names (world_refs), so a rule reads «on entering the chapel», not the entry id."""
    s = {**_s(lang), "_names": names or {}}
    out = []
    for c in changes:
        sec, n = c["sec"], (c.get("i", 0) + 1)
        label = s.get(f"sec_{sec}", sec)
        if sec == "reveal":
            txt = s["line_reveal"].replace("{after}", c.get("after") or "—")
        elif c["op"] == "add":
            txt = s["line_add"].replace("{sec}", label).replace("{n}", str(n)).replace("{what}", _summary(sec, c["after"], s))
        elif c["op"] == "del":
            txt = s["line_del"].replace("{sec}", label).replace("{n}", str(n)).replace("{what}", _summary(sec, c["before"], s))
        else:
            fmt = lambda v: _summary(sec, {"trigger": v}, s) if c.get("field") == "trigger" and isinstance(v, dict) else str(v if v not in (None, "") else "—")  # noqa: E731
            txt = s["line_set"].replace("{sec}", label).replace("{n}", str(n)).replace("{field}", s.get(f"f_{c['field']}", c["field"]))\
                .replace("{before}", fmt(c.get("before"))).replace("{after}", fmt(c.get("after")))
        out.append({k: c[k] for k in ("op", "sec", "i", "field") if k in c} | {"text": txt})
    return out


def _closed_line(why: str, s: dict[str, Any]) -> str:
    """«this template does not open X» for a rejected op."""
    what = why[len("closed:"):]
    if what in creation.ADD or what == "reveal":
        return s["closed_sec"].replace("{x}", s.get(f"sec_{what}", what))
    for k, tag in (("trigger.when", "closed_when"), ("trigger.then", "closed_then")):
        if k in what:
            name = what.split("'")[1] if "'" in what else what
            return s[tag].replace("{x}", s.get(f"{'w' if 'when' in k else 't'}_{name}", name).replace("{v}", "").strip())
    if "must be one of " in what:
        field, _, opts = what.partition(": must be one of ")
        field = field.rsplit(".", 1)[-1]
        return s["closed_opt"].replace("{field}", s.get(f"f_{field}", field)).replace("{x}", opts.split(";")[0])
    return s["closed_other"].replace("{x}", what)


# ── the agent ─────────────────────────────────────────────────────────────────

def _parse(raw: str) -> dict[str, Any] | None:
    from neonrp.core.json_repair import loads_repaired

    txt = (raw or "").strip()
    if "```" in txt:
        txt = txt.split("```", 2)[1].removeprefix("json").strip() if txt.count("```") >= 2 else txt.replace("```", "")
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        obj = loads_repaired(txt[a:b + 1])
    except Exception:  # noqa: BLE001
        return None
    return obj if isinstance(obj, dict) else None


def _adapter() -> Any:
    try:
        from neonrp.core.hub_publish import adapter_for_preset

        a = adapter_for_preset(None)
    except Exception as exc:  # noqa: BLE001 — no model configured
        raise AssistError("no_model", str(exc)[:200]) from exc
    if type(a).__name__ == "StubAdapter":
        raise AssistError("no_model", "the configured model is the stub")
    return a


def assist(t: Any, addition: dict[str, Any] | None, say: str, *, lang: str = "zh", adapter: Any = None,
           max_steps: int = MAX_STEPS) -> dict[str, Any]:
    """Turn what the creator said into a patch of ``addition`` (never written anywhere) →
    {ok, reply, ops, preview, addition, problems, unsupported, steps, rule_text}. ``ok`` = something changed and check passes."""
    from neonrp import prompts

    say = str(say or "").strip()[:SAY_MAX]
    if not say:
        raise AssistError("empty", "say something first")
    if not creation.spec(t)["open"]:
        raise AssistError("closed", "this template does not open anything to creators")
    lang = lang if lang in prompts.LANGS else "zh"
    adapter = adapter or _adapter()
    s, f = _s(lang), creation.form(t)
    draft: dict[str, Any] = json.loads(json.dumps(addition or {}))
    system = prompts.text("creation_assist", lang)
    log: list[str] = [f"[say] {say}"]
    ops: list[Any] = []
    changes: list[dict[str, Any]] = []
    rejected: list[str] = []
    reply, said_unsupported, steps = "", [], 0
    for steps in range(1, max_steps + 1):
        try:
            out = adapter.generate(system, "\n\n".join(log))
        except Exception as exc:  # noqa: BLE001 — a model error ends the turn with what was applied so far
            reply = reply or s["model_error"].replace("{x}", str(exc)[:120])
            break
        # the adapter flags a reply it cannot read as a "proposal" as an error, raw text and all: this parser reads it itself
        raw = str(getattr(out, "raw_output", "") or getattr(out, "proposal_text", "") or "")
        if not raw and getattr(out, "error", None):
            reply = reply or s["model_error"].replace("{x}", str(out.error)[:120])
            break
        call = _parse(raw)
        log.append(f"[you] {raw.strip()[:2000]}")
        if call is None:
            log.append('[engine] {"error": "reply with exactly one JSON object: {\\"tool\\": …}"}')
            continue
        tool = str(call.get("tool") or "")
        if tool == "read_form":
            res: Any = context(t, draft)
        elif tool == "propose":
            res = {"applied": [], "rejected": []}
            for op in call.get("ops") or []:
                ch, why = apply_op(t, f, draft, op)
                if ch is None:
                    res["rejected"].append({"op": op, "why": why})
                    rejected.append(why)
                else:
                    ops.append(op)
                    changes.append(ch)
                    res["applied"].append(ch)
            res["problems"] = creation.check(t, draft)
        elif tool == "check":
            res = {"problems": creation.check(t, draft)}
        elif tool == "done":
            reply = str(call.get("reply") or "").strip()
            said_unsupported = [u for u in call.get("unsupported") or [] if isinstance(u, dict) and u.get("what")]
            break
        else:
            res = {"error": f"unknown tool {tool!r} (read_form / propose / check / done)"}
        log.append("[engine] " + json.dumps(res, ensure_ascii=False)[:6000])
    unsupported = [{"what": str(u["what"]), "nearest": str(u.get("nearest") or "")} for u in said_unsupported]
    for why in dict.fromkeys(w for w in rejected if w.startswith("closed:")):   # the engine's own word, model or not
        line = _closed_line(why, s)
        if not any(line == u["what"] for u in unsupported):
            unsupported.append({"what": line, "nearest": ""})
    clean = {k: v for k, v in draft.items() if v not in ([], None, "")}
    problems = creation.check(t, clean) if clean else []
    refs = world_refs(t)
    names = {r["id"]: r["name"] for k in ("places", "characters") for r in refs[k] if r.get("name")}
    s = {**s, "_names": names}
    return {"ok": bool(changes) and not problems, "reply": reply, "ops": ops, "preview": preview(changes, lang, names),
            "addition": clean, "problems": problems, "unsupported": unsupported, "steps": steps,
            "rule_text": [_summary("rule", r, s) for r in clean.get("rule") or []]}   # each rule in words (the form shows it read-only)
