"""Settlement — the run's fixed output at its exit (deaths: 「死亡结算算在
Template 的合约里」, template/contract.py).

Called at the end of every ``sdk.apply`` (every Resolve passes there):

- **deaths**: a character who died this beat (an ``{"op": "event", "event": "dead"}`` from the pack's down rule, or an
  entry whose ``dead`` prop is set) is recorded once in ``game/meta/deaths.json`` {who, name, kind, turn, cause}.
  kind = player · companion (a soul) · other (an NPC). Only the contract decides whether a death ends the run.
- **exit** — the first that holds:
    ending      an ending fired (a trigger's ``{"to": "end"}`` → ``res.ended`` / ``meta/ending.json``)
    death       the player died (or a companion, when the contract says so) → the template's first ending of the
                contract's ``ending_kind`` (usually ``fail``) is fired like a trigger would (CG and epilogue come with
                it); without one, a plain ``death`` exit
    insanity    the player's sanity (``player.san``) reached 0 and the contract has ``deaths.insanity``
- **segments**: a contract whose ``exit.on`` is ``segment`` (open-adventure: a day) gets a segment record each time the
  day turns (``game/meta/segments/<n>.json``, ledger ``run.segment``); the run goes on.

At an exit ``game/meta/settlement.json`` is written once (idempotent), the run is flagged ``ended`` and
``res.settled`` carries it (ledger ``run.settled``). No contract → the defaults (the player's death exits).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA = "worldlines.settlement/1"


def _meta(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(root) / "meta"


def _read(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _kind_of(reg: Any, who: str) -> str:
    if who == "player":
        return "player"
    e = reg.entries.get(who)
    return "companion" if e is not None and e.cls == "soul" else "other"


def _installed_endings(root: Path) -> list[dict[str, Any]]:
    """Every ending of the plots installed in the run: {id, title, kind, assets, text, plot}."""
    out: list[dict[str, Any]] = []
    for pid, info in (_read(_meta(root) / "plots.json", {}) or {}).items():
        pdir = Path(root) / str((info or {}).get("dir") or "")
        pdef = _read(pdir / "plot.json", {}) or {}
        reveal = pdef.get("reveal") or _read(pdir / "reveal.json", None)  # a template build keeps the reveal beside the plot
        for eid, spec in (pdef.get("endings") or {}).items():
            spec = spec if isinstance(spec, dict) else {}
            out.append({"id": str(eid), "title": spec.get("title"), "kind": spec.get("kind"), "assets": spec.get("assets") or {},
                        "text": spec.get("text") or spec.get("epilogue") or spec.get("desc") or "", "plot": pid,
                        "reveal": spec.get("reveal") or reveal})
    return out


def record_deaths(root: Path, reg: Any, res: Any, turn: int) -> list[dict[str, Any]]:
    """New deaths this beat → deaths.json. Returns the new rows."""
    path = _meta(root) / "deaths.json"
    rows = _read(path, []) or []
    known = {str(r.get("who")) for r in rows}
    new: list[dict[str, Any]] = []
    causes = {str(a.get("who")): str(a.get("cause") or a.get("by") or "") for a in getattr(res, "applied", None) or []
              if a.get("op") == "event" and a.get("event") == "dead"}
    dead = set(causes) | {eid for eid, e in reg.entries.items() if e.cls in ("soul", "npc", "player") and int(e.props.get("dead") or 0)}
    for who in sorted(dead - known):
        e = reg.entries.get(who)
        new.append({"who": who, "name": e.name if e is not None else who, "kind": _kind_of(reg, who), "turn": turn,
                    "cause": causes.get(who) or "dead"})
    if new:
        _write(path, rows + new)
    return new


def _fire_ending(root: Path, reg: Any, res: Any, turn: int, ending: dict[str, Any] | None, *, why: str) -> dict[str, Any]:
    """The run ends as a trigger would end it: meta/ending.json, the ``ended`` flag, ``res.ended``."""
    from neonrp.core.sdk import _apply_update

    e = ending or {"id": why, "title": "", "kind": why}
    rec = {"id": e["id"], "title": e.get("title") or "", "turn": turn, "trigger": f"settlement:{why}", "kind": e.get("kind")}
    if not (_meta(root) / "ending.json").exists():
        _write(_meta(root) / "ending.json", rec)
    try:
        _apply_update(root, {"op": "flag", "key": "ended"}, reg, res)
    except Exception:  # noqa: BLE001 — a world without the flag op still ends (ending.json is the record)
        pass
    res.ended = {k: rec[k] for k in ("id", "title", "turn", "trigger")}
    return rec


def _rewards(root: Path, reg: Any, c: dict[str, Any] | None, cg: list[str]) -> dict[str, Any]:
    """The contract's declared rewards, valued where the engine can tell (the rest null — R5: recorded, not carried)."""
    out: dict[str, Any] = {}
    for side, names in ((c or {}).get("rewards") or {}).items():
        vals: dict[str, Any] = {}
        for n in names or []:
            if n in ("ending_cg", "date_cg"):
                vals[n] = list(cg)
            elif n in ("trust", "affection"):
                vals[n] = {e.name: e.props.get("trust") for e in reg.of_class("soul") if e.props.get("trust") is not None}
            elif n == "clue_codex":
                vals[n] = sorted(e.name for e in reg.entries.values() if e.cls in ("clue", "clues"))
            elif n == "cards":  # the world's reward cards this run earned so far (core/rewards adds the last beat's)
                from neonrp.core import player_data

                w = player_data.world_of(root)
                vals[n] = [c.get("id") for c in player_data.read()["cards"] if c.get("world") == w and c.get("run") == Path(root).name]
            else:
                vals[n] = None
        out[str(side)] = vals
    return out


