"""Triggers — the world author's rules over the closed schema, as WHEN / IF / THEN / ELSE
(「值变动 → 条件 → then / else,不跳出 Register 框架」).

A rule is one row of the registry's fifth table (``game/meta/triggers.json`` via
``registry.register(root, "triggers", …)``, or ``manifest.json["triggers"]``). The engine
evaluates every row deterministically after ⑤ APPLY; nothing here calls an LLM.

    {"when": {"var": "player.gold"},                 # WHEN — what wakes the rule (one of):
             # {"entry": "T001/inn", "event": "enter", "who": "player"}   an entry event (enter/leave/talk/patch/created/inspect/pick)
             # {"entry": "Q001", "prop": "stage"}                        a typed prop changed
             # {"flag": "met_guard"}                                     a flag was set
             # {"text": "player" | "narration" | "both"}                 a text arrived this turn
             # {"turn": true}                                            every turn (poll; pair with `if` + once)
             # {"op": "advance", "who": "*"}                             an op landed (any registered op; payload = its applied record)
             # {"check": "急救"}                                           the player's check of that name was rolled this turn ("who" for another)
             #                                                             (any of its names; "*" any; payload = label / passed / level / total / vs)
     "if":   [{"var": "player.gold", "<": 3}],        # IF — conditions on the state after the change; all must hold
             # {"var": "trust.elena", "delta<=": -2}     change since before this apply
             # {"flag": "door_open"} / {"flag": "x", "is": false}
             # {"entry": "N009", "prop": "hp", "<=": 0}
             # {"text": "钥匙" | [...], "in": "player" | "narration" | "both"}
             # {"who": "player", "at": "T001/inn"}       someone is somewhere ("at": "player" = where the player stands; "is": false = not)
             # {"var": "talk.a", ">": {"var": "talk.b"}} the other side may be another variable
             # {"check": "急救", "passed": true}         a check of that name rolled this turn (+ "level": "crit" / "fumble" …, "who")
             # {"any": [c1, c2]}                          or-group
     "then": [{"to": "narration", "text": "钱袋快空了({after} 枚)。"},   # THEN — emits when `if` holds
              {"to": "soul", "who": "艾琳娜", "text": "玩家的钱快花光了", "important": true},
              {"to": "flag", "key": "broke"},
              {"to": "var", "var": "player.hp", "add": -1},
              {"to": "tool", "name": "referee", "args": {"check": "poverty"}},
              {"to": "end", "ending": "E01", "title": "…"},
              {"to": "move", "who": "镜子", "place": "T001"},          # a soul is moved by the world (no map judge)
              {"to": "status", "name": "噪蚀"} / {"to": "status", "name": "褪色", "remove": true},   # the player's effect
              {"to": "audio", "mood": "crisis", "bgm"?: <music>, "ambient"?: <bed>},   # what plays from now on (core/audio)
              {"to": "show", "slot": "G106"},                           # the screen shows one of the template's pictures (core/show)
              {"to": "form", "who": "xiulian", "form": "elder"},        # a soul takes another of her forms (soul.json `forms`)
              {"to": "log"}],
     "else": [],                                       # ELSE — emits when the rule woke but `if` did not hold
     "edge": true,                                     # `if` must have been false before (no repeat while it stays true)
     "once": false, "cooldown": 0, "enabled": true, "doc": "…"}

The 09-26 shape (``on`` + ``emit``, comparisons inside ``on``) is still accepted and normalised
into this one by :func:`normalize`; new rules are written in the four-word shape.

Every firing is recorded with its reason chain: what woke it, before → after, which conditions
held, what was emitted. A rule's own var / flag emits are state too, so the remaining rules are
re-evaluated (≤ CASCADE_DEPTH passes) inside the same apply.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name
from neonrp.core.registry import Registry, TriggerSpec

logger = logging.getLogger(__name__)

WHEN_VALUE = ("<", "<=", ">", ">=", "==", "!=")
WHEN_DELTA = ("delta<=", "delta>=", "changed")
CMP_OPS = ("<", "<=", ">", ">=", "==", "!=", "delta<=", "delta>=")
WHEN_KINDS = ("var", "entry", "flag", "text", "turn", "op", "check")
EVENTS = ("enter", "leave", "set", "created", "talk", "patch", "inspect", "pick")
CASCADE_DEPTH = 3  # passes per apply: a trigger's var/flag emit can wake at most two more layers
EMIT_TO = ("narration", "soul", "flag", "var", "tool", "log", "end", "move", "status", "audio", "show", "form")
_CHECKS = "checks.json"  # the checks rolled, by turn (core/tool_watch records them; `check` watches / conditions read them)

_INBOX = "trigger_inbox.json"
_STATE = "trigger_state.json"


def _meta(root: Path) -> Path:
    return root / get_data_dir_name(root) / "meta"


def _read(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── normalise (09-26 on/emit → when/if/then/else) ────────────────────────────

def normalize(spec: dict[str, Any]) -> dict[str, Any]:
    """Canonical four-word shape. Accepts the 09-26 ``on`` / ``emit`` / ``level`` shape."""
    out: dict[str, Any] = {k: v for k, v in spec.items() if k not in ("on", "emit", "level", "when", "if", "then", "else")}
    when = dict(spec.get("when") or {})
    conds = spec.get("if")
    conds = [] if conds is None else (list(conds) if isinstance(conds, list) else [conds])
    then = list(spec.get("then") or spec.get("emit") or [])
    on = spec.get("on")
    if isinstance(on, dict) and on and not when:
        if len([k for k in ("var", "entry", "flag", "keyword") if k in on]) != 1:
            when = dict(on)  # ambiguous legacy watch → validate reports it
        elif "keyword" in on:
            when = {"text": str(on.get("where") or "both")}
            conds.append({"text": on["keyword"], "in": str(on.get("where") or "both")})
        elif "var" in on:
            when = {"var": on["var"]}
            w = str(on.get("when") or "changed")
            if w in CMP_OPS:
                conds.append({"var": on["var"], w: on.get("value")})
        elif "entry" in on and "prop" in on:
            when = {"entry": on["entry"], "prop": on["prop"]}
            w = str(on.get("when") or "changed")
            if w in CMP_OPS:
                conds.append({"entry": on["entry"], "prop": on["prop"], w: on.get("value")})
        elif "entry" in on:
            when = {k: on[k] for k in ("entry", "event", "who") if k in on}
        elif "flag" in on:
            when = {"flag": on["flag"]}
        else:
            when = dict(on)
    out["when"], out["if"], out["then"], out["else"] = when, conds, then, list(spec.get("else") or [])
    out["edge"] = bool(spec.get("edge", not spec.get("level", False)))
    return out


# ── validation (shared with registry.register) ───────────────────────────────

def validate(reg: Registry | None, spec: dict[str, Any]) -> list[str]:
    """Problems with a trigger spec (empty = ok). ``reg`` None = skip reference checks."""
    probs: list[str] = []
    if not isinstance(spec, dict):
        return ["trigger must be an object"]
    n = normalize(spec)
    when = n["when"]
    if not when:
        return ["trigger needs a `when` (what wakes it): var / entry / flag / text / turn"]
    kinds = [k for k in WHEN_KINDS if k in when]
    if len(kinds) != 1:
        probs.append("`when` must name exactly one of var / entry / flag / text / turn")
    elif kinds[0] == "var":
        if reg is not None and str(when["var"]) not in reg.variables:
            probs.append(f"unknown variable {when['var']!r}")
    elif kinds[0] == "entry":
        if "prop" not in when and str(when.get("event") or "enter") not in EVENTS:
            probs.append(f"entry watch `event` must be one of {EVENTS}")
        if reg is not None and when["entry"] != "*" and not reg.resolve(str(when["entry"])):
            probs.append(f"unknown entry {when['entry']!r}")
    elif kinds[0] == "text":
        if str(when["text"]) not in ("player", "narration", "both"):
            probs.append("text watch must be player | narration | both")
    elif kinds[0] == "check":
        if not str(when["check"] or "").strip():
            probs.append("check watch needs a skill / attribute name (or *)")
    elif kinds[0] == "op":
        if not str(when["op"] or "").strip():
            probs.append("op watch needs an op name (or *)")
        elif reg is not None and when["op"] != "*" and str(when["op"]) not in reg.actions:
            probs.append(f"unknown op {when['op']!r}")
    for i, c in enumerate(n["if"]):
        probs += [f"if[{i}] {pr}" for pr in _validate_cond(reg, c)]
    if not n["then"] and not n["else"]:
        probs.append("trigger needs a non-empty `then` (or `else`) list")
    for branch in ("then", "else"):
        for i, e in enumerate(n[branch]):
            if not isinstance(e, dict) or str(e.get("to") or "") not in EMIT_TO:
                probs.append(f"{branch}[{i}].to must be one of {EMIT_TO}")
                continue
            to = e["to"]
            if to in ("narration", "soul") and not str(e.get("text") or "").strip():
                probs.append(f"{branch}[{i}] ({to}) needs `text`")
            if to == "soul" and reg is not None and not reg.resolve(str(e.get("who") or "")):
                probs.append(f"{branch}[{i}] unknown soul {e.get('who')!r}")
            if to == "flag" and not str(e.get("key") or "").strip():
                probs.append(f"{branch}[{i}] flag needs `key`")
            if to == "var":
                if not str(e.get("var") or "").strip() or not any(k in e for k in ("set", "add")):
                    probs.append(f"{branch}[{i}] var needs `var` + set|add")
                elif reg is not None and str(e["var"]) not in reg.variables:
                    probs.append(f"{branch}[{i}] unknown variable {e['var']!r}")
            if to == "tool" and not str(e.get("name") or "").strip():
                probs.append(f"{branch}[{i}] tool needs `name`")
            if to == "end" and not str(e.get("ending") or "").strip():
                probs.append(f"{branch}[{i}] end needs `ending` (an id; `title` optional)")
            if to == "move":
                if not str(e.get("who") or "").strip() or not str(e.get("place") or "").strip():
                    probs.append(f"{branch}[{i}] move needs `who` (a soul) + `place`")
                elif reg is not None and not reg.resolve(str(e["who"])):
                    probs.append(f"{branch}[{i}] unknown soul {e.get('who')!r}")
                elif reg is not None and not reg.resolve(str(e["place"])):
                    probs.append(f"{branch}[{i}] unknown place {e.get('place')!r}")
            if to == "status" and not str(e.get("name") or "").strip():
                probs.append(f"{branch}[{i}] status needs `name`")
            if to == "audio":
                if not any(k in e for k in ("mood", "bgm", "ambient")):
                    probs.append(f"{branch}[{i}] audio needs mood | bgm | ambient")
                elif "mood" in e and e["mood"] not in ("calm", "tense", "crisis", "default", None):
                    probs.append(f"{branch}[{i}] audio mood is calm | tense | crisis | default")
            if to == "show" and not str(e.get("slot") or "").strip():
                probs.append(f"{branch}[{i}] show needs `slot` (a slot id, or a plot entry's id / name)")
            if to == "form":
                if not str(e.get("who") or "").strip() or not str(e.get("form") or "").strip():
                    probs.append(f"{branch}[{i}] form needs `who` (a soul) + `form` (a key of her soul.json `forms`)")
                elif reg is not None and not reg.resolve(str(e["who"])):
                    probs.append(f"{branch}[{i}] unknown soul {e.get('who')!r}")
    if n.get("cooldown") is not None:
        try:
            int(n.get("cooldown") or 0)
        except (TypeError, ValueError):
            probs.append("cooldown must be an int")
    return probs


def _validate_cond(reg: Registry | None, c: Any) -> list[str]:
    if not isinstance(c, dict) or not c:
        return ["condition must be a non-empty object"]
    if "any" in c:
        if not isinstance(c["any"], list) or not c["any"]:
            return ["`any` needs a non-empty list"]
        return [f"any[{i}] {pr}" for i, sub in enumerate(c["any"]) for pr in _validate_cond(reg, sub)]
    ops = [k for k in CMP_OPS if k in c]
    if "check" in c:
        probs = [] if str(c["check"] or "").strip() else ["check condition needs a skill / attribute name (or *)"]
        if "passed" in c and not isinstance(c["passed"], bool):
            probs.append("check `passed` must be true|false")
        return probs
    if "var" in c:
        if len(ops) != 1:
            return [f"var condition needs exactly one of {CMP_OPS}"]
        if reg is not None and str(c["var"]) not in reg.variables:
            return [f"unknown variable {c['var']!r}"]
        other = c[ops[0]]
        if isinstance(other, dict):
            if set(other) != {"var"}:
                return ["a compared value is a literal or {\"var\": name}"]
            if reg is not None and str(other["var"]) not in reg.variables:
                return [f"unknown variable {other['var']!r}"]
        return []
    if "entry" in c and "prop" in c:
        if len(ops) != 1:
            return [f"prop condition needs exactly one of {CMP_OPS}"]
        if reg is not None and not reg.resolve(str(c["entry"])):
            return [f"unknown entry {c['entry']!r}"]
        return []
    if "flag" in c:
        return [] if isinstance(c.get("is", True), bool) else ["flag `is` must be true|false"]
    if "text" in c:
        kw = c["text"]
        ok = (isinstance(kw, str) and kw.strip()) or (isinstance(kw, list) and kw and all(isinstance(x, str) and x.strip() for x in kw))
        probs = [] if ok else ["text condition needs a non-empty string or list of strings"]
        if str(c.get("in") or "both") not in ("player", "narration", "both"):
            probs.append("text `in` must be player | narration | both")
        return probs
    if "at" in c:
        probs = []
        if reg is not None and str(c["at"]) != "player" and not reg.resolve(str(c["at"])):
            probs.append(f"unknown place {c['at']!r}")
        if reg is not None and str(c.get("who") or "player") != "player" and not reg.resolve(str(c.get("who"))):
            probs.append(f"unknown entity {c.get('who')!r}")
        return probs
    return ["condition must be one of var / entry+prop / flag / text / at / any"]


def _cmp(op: str, a: Any, v: Any) -> bool:
    try:
        if op in ("==", "!="):
            eq = (a == v) or (str(a) == str(v))
            return eq if op == "==" else not eq
        x, y = float(a), float(v)
    except (TypeError, ValueError):
        return False
    return {"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y}[op]


def snapshot(reg: Registry) -> dict[str, Any]:
    return {"vars": {k: v.value for k, v in reg.variables.items()}, "player": reg.player_location,
            "souls": {e.id: e.parent for e in reg.of_class("soul")},
            "props": {e.id: dict(e.props) for e in reg.entries.values() if reg.classes.get(e.cls) and reg.classes[e.cls].custom}}


def events_from_applied(applied: list[dict[str, Any]], created: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Discrete events this apply produced (entry / flag watches read these)."""
    ev: list[dict[str, Any]] = []
    for a in applied:
        if a.get("op") == "move_to":
            ev.append({"kind": "enter", "who": a.get("who"), "entry": a.get("to")})
        elif a.get("op") == "flag":
            ev.append({"kind": "set", "flag": a.get("key")})
        elif a.get("op") == "patch":
            ev.append({"kind": "patch", "who": a.get("who"), "entry": a.get("who")})
        elif a.get("op") == "talk":
            ev.append({"kind": "talk", "who": a.get("who"), "entry": a.get("who")})
        elif a.get("op") in ("inspect", "pick"):  # the player's structured action (when: {"entry": "I701", "event": "pick"})
            ev.append({"kind": a.get("op"), "who": a.get("who") or "player", "entry": a.get("what")})
    for c in created:
        ev.append({"kind": "created", "entry": c.get("id"), "cls": c.get("class")})
    for a in applied:  # P1 (09-27): every landed op is an event — the board games' natural wake source
        ev.append({"kind": "op", "name": a.get("op"), **{k: v for k, v in a.items() if k != "op"}})
    return ev


