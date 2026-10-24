"""rpg combat — a one-shot node of the orchestration graph (10-18): the Resolve's
narrator calls ``[combat roster]what each one does this beat[/combat]``; the combat layer (its own prompt, the packed
rules, the foes and the sheets) writes this exchange once, its dice thrown by the engine, its hp changes written as ops;
the narrator gets the result back and goes on. No mode starts or ends: the foes are world data (``run_state.combat``)
that stays while any of them can still fight here, read by the next beat's talk and the next call."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from neonrp.core.modes import _rs_path

_KEY = "combat"


def read(root: Path) -> dict[str, Any] | None:
    """The fight's world data — ``{"round", "foes", "note", "since_turn", "at"}`` — or None."""
    try:
        st = json.loads(_rs_path(root).read_text(encoding="utf-8")).get(_KEY)
    except (OSError, ValueError):
        return None
    return st if isinstance(st, dict) and st.get("foes") else None


def write(root: Path, st: dict[str, Any] | None) -> None:
    p = _rs_path(root)
    try:
        rs = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rs = {}
    if st is None:
        rs.pop(_KEY, None)
    else:
        rs[_KEY] = st
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")


def standing(st: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The foes that can still fight (hp above 0, not fled)."""
    return {k: f for k, f in ((st or {}).get("foes") or {}).items() if int(f.get("hp") or 0) > 0 and f.get("status") != "fled"}


# Foe stat blocks live in packs/rpg/data/foes.json (stable ids, names per language, aliases in any language);
# a world adds / overrides in game/rules/foes.json or world_map.json "foes".
_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "几": 3}
_EN_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "several": 3, "a few": 3, "some": 3}


def _count(tok: str) -> int:
    tok = str(tok or "").strip().lower()
    if tok.isdigit():
        return int(tok)
    if tok in _EN_NUM:
        return _EN_NUM[tok]
    vals = [_CN_NUM[c] for c in tok if c in _CN_NUM]
    return max(vals) if vals else 1  # 「四五名」→ 5


def _foes_table(root: Path) -> dict[str, dict[str, Any]]:
    from neonrp.packs.rpg import data

    return data.table(root, "foes")


def _name_patterns(root: Path) -> list[tuple[str, str]]:
    """(alias, foe id), longest alias first, over every language."""
    out = []
    for fid, f in _foes_table(root).items():
        for a in [*((f.get("names") or {}).values()), *(f.get("aliases") or [])]:
            if a and len(str(a)) >= 1:
                out.append((str(a), fid))
    return sorted(set(out), key=lambda x: -len(x[0]))


def parse_roster(root: Path, text: str) -> list[tuple[str, int]]:
    """「山贼×5 独眼虎×1」「四五名山贼」「3 bandits」「two fog-fang wolves」 → [(foe id, count)], any language."""
    text = str(text or "")
    found: dict[str, int] = {}
    num = r"(\d+|[一二两三四五六七八九十几]+|a few|several|some|an?|one|two|three|four|five|six)"
    for alias, fid in _name_patterns(root):
        a = re.escape(alias)
        for m in re.finditer(rf"{num}\s*[名个人只头条]?\s*{a}(?:e?s)?\b|{num}\s*[名个人只头条]?\s*{a}|{a}(?:e?s)?\s*[×x*]\s*(\d+)|{a}", text, re.IGNORECASE):
            tok = next((g for g in m.groups() if g), None)
            n = _count(tok) if tok else 1
            found[fid] = max(found.get(fid, 0), n)
        if found.get(fid):
            text = re.sub(a, " ", text, flags=re.IGNORECASE)  # 「独眼虎」 must not count again as a shorter alias
    return [(k, max(1, min(v, 6))) for k, v in found.items()]


def roster_names(text: str) -> list[tuple[str, int]]:
    """The roster as written, for foes the table does not have: "wolf×3", "big-beast×1 small-beast×2" → [(name, count)]."""
    out: list[tuple[str, int]] = []
    for tok in re.split(r"[\s,;，、；]+", str(text or "")):
        m = re.match(r"^(.+?)\s*[×xX*]\s*(\d+)$", tok)
        name, n = (m.group(1), int(m.group(2))) if m else (tok, 1)
        name = name.strip("[]【】")
        if name and len(name) <= 16 and not any(name == x for x, _ in out):
            out.append((name, max(1, min(n, 6))))
    return out[:4]


def _core(name: str) -> str:
    """A roster name without its qualifiers: "beast(big)" → "beast", "beast·big" → "beast"."""
    return re.split(r"[\u00b7\u30fb]", re.sub(r"[(（\[【].*?[)）\]】]", "", str(name)))[0].strip()


def seen_in(name: str, text: str) -> bool:
    """Whether a foe's name shows in a text: the whole name, or its head (the last word; for an unspaced script the
    last character, the head noun of a name in such scripts)."""
    core, t = _core(name).lower(), str(text or "").lower()
    if not core or not t:
        return False
    if core in t:
        return True
    if " " in core:
        return core.split()[-1] in t
    return len(core) >= 2 and not core.isascii() and core[-1] in t


def _known_combatants(reg: Any, roster: str, note: str) -> tuple[list[Any], str, str]:
    """Characters / NPCs of this world named in the roster — the other side; their names taken out of the text so they do
    not also count as a generic foe. The hand-off note says what everyone does, companions too, so it names no foe
    (10-19 N2 r3: 「艾琳娜贴地低进,短刀割右侧那只」 put her on the other side). Returns (entries, roster left, note)."""
    if reg is None or not roster:
        return [], roster, note
    src = roster
    found: list[Any] = []
    cands = [e for e in [*reg.of_class("soul"), *reg.of_class("npc")]]
    pairs = sorted(((str(n), e) for e in cands for n in {e.name, *getattr(e, "aliases", set())} if n and len(str(n)) >= 2),
                   key=lambda x: -len(x[0]))
    for n, e in pairs:
        if n in src and e not in found:
            found.append(e)
            src = re.sub(rf"{re.escape(n)}\s*[×x*]?\s*\d*", " ", src)
    return found, src, note


def spawn(root: Path, reg: Any, *, note: str = "", turn: int = 0, room: Any = None, roster: str = "") -> dict[str, Any]:
    """Who is on the other side: the switch tag's roster, the pending journey stop, the room's encounter table, or the
    hand-off note — in that order; seeded per turn. Names shown in the world's language. Returns the mode state."""
    from neonrp.packs.rpg import data, travel
    from neonrp.packs.rpg.i18n import lang_of

    lang = lang_of(root)
    table = _foes_table(root)
    rng = random.Random(f"combat:{turn}")
    # someone the world already has (a character, an NPC) named in the roster / hand-off fights as herself — her own hp,
    # bound to her record — not as a fresh nameless foe (10-05: 「[combat 艾琳娜×1]」 spawned 「foe1」)
    known, roster, note = _known_combatants(reg, roster, note)
    wanted: list[tuple[str, int]] = parse_roster(root, roster) if roster else []

    def from_room(r: Any) -> list[tuple[str, int]]:
        out = []
        for row in (r.props.get("encounters") or []) if r is not None and r.cls == "room" else []:
            cnt = str(row.get("count") or "1")
            lo, hi = (cnt.split("-") + [cnt])[:2]
            out.append((data.foe_key(root, str(row.get("enemy"))) or "foe", rng.randint(int(lo), int(hi))))
        return out

    if not wanted and room is not None:  # an encounter on entering this room
        wanted = from_room(room)
    j = travel.journey(root)
    if not wanted and j and j.get("pending"):  # the road stop's own foes, from the hazards table (no tag named in code, 10-01)
        hz = (data.table(root, "hazards").get(str(j["pending"].get("tag"))) or {}).get("foes") or {}
        wanted = [(str(k), rng.randint(int(v[0]), int(v[-1]))) for k, v in hz.items() if isinstance(v, (list, tuple)) and v]
    if not wanted:
        wanted = from_room(reg.entries.get(reg.player_location or ""))
    if not wanted and note:
        wanted = parse_roster(root, note)
    named: dict[str, str] = {}  # foes the narrator brought in that the table does not have: their own names, the default sheet
    if not wanted and not known and roster:
        for name, n in roster_names(roster):
            key = f"foe_{len(named) + 1}"
            named[key] = name
            wanted.append((key, n))
    if not wanted and not known:
        wanted = [("foe", 1)]
    labels = data.pick(data.rules(root).get("unit_labels"), lang) or "ABCDEF"
    sep = "" if lang in ("zh", "ja") else " "
    foes: dict[str, dict[str, Any]] = {}
    dflt = table.get("foe") or {"hp": 8, "def": 11, "atk": 2, "dmg": "1d6"}
    for e in known:
        hp = int(e.props.get("hp") or dflt["hp"])
        foes[e.id] = {"name": e.name, "ref": e.id, "kind": e.cls, "hp": hp, "max_hp": int(e.props.get("max_hp") or hp),
                      "def": int(e.props.get("def") or dflt["def"]), "atk": int(e.props.get("atk") or dflt["atk"]),
                      "dmg": str(e.props.get("dmg") or dflt["dmg"]), "traits": "", "status": "", "posture": "aggressive"}
    for fid0, n in wanted:
        base = table.get(fid0) or table.get("foe") or {"hp": 8, "def": 11, "atk": 2, "dmg": "1d6"}
        disp = named.get(fid0) or data.pick(base.get("names"), lang) or fid0
        for i in range(n):
            fid = f"{fid0}{i + 1}"
            while fid in foes:
                fid = f"{fid}x"
            foes[fid] = {"name": f"{disp}{(sep + labels[i]) if n > 1 and i < len(labels) else ''}", "kind": fid0, "hp": int(base["hp"]), "max_hp": int(base["hp"]),
                         "def": int(base["def"]), "atk": int(base["atk"]), "dmg": str(base["dmg"]), "traits": data.pick(base.get("traits"), lang),
                         "status": "", "posture": "aggressive"}
    return {"round": 1, "foes": foes, "log": []}


