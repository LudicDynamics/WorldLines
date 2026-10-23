"""Down and dead — an event and a rule, both the rpg layer's (「倒地是一个事件,记在 Pack 里」;
rule names after the open SRD / BRP rules).

Run inside every apply (a pack tick, after the turn's own ops):

- hp reaches 0 (a class with hp in its schema) → the character goes down: ``down`` 1 and a 「倒地」 status on her. A
  character without hp goes down when the prose sets ``char.<id>.down`` to 1.
- while down, not stable, not dead: each Resolve rolls once by the world's rule (rules.json ``down_rule``):
    srd         d20 ≥ 10 a success; 1 counts two failures; 20 gets up at 1 hp; 3 successes → stable; 3 failures → dead
    simple      d20 + VIT modifier ≥ 12 keeps her alive; one failure → dead; 3 successes → stable
  The going-down Resolve itself does not roll.
- hp back above 0 (first aid, healing) → up: down / stable / counters cleared, the status removed.
- dead: ``dead`` 1, 「死亡」 instead of 「倒地」; her agent takes no more turns.

Every roll goes through the dice tool (ledger, the dice line on screen). Seeded per turn and character.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _hp(reg: Any, eid: str) -> int | None:
    from neonrp.packs.rpg import character_state as cs

    v = cs.hp_var(reg, eid)
    if v is None:
        return None
    try:
        return int(reg.variables[v].value)
    except (TypeError, ValueError):
        return None


def _status_ops(reg: Any, eid: str, add: str | None, drop: tuple[str, ...]) -> list[dict[str, Any]]:
    from neonrp.core import effects

    ops: list[dict[str, Any]] = [{"op": "remove", "who": e.id} for e in effects.instances(reg, eid) if e.name in drop]
    if add and not any(e.name == add for e in effects.instances(reg, eid)):
        ops.append({"op": "new", "class": "status", "name": add, "props": {"on": eid}})
    return ops


def _roll(root: Path, reg: Any, eid: str, name: str, rule: str, turn: int) -> tuple[int, int, bool]:
    """(natural die, total, passed) through the dice tool. ``pct``: d100 ≤ CON × 5 (packs/pct/rules.py)."""
    if rule == "pct":
        from neonrp.core.handlers import resolve

        return resolve("neonrp.packs.pct.rules:down_roll")(root, reg, eid, name, turn)
    from neonrp.core import tool_watch
    from neonrp.packs.rpg import data
    from neonrp.packs.rpg.i18n import t

    mod, dc, why = 0, 10, t(root, "down_save", name=name)
    if rule == "simple":
        e = reg.entries.get(eid)
        attrs = (e.props.get("attributes") if e is not None else None) or {}
        base = int(data.rules(root).get("attr_mod_base", 5))
        try:
            mod = int(attrs.get("vit", base)) - base
        except (TypeError, ValueError):
            mod = 0
        dc, why = 12, t(root, "dying_check", name=name)
    d = tool_watch.call(root, reg, "dice", "neonrp.packs.rpg.tools:dice",
                        {"dice": f"1d20{mod:+d}", "vs": dc, "reason": why, "source": "rule", "who": eid, "seed_key": f"down:{turn}:{eid}"},
                        None, seed=f"down:{turn}", source="rule")
    nat = int((d.get("rolls") or [1])[0])
    return nat, nat + mod, nat + mod >= dc


def _forget_event(root: Path, eid: str) -> None:
    import json

    from neonrp.packs.rpg import character_state as cs

    p = Path(root) / cs.rel_path(root, eid)
    st = cs.read(root, eid)
    if st.pop("down_turn", None) is not None:
        p.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tick(root: Path, reg: Any, *, turn: int = 0, res: Any = None) -> list[dict[str, Any]]:
    from neonrp.packs.rpg import character_state as cs, data
    from neonrp.packs.rpg.i18n import t

    rule = str(data.rules(root).get("down_rule") or "srd")
    rule = {"dnd": "srd", "coc_simple": "simple"}.get(rule, rule)  # the ids before 10-14, still read
    DOWN, DEAD, STABLE = t(root, "st_down"), t(root, "st_dead"), t(root, "st_stable")
    names = data.rules(root).get("down_names")  # a pack's own words for the three (pct: 濒死 / 稳住了 / 死亡)
    if isinstance(names, dict):
        from neonrp.core.output_lang import pick_lang
        from neonrp.packs.rpg.i18n import lang_of

        lg = lang_of(root)
        DOWN = pick_lang(names.get("down"), lg, DOWN)
        STABLE = pick_lang(names.get("stable"), lg, STABLE)
        DEAD = pick_lang(names.get("dead"), lg, DEAD)
    ops: list[dict[str, Any]] = []
    people = [("player", reg.entries.get("player"))] + [(e.id, e) for e in cs.characters(reg)]
    for eid, e in people:
        if e is None:
            continue
        st = cs.read(root, eid)
        if int(st.get("dead") or 0):
            continue
        name = e.name
        hp = _hp(reg, eid)
        down = int(st.get("down") or 0) or int((reg.variables.get(f"char.{eid}.down").value if f"char.{eid}.down" in reg.variables else 0) or 0)
        if hp is not None and hp <= 0 and not down:  # the event: she goes down (no roll this Resolve)
            cs.write(root, eid, down=1, stable=0, down_pass=0, down_fail=0, down_turn=turn)
            ops += _status_ops(reg, eid, DOWN, (STABLE,))
            if res is not None:
                res.applied.append({"op": "event", "who": eid, "event": "down", "by": "tick:downed"})
            continue
        if not down:
            continue
        if hp is not None and hp > 0:  # healed back up
            cs.write(root, eid, down=0, stable=0, down_pass=0, down_fail=0)
            _forget_event(root, eid)
            if f"char.{eid}.down" in reg.variables:
                ops.append({"op": "set", "var": f"char.{eid}.down", "value": 0})
            ops += _status_ops(reg, eid, None, (DOWN, STABLE))
            if res is not None:
                res.applied.append({"op": "event", "who": eid, "event": "up", "by": "tick:downed"})
            continue
        if "down_turn" not in st:  # set by the prose (`char.<id>.down` 1 — a world without hp): the event, now
            cs.write(root, eid, down=1, stable=0, down_pass=0, down_fail=0, down_turn=turn)
            ops += _status_ops(reg, eid, DOWN, (STABLE,))
            if res is not None:
                res.applied.append({"op": "event", "who": eid, "event": "down", "by": "tick:downed"})
            continue
        if int(st.get("stable") or 0) or int(st.get("down_turn") or -1) == turn:
            continue
        nat, total, ok = _roll(root, reg, eid, name, rule, turn)
        p, f = int(st.get("down_pass") or 0), int(st.get("down_fail") or 0)
        if rule == "srd" and nat == 20:
            cs.write(root, eid, down=0, stable=0, down_pass=0, down_fail=0)
            _forget_event(root, eid)
            v = cs.hp_var(reg, eid)
            if v:
                ops.append({"op": "set", "var": v, "value": 1})
            if f"char.{eid}.down" in reg.variables:
                ops.append({"op": "set", "var": f"char.{eid}.down", "value": 0})
            ops += _status_ops(reg, eid, None, (DOWN,))
            continue
        if ok:
            p += 1
        else:
            f += 2 if (rule == "srd" and nat == 1) else 1
        dead = f >= (1 if rule in ("simple", "pct") else 3)
        stable = not dead and p >= 3
        cs.write(root, eid, down_pass=p, down_fail=f, dead=int(dead), stable=int(stable))
        if res is not None:
            res.applied.append({"op": "event", "who": eid, "event": "dead" if dead else "stable" if stable else "down_roll",
                                "pass": p, "fail": f, "roll": nat, "total": total, "by": "tick:downed"})
        if dead:
            ops += _status_ops(reg, eid, DEAD, (DOWN, STABLE))
        elif stable:
            ops += _status_ops(reg, eid, STABLE, (DOWN,))
    return ops


# O7 (10-06): what this background unit may write (down / up / dead, the down rule's dice)
tick.unit = {"on": "apply", "llm": False,  # type: ignore[attr-defined]
             "writes": ["var:char.*", "var:player.hp", "op:new", "op:remove"]}