# ── WHEN ─────────────────────────────────────────────────────────────────────

def _when(reg: Registry, when: dict[str, Any], before: dict[str, Any], after: dict[str, Any],
          events: list[dict[str, Any]], texts: dict[str, str], depth: int) -> tuple[bool, str, dict[str, Any]]:
    """Did the thing this rule watches happen in this apply? → (woke, why, payload)."""
    payload: dict[str, Any] = {}
    if "var" in when:
        name = str(when["var"])
        b, a = before["vars"].get(name), after["vars"].get(name)
        payload.update({"var": name, "before": b, "after": a})
        return (a != b), (f"{name} 变了:{b} → {a}" if a != b else f"{name} 没变({a})"), payload
    if "entry" in when and "prop" in when:
        tid = reg.resolve(str(when["entry"])) or str(when["entry"])
        name = str(when["prop"])
        b, a = (before.get("props") or {}).get(tid, {}).get(name), (after.get("props") or {}).get(tid, {}).get(name)
        payload.update({"entry": tid, "prop": name, "before": b, "after": a})
        return (a != b), (f"{tid}.{name} 变了:{b} → {a}" if a != b else f"{tid}.{name} 没变({a})"), payload
    if "entry" in when:
        target = str(when["entry"])
        tid = reg.resolve(target) if target != "*" else "*"
        want = str(when.get("event") or "enter")
        who = when.get("who")
        for e in events:
            if e.get("kind") != want:
                continue
            ent = e.get("entry")
            if tid != "*" and reg.resolve(str(ent or "")) != tid and ent != tid:
                continue
            if who and str(who) != "*" and (reg.resolve(str(who)) or who) != (e.get("who") or ""):
                continue
            payload.update({"entry": ent, "who": e.get("who"), "event": want})
            return True, f"{e.get('who') or '—'} {want} {ent}(规则:{target})", payload
        return False, f"本回合没有 {want} {target}", payload
    if "flag" in when:
        key = str(when["flag"])
        b, a = before["vars"].get(f"flag.{key}"), after["vars"].get(f"flag.{key}")
        payload.update({"flag": key, "before": b, "after": a})
        hit = any(e.get("kind") == "set" and e.get("flag") == key for e in events) or bool(a and not b)
        return hit, (f"flag {key} 被设为 true" if hit else f"flag {key} 未设"), payload
    if "text" in when:
        where = str(when["text"])
        srcs = ("player", "narration") if where == "both" else (where,)
        hit = any((texts.get(x) or "").strip() for x in srcs)
        return hit, ("有" if hit else "没有") + "新文本(" + "/".join(srcs) + ")", payload
    if "op" in when:
        want = str(when["op"])
        who = when.get("who")
        for e in events:
            if e.get("kind") != "op" or (want != "*" and e.get("name") != want):
                continue
            if who and str(who) != "*" and (reg.resolve(str(who)) or who) != (e.get("who") or ""):
                continue
            payload.update({k: v for k, v in e.items() if k != "kind"})
            return True, f"op {e.get('name')} 落地" + (f"(who={e.get('who')})" if e.get("who") else ""), payload
        return False, f"本回合没有 op {want}", payload
    if "check" in when:
        for ck in texts.get("_checks") or []:  # type: ignore[union-attr]
            if _check_is(ck, str(when["check"])) and _check_by(reg, ck, when.get("who")):
                payload.update({k: ck.get(k) for k in ("label", "passed", "level", "total", "vs", "who")})
                return True, f"检定 {ck.get('label')} 掷出 {ck.get('total')}" + (f" vs {ck.get('vs')}" if ck.get("vs") is not None else ""), payload
        return False, f"本回合没有 {when['check']} 检定", payload
    if "turn" in when:
        return True, "每回合", payload  # wakes on every pass, so a cascade's changes are seen too
    return False, "规则无 when", payload