def state_block(root: Path, reg: Any) -> str:
    """# 战斗状态 — what the layer sees every call: round, foes as variables, the player's sheet."""
    st = read(root)
    if not st:
        return ""
    from neonrp.packs.rpg import data
    from neonrp.packs.rpg.i18n import t as _t

    R = data.rules(root)
    base = int(R.get("attr_mod_base", 5))
    lines = [_t(root, "state_head", r=st.get("round", 1), note=st.get("note") or "—")]
    for fid, f in (st.get("foes") or {}).items():
        alive = int(f.get("hp", 0)) > 0
        lines.append(_t(root, "state_foe", fid=fid, hp=f.get("hp"), max=f.get("max_hp"), name=f.get("name"), df=f.get("def"), atk=f.get("atk"), dmg=f.get("dmg"),
                        traits=(f", {f['traits']}" if f.get("traits") else ""), down="" if alive else _t(root, "state_down"),
                        status=_t(root, "state_status", s=f["status"]) if f.get("status") else ""))
    pl = reg.entries.get("player")
    if pl is not None:
        a = pl.props.get("attributes") or {}
        mods = " ".join(f"{k.upper()}{'+' if int(v) - base >= 0 else ''}{int(v) - base}" for k, v in a.items()) if a else ""
        w = pl.props.get("weapon") or {}
        ar = pl.props.get("armor") or {}
        df = int(R.get("def_base", 10)) + int(ar.get("def") or 0) + int(a.get("vit", base)) - base
        lines.append(_t(root, "state_player", hp=pl.props.get("hp"), max=pl.props.get("max_hp"), mods=mods, w=w.get("name"), atk=w.get("atk"),
                        dmg=w.get("base_damage"), die=str(R.get("damage_die", "1d6")).removeprefix("1"), df=df))
    lines.append(_t(root, "state_rule", hit=R.get("hit_die", "1d20"), dmg=R.get("damage_die", "1d6")))
    return "\n".join(lines)


