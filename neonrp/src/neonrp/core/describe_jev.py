"""Describe, then Jev (experiment ``turn.solve.structured = describe``).

The narrator writes the prose (and calls its tools) as before; then, instead of writing ops in a pseudo-code, the model
says in plain words **what changed and why** (``<changes>``) and **what the player might do next** (``<possible>``).
Jev — a System One model that only picks among typed answers (yes/no · one of N · a level) — turns that description into
the engine's JSON changes, against the world's current state; and picks the options. Every answer lands inside the set
it was offered, so there is no format to get wrong; verify / apply take the JSON as they always have.

Two Jev calls per beat: ① gates (which variables changed, was a status gained / cleared, an item gained / lost, a move)
and option fit scores; ② for what changed, the new value / which status / which item / where to. Everything asked and
answered is returned in ``log`` for inspection. The questions are in the run's language (prompts/describe_jev.*.json).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_TIME = re.compile(r"(?<!\d)(\d{1,2})[:：](\d{2})(?!\d)")


def _L(root: Path) -> dict[str, Any]:
    from neonrp.core.output_lang import prompt_lang
    from neonrp.prompts import strings

    return strings("describe_jev", prompt_lang(root))


def parse(text: str) -> tuple[str, list[str]]:
    """(<changes> text, <possible> lines)."""
    from neonrp.core import sdk as _sdk

    ch = (_sdk._block("changes", text or "") or "").strip()
    po = [re.sub(r"^\s*(?:[-*•]|\d+[.、)])\s*", "", ln).strip() for ln in (_sdk._block("possible", text or "") or "").splitlines()]
    return ch, [x for x in po if x]


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(v: Any) -> str:
    n = _num(v)
    return f"{n:g}" if n is not None else str(v)


def _label(key: str, reg: Any, L: dict[str, Any]) -> str:
    tail = key.rsplit(".", 1)[-1]
    head = key.split(".", 1)[0]
    if head == "char" and key.count(".") >= 2:
        iid = key.split(".")[1]
        e = reg.entries.get(iid)
        who = e.name if e is not None else iid
    elif head == "player":
        who = L["player"]
    else:
        who = head
    return f"{who}{L['of']}{(L.get('labels') or {}).get(tail, tail)} ({key})"


def _people(reg: Any, L: dict[str, Any]) -> dict[str, str]:
    out = {str(L["player"]): "player"}
    for e in reg.of_class("soul"):
        out[str(e.name)] = str(e.id)
    return out


def _places(root: Path, reg: Any, text: str) -> dict[str, str]:
    """name → node id: the player's exits, plus any place the description names."""
    from neonrp.core import place_nav

    out: dict[str, str] = {}
    town, node = place_nav.split_location(str(reg.player_location or ""))
    v = place_nav.town_node_view(root, node, prefer_town=town) if node else None
    for x in (v or {}).get("exits") or []:
        out[str(x.get("name") or x.get("id"))] = place_nav.join_location(town, str(x.get("id")))
    for e in reg.of_class("place"):
        if e.name and str(e.name) in text:
            out.setdefault(str(e.name), str(e.id))
    return out


def _gains(text: str, verbs: list[str]) -> list[str]:
    if not verbs:
        return []
    # the name after a verb of gaining, up to the next punctuation (CJK punctuation written as escapes)
    rx = re.compile("(?:" + "|".join(re.escape(v) for v in verbs)
                    + r")[\u4e86 ]*[\u300c\u201c\"]?([^,\uff0c\u3002.!\uff01?\uff1f;\uff1b\u300c\u300d\u201c\u201d\"\n]{1,16})")
    return list(dict.fromkeys(m.strip() for m in rx.findall(text) if m.strip()))[:12]