def _segment(root: Path, reg: Any, res: Any, c: dict[str, Any] | None, turn: int) -> None:
    ex = (c or {}).get("exit") or {}
    if ex.get("on") != "segment" or str(ex.get("segment") or "day") != "day":
        return
    for a in getattr(res, "applied", None) or []:
        if a.get("var") == "time.day" and isinstance(a.get("to"), int) and isinstance(a.get("from"), int) and a["to"] > a["from"]:
            p = _meta(root) / "segments" / f"day-{a['from']}.json"
            if not p.exists():
                _write(p, {"schema": SCHEMA, "segment": {"kind": "day", "id": a["from"], "turn": turn},
                           "deaths": _read(_meta(root) / "deaths.json", []) or [], "contract": (c or {}).get("_ref")})
                try:
                    from neonrp.core import ledger

                    ledger.append(root, turn, [("run.segment", {"kind": "day", "id": a["from"]})])
                except Exception:  # noqa: BLE001
                    pass


def after_apply(root: Path, reg: Any, res: Any, *, turn: int) -> dict[str, Any] | None:
    from neonrp.template import contract as C

    meta = _meta(root)
    if (meta / "settlement.json").exists():
        return None  # settled once; a run that reached its exit does not settle again
    c = C.run_contract(root)
    rules = C.deaths(c)
    new = record_deaths(root, reg, res, turn)
    _segment(root, reg, res, c, turn)
    exit_: dict[str, Any] | None = None
    ending: dict[str, Any] | None = None
    if getattr(res, "ended", None) or (meta / "ending.json").exists():
        rec = getattr(res, "ended", None) or _read(meta / "ending.json", {}) or {}
        ending = next((x for x in _installed_endings(root) if x["id"] == str(rec.get("id"))), None)
        exit_ = {"kind": "ending", "id": rec.get("id"), "turn": turn}
    else:
        why, rule = None, None
        for d in new:
            r = rules.get(d["kind"]) or {}
            if C.ends_run(r):
                why, rule = ("death", r)
                break
        san = reg.variables.get("player.san")
        if why is None and san is not None and isinstance(san.value, (int, float)) and san.value <= 0 and "insanity" in rules:
            if C.ends_run(rules["insanity"]):
                why, rule = ("insanity", rules["insanity"])
        if why is not None:
            kind = str((rule or {}).get("ending_kind") or "")
            ending = next((x for x in _installed_endings(root) if kind and str(x.get("kind") or "") == kind), None)
            rec = _fire_ending(root, reg, res, turn, ending, why=why)
            exit_ = {"kind": why, "id": rec["id"], "turn": turn}
    if exit_ is None:
        return None
    cg = [ending["id"]] if ending and (ending.get("assets") or {}).get("image") else []
    out = {"schema": SCHEMA, "exit": exit_, "cg_unlocked": cg,
           "epilogue": (ending or {}).get("text") or (ending or {}).get("title") or "",
           "deaths": _read(meta / "deaths.json", []) or [],
           "rewards": _rewards(root, reg, c, cg),
           "contract": (c or {}).get("_ref") or ((f"{c.get('id')}@{c.get('version')}") if c else None)}
    if cg and ending:
        out["ending_cg"] = _ending_cg(root, ending)
    out.update(_contract_outputs(root, reg, c, ending))
    out["collected"] = _collected(root, reg, ending)
    _write(meta / "settlement.json", out)
    res.settled = out
    return out


