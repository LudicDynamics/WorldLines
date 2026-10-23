"""Jev fills the JSON, sentence by sentence (experiment ``turn.solve.structured = jevjson``).

The written changes are the ground truth, not a preset table. The model says, one change per line, what
changed and why; then for each line:

  ① which of **our tools** it is — the rule pack's registered, world-changing tools (registry ActionSpec), each offered
     with its own registered description; or "only description, nothing changed"
  ② the JSON skeleton = that tool's registered ``fields``
  ③ each field one choice, the candidates taken **from the line itself** (the names, places, numbers, times, the
     "from A to B" parts, quoted words, phrases) plus what in the world those name
  ④ a line Jev is unsure of (a field under the bar, or "none of these") goes to the pseudo-code fallback, alone

Two Jev calls per beat whatever the world's size (all lines' ① together; all fields' ③ together).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

BAR = 0.5  # a choice below this is "unsure" → the line goes to the fallback
_FILE_OPS = {"write", "edit", "rm", "mkdir", "rmdir"}
_NUM = re.compile(r"(?<![\w.:：])[-+]?\d+(?:\.\d+)?(?![\w.:：])")
_TIME = re.compile(r"(?<!\d)(\d{1,2})[:：](\d{2})(?!\d)")
_ID = re.compile(r"\b[A-Za-z]+\d*/[\w\-]+\b|\b[A-Z]{2,}\d+\b")
_SPLIT = re.compile(r"[,，。.;；!！?？、()（）「」『』“”\"\[\]【】\n]")


def _L(root: Path) -> dict[str, Any]:
    from neonrp.core.output_lang import prompt_lang
    from neonrp.prompts import strings

    return strings("jev_json", prompt_lang(root))


def sentences(changes: str, nothing: list[str]) -> list[str]:
    out = []
    for ln in (changes or "").splitlines():
        t = re.sub(r"^\s*(?:[-*•]|\d+[.、)])\s*", "", ln).strip()
        if t and not any(t.rstrip("。.!").lower() == str(w).lower() for w in nothing):
            out.append(t)
    return out


def tools(reg: Any, lang: str) -> dict[str, dict[str, Any]]:
    """Our world-changing tools as registered: op → {fields, doc} (file tools left out — prose does not change files)."""
    out = {}
    for op, a in reg.actions.items():
        if not getattr(a, "enabled", True) or a.kind not in ("action", "update") or getattr(a, "scope", "world") != "world" or op in _FILE_OPS:
            continue
        doc = (a.doc_for(lang) if hasattr(a, "doc_for") else a.doc) or op  # lang → en → zh, the same pick as the prompt's op list
        out[op] = {"fields": list(a.fields or []), "doc": " ".join(str(doc).split())[:140]}
    return out


# ── candidates, out of the line ───────────────────────────────────────────────────────────────────────────────────────

def _phrases(s: str, connectors: list[str]) -> list[str]:
    parts = _SPLIT.split(s)
    if connectors:
        rx = re.compile("|".join(re.escape(c) for c in sorted(connectors, key=len, reverse=True)))
        parts = [q for p in parts for q in rx.split(p)]
    return list(dict.fromkeys(p.strip() for p in parts if 1 <= len(p.strip()) <= 24))


def _from_to(s: str, pairs: list[list[str]]) -> list[str]:
    """The B (and A) of 「从 A 变成 B」-like phrasings (the table gives the words per language)."""
    out: list[str] = []
    for a, b in pairs:
        for m in re.finditer(re.escape(a) + r"\s*(.{1,24}?)\s*" + re.escape(b) + r"\s*([^,，。.;；)）\n]{1,24})", s):
            out += [m.group(2).strip(), m.group(1).strip()]
    return out


def _entities(reg: Any, s: str, L: dict[str, Any]) -> dict[str, str]:
    """label → id: the entries the line names (people, places, things, statuses) + the player when the line says so."""
    out: dict[str, str] = {}
    if any(w in s for w in L.get("player_words") or []):
        out[str(L["player"])] = "player"
    for e in reg.entries.values():
        names = [str(e.name or "")] + [str(x) for x in (e.props.get("aliases") or []) if isinstance(e.props, dict)]
        if any(n and len(n) >= 2 and n in s for n in names) or (e.id and str(e.id) in s):
            out.setdefault(f"{e.name or e.id} ({e.id})", str(e.id))
    for w in reg.of_class("world"):
        out.setdefault(f"{L['world']} ({w.id})", str(w.id))
    return out


def _places(reg: Any, s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in list(reg.of_class("place")) + list(reg.of_class("town")):
        if (e.name and str(e.name) in s) or str(e.id) in s:
            out[f"{e.name} ({e.id})"] = str(e.id)
    for m in _ID.findall(s):
        if m in reg.entries:
            out.setdefault(m, m)
    return out


def _vars(reg: Any, ents: dict[str, str], s: str) -> dict[str, str]:
    ids = set(ents.values())
    out = {}
    for k, v in reg.variables.items():
        if getattr(v, "readonly", False):
            continue
        head = k.split(".")
        if (head[0] == "player" and "player" in ids) or (head[0] == "char" and len(head) > 2 and head[1] in ids) \
                or head[0] in ("time", "world", "table", "weather") or k in s:
            out[f"{k} = {v.value}"] = k
    return out


def _cands(field: str, s: str, reg: Any, L: dict[str, Any], doc: str) -> dict[str, str]:
    """label → value for one field of one line — one label per value (two labels for the same place split Jev's
    probability between them: 「冒险者公会 (T001/guild)」 and 「T001/guild」 each got half, 10-10)."""
    out: dict[str, str] = {}
    seen: set[str] = set()
    for label, value in _cands_raw(field, s, reg, L, doc).items():
        if str(value) in seen:
            continue
        seen.add(str(value))
        out[label] = value
    return out


def _cands_raw(field: str, s: str, reg: Any, L: dict[str, Any], doc: str) -> dict[str, str]:
    ph = _phrases(s, list(L.get("connectors") or []))
    nums = list(dict.fromkeys(_NUM.findall(s)))
    times = [f"{int(h):02d}:{m}" for h, m in _TIME.findall(s)]
    ft = _from_to(s, list(L.get("from_to") or []))
    ents, places = _entities(reg, s, L), _places(reg, s)
    if field in ("who", "a", "b"):
        return {**ents, **places}
    if field in ("to", "at", "parent", "links"):
        return {**places, **{p: p for p in ph}}
    if field == "var":
        return _vars(reg, ents, s)
    if field == "value":
        return {x: x for x in dict.fromkeys([*times, *ft, *nums, *ph])}
    if field == "delta":
        return {f"{sg}{n.lstrip('+-')}": f"{sg}{n.lstrip('+-')}" for n in nums for sg in ("+", "-")}
    if field == "class":
        return {c: c for c in reg.classes}
    if field == "kind":
        return {"class": "class"}
    if field in ("name", "key", "role", "outcome"):
        enum = re.findall(r"\b(\w+(?:\|\w+)+)\b", doc)
        if enum and field == "outcome":
            return {x: x for x in enum[0].split("|")}
        return {p: p for p in dict.fromkeys([*ft, *ph])}
    return {p: p for p in ph}


# ── one speculative Jev request (the official function-calling shape) ───────────────────────────────────────────────────

def parts() -> set[str]:
    """Ablation switches (``NEONRP_JEV_PARTS``): lines (the tag list, per line × per tool) · vars (the variable list) ·
    fallback (unsure lines → pseudo-code) · twocall (route first, then fields — the slow shape, for comparison)."""
    import os

    raw = os.environ.get("NEONRP_JEV_PARTS", "").strip()
    return {x.strip() for x in raw.split(",") if x.strip()} if raw else {"lines", "vars", "fallback"}


def _prob(ans: Any) -> float:
    if ans is None:
        return 0.0
    v = getattr(ans, "value", None)
    if getattr(ans, "type", "") == "noul" or isinstance(v, (int, float)) and not getattr(ans, "probabilities", None):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    pr = getattr(ans, "probabilities", None) or {}
    return float(pr.get(v, getattr(ans, "confidence", 0.0)) or 0.0)


def to_ops(root: Path, reg: Any, changes: str, narration: str) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """The written changes → (JSON changes, lines left for the fallback, log). One Jev request holds:
    the tag list — per line, one yes/no per registered tool (a line may be two changes); the speculative field
    questions — per line × tool × field, candidates from the line; the variable list — per relevant variable, changed? and
    to what. Code then keeps only the answers of the tools a line was tagged with; a call's confidence = its least sure
    field; under the bar → the line goes to the fallback."""
    from neonrp.core import system_one as s1
    from neonrp.core.output_lang import prompt_lang

    P = parts()
    L = _L(root)
    lang = prompt_lang(root)
    T = tools(reg, lang)
    none = str(L["none"])
    lines = sentences(changes, list(L.get("nothing") or []))
    log: dict[str, Any] = {"parts": sorted(P), "lines": [], "vars": [], "rounds": []}
    if not lines:
        return [], [], log
    fq = dict(L.get("field_q") or {})
    state = {"lines": lines, "story": narration[-1200:]}

    def qtext(i: int, op: str, field: str) -> str:
        q = fq.get(f"{op}.{field}") or str(L["q_field"]).replace("{field}", field).replace("{op}", op).replace("{doc}", T[op]["doc"]).replace("{line}", "")
        return f"`lines[{i}]` · {op}({T[op]['doc']}) · {q}"

    Q: dict[str, Any] = {}
    cands: dict[str, dict[str, str]] = {}
    if "lines" in P and T:
        for i, ln in enumerate(lines):
            for op, t in T.items():
                Q[f"t{i}.{op}"] = s1.noul(str(L["q_tag"]).replace("{i}", str(i)).replace("{op}", op).replace("{doc}", t["doc"]))
                if "twocall" in P:
                    continue
                for f in t["fields"]:
                    for sub in (("props_key", "props_value") if f == "props" else (f,)):
                        base = "name" if sub == "props_key" else ("value" if sub == "props_value" else sub)
                        c = _cands(base, ln, reg, L, t["doc"])
                        if sub == "props_key":
                            c = {**{k: k for k in (L.get("prop_keys") or [])}, **c}
                        if c:
                            key = f"f{i}.{op}.{sub}"
                            cands[key] = dict(list(c.items())[:40])
                            Q[key] = s1.choice(qtext(i, op, sub), {**cands[key], "none": none})
    vlist: dict[str, Any] = {}
    if "vars" in P:  # the variable list: what the world holds, asked against what was written
        allt = "\n".join(lines)
        ents = _entities(reg, allt, L)
        vlist = {k: reg.variables[k] for k in _vars(reg, ents, allt).values() if k in reg.variables}
        nums = list(dict.fromkeys(_NUM.findall(allt)))
        times = [f"{int(h):02d}:{m}" for h, m in _TIME.findall(allt)]
        for j, (k, v) in enumerate(vlist.items()):
            Q[f"v{j}"] = s1.noul(str(L["q_var"]).replace("{var}", k).replace("{now}", str(v.value)))
            opts: dict[str, str] = {}
            cur = v.value
            for n in nums:
                try:
                    c0, n0 = float(cur), float(n.lstrip("+"))
                    for val in (n0, c0 + n0, c0 - n0):
                        if val >= 0 and val != c0:
                            opts.setdefault(f"{val:g}", f"{val:g}")
                except (TypeError, ValueError):
                    opts.setdefault(n, n)
            for t_ in times:
                opts.setdefault(t_, t_)
            if opts:
                cands[f"vv{j}"] = dict(list(opts.items())[:40])
                Q[f"vv{j}"] = s1.choice(str(L["q_var_to"]).replace("{var}", k).replace("{now}", str(cur)), {**cands[f"vv{j}"], "none": none})
    if not Q:
        return [], (lines if "fallback" in P else []), log
    A = s1.ask(state, Q)
    log["rounds"].append({"n": len(Q), "q": {k: v.instructions for k, v in Q.items()}, "a": {k: getattr(v, "value", None) for k, v in (A or {}).items()}})
    if A is None:
        log["error"] = "jev unavailable"
        return [], (lines if "fallback" in P else []), log
    if "twocall" in P and "lines" in P:  # the two-step shape: fields asked only for the tagged tools
        Q2: dict[str, Any] = {}
        for i, ln in enumerate(lines):
            for op, t in T.items():
                if _prob(A.get(f"t{i}.{op}")) < 0.6:
                    continue
                for f in t["fields"]:
                    for sub in (("props_key", "props_value") if f == "props" else (f,)):
                        base = "name" if sub == "props_key" else ("value" if sub == "props_value" else sub)
                        c = _cands(base, ln, reg, L, t["doc"])
                        if c:
                            key = f"f{i}.{op}.{sub}"
                            cands[key] = dict(list(c.items())[:40])
                            Q2[key] = s1.choice(qtext(i, op, sub), {**cands[key], "none": none})
        A2 = s1.ask(state, Q2) if Q2 else {}
        log["rounds"].append({"n": len(Q2), "q": {k: v.instructions for k, v in Q2.items()}, "a": {k: getattr(v, "value", None) for k, v in (A2 or {}).items()}})
        A = {**A, **(A2 or {})}

    def pick(key: str) -> tuple[Any, float]:
        ans = A.get(key)
        v = getattr(ans, "value", None)
        if v in (None, "none"):
            return None, 0.0
        return cands.get(key, {}).get(v, v), _prob(ans)

    ops: list[dict[str, Any]] = []
    fallback: list[str] = []
    for i, ln in enumerate(lines):
        rec: dict[str, Any] = {"line": ln, "tags": {}, "calls": [], "fallback": None}
        log["lines"].append(rec)
        if "lines" not in P:
            continue
        tagged = sorted(((op, _prob(A.get(f"t{i}.{op}"))) for op in T), key=lambda x: -x[1])
        rec["tags"] = {op: round(p_, 2) for op, p_ in tagged[:4]}
        hits = [op for op, p_ in tagged if p_ >= 0.6]
        if not hits:
            if tagged and tagged[0][1] >= 0.35:  # something, but not sure which: the fallback writes it
                rec["fallback"] = "tag unsure"
                fallback.append(ln)
            continue
        for op in hits[:2]:
            o: dict[str, Any] = {"op": op}
            conf, fields = 1.0, []
            for f in T[op]["fields"]:
                if f == "props":
                    (k_, pk), (v_, pv) = pick(f"f{i}.{op}.props_key"), pick(f"f{i}.{op}.props_value")
                    fields += [("props_key", k_, pk), ("props_value", v_, pv)]
                    conf = min(conf, pk, pv)
                    if k_ is not None and v_ is not None:
                        o["props"] = {str(k_): v_}
                    continue
                v, pv = pick(f"f{i}.{op}.{f}")
                fields.append((f, v, pv))
                if f"f{i}.{op}.{f}" in Q or "twocall" in P:
                    conf = min(conf, pv)
                if v is not None:
                    sv = str(v).strip()
                    o[f] = int(sv) if re.fullmatch(r"[-+]?\d+", sv) and f in ("value", "delta") else (float(sv) if re.fullmatch(r"[-+]?\d+\.\d+", sv) and f in ("value", "delta") else v)
            call = {"tool": op, "fields": [{"field": f, "answer": v, "p": round(p_, 2)} for f, v, p_ in fields], "confidence": round(conf, 2)}
            rec["calls"].append(call)
            if conf >= BAR and all(o.get(f) is not None for f in T[op]["fields"] if f != "props") and (op != "patch" or "props" in o):
                o.update({"_from": "jev", "_line": ln})
                ops.append(o)
                call["json"] = {k: v for k, v in o.items() if not k.startswith("_")}
            else:
                call["json"] = None
        if rec["calls"] and not any(c.get("json") for c in rec["calls"]):  # none of its tagged tools came out whole
            rec["fallback"] = "field unsure"
            fallback.append(ln)
    if "vars" in P:  # the variable list catches what the lines did not turn into JSON
        for j, (k, v) in enumerate(vlist.items()):
            pc = _prob(A.get(f"v{j}"))
            val, pv = pick(f"vv{j}")
            row = {"var": k, "now": v.value, "changed": round(pc, 2), "to": val, "p": round(pv, 2), "json": None}
            log["vars"].append(row)
            if pc >= 0.6 and val is not None and pv >= BAR and not any(o.get("var") == k for o in ops):
                sv = str(val)
                o = {"op": "set", "var": k, "value": int(sv) if re.fullmatch(r"-?\d+", sv) else (float(sv) if re.fullmatch(r"-?\d+\.\d+", sv) else sv), "_from": "jev-var"}
                ops.append(o)
                row["json"] = {kk: vv for kk, vv in o.items() if not kk.startswith("_")}
    return ops, (list(dict.fromkeys(fallback)) if "fallback" in P else []), log