def to_ops(root: Path, reg: Any, changes: str, possible: list[str], narration: str, *,
           prose_options: list[str] | None = None, n_options: int = 4) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """The description → (JSON changes, options, log). Jev off / failing → ([], prose options, log with why)."""
    from neonrp.core import effect_rules
    from neonrp.core import system_one as s1

    L = _L(root)
    none = str(L["none"])

    def ch(instr: str, opts: dict[str, str]) -> Any:  # a choice with a way out (Jev needs ≥ 2; the text may match none)
        return s1.choice(instr, {**dict(list(opts.items())[:40]), "none": none})

    log: dict[str, Any] = {"changes": changes, "possible": possible, "rounds": []}
    nothing = not changes.strip() or any(changes.strip().rstrip("。.!").lower() == str(w).lower() for w in L.get("nothing") or [])
    numeric = {k: v for k, v in reg.variables.items() if not getattr(v, "readonly", False) and _num(v.value) is not None
               and k.split(".", 1)[0] in ("player", "char", "time", "table")}
    nums = sorted({float(x) for x in _NUM.findall(changes)})
    times = sorted({f"{int(h):02d}:{m}" for h, m in _TIME.findall(changes)})
    statuses = list(effect_rules.table(root))
    people = _people(reg, L)
    carried = {str(e.name): str(e.id) for e in reg.of_class("carry")}
    gains = _gains(changes, list(L.get("gain_verbs") or []))
    places = _places(root, reg, changes)
    clock = reg.variables.get("time.clock")
    world = {"vars": {_label(k, reg, L): v.value for k, v in numeric.items()}, "time": clock.value if clock else None,
             "carried": list(carried), "statuses_known": statuses, "people": list(people), "places_reachable": list(places)}
    state = {"changes": changes, "story": narration[-1500:], "world": world}

    cand = list(dict.fromkeys([*possible, *(prose_options or [])]))
    cand += [str(L["go"]).replace("{p}", n) for n in list(places)[:4]]
    cand = [c for c in cand if c][:12]

    q1: dict[str, Any] = {}
    if not nothing:
        for i, k in enumerate(numeric):
            q1[f"v{i}"] = s1.noul(L["q_var"].replace("{label}", _label(k, reg, L)).replace("{now}", _fmt(numeric[k].value)))
        if times:
            q1["clock"] = s1.noul(L["q_clock"])
        q1["st_new"] = s1.noul(L["q_st_new"])
        q1["st_gone"] = s1.noul(L["q_st_gone"])
        if gains:
            q1["gain"] = s1.noul(L["q_gain"])
        if carried:
            q1["lose"] = s1.noul(L["q_lose"])
        if len(people) > 1:
            q1["soul_move"] = s1.noul(L["q_soul_move"])
    for i, c in enumerate(cand):
        q1[f"o{i}"] = s1.score(L["q_opt"].replace("{c}", c), list(L["levels"]))
    if not q1:
        return [], list(prose_options or []), log
    a1 = s1.ask(state, q1)
    log["rounds"].append({"q": {k: v.instructions for k, v in q1.items()}, "a": {k: getattr(v, "value", None) for k, v in (a1 or {}).items()}})
    if a1 is None:
        log["error"] = "jev unavailable"
        return [], list(prose_options or []), log

    def yes(key: str, th: float = 0.6) -> bool:
        v = getattr(a1.get(key), "value", None)
        return isinstance(v, (int, float)) and v >= th

    q2: dict[str, Any] = {}
    changed = [k for i, k in enumerate(numeric) if yes(f"v{i}")]
    for j, k in enumerate(changed):
        cur = _num(numeric[k].value) or 0.0
        opts = {"same": str(L["same"]).replace("{now}", _fmt(cur))}
        for n in nums:
            for val in (n, cur + n, cur - n):
                if val >= 0 and val != cur and f"{val:g}" not in opts.values():
                    opts[f"x{len(opts)}"] = f"{val:g}"
        if len(opts) > 1:
            q2[f"val{j}"] = ch(L["q_val"].replace("{label}", _label(k, reg, L)).replace("{now}", _fmt(cur)), opts)
    if yes("clock") and times:
        q2["clock_to"] = ch(L["q_clock_to"], {f"t{i}": t for i, t in enumerate(times)})
    if yes("st_new"):
        q2["st_who"] = ch(L["q_st_who"], {f"p{i}": n for i, n in enumerate(people)})
        q2["st_what"] = ch(L["q_st_what"], {f"s{i}": n for i, n in enumerate(statuses)})
    if yes("st_gone"):
        q2["sg_what"] = ch(L["q_sg_what"], {f"s{i}": n for i, n in enumerate(statuses)})
    if yes("gain") and gains:
        q2["gain_what"] = ch(L["q_gain_what"], {f"g{i}": g for i, g in enumerate(gains)})
    if yes("lose") and carried:
        q2["lose_what"] = ch(L["q_lose_what"], {f"c{i}": c for i, c in enumerate(carried)})
    if places and not nothing:  # a choice with a way out: no yes/no gate in front (Jev was under-confident on it, 10-10 run)
        q2["move_to"] = ch(L["q_move_to"], {f"m{i}": n for i, n in enumerate(places)})
    town_places = {str(e.name): str(e.id) for e in reg.of_class("place") if e.name}  # a character may go anywhere the text names
    if yes("soul_move"):
        souls = {n: i for n, i in people.items() if i != "player"}
        q2["soul_who"] = ch(L["q_soul_who"], {f"p{i}": n for i, n in enumerate(souls)})
        q2["soul_to"] = ch(L["q_soul_to"], {f"m{i}": n for i, n in enumerate({**places, **{k: v for k, v in town_places.items() if k in changes}})})
    a2 = (s1.ask(state, q2) or {}) if q2 else {}
    if q2:
        log["rounds"].append({"q": {k: v.instructions for k, v in q2.items()}, "a": {k: getattr(v, "value", None) for k, v in a2.items()}})

    def pick(key: str) -> str | None:
        ans = getattr(a2.get(key), "value", None)
        if ans in (None, "none", "same"):
            return None
        crit = getattr(q2.get(key), "criteria", None) or {}
        got = crit.get(ans, ans) if isinstance(crit, dict) else ans
        return None if got in (none, None) else str(got)

    ops: list[dict[str, Any]] = []
    for j, k in enumerate(changed):
        n = _num(pick(f"val{j}"))
        if n is not None:
            ops.append({"op": "set", "var": k, "value": int(n) if float(n).is_integer() else n, "_from": "jev"})
    if pick("clock_to"):
        ops.append({"op": "set", "var": "time.clock", "value": pick("clock_to"), "_from": "jev"})
    st, who = pick("st_what"), pick("st_who")
    if st:
        pid = people.get(str(who), "player")
        ops.append({"op": "new", "class": "status", "name": st, "props": ({} if pid == "player" else {"on": pid}), "_from": "jev"})
    gone = pick("sg_what")
    if gone:
        sid = next((str(e.id) for e in reg.of_class("status") if str(e.name) == gone), None)  # the entry, not its name
        if sid:
            ops.append({"op": "remove", "who": sid, "_from": "jev"})
    if pick("gain_what"):
        ops.append({"op": "new", "class": "carry", "name": pick("gain_what"), "props": {"qty": 1}, "_from": "jev"})
    lost = pick("lose_what")
    if lost and lost in carried:
        ops.append({"op": "remove", "who": carried[lost], "_from": "jev"})
    to = pick("move_to")
    if to and to in places:
        ops.append({"op": "move_to", "who": "player", "to": places[to], "_from": "jev"})
    sw, sto = pick("soul_who"), pick("soul_to")
    if sw and sto and sw in people and (sto in places or sto in town_places):
        ops.append({"op": "move_to", "who": people[sw], "to": places.get(sto) or town_places[sto], "_from": "jev"})

    scored = sorted(((float(getattr(a1.get(f"o{i}"), "value", 0) or 0), i, c) for i, c in enumerate(cand)), key=lambda x: (-x[0], x[1]))
    options = [c for s, _i, c in scored if s >= 2][:n_options] or [c for _s, _i, c in scored][:n_options]
    # 10-16: a natural "@someone …" / "/skill …" candidate keeps a seat (players did not know these two moves) — it takes
    # the place of the lowest plain one, never of the other kind
    for lead in ("@", "/"):
        if options and not any(o.lstrip().startswith(lead) for o in options):
            alt = next((c for s, _i, c in scored if s >= 2 and c.lstrip().startswith(lead) and c not in options), None)
            plain = [k for k in range(len(options) - 1, -1, -1) if options[k].lstrip()[:1] not in ("@", "/")]
            if alt and plain:
                options[plain[0]] = alt
    log["ops"], log["options"] = ops, options
    return ops, options, log