def _check_by(reg: Registry, ck: dict[str, Any], who: Any) -> bool:
    """Whose roll: the player's unless the rule names someone ("*" = anyone)."""
    w = str(who or "player")
    return w == "*" or str(ck.get("who") or "player") == (w if w == "player" else (reg.resolve(w) or w))


def _check_is(ck: dict[str, Any], name: str) -> bool:
    """A recorded check answers to this name: "*", its label, or any name of its rule row (every language)."""
    n = name.strip().casefold()
    return n == "*" or n in {str(x).casefold() for x in [ck.get("label"), *(ck.get("names") or [])] if x}


# ── IF ───────────────────────────────────────────────────────────────────────

def _cond(reg: Registry, c: dict[str, Any], before: dict[str, Any], state: dict[str, Any],
          texts: dict[str, str], payload: dict[str, Any]) -> tuple[bool, str]:
    """One condition against a snapshot (`state`); delta / text conditions also look at `before` / the turn's texts."""
    if "any" in c:
        parts = [_cond(reg, sub, before, state, texts, payload) for sub in c["any"]]
        ok = any(p[0] for p in parts)
        return ok, "(" + " 或 ".join(p[1] for p in parts) + ")"
    if "check" in c:  # like text: what was rolled this turn (never "held before")
        for ck in texts.get("_checks") or []:  # type: ignore[union-attr]
            if not _check_is(ck, str(c["check"])):
                continue
            if "passed" in c and (ck.get("passed") is None or bool(ck.get("passed")) != bool(c["passed"])):
                continue  # a plain roll under a name (「绝笔」 damage) has no pass / fail
            if "level" in c and str(ck.get("level") or "") not in ([c["level"]] if isinstance(c["level"], str) else list(c["level"])):
                continue
            if not _check_by(reg, ck, c.get("who")):
                continue
            return True, f"检定 {ck.get('label')} {'成功' if ck.get('passed') else '失败'}({ck.get('level') or ck.get('total')})"
        return False, f"本回合没有符合的 {c['check']} 检定"
    if "var" in c:
        name = str(c["var"])
        op = next(k for k in CMP_OPS if k in c)
        v = c[op]
        if isinstance(v, dict) and "var" in v:  # the other side is a variable too
            v = state["vars"].get(str(v["var"]))
        a = state["vars"].get(name)
        if op.startswith("delta"):
            try:
                delta = float(a) - float(before["vars"].get(name))
            except (TypeError, ValueError):
                return False, f"{name} 不是数"
            payload.setdefault("delta", delta)
            ok = delta <= float(v) if op == "delta<=" else delta >= float(v)
            return ok, f"{name} 变化 {delta:+g} {op[5:]} {v} " + ("成立" if ok else "不成立")
        ok = _cmp(op, a, v)
        return ok, f"{name} = {a} {op} {v} " + ("成立" if ok else "不成立")
    if "entry" in c and "prop" in c:
        tid = reg.resolve(str(c["entry"])) or str(c["entry"])
        name = str(c["prop"])
        op = next(k for k in CMP_OPS if k in c)
        a = (state.get("props") or {}).get(tid, {}).get(name)
        ok = _cmp(op, a, c[op]) if not op.startswith("delta") else False
        return ok, f"{tid}.{name} = {a} {op} {c[op]} " + ("成立" if ok else "不成立")
    if "flag" in c:
        key = str(c["flag"])
        want = bool(c.get("is", True))
        a = bool(state["vars"].get(f"flag.{key}"))
        return a == want, f"flag {key} {'已设' if a else '未设'}" + ("" if a == want else "(要的是相反)")
    if "text" in c:
        kws = [c["text"]] if isinstance(c["text"], str) else list(c["text"])
        where = str(c.get("in") or "both")
        for w in kws:
            for src in (("player", "narration") if where == "both" else (where,)):
                if w and w.lower() in (texts.get(src) or "").lower():
                    payload.update({"keyword": w, "where": src})
                    return True, f"「{w}」出现在{'玩家的话' if src == 'player' else '叙事'}里"
        return False, f"关键词 {kws} 没出现"
    if "at" in c:
        place = state.get("player") if str(c["at"]) == "player" else (reg.resolve(str(c["at"]), cls="place") or str(c["at"]))
        who = str(c.get("who") or "player")
        here = state.get("player") if who == "player" else (state.get("souls") or {}).get(reg.resolve(who) or who)
        ok = (here == place) == bool(c.get("is", True))  # "is": false = not there
        return ok, f"{who} 在 {here}" + ("" if here == place else f",不在 {place}")
    return False, "条件无法识别"