def foe_vars(root: Path) -> dict[str, dict[str, Any]]:
    return dict(((read(root) or {}).get("foes")) or {})


def _turn(reg: Any) -> int:
    try:
        return int(reg.variables["turn"].value or 0) if "turn" in reg.variables else 0
    except (TypeError, ValueError):
        return 0


def exchange(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    """``[combat roster]what each one does[/combat]`` — one exchange of the fight, written once by the combat layer.
    Who is on the other side: the foes still standing here, else the pack's ``spawn`` (roster · road stop · room · note).
    Returns the layer's lines and dice for the narrator, its hp ops (landed with the beat), and the formation card."""
    from neonrp.core import layer_call, modes
    from neonrp.core.handlers import resolve as _resolve
    from neonrp.core.registry import load_registry

    roster = " ".join(str(x) for x in (op.get("args") or [])) or str(op.get("roster") or "")
    ask = " ".join(str(op.get("note") or op.get("reason") or "").split())
    turn = _turn(reg)
    st = read(root)
    if not standing(st) or (st or {}).get("at") != reg.player_location:  # a new fight (the last one is over, or was elsewhere)
        spec = modes.spec_of(root, "combat") or {}
        st = _resolve(str(spec.get("spawn") or "neonrp.packs.rpg.combat:spawn"))(root, reg, note=ask or roster, turn=turn, roster=roster)
        st.update({"note": (ask or roster)[:400], "since_turn": turn, "at": reg.player_location, "last_turn": turn})
    else:  # the same fight, the next exchange: the next round
        st.update({"round": int(st.get("round", 1)) + 1, "last_turn": turn})
    st["this_beat"] = True  # the tick after this beat's apply: a move now is the fight moving, not a flight
    write(root, st)
    r = layer_call.run(root, load_registry(root), "combat", ask or roster, seed=seed, turn=turn)
    dice = [str(a.get("text") or a.get("why") or "") for a in r.get("answers") or []]
    text = "\n".join(x for x in [r.get("text") or "", *dice] if x)
    after = _after_ops(st.get("foes") or {}, r.get("ops") or [])  # the foes as this round leaves them (the ops land with the beat)
    out: dict[str, Any] = {"ok": True, "text": text, "ops": list(r.get("ops") or []), "reload": True, "round": st.get("round"),
                           "foes": {k: {"name": f.get("name"), "hp": after.get(k, f.get("hp"))} for k, f in (st.get("foes") or {}).items()},
                           "answers": r.get("answers") or [], "ms": r.get("ms")}
    raw = (r.get("panels") or {}).get("formation")
    if raw:  # the card as written: the beat finishes it after the write-down, so its hp are this beat's
        out.update({"panel": "formation", "panel_value": raw})
    return out


def _after_ops(foes: dict[str, dict[str, Any]], ops: list[dict[str, Any]]) -> dict[str, int]:
    """Each foe's hp once the layer's own ``foe.<id>.hp`` changes are counted (floored at 0)."""
    hp = {k: int(f.get("hp") or 0) for k, f in foes.items()}
    for o in ops:
        parts = str(o.get("var") or "").split(".")
        if len(parts) != 3 or parts[0] != "foe" or parts[2] != "hp" or parts[1] not in hp:
            continue
        try:
            if o.get("op") == "add":
                hp[parts[1]] += int(o.get("delta") if o.get("delta") is not None else o.get("value") or 0)
            elif o.get("op") == "set":
                hp[parts[1]] = int(o.get("value") or 0)
        except (TypeError, ValueError):
            continue
    return {k: max(0, v) for k, v in hp.items()}


def _hp_now(root: Path, reg: Any, fid: str, f: dict[str, Any]) -> int:
    """A foe's hp after this beat's ops: the world's own people keep theirs in their own state."""
    if f.get("ref"):
        from neonrp.packs.rpg import character_state as _cs

        hp = _cs.read(root, str(f["ref"])).get("hp")
        if hp is not None:
            return int(hp)
    return int(f.get("hp") or 0)


def tick(root: Path, reg: Any, *, turn: int = 0, res: Any = None) -> list[dict[str, Any]]:
    """After every apply: a fight whose foes are all down or fled is over (won); one the player walked away from is over
    (fled). The engine writes ``end_combat`` itself — world triggers key on it (a plot's 「the camp is broken」)."""
    st = read(root)
    if not st:
        return []
    for fid, f in (st.get("foes") or {}).items():
        f["hp"] = _hp_now(root, reg, fid, f)
    write(root, st)
    if not standing(st):
        return [{"op": "end_combat", "outcome": "won"}]
    if st.get("at") and reg.player_location and reg.player_location != st.get("at"):
        if st.pop("this_beat", None):  # fought this very beat and moved with it: the fight goes along
            st["at"] = reg.player_location
            write(root, st)
            return []
        return [{"op": "end_combat", "outcome": "fled"}]
    if st.pop("this_beat", None):
        write(root, st)
    return []


tick.unit = {"on": "apply", "llm": False, "writes": ["op:end_combat"]}  # type: ignore[attr-defined]


def end(root: Path, reg: Any, op: dict[str, Any], res: Any = None) -> bool:
    """``end_combat outcome=won|fled`` — written by the engine's tick only (the narrator's own is ignored): the world data
    goes, a summary stays (``last_combat``), a pending road stop is settled, the narrator is told."""
    if not str(op.get("by") or "").startswith("tick:"):
        return False
    st = read(root)
    if not st:
        return False
    outcome = str(op.get("outcome") or (op.get("args") or ["won"])[0] or "won").lower()
    write(root, None)
    try:  # the last fight's summary stays readable (records / E5 checks)
        rs = json.loads(_rs_path(root).read_text(encoding="utf-8"))
        hp_var = reg.variables.get("player.hp")
        rs["last_combat"] = {"outcome": outcome, "rounds": st.get("round"), "since_turn": st.get("since_turn"), "note": st.get("note"),
                             "foes": {k: {"name": f.get("name"), "hp": f.get("hp"), "max_hp": f.get("max_hp")} for k, f in (st.get("foes") or {}).items()},
                             "player_hp": hp_var.value if hp_var is not None else None}
        _rs_path(root).write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        pass
    from neonrp.packs.rpg import travel

    j = travel.journey(root)
    if j and j.get("pending"):  # the die is the fight itself: won = through, fled = through at a day's cost
        travel.resolve(root, reg, total=6 if outcome == "won" else 0)
    from neonrp.core.triggers import _INBOX, _meta, _read, _write
    from neonrp.packs.rpg.i18n import t as _t

    inbox = _read(_meta(root) / _INBOX)
    items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
    turn = _turn(reg)
    items.append({"turn": turn, "trigger": "combat", "kind": "event", "id": "combat", "text": _t(root, "combat_end", w=_t(root, outcome), r=st.get("round", "?"))})
    inbox["items"] = items[-30:]
    _write(_meta(root) / _INBOX, inbox)
    return True


def dump(root: Path) -> str:
    return json.dumps(read(root), ensure_ascii=False)


def maybe_encounter(root: Path, reg: Any, room: Any, *, turn: int) -> dict[str, Any] | None:
    """Landing in a dungeon room rolls its encounter table (seeded per turn + room). A hit puts the foes in the room and
    tells the narrator as an <event>; whether and how they fight is the next beats' (the talk, then [combat]). A cleared
    room never rolls again; a run whose graph has no combat node rolls nothing."""
    if read(root) or room is None or room.cls != "room":
        return None
    from neonrp.core import orchestration

    if "combat" not in (orchestration.graph(root).get("nodes") or {}):
        return None
    st = room.props.get("state") if isinstance(room.props.get("state"), dict) else {}
    if st.get("cleared"):
        return None
    rows = [x for x in (room.props.get("encounters") or []) if isinstance(x, dict)]
    rng = random.Random(f"encounter:{turn}:{room.id}")
    hit = [x for x in rows if rng.random() < float(x.get("chance") or 0)]
    if not hit:
        return None
    from neonrp.core import modes
    from neonrp.core.handlers import resolve as _resolve
    from neonrp.packs.rpg.i18n import t as _t

    note = _t(root, "encounter_note", room=room.name, what="、".join(f"{x.get('enemy')}×{x.get('count')}" for x in hit))
    spec = modes.spec_of(root, "combat") or {}
    fight = _resolve(str(spec.get("spawn") or "neonrp.packs.rpg.combat:spawn"))(root, reg, note=note, turn=turn, room=room)
    fight.update({"note": note[:400], "since_turn": turn, "at": room.id, "last_turn": turn})
    write(root, fight)
    names = "、".join(f.get("name", "?") for f in (fight.get("foes") or {}).values())
    from neonrp.core.triggers import _INBOX, _meta, _read, _write

    inbox = _read(_meta(root) / _INBOX)
    items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
    items.append({"turn": turn, "trigger": "encounter", "kind": "event", "id": "encounter", "text": _t(root, "encounter_event", room=room.name, names=names)})
    inbox["items"] = items[-30:]
    _write(_meta(root) / _INBOX, inbox)
    return fight