def _ending_cg(root: Path, ending: dict[str, Any]) -> dict[str, Any]:
    """The ending's picture for this run: the template slot (``<slot>@<sid>`` when the companion the player picked has
    their own variant, 10-15) and the file inside the run's plot folder."""
    from neonrp.core import scene_cg
    from neonrp.template import run_companion, variant_slot

    sid = run_companion(root)
    assets = ending.get("assets") or {}
    own = scene_cg.variants(assets).get(sid or "")
    rec = _read(_meta(root) / "template.json", {}) or {}
    rel = ((rec.get("built") or {}).get("plot_dirs") or {}).get(ending["plot"]) or f"plots/{ending['plot']}"
    info = (_read(_meta(root) / "plots.json", {}) or {}).get(ending["plot"]) or {}
    return {"id": ending["id"], "slot": variant_slot(f"plot:{rel}:ending:{ending['id']}", assets, sid), "variant": sid if own else None,
            "image": f"{str(info.get('dir') or '').rstrip('/')}/{own or assets.get('image')}"}


def _collected(root: Path, reg: Any, ending: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Who the player may collect from this run (the plots' collect rules, template/creation.py); the Hub hands them out."""
    from neonrp.template import creation

    plots = []
    for info in (_read(_meta(root) / "plots.json", {}) or {}).values():
        pdef = _read(Path(root) / str((info or {}).get("dir") or "") / "plot.json", {}) or {}
        if pdef.get("collect"):
            plots.append(pdef)
    if not plots:
        return []
    from neonrp.core import player_data

    if player_data.free_zone(root):  # a Free-Zone run hands nobody out (niko 10-18)
        return []
    flags = {k.removeprefix("flag."): bool(v.value) for k, v in reg.variables.items() if k.startswith("flag.")}
    rows = creation.granted(plots, ending=ending, flags=flags)
    souls = player_data.run_souls(root)
    for r in rows:  # the screen's face for each: the run's own entry (a plot NPC's who is its entry id — mine_N01)
        iid = next((i for i, x in souls.items() if r["who"] in (i, x["sid"], x["name"])), None)
        e = reg.entries.get(iid or r["who"])
        if iid or e is not None:
            r.update({"iid": iid or r["who"], "name": (e.name if e is not None else "") or (souls.get(iid) or {}).get("name") or r["who"],
                      "cls": e.cls if e is not None else ("npc" if (souls.get(iid) or {}).get("npc") else "soul")})
    return rows


def _contract_outputs(root: Path, reg: Any, c: dict[str, Any] | None, ending: dict[str, Any] | None) -> dict[str, Any]:
    """The outputs the contract names that are not already in the settlement (10-08 E4): ``truth_reveal`` = the plot's
    reveal in the run's language + what the pack adds (every role); ``accusation`` and anything else = the pack's
    ``run_outputs`` mechanic (only the pack knows what an accusation is)."""
    want = [str(x) for x in ((c or {}).get("outputs") or []) if str(x) in ("truth_reveal", "accusation")]
    if not want:
        return {}
    extra: dict[str, Any] = {}
    try:
        from neonrp.core import mechanics as _mech

        extra = _mech.get(root, "run_outputs")(root, reg, c) or {}
    except Exception:  # noqa: BLE001 — a pack's output hook never stops the run from settling
        extra = {}
    out: dict[str, Any] = {}
    if "truth_reveal" in want:
        from neonrp.core.output_lang import pick_lang, prompt_lang

        rv = (ending or {}).get("reveal")
        text = str(pick_lang(rv, prompt_lang(root)) if isinstance(rv, dict) else (rv or ""))
        add = extra.get("truth_reveal")
        out["truth_reveal"] = {"text": text, **(add if isinstance(add, dict) else {})}
    if "accusation" in want:
        out["accusation"] = extra.get("accusation") or []
    return out


def read(root: Path) -> dict[str, Any] | None:
    d = _read(_meta(root) / "settlement.json")
    return d if isinstance(d, dict) else None