def _if(reg: Registry, conds: list[dict[str, Any]], before: dict[str, Any], after: dict[str, Any],
        texts: dict[str, str], payload: dict[str, Any]) -> tuple[bool, bool, list[str]]:
    """(holds now, held before, why). Text conditions never 'held before' — text is new each turn."""
    if not conds:
        return True, False, []
    now, why = [], []
    for c in conds:
        ok, w = _cond(reg, c, before, after, texts, payload)
        now.append(ok)
        why.append(w)
    was = all(_cond(reg, c, before, before, {"player": "", "narration": ""}, {})[0] for c in conds)
    return all(now), was, why


def _fmt(text: str, payload: dict[str, Any]) -> str:
    class _D(dict):
        def __missing__(self, k: str) -> str:
            return "{" + k + "}"
    try:
        return text.format_map(_D(payload))
    except (ValueError, IndexError):
        return text


def run(root: Path, reg: Registry, before: dict[str, Any], res: Any, *, turn: int,
        narration: str = "", player_says: str = "") -> list[dict[str, Any]]:
    """Evaluate every enabled rule: WHEN woke? → IF holds (edge: and did not hold before)? → THEN, else ELSE.
    Then re-evaluate the rest against the emits' own changes (≤ CASCADE_DEPTH passes). Record reason chains."""
    if not getattr(reg, "triggers", None):
        return []
    t0 = time.perf_counter()
    after = snapshot(reg)
    events = events_from_applied(res.applied, res.created)
    heard = checks_of(root, turn)
    texts: dict[str, Any] = {"player": player_says or "", "narration": narration or "", "_checks": heard}
    state = _read(_meta(root) / _STATE)
    fired: list[dict[str, Any]] = []
    for depth in range(CASCADE_DEPTH):
        done = {f["trigger"] for f in fired}
        cascaded = False
        for tid, spec in reg.triggers.items():
            if not spec.enabled or tid in done:
                continue
            woke, why_when, payload = _when(reg, spec.when, before, after, events, texts, depth)
            if not woke:
                continue
            st = state.get(tid) or {}
            holds, held, why_if = _if(reg, spec.cond, before, after, texts, payload)
            why = [f"when:{why_when}"] + [f"if:{w}" for w in why_if]
            if depth:
                why.append(f"由上一层规则的改动引出(第 {depth + 1} 层)")
            stateful = ("var" in spec.when) or ("prop" in spec.when) or ("turn" in spec.when)
            if holds and held and spec.edge and stateful:  # edge: only when `if` turned true in this apply
                why.append("条件在改动前已成立,边沿规则不重复")
                continue
            branch = "then" if holds else "else"
            emits = spec.then if holds else spec.else_
            if not emits:
                continue
            if branch == "then":
                if spec.once and st.get("count"):
                    why.append("once=true 且已触发过 → 不再触发")
                    continue
                if spec.cooldown and st.get("last_turn") is not None and turn - int(st["last_turn"]) <= spec.cooldown:
                    why.append(f"冷却中(上次回合 {st['last_turn']},冷却 {spec.cooldown})→ 不触发")
                    continue
            emitted = _emit(root, reg, spec, emits, payload, res, turn=turn)
            rec = {"trigger": tid, "turn": turn, "branch": branch, "why": why, "payload": payload, "emitted": emitted, "doc": spec.doc}
            fired.append(rec)
            if branch == "then":
                state[tid] = {"count": int(st.get("count", 0)) + 1, "last_turn": turn}
            cascaded = cascaded or any(e.get("to") in ("var", "flag") for e in emitted)
        if not cascaded:
            break
        before, after, events, texts = after, snapshot(reg), [], {"player": "", "narration": ""}
    if fired:
        _write(_meta(root) / _STATE, state)
    if heard:  # a check is heard by one apply only
        d = _read(_meta(root) / _CHECKS)
        for i in d.get("items") or []:
            if isinstance(i, dict) and i in heard:
                i["used"] = True
        _write(_meta(root) / _CHECKS, d)
    res.ms_triggers = round((time.perf_counter() - t0) * 1000, 1)
    return fired


def _emit(root: Path, reg: Registry, spec: TriggerSpec, emits: list[dict[str, Any]], payload: dict[str, Any], res: Any, *, turn: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in emits:
        to = e.get("to")
        try:
            if to == "narration":
                text = _fmt(str(e.get("text") or ""), payload)
                inbox = _read(_meta(root) / _INBOX)
                items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
                items.append({"turn": turn, "trigger": spec.id, "kind": "event", "text": text})
                inbox["items"] = items[-30:]
                _write(_meta(root) / _INBOX, inbox)
                out.append({"to": "narration", "text": text})
            elif to == "soul":
                who = reg.resolve(str(e.get("who") or "")) or str(e.get("who") or "")
                text = _fmt(str(e.get("text") or ""), payload)
                sdir = _soul_dir(root, who)
                if sdir is None:
                    out.append({"to": "soul", "who": who, "error": "soul dir not found"})
                    continue
                path = sdir / "short-term-memo" / "recent_events.json"
                memo = _read(path)
                evs = memo.get("events") if isinstance(memo.get("events"), list) else []
                evs.append({"turn": turn, "event": text, "my_reaction": "", "affect": "", "by": f"engine.trigger:{spec.id}",
                            **({"important": True} if e.get("important") else {})})
                memo["events"] = evs[-40:]
                _write(path, memo)
                out.append({"to": "soul", "who": who, "text": text})
            elif to == "flag":
                from neonrp.core.sdk import _apply_update

                _apply_update(root, {"op": "flag", "key": str(e["key"])}, reg, res)
                out.append({"to": "flag", "key": e["key"]})
            elif to == "var":
                from neonrp.core.sdk import _apply_update

                op = {"op": "add", "var": str(e["var"]), "delta": int(e["add"])} if "add" in e else {"op": "set", "var": str(e["var"]), "value": e["set"]}
                _apply_update(root, op, reg, res)
                out.append({"to": "var", **{k: v for k, v in op.items() if k != "op"}})
            elif to == "tool":
                req = {"kind": "tool", "name": str(e.get("name")), "args": dict(e.get("args") or {}), "trigger": spec.id, "payload": payload}
                res.requests.append(req)
                out.append({"to": "tool", "name": req["name"]})
            elif to == "end":
                # an ending: the playthrough is marked, the world hears it once (epilogue next solve), `ended` flag set
                eid = str(e.get("ending"))
                t_ = e.get("title")
                if isinstance(t_, dict):  # a pack's {zh, en, ja, ko} title: the run's language (10-16)
                    from neonrp.core.output_lang import pick_lang, prompt_lang

                    t_ = pick_lang(t_, prompt_lang(root))
                title = _fmt(str(t_ or eid), payload)
                if not (_meta(root) / "ending.json").exists():
                    _write(_meta(root) / "ending.json", {"id": eid, "title": title, "turn": turn, "trigger": spec.id, "why": _fmt(str(e.get("text") or ""), payload)})
                    inbox = _read(_meta(root) / _INBOX)
                    items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
                    items.append({"turn": turn, "trigger": spec.id, "kind": "end", "id": eid, "title": title,
                                  "text": f"结局「{title}」已触发:这一段是尾声,把这条线收住,不再开新的事。" + (" " + _fmt(str(e.get("text")), payload) if e.get("text") else "")})
                    inbox["items"] = items[-30:]
                    _write(_meta(root) / _INBOX, inbox)
                    from neonrp.core.sdk import _apply_update

                    _apply_update(root, {"op": "flag", "key": "ended"}, reg, res)
                    res.ended = {"id": eid, "title": title, "turn": turn, "trigger": spec.id}
                out.append({"to": "end", "ending": eid, "title": title})
            elif to == "move":
                from neonrp.core.sdk import _apply_action

                who = reg.resolve(str(e.get("who") or "")) or str(e.get("who") or "")
                place = reg.resolve(str(e.get("place") or "")) or str(e.get("place") or "")
                if reg.entries.get(who) is not None and reg.entries[who].parent == place:
                    out.append({"to": "move", "who": who, "place": place, "stayed": True})
                    continue
                _apply_action(root, {"op": "move_to", "who": who, "to": place, "by": f"trigger:{spec.id}"}, reg, res, writers="on")
                out.append({"to": "move", "who": who, "place": place})
            elif to == "status":
                out.append(_emit_status(root, reg, res, e))
            elif to == "audio":  # 10-15: the music / bed from this beat on (core/audio)
                from neonrp.core import audio as _audio

                out.append(_audio.set_author(root, e, turn=turn, by=f"trigger:{spec.id}"))
            elif to == "show":  # 10-16: a picture at a story moment, not only on arrival (core/show)
                from neonrp.core import show as _show

                hit = _show.resolve(root, reg, str(e.get("slot") or ""))
                if hit is None:
                    out.append({"to": "show", "slot": e.get("slot"), "error": "no such slot in this template"})
                    continue
                _show.queue(root, {**hit, "by": f"trigger:{spec.id}"})
                out.append({"to": "show", "slot": hit["slot"]})
            elif to == "form":
                out.append(_emit_form(root, reg, e))
            else:
                out.append({"to": "log"})
        except Exception as exc:  # noqa: BLE001 — one emit failing never kills the turn
            logger.warning("trigger %s emit %s failed: %s", spec.id, to, exc, exc_info=True)
            out.append({"to": to, "error": str(exc)[:160]})
    return out


def _emit_form(root: Path, reg: Registry, e: dict[str, Any]) -> dict[str, Any]:
    """A soul takes another of her forms (10-16, 归乡: 莲妹 → 秀莲婆). Her run copy's ``soul.json`` declares them::

        "forms": {"elder": {"name": "Granny Xiulian", "name_local": "秀莲婆", "summary": "…", "charter": "forms/elder/soul.md"}}

    The names change (the old ones stay aliases, so ``@莲妹`` still finds her), ``character/profile.json`` follows, and
    ``charter`` (a file in her folder) becomes her ``soul.md`` — what the character agent reads first, so she speaks as
    that form from now on. Portrait / voice stay. Taking the form she already has is a no-op."""
    who = reg.resolve(str(e.get("who") or "")) or str(e.get("who") or "")
    form = str(e.get("form") or "")
    sdir = _soul_dir(root, who)
    if sdir is None:
        return {"to": "form", "who": who, "error": "soul dir not found"}
    sj = _read(sdir / "soul.json")
    fs = (sj.get("forms") or {}).get(form) if isinstance(sj.get("forms"), dict) else None
    if not isinstance(fs, dict):
        return {"to": "form", "who": who, "form": form, "error": f"no form {form!r} in her soul.json"}
    if sj.get("form") == form:
        return {"to": "form", "who": who, "form": form, "stayed": True}
    was = [str(sj.get(k) or "") for k in ("name_local", "name")]
    for k in ("name", "name_local", "intro_i18n"):
        if fs.get(k):
            sj[k] = fs[k]
    now = {str(sj.get("name_local") or ""), str(sj.get("name") or "")}
    sj["aliases"] = [a for a in dict.fromkeys([*(sj.get("aliases") or []), *was]) if a and a not in now]
    sj["form"] = form
    _write(sdir / "soul.json", sj)
    prof_p = sdir / "character" / "profile.json"
    if prof_p.is_file():
        prof = _read(prof_p)
        prof.update({"display_name": sj.get("name_local") or sj.get("name"), "name_local": sj.get("name_local") or prof.get("name_local")})
        if fs.get("summary"):
            prof["summary"] = fs["summary"]
        _write(prof_p, prof)
    charter = sdir / str(fs.get("charter") or "")
    if fs.get("charter") and charter.is_file():
        (sdir / "soul.md").write_text(charter.read_text(encoding="utf-8"), encoding="utf-8")
    return {"to": "form", "who": who, "form": form, "name": sj.get("name_local") or sj.get("name"), "was": was[0] or was[1]}


def _emit_status(root: Path, reg: Registry, res: Any, e: dict[str, Any]) -> dict[str, Any]:
    """The player's effect by name: added (completed from the world's status line, like the narrator's ``new status``)
    unless one of that name is on already; ``remove: true`` takes every one of that name off."""
    from neonrp.core.sdk import _apply_action, _apply_update

    name = str(e.get("name") or "").strip()
    have = [x for x in reg.of_class("status") if x.name == name]
    if e.get("remove"):
        for x in have:
            _apply_update(root, {"op": "remove", "who": x.id}, reg, res)
        return {"to": "status", "name": name, "removed": len(have)}
    if have or "status" not in reg.classes:
        return {"to": "status", "name": name, "kept": bool(have)}
    props = {"name": name, **{k: v for k, v in e.items() if k in ("turns", "check", "each", "note", "rule", "hours")}}
    _apply_action(root, {"op": "new", "class": "status", "name": name, "props": props}, reg, res, writers="on")
    return {"to": "status", "name": name}


def enter_refused(root: Path, reg: Registry, who: str, cur: str | None, place: str) -> str | None:
    """A place's own way in (``enter_if`` in its location.json: the conditions of a trigger's `if`, all must hold) for the
    player's move: None = may enter, else why not (its ``enter_refused`` line, {lang: line} or a string). ``"at"`` reads
    where the player stands before the step (「from the tunnel」), so an island at high tide can still be reached from
    below. Souls are the world's to move; only the player is stopped."""
    e = reg.entries.get(place)
    conds = (e.props.get("enter_if") if e is not None else None) or []
    if who != "player" or not isinstance(conds, list) or not conds:
        return None
    state = snapshot(reg)
    state["player"] = cur
    ok = all(_cond(reg, c, state, state, {"player": "", "narration": ""}, {})[0] for c in conds if isinstance(c, dict))
    if ok:
        return None
    why = e.props.get("enter_refused")
    if isinstance(why, dict):
        from neonrp.core.output_lang import prompt_lang

        lang = prompt_lang(root)
        why = why.get(lang) or why.get("en") or next(iter(why.values()), "")
    return str(why or f"{e.name or place}: the way in is shut right now").strip()


def record_check(root: Path, turn: int | None, args: dict[str, Any], result: Any) -> None:
    """A roll the dice tool named (a skill / attribute check, or a named roll like 「绝笔」) → ``checks.json`` for this
    turn's ``check`` watches. Every name of its rule row rides along, so a rule written 「急救」 hears 「First Aid」."""
    if not (isinstance(result, dict) and result.get("ok") and result.get("label")):
        return
    label = str(result["label"])
    names: list[str] = []
    try:
        from neonrp.packs.rpg import data as _data
        from neonrp.packs.rpg import sheet as _sheet

        R = _data.rules(root)
        for table in ("skills", "attrs"):
            hit = _sheet.row_for(R.get(table) or {}, label)
            if hit:
                names = _sheet._names(*hit)
                break
    except Exception:  # noqa: BLE001 — no rule table: the label alone
        names = []
    p = _meta(root) / _CHECKS
    d = _read(p)
    items = [i for i in (d.get("items") or []) if isinstance(i, dict) and int(i.get("turn", -1)) >= int(turn or 0) - 3]
    items.append({"turn": int(turn or 0), "label": label, "names": names, "who": str(args.get("who") or "player"),
                  "passed": result.get("passed"), "level": result.get("level"), "total": result.get("total"), "vs": result.get("vs")})
    d["items"] = items[-20:]
    _write(p, d)


def checks_of(root: Path, turn: int) -> list[dict[str, Any]]:
    """The checks rolled for this turn and not heard yet (a command's roll is recorded under the run's turn counter,
    which may still be a step or two behind the apply's turn)."""
    items = _read(_meta(root) / _CHECKS).get("items") or []
    return [i for i in items if isinstance(i, dict) and turn - 2 <= int(i.get("turn", -99)) <= turn and not i.get("used")]


def _soul_dir(root: Path, iid: str) -> Path | None:
    souls = root / "souls"
    if not souls.is_dir():
        return None
    for d in souls.iterdir():
        if d.is_dir() and (d.name.endswith(iid) or d.name == iid):
            return d
    return None


def inbox_for_pack(root: Path, turn: int | None) -> list[str]:
    """Messages a trigger left for the world, in the context's own tag grammar (引擎给模型的消息也 pack 成 <> []):
    ``<event P01.key>text</event>`` for a narration emit, ``<end E01>text</end>`` for an ending."""
    items = _read(_meta(root) / _INBOX).get("items") or []
    picked = items[-5:] if turn is None else [i for i in items if int(i.get("turn", -1)) >= turn - 1][-8:]
    return [as_tag(i) for i in picked]


def as_tag(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "event")
    head = str(item.get("id") or item.get("trigger") or "")
    return f"<{kind} {head}>{item.get('text')}</{kind}>"
