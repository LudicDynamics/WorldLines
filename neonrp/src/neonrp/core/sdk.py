"""Engine v3 SDK — one read face, one write face (SCHEMA-AND-SDK §5).

    pack(root, viewer=None)   -> Pack        the 词条包; ``viewer=<iid>`` = a soul's own view
    render_pack(pack)         -> str         what the model reads
    parse_solve_output(text)  -> SolveOutput {narration, ops}; JSON or ⟦STATE⟧ block
    verify(root, ops, reg)    -> VerifyResult L1, three scopes (field / entity / world)
    apply(root, ops, reg)     -> ApplyResult  handlers: actions then updates (single writer)

Nothing outside this module (and the registry it reads) writes world state in
a v3 turn. ``ApplyResult`` is the SDK response; today it lands in the turn
trace, later it is returned to callers directly — the field names are final.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name
from neonrp.core.place_nav import canonical_node, join_location, split_location
from neonrp.core.registry import ClassSpec, Envelope, Registry, VarSpec, check_props, load_registry

logger = logging.getLogger(__name__)

PLAYER_IDS = {"player"}


# ── pack ─────────────────────────────────────────────────────────────────────


@dataclass
class Pack:
    viewer: str | None
    variables: dict[str, Any]
    here: Envelope | None
    chain: list[Envelope]
    exits: list[Envelope]
    present: list[Envelope]  # souls + npcs at the viewer's location (viewer excluded)
    away: list[Envelope]  # souls elsewhere (world view only)
    places: list[Envelope]  # all places in the current town
    player: Envelope | None
    me: Envelope | None  # the viewer soul (soul view only)
    lore: str
    history: list[str]
    meta: dict[str, Any] = field(default_factory=dict)
    timeline: dict[str, Any] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)
    budget: int = 0
    triggered: list[str] = field(default_factory=list)  # messages triggers left for the world (last turn)
    recent: list[str] = field(default_factory=list)  # a per-turn digest of the ledger's last turns (what happened, not how it was told)
    custom: dict[str, list[Envelope]] = field(default_factory=dict)  # author-registered classes → instances in scope

    def ids(self, cls: str) -> set[str]:
        return {e.id for e in self.places if cls == "place"} if cls == "place" else {
            e.id for e in [*self.present, *self.away] if e.cls == cls}


WORLD_BUDGET_CHARS = 7000
SOUL_BUDGET_CHARS = 2600


def pack(root: Path, *, viewer: str | None = None, history: list[str] | None = None,
         registry: Registry | None = None, budget_chars: int | None = None) -> Pack:
    """Assemble the 词条包 for the world (``viewer=None``) or for one soul.

    A soul's view is the PA-POMDP observation ``o_i``: only what is at its own
    location, its own persona / rules / memory, no other soul's private memo,
    no gm-truth. ``budget_chars`` trims the lowest tiers first (see render).
    """
    t0 = time.perf_counter()
    reg = registry or load_registry(root)
    me: Envelope | None = None
    if viewer:
        me = reg.entries.get(viewer) or (reg.entries.get(reg.resolve(viewer) or "") if reg.resolve(viewer) else None)
    anchor = (me.parent if me else reg.player_location) or reg.player_location
    here = reg.entries.get(anchor or "") if anchor else None
    if here is None and anchor:
        t, n = split_location(anchor)
        here = reg.entries.get(join_location(t or reg.current_town, canonical_node(n)) if n else (t or "")) if (t or n) else None
    chain = reg.chain(here.id) if here else ([reg.entries[reg.current_town]] if reg.current_town in reg.entries else [])
    town = next((e for e in chain if e.cls == "town"), None)
    town_id = town.id if town else reg.current_town
    places = [e for e in reg.of_class("place") if e.parent == town_id] if (town_id and (town is not None or not reg.of_class("town"))) else []  # in a dungeon there is no "this town"
    here_id = here.id if here else None

    def at_here(e: Envelope) -> bool:
        return here_id is not None and e.parent == here_id

    souls = [e for e in reg.of_class("soul") if e.id != viewer]
    npcs = [e for e in reg.of_class("npc")]
    present = sorted([e for e in [*souls, *npcs] if at_here(e)], key=lambda e: (e.cls, e.id))
    if viewer is None:
        away = sorted([e for e in souls if not at_here(e)], key=lambda e: e.id)
        present_npc_ids = {e.id for e in present}
        town_npcs = [e for e in npcs if e.props.get("town") == town_id and e.id not in present_npc_ids]
    else:
        away, town_npcs = [], []
    player = reg.entries.get("player")
    if viewer and player is not None and not at_here(player):
        player = None  # the soul cannot see a player who is elsewhere
    texts = dict(getattr(reg, "texts", {}) or {})
    timeline = dict(getattr(reg, "timeline", {}) or {})
    if viewer is None:
        variables = {k: v.value for k, v in reg.variables.items() if _var_relevant(v, reg, here_id)}
    else:
        variables = {"location": here_id}
        for k in ("time.day", "time.clock"):
            if k in reg.variables:
                variables[k] = reg.variables[k].value
    budget = budget_chars if budget_chars is not None else (SOUL_BUDGET_CHARS if viewer else WORLD_BUDGET_CHARS)
    status_table: dict[str, str] = {}
    if viewer is None and any(getattr(c, "effect", False) for c in reg.classes.values()):  # the effect rule lines (10-05)
        try:
            from neonrp.core import effect_rules as _er

            status_table = _er.table(root)
        except Exception:  # noqa: BLE001
            status_table = {}
    _lang = _pack_lang(root)
    p = Pack(viewer=viewer, variables=variables, here=here, chain=chain, exits=reg.exits(here_id) if here_id else [],
             present=present + town_npcs, away=away, places=places, player=player, me=me,
             lore=texts.get("lore", "") if viewer is None else "", history=list(history or [])[-6:],
             meta={"ms": round((time.perf_counter() - t0) * 1000, 2), "reads": reg.reads, "town": town_id, "lang": _lang, "status_table": status_table,
                   "classes": {c.name: {"render": _loc(c.render, _lang), "tier": c.tier, "title": _loc(c.title, _lang)}
                               for c in reg.classes.values() if c.custom or c.packed},
                   "var_rules": {k: v.doc for k, v in reg.variables.items() if v.doc and k in variables},
                   "registrable": [_registrable_line(c, _lang) for c in reg.classes.values() if c.custom and (c.policy or "auto") != "forbid"],
                   **(_world_files_meta(root) if viewer is None else {})},
             timeline=timeline, texts=texts, budget=budget)
    if viewer is None:
        from neonrp.core.triggers import inbox_for_pack

        tv = reg.variables.get("turn")
        p.triggered = inbox_for_pack(root, int(tv.value) if tv and isinstance(tv.value, (int, float)) else None)
        p.recent = recent_events(root, reg, turns=3)
    # author-registered classes (open schema extension): instances in scope, by class
    for cls, spec in reg.classes.items():
        if not (spec.custom or spec.packed):
            continue
        if viewer and "/player/" in "/" + str(getattr(spec, "folder", "") or ""):
            continue  # 10-02: the player's bag / status is theirs — a soul's view never lists it as her own (L9「那束草是我的」)
        inst = [e for e in reg.of_class(cls) if not e.props.get("way")]  # a way out nobody stands on (rpg roads, 10-19): a move target, not a sight
        if spec.packed and here is not None:
            inst = [e for e in inst if e.id != here.id and e.id not in {c.id for c in chain}]  # the chain renders here / its parents itself
        if spec.scope == "place":
            inst = [e for e in inst if at_here(e)]
        elif spec.scope == "town":
            inst = [e for e in inst if e.parent == town_id or (e.parent in reg.entries and reg.entries[e.parent].parent == town_id) or e.props.get("town") == town_id]
        if inst:
            p.custom[cls] = sorted(inst, key=lambda e: e.id)
    return p


def _pack_lang(root: Path) -> str:
    from neonrp.core.output_lang import prompt_lang

    return prompt_lang(root)


def _PL(lang: str) -> dict[str, Any]:
    """The pack's headings (src/neonrp/prompts/sdk.<lang>.json)."""
    from neonrp import prompts

    return prompts.strings("sdk", lang or "zh")


def _f(s: str, /, **kw: Any) -> str:
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def _cut_paragraph(text: str, n: int) -> str:
    """Cut at a paragraph (or line) boundary at or before n — never mid-sentence."""
    t = text.strip()
    if len(t) < n:
        return t
    head = t[:n]
    for sep in ("\n\n", "\n", "。", ". "):
        i = head.rfind(sep)
        if i > n // 2:
            out = head[: i + (len(sep) if sep in ("。", ". ") else 0)].rstrip()
            while out.splitlines() and out.splitlines()[-1].lstrip().startswith("#"):  # never end on a dangling heading
                out = "\n".join(out.splitlines()[:-1]).rstrip()
            return out
    return head


def recent_events(root: Path, reg: Registry, *, turns: int = 3) -> list[str]:
    """What happened in the last N turns, from the ledger — one line per turn: moves, variable changes, flags, rules, endings, new things."""
    from neonrp.core import ledger

    try:
        evs = ledger.events(root, limit=600)
    except Exception:  # noqa: BLE001
        return []
    if not evs:
        return []
    last_turn = max(int(e.get("turn", 0)) for e in evs)
    L = _PL(_pack_lang(root))
    by_turn: dict[int, list[str]] = {}
    name = lambda x: (reg.entries[x].name if x in reg.entries else str(x))  # noqa: E731
    for e in evs:
        t = int(e.get("turn", 0))
        if t < last_turn - turns + 1:
            continue
        p, typ = e.get("payload") or {}, e.get("type")
        line = ""
        if typ == "entry.entered":
            line = f"{name(p.get('who'))} → {name(p.get('entry'))}"
        elif typ == "var.changed":
            line = f"{p.get('var')} {p.get('from')}→{p.get('to')}"
        elif typ == "flag.set":
            line = f"flag {p.get('key')}"
        elif typ == "trigger.fired":
            line = _f(L["ev_rule"], id=p.get('id'))
        elif typ == "turn.ended":
            line = _f(L["ev_end"], title=p.get('title') or p.get('id'))
        elif typ == "entity.created":
            line = _f(L["ev_new"], cls=p.get('class'), name=p.get('name') or p.get('id'))
        if line:
            by_turn.setdefault(t, []).append(line)
    return [_f(L["ev_turn"], t=t) + L["ev_sep"].join(lines) for t, lines in sorted(by_turn.items())]


def _var_relevant(v: Any, reg: Registry, here_id: str | None) -> bool:
    """A variable about one entry is listed when the entry is here (with the player) or its value is off its rest."""
    about = getattr(v, "about", None)
    if not about:
        return True
    if getattr(v, "rest", None) is not None and v.value != v.rest:
        return True
    e = reg.entries.get(about)
    return e is not None and here_id is not None and e.parent == here_id


def _body(e: Envelope, L: dict[str, Any]) -> str:
    """A character's run state on its roster line (10-05 Character State): hp when hurt, down / dead."""
    out = ""
    hp, mx = e.props.get("hp"), e.props.get("max_hp")
    if hp is not None and mx and str(hp) != str(mx):
        out += f" hp={hp}/{mx}"
    if int(e.props.get("dead") or 0):
        out += L.get("body_dead", " [dead]")
    elif int(e.props.get("down") or 0):
        out += L.get("body_down", " [down]")
    return out


def _sections(p: Pack) -> list[tuple[int, str]]:
    """(tier, text) — tier 0 never cut; higher tiers trimmed first when over budget."""
    S: list[tuple[int, str]] = []
    L = _PL(str(p.meta.get("lang") or "zh"))
    here_id = p.here.id if p.here else None
    S.append((0, L["h_world"] if p.viewer is None else L["h_view"]))
    if p.viewer is None and p.player is not None:  # who the player is comes second (Yumina's order): identity, then the world
        pr = p.player.props
        bio = " ".join(x for x in (str(pr.get("background") or ""), str(pr.get("summary") or "")) if x)[:300]
        rel = []
        for e in p.present:
            if e.cls == "soul":
                tr = e.props.get("trust")
                known = (e.props.get("relationships") or {}).get("player") or {}
                rel.append(f"{e.name}:" + (_f(L["trust"], v=tr) if tr is not None else L["trust_unknown"]) + (_f(L["rel_more"], v=known.get('disposition')) if known.get("disposition") else "") + (_f(L["rel_more"], v=str(known.get('truth'))[:60]) if known.get("truth") else ""))
        S.append((0, _f(L["player_file"], name=p.player.name) + (_f(L["player_class"], cls=pr.get('class')) if pr.get("class") else "") + (f"\n{bio}" if bio else "") + ((L["rel_head"] + L["ev_sep"].join(rel)) if rel else "")))
    if p.timeline:
        tl = p.timeline
        threads = L["list_sep"].join(str(x) for x in (tl.get("active_threads") or [])[:6])
        S.append((0, _f(L["time"], day=tl.get('day', '?'), period=(L.get("periods") or {}).get(str(tl.get('period') or ''), tl.get('period') or ''), clock=tl.get('clock') or '', weather=tl.get('weather') or '?')
                  + (_f(L["threads"], threads=threads) if threads and p.viewer is None else "")))
    for e in reversed(p.chain):
        if e.cls == "world":
            continue
        if e.cls == "town":
            S.append((0, _f(L["town"], id=e.id, name=e.name, overview=str(e.props.get('overview') or '')[:400])))
        elif e.cls == "place":
            up = str(e.props.get("within") or "")
            side = [x for x in p.exits if x.id != up and x.props.get("within") != e.id]
            inside = [x for x in p.exits if x.props.get("within") == e.id]
            ex = L["list_sep"].join(f"{x.id}({x.name})" for x in side) or L["none"]
            if inside:  # the layers (10-02): what is inside this place, and the way back out
                ex += L["inside"] + L["list_sep"].join(f"{x.id}({x.name})" for x in inside)
            if up and up in {x.id for x in p.exits}:
                ex += _f(L["out_to"], id=up, name=next(x.name for x in p.exits if x.id == up))
            body = str(e.props.get("summary") or e.props.get("description") or "")[:500]
            fac = e.props.get("facility")
            fac_txt = ""
            if isinstance(fac, dict):
                fac_txt = L["facility"] + json.dumps({k: v for k, v in fac.items() if k != "name"}, ensure_ascii=False)[:600]
            S.append((0, _f(L["here"], id=e.id, name=e.name, body=body, fac=fac_txt, exits=ex)))
        elif e.cls in (p.meta.get("classes") or {}):  # a pack's own place-like class on the chain (dungeon / room …): its render template
            spec = ClassSpecProxy.from_pack(p, e.cls)
            txt = _render_entry(spec, e, exits=p.exits if e.id == here_id else None, L=L).lstrip("- ")
            S.append((0, txt if txt.startswith("#") else "## " + txt))
    if p.viewer is None and p.places:
        S.append((0, L["places"] + L["list_sep"].join(f"{e.id}({e.name})" for e in p.places)))
    if p.present:
        # Town NPCs elsewhere listed under 「在场」 read as standing next to the player — only who is HERE is
        # 「在场」; the rest of the town goes under its own heading
        here_ids = {here_id} if here_id else set()
        _here = [e for e in p.present if e.cls == "soul" or not e.parent or e.parent in here_ids]
        _elsewhere = [e for e in p.present if e not in _here]
        lines = [L["present_view"] if p.viewer else L["present_world"]]
        if not _here:
            lines.append(L["nobody_else"])
        for e in _here + ([] if p.viewer else _elsewhere):
            if e is (_elsewhere[0] if _elsewhere else None):
                lines.append(L["elsewhere_npc"])
            if e.cls == "soul":
                if p.viewer is None:
                    st = _f(L["soul_state"], mood=e.props.get('mood') or '?') + (_f(L["soul_trust"], trust=e.props.get('trust')) if e.props.get("trust") is not None else "")
                    lines.append(f"- {_handle(e)} {e.name}{L['soul_mark']}{st}{_body(e, L)}")
                else:
                    lines.append(f"- {_handle(e)} {e.name}{L['soul_mark']}{_body(e, L)}")
            else:
                where = "" if e.parent == here_id else (L["npc_elsewhere"] if e.parent == p.meta.get("town") else f" @ {e.parent}")
                tr = L["list_sep"].join(str(t) for t in (e.props.get("traits") or [])[:3])
                st = e.props.get("state") if isinstance(e.props.get("state"), dict) else {}
                sts = " ".join(f"{k}={v}" for k, v in st.items() if k != "met" and v not in (None, "", [], {}))  # what the world wrote on them (open props)
                lines.append(f"- {e.id} {e.name}" + _f(L["npc_line"], role=e.props.get('role') or '', traits=(L["npc_traits_sep"] + tr) if tr else '') + where + (_f(L["npc_status"], s=sts) if sts else "") + _body(e, L))
        S.append((0, "\n".join(lines)))
    if p.player is not None:
        hp = f" hp={p.player.props.get('hp')}/{p.player.props.get('max_hp')}" if p.player.props.get("hp") is not None else ""
        sheet = str(p.player.props.get("sheet") or "")  # the template's one-line character sheet (attributes / skills / gear / bag), if its loader wrote one
        S.append((0, _f(L["player"], name=p.player.name, hp=hp) + (f"\n{sheet}" if sheet and p.viewer is None else "")))
    # tier 1: who the present souls are (world view) / who I am (soul view)
    if p.viewer is None:
        for e in p.present:
            if e.cls == "soul" and e.props.get("persona"):
                goals = L["list_sep"].join(e.props.get("goals") or [])
                S.append((1, _f(L["persona"], name=e.name, persona=_cut_paragraph(str(e.props.get('persona') or ''), 900)) + (_f(L["goals"], goals=goals) if goals else "")))
    if p.me is not None:
        m = p.me
        S.append((0, _f(L["you"], id=m.id, name=m.name, mood=m.props.get('mood') or '?', where=m.parent or '?')
                  + (_f(L["you_trust"], trust=m.props.get('trust')) if m.props.get("trust") is not None else "")
                  + (_f(L["you_intent"], intent=m.props.get('intention')) if m.props.get("intention") else "")))
        S.append((1, _f(L["you_who"], persona=str(m.props.get('persona') or '')[:900])))
        if m.props.get("rules"):
            S.append((1, _f(L["you_rules"], rules=str(m.props.get('rules'))[:500])))
        if m.props.get("goals"):
            S.append((1, L["you_goals"] + "\n".join(f"- {g}" for g in m.props["goals"])))
        if m.props.get("recent"):
            S.append((1, L["you_recent"] + "\n".join(_f(L["you_recent_line"], turn=r.get('turn'), event=r.get('event'), reaction=r.get('my_reaction')) for r in m.props["recent"])))
        if m.props.get("relationships"):
            S.append((2, L["you_people"] + "\n".join(_f(L["you_person"], who=k, what=v.get('disposition') or v.get('truth') or '') for k, v in m.props["relationships"].items())))
    # tier 2: world texts
    if p.viewer is None:
        if p.away:
            S.append((1, L["away"] + "\n".join(f"- {_handle(e)} {e.name} @ {e.parent or '?'}" for e in p.away)))
        if p.meta.get("status_table"):
            S.append((2, L["status_table"] + "\n" + "\n".join(f"- {n}: {r}" for n, r in p.meta["status_table"].items())))
        if p.texts.get("notes"):
            S.append((2, L["notes"] + p.texts["notes"][:1200]))
        if p.texts.get("rumors"):
            S.append((3, L["rumors"] + p.texts["rumors"][:600]))
        if p.lore:
            S.append((2, L["lore"] + p.lore[:2500]))
    if p.custom:
        reg_classes = {c.name: c for c in [ClassSpecProxy.from_pack(p, cls) for cls in p.custom]}
        for cls, inst in p.custom.items():
            spec = reg_classes.get(cls)
            title = (spec.title if spec and getattr(spec, "title", "") else cls)
            S.append((spec.tier if spec else 2, f"## {title}\n" + "\n".join(_render_entry(spec, e, L=L) + _owner_tag(e) for e in inst)))
    if p.viewer is None and p.meta.get("registrable"):
        S.append((1, L["registrable"] + "\n".join(p.meta["registrable"])))
    if p.viewer is None and p.meta.get("world_tree"):
        S.append((2, L["world_tree"] + p.meta["world_tree"]
                  + ((L["world_created"] + p.meta["world_created"]) if p.meta.get("world_created") else "")))
    if p.triggered:
        S.append((0, L["triggered"] + "\n".join(p.triggered)))
    rules = p.meta.get("var_rules") or {}
    if p.viewer is None:  # the variables and their op rules are the narrator's tools; a soul sees time and place above
        S.append((0, L["variables"] + "\n".join(f"- {k} {json.dumps(v, ensure_ascii=False)}" + (_f(L["var_rule"], rule=rules[k]) if rules.get(k) else "") for k, v in p.variables.items())))
    if p.recent:
        S.append((1, L["recent"] + "\n".join(p.recent)))
    if p.history:
        S.append((1, L["history"] + "\n\n".join(h[:1500] for h in p.history)))
    return S


def _handle(e: Envelope) -> str:
    """A character's stable id (`elena`) rather than this run's instance id — what the model writes back (Registry.handle)."""
    return str(e.props.get("sid") or e.id) if e.cls == "soul" else e.id


def _owner_tag(e: Envelope) -> str:
    """Someone else's thing in a list that reads as the player's (an effect on a character): whose, as the model writes it
    back (`owner/name`, ENTITY-IDENTITY-1012)."""
    on = e.props.get("on")
    return f" @{on}" if on not in (None, "", "player") else ""


class ClassSpecProxy:
    """The class spec the pack needs for rendering (kept in ``meta`` so Pack stays serialisable)."""

    def __init__(self, name: str, render: str, tier: int, title: str = "") -> None:
        self.name, self.render, self.tier, self.title = name, render, tier, title

    @classmethod
    def from_pack(cls, p: Pack, name: str) -> "ClassSpecProxy":
        d = (p.meta.get("classes") or {}).get(name) or {}
        return cls(name, str(d.get("render") or ""), int(d.get("tier", 2)), str(d.get("title") or ""))


_OPT_SEG = re.compile(r"⟨([^⟨⟩]*)⟩")


def _render_entry(spec: Any, e: Envelope, exits: list[Envelope] | None = None, L: dict[str, Any] | None = None) -> str:
    if spec is not None and spec.render:
        class _D(dict):
            def __missing__(self, k: str) -> str:
                return "?"
        sep, none = (L or {}).get("list_sep", "、"), (L or {}).get("none", "无")  # the run's language (10-06)
        ex = sep.join(f"{x.id}({x.name})" for x in exits) if exits is not None else sep.join(e.links)
        vals = {"id": e.id, "name": e.name, "parent": e.parent or "", "links": ex or none, **{k: v for k, v in e.props.items()}, **{f"rel_{k}": v for k, v in e.rels.items()}}
        # ⟨…⟩ = an optional segment: dropped when a field in it is missing or empty (10-05: no 「检定 ?」 for an effect
        # whose rule line has no number)
        tpl = _OPT_SEG.sub(lambda m: m.group(1) if all(vals.get(k) not in (None, "") for k in re.findall(r"\{(\w+)\}", m.group(1))) else "",
                           spec.render)
        return tpl.format_map(_D(vals))
    extra = ", ".join(f"{k}={v}" for k, v in e.props.items() if k != "name" and not isinstance(v, (dict, list)))
    rels = ", ".join(f"{k}→{v}" for k, v in e.rels.items())
    return f"- {e.id} {e.name}" + (f"({extra})" if extra else "") + (f" [{rels}]" if rels else "") + (f" @ {e.parent}" if e.parent else "")


def render_pack(p: Pack) -> str:
    """Render the pack; trims tier 3 → 2 → 1 (never 0) until within ``p.budget`` chars."""
    S = _sections(p)
    total = sum(len(t) for _, t in S) + 2 * len(S)
    if p.budget and total > p.budget:
        for tier in (3, 2, 1):
            keep: list[tuple[int, str]] = []
            for tr, t in S:
                if tr == tier and total > p.budget:
                    cut = min(len(t), total - p.budget)
                    t2 = t[: max(0, len(t) - cut)]
                    total -= len(t) - len(t2)
                    if len(t2) > 40:
                        keep.append((tr, t2 + "…"))
                else:
                    keep.append((tr, t))
            S = keep
            if total <= p.budget:
                break
    return "\n\n".join(t for _, t in S)


# ── solve output ─────────────────────────────────────────────────────────────


@dataclass
class SolveOutput:
    narration: str
    ops: list[dict[str, Any]]
    fmt: str  # adv | json | tags | brackets | none
    raw: str = ""
    options: list[str] = field(default_factory=list)  # <options> — what the player might say / do next (2–4)
    cot: str = ""  # <cot> — the model's short reasoning, kept for the trace, never shown
    request_at: int | None = None  # line index (in narration) of the first [request]: the stream's stop point
    prefix: str = ""  # the lines before that request — already final (shown to the player); the continuation appends
    panels: dict[str, str] = field(default_factory=dict)  # <formation>…</formation> etc.: a layer's monospace cards (画面, not state)
    marks: list[dict[str, Any]] = field(default_factory=list)  # how each inline op was marked vs what the registry declares


def _block(tag: str, text: str) -> str | None:
    m = re.search(rf"<{tag}\s*>(.*?)</{tag}\s*>", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    # unterminated (stream cut / model forgot the closer): take up to the next opening tag
    m = re.search(rf"<{tag}\s*>(.*?)(?=</?(?:cot|lines|narration|ops|options|fields)\s*>|$)", text, re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else None


def _adv_line_op(line: str) -> dict[str, Any] | None:
    """One <ops> line → op. Accepts the bracket grammar without brackets (`player.gold -3` · `move player inn` ·
    `flag paid` · `ask 艾琳娜` · `new quest 找罗文` · `无变化`), the tag-line grammar (`move_to player inn` · `set …` ·
    `new_location "…"`), and for template ops a positional form (`vote S01 S02`) that verify maps onto the op's fields."""
    line = line.strip()
    awaiting = line.startswith("[") and line.endswith("]")  # [tag_ask_request args] — a request the engine answers before the prose continues
    line = line.strip("[]").strip()
    if line.startswith("~"):  # [~flag paid] — async by the model's mark (the registry still decides, turn_v3)
        line, awaiting = line[1:].strip(), False
    if not line or line.startswith(("#", "//")):
        return None
    o = _bracket_op(line)
    if o is not None and awaiting and o.get("op") != "noop":
        o["await"] = True
    if o is not None:
        return o
    parsed = _parse_tag_lines(line)
    if parsed and not parsed[0].get("malformed"):
        return {**parsed[0], **({"await": True} if awaiting else {})}
    parts = line.split()
    kv = {k: v for k, v in (p.split("=", 1) for p in parts[1:] if "=" in p)}
    args = [p for p in parts[1:] if "=" not in p]
    return {"op": parts[0], "args": args, **kv, **({"await": True} if awaiting else {})}


_STRUCT_TAGS = ("cot", "lines", "narration", "ops", "options", "fields")
# an ACTION tag (「<tag action> 和 <tag action>message</tag> 等价」): the tag name is the action, the rest of the
# opening tag its arguments; the body, if any, is a message that stays on screen.  <move player inn>  ≡  <move player inn>你推门进去。</move>
_ACTION_TAG_RE = re.compile(r"<([A-Za-z_][\w.\-]*)((?:\s+[^<>]*?)?)\s*/?>(?:(.*?)</\1\s*>)?", re.DOTALL)


def _lift_action_tags(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Pull inline action tags out of a message stream: returns (text with the tags replaced by their bodies, ops)."""
    ops: list[dict[str, Any]] = []

    def repl(m: re.Match[str]) -> str:
        name, args, body = m.group(1), (m.group(2) or "").strip(), m.group(3)
        if name.lower() in _STRUCT_TAGS or name in PANEL_TAGS:
            return m.group(0)
        o = _adv_line_op(f"{name} {args}".strip())
        if o is not None and o.get("op") != "noop":
            ops.append(o)
        return (body or "").strip()

    return _ACTION_TAG_RE.sub(repl, text), ops


_REQUEST_RE = re.compile(r"\[\s*([A-Za-z_][\w.\-]*)([^\[\]\n]*)\]")  # [roll d20] · [ask 艾琳娜] · [player.gold -3]; 「[禁入]」 (no ASCII head) stays prose


def _lift_requests(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Bracketed requests in the ADV stream → ops flagged ``await``; the bracket is removed from the prose."""
    ops: list[dict[str, Any]] = []

    def repl(m: re.Match[str]) -> str:
        o = _adv_line_op(m.group(0))
        if o is None or o.get("op") == "noop":
            return "" if o is not None else m.group(0)
        ops.append(o)
        return ""

    return _REQUEST_RE.sub(repl, text), ops


_LABEL_RE = re.compile(r"^(cot|lines|ops|options)\s*[:：]\s*$", re.IGNORECASE | re.MULTILINE)


_DIVIDER_RE = re.compile(r"^=+\s*(cot|lines|ops|options)\s*=+\s*$", re.IGNORECASE | re.MULTILINE)
_SEC_FENCE_RE = re.compile(r"^```\s*(cot|lines|ops|options)\s*$", re.IGNORECASE | re.MULTILINE)


def _sections_to_tags(text: str) -> str:
    """The other section styles (turn.solve.sections): `=== lines ===` dividers (no closer) and ```lines fences → tags."""
    if "<lines" in text.lower():
        return text
    if _SEC_FENCE_RE.search(text):
        out, open_tag = [], None
        for ln in text.splitlines():
            m = _SEC_FENCE_RE.match(ln.strip())
            if m:
                if open_tag:
                    out.append(f"</{open_tag}>")
                open_tag = m.group(1).lower()
                out.append(f"<{open_tag}>")
            elif ln.strip() == "```" and open_tag:
                out.append(f"</{open_tag}>")
                open_tag = None
            else:
                out.append(ln)
        if open_tag:
            out.append(f"</{open_tag}>")
        return "\n".join(out)
    if _DIVIDER_RE.search(text):
        out, open_tag = [], None
        for ln in text.splitlines():
            m = _DIVIDER_RE.match(ln.strip())
            if m:
                if open_tag:
                    out.append(f"</{open_tag}>")
                open_tag = m.group(1).lower()
                out.append(f"<{open_tag}>")
            else:
                out.append(ln)
        if open_tag:
            out.append(f"</{open_tag}>")
        return "\n".join(out)
    return text


def _labels_to_tags(text: str) -> str:
    """adv4 N5·局2: the model copied the definition style — `lines:` / `ops:` / `options:` as bare labels instead of tags —
    and the whole reply leaked into the prose. Bare labels on their own line are read as the tags they name."""
    text = _sections_to_tags(text)
    if "<lines" in text.lower() or not _LABEL_RE.search(text):
        return text
    out: list[str] = []
    open_tag: str | None = None
    for ln in text.splitlines():
        m = _LABEL_RE.match(ln.strip())
        if m:
            if open_tag:
                out.append(f"</{open_tag}>")
            open_tag = m.group(1).lower()
            out.append(f"<{open_tag}>")
        else:
            out.append(ln)
    if open_tag:
        out.append(f"</{open_tag}>")
    return "\n".join(out)


WAIT_OPS: set[str] = set()  # op names / aliases the registry says are awaited ([dice] [referee] [ask]); turn_v3 sets them
FIRE_OPS: set[str] = set()  # … and those that are not (<map>, <move …>, <flag …>); empty = no registry, the model's mark stands
_TILDE_RE = re.compile(r"\[~\s*([A-Za-z_][\w.\-]*)([^\[\]\n]*)\]")
_ANGLE_RE = re.compile(r"<([A-Za-z_][\w.\-]*)((?:\s[^<>\n]*)?)\s*/?>")


def _tilde_wait_prepass(raw: str, marks: list[dict[str, Any]]) -> str:
    """[~dice …] — a sync op marked async: the registry wins, it becomes a request (before the dice-body lift)."""
    def r(m: re.Match[str]) -> str:
        if m.group(1) in WAIT_OPS:
            marks.append({"op": m.group(1), "wrote": "tilde", "declared": "wait", "ok": False})
            return f"[{m.group(1)}{m.group(2)}]"
        return m.group(0)
    return _TILDE_RE.sub(r, raw)


_OP_AFFIX = ("start", "begin", "enter", "open", "init")


def op_meant(name: str) -> str | None:
    """The one registered op an unregistered bracket name plainly means: the op with a start-like word on either side
    (``combat_start`` / ``start_combat`` → ``combat``; N2 watch4 10-17: the prose wrote [~combat_start], the engine
    dropped it and the fight never entered its layer). None when no op, or more than one, fits."""
    n = name.strip().lower()
    hits = {k for k in WAIT_OPS | FIRE_OPS if k and any(n in (f"{k}_{a}", f"{a}_{k}") for a in _OP_AFFIX)}
    return next(iter(hits)) if len(hits) == 1 else None


def _normalize_marks(text: str, marks: list[dict[str, Any]]) -> str:
    """Inside lines: every inline op ends as <op …> (async, lifted silently) or [op …] (a stop point), by the registry
    when it is known — the model's bracket is a hint; each disagreement is recorded in ``marks``. One pass, so a
    rewritten mark is never counted twice."""
    known = bool(WAIT_OPS or FIRE_OPS)

    def declared(n: str) -> str:
        if n in WAIT_OPS:
            return "wait"
        return "fire" if (n in FIRE_OPS or "." in n) else "?"

    def one(m: re.Match[str]) -> str:
        tilde, n, args = m.group(1) is not None, m.group(2) or m.group(4), ((m.group(3) if m.group(2) else m.group(5)) or "").rstrip().rstrip("/")
        if m.group(2) and known and declared(n) == "?":  # a name the registry does not have: one it plainly means, or say so
            k = op_meant(n)
            if k:
                marks.append({"op": n, "as": k, "wrote": "tilde" if tilde else "plain", "declared": declared(k), "ok": False})
                n = k
            elif tilde or "_" in n:
                marks.append({"op": n, "wrote": "tilde" if tilde else "plain", "declared": "?", "unknown": True, "ok": False})
        if m.group(2):  # [~op …] / [op …]
            d = declared(n)
            if tilde:
                marks.append({"op": n, "wrote": "tilde", "declared": d, "ok": d != "wait"})
                return f"[{n}{args}]" if d == "wait" else f"<{n}{args.rstrip()}>"
            if not known or d == "?":
                return m.group(0)
            marks.append({"op": n, "wrote": "plain", "declared": d, "ok": d == "wait"})
            return m.group(0) if d == "wait" else f"<{n}{args.rstrip()}>"
        # <op …>: only bodiless — <roll 1d6>4</roll> with a body is the engine's own reply echoed back, left as it was
        if not known or n.lower() in _STRUCT_TAGS or n in PANEL_TAGS or n in SWITCH_TAGS or re.search(rf"</{re.escape(n)}\s*>", text[m.end():]):
            return m.group(0)
        d = declared(n)
        if d == "?":
            return m.group(0)
        marks.append({"op": n, "wrote": "angle", "declared": d, "ok": d == "fire"})
        return f"[{n}{args.rstrip()}]" if d == "wait" else m.group(0)

    return re.sub(r"\[(~)?\s*([A-Za-z_][\w.\-]*)([^\[\]\n]*)\]|<([A-Za-z_][\w.\-]*)((?:\s[^<>\n]*)?)\s*/?>", one, text)


def _drop_answer_echoes(text: str) -> str:
    """The annotated history shows the engine's answers as <referee>…</referee>; a model copying that shape would put a
    ruling it made up on screen. An engine-answer tag (a sync op, with a body) in the model's prose is dropped whole."""
    names = sorted((n for n in WAIT_OPS if n not in SWITCH_TAGS), key=len, reverse=True)
    if not names:
        return text
    alt = "|".join(re.escape(n) for n in names)
    return re.sub(rf"<({alt})(\s[^<>\n]*)?>.*?</\1\s*>", "", text, flags=re.DOTALL)


_M_OPEN = r"\[(~)?\s*([A-Za-z_][\w.\-]*)([^\[\]\n]*)\]"
_MARK_TOKEN_RE = re.compile(rf"{_M_OPEN}(?:(.*?)\[/\2\s*\])?|<([A-Za-z_][\w.\-]*)((?:\s[^<>\n]*)?)>(.*?)</\5\s*>", re.DOTALL)


def mark_events(annotated: str) -> list[dict[str, Any]]:
    """Every mark in an annotated turn, in order: ``{"kind": "request" | "action" | "answer", "op", "args", "body",
    "line"}`` — ``line`` = how many prose lines the player has read when it fires (the SDK / Godot hook point:
    a dice animation on <dice>, a coin sound on [~player.gold +18], an entrance on [~new_npc …])."""
    out: list[dict[str, Any]] = []
    prose = 0
    for ln in (annotated or "").splitlines():
        rest = _MARK_TOKEN_RE.sub("", ln).strip()
        for m in _MARK_TOKEN_RE.finditer(ln):
            if m.group(2):
                out.append({"kind": "action" if m.group(1) else "request", "op": m.group(2), "args": m.group(3).strip(),
                            "body": (m.group(4) or "").strip(), "line": prose})
            else:
                out.append({"kind": "answer", "op": m.group(5), "args": (m.group(6) or "").strip(), "body": (m.group(7) or "").strip(), "line": prose})
        if rest:
            prose += 1
    return out


def strip_marks(annotated: str) -> str:
    """The player's text: every mark (and the request reasons / engine answers inside them) removed; a line that was
    only marks disappears. ``strip_marks(turn["annotated"]) == turn["narration"]``. The one stripper every UI uses."""
    lines = []
    for ln in (annotated or "").splitlines():
        if not _MARK_TOKEN_RE.search(ln):
            lines.append(ln)
            continue
        rest = _MARK_TOKEN_RE.sub("", ln).strip()
        if rest:
            lines.append(rest)
    return "\n".join(lines)


PANEL_TAGS: set[str] = set()  # a layer's panel blocks (turn_v3 sets them): <formation>…</formation> is a card for the screen, not prose, not ops
SWITCH_TAGS: set[str] = set()  # ops whose bracket carries a body (turn_v3 sets them from the registry): a mode switch, or a one-shot layer's call — <combat>what each does</combat> ≡ [combat …]…[/combat], a stop point
_DICE_BODY_RE = re.compile(r"\[\s*dice\s+([^\]\n]*)\](.*?)\[/dice\s*\]", re.DOTALL | re.IGNORECASE)


_WRITE_BODY_RE = re.compile(r"\[~?\s*write\s+(\S+)\s*\](.*?)\[/write\s*\]", re.DOTALL | re.IGNORECASE)


def _lift_writes(raw: str) -> tuple[str, dict[str, str]]:
    """``[~write towns/T009/notes.md]…[/write]`` anywhere in the output → the op line stays, its body is kept for the op
    (a file's content is never prose)."""
    bodies: dict[str, str] = {}

    def w(m: re.Match[str]) -> str:
        bodies[m.group(1)] = m.group(2).strip("\n")
        return f"\n[~write {m.group(1)}]\n"

    return _WRITE_BODY_RE.sub(w, raw), bodies


def _step_why(var: str, spec: VarSpec) -> str:
    # refusals are the engine's feedback to the narrator: English in every run (the narrator writes in the run's language anyway, 10-16)
    return (f"{var} changes by at most {spec.max_step:g} per turn (now {spec.value}): the player saying 'a long time passes' is "
            f"an intent, not time already gone — write what happens at this moment; a long stretch needs travel / rest / "
            f"waiting, and the engine advances it")


_WRAP_MIN = 240  # a clock set this many minutes or more earlier is the next day (17:40 → 07:10), less is a mistake (11:00 → 10:55)


def _hhmm(v: Any) -> int | None:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(v or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _clock_back(spec: VarSpec, cur: Any, new: Any) -> str | None:
    """For an HH:MM clock: "back" (set earlier the same day — refused), "next" (hours earlier: the next day), else None."""
    a, b = _hhmm(cur), _hhmm(new)
    if a is None or b is None or b >= a:
        return None
    return "next" if spec.carry and a - b >= _WRAP_MIN else "back"


def _raised_in(reg: Registry, ops: list[dict[str, Any]]) -> set[str]:
    """Numeric variables some op in the batch moves up."""
    up: set[str] = set()
    for o in ops:
        spec = reg.variables.get(str(o.get("var") or ""))
        if spec is None or o.get("op") not in ("set", "add"):
            continue
        try:
            if (o["op"] == "add" and float(o.get("delta")) > 0) or (o["op"] == "set" and float(o.get("value")) > float(spec.value)):
                up.add(spec.name)
        except (TypeError, ValueError):
            pass
    return up


def _back_why(var: str, now: Any) -> str:
    return f"{var} never goes back (now {now}): write what happens at this moment; the engine moves it forward"


def _world_files_meta(root: Path) -> dict[str, str]:
    from neonrp.core import worldfiles as _wf

    try:
        return {"world_tree": _wf.tree(root), "world_created": _wf.created_contents(root)}
    except Exception:  # noqa: BLE001 — the pack never fails on a listing
        return {}


def _one_bracket(body: str) -> dict[str, str]:
    """``[combat roster | what each one does]`` in one bracket (N2 1019: 「[combat 食尸鬼(大)×1 食尸鬼(小)×2 | 旅人顶正面…]」):
    the roster before the bar, the hand-off after it; no bar = all of it the hand-off."""
    head, bar, rest = str(body).partition("|")
    if bar:
        return {"note": " ".join(rest.split())[:400], "roster": " ".join(head.split())[:200]}
    return {"note": body.strip()[:400], "roster": ""}


_SECTION_HEADER_RE = re.compile(r"^[ \t]*\[\s*(lines|narration|ops|options)\b\s*([^\[\]\n]*)\][ \t]*$", re.IGNORECASE | re.MULTILINE)


def _headers_to_tags(raw: str) -> str:
    """A section written as a bracket header on its own line — `[options]` with the choices under it, or
    `[options a | b | c]` (N2 1019 M r2 / T1 r6: the choices were lost) — is that section; like any block left open,
    the next block or the end closes it."""
    def r(m: re.Match[str]) -> str:
        tag, args = m.group(1).lower(), m.group(2).strip()
        if tag == "options":
            args = "\n".join(x.strip() for x in args.split("|") if x.strip())
        return f"<{tag}>\n{args}" if args else f"<{tag}>"

    return _SECTION_HEADER_RE.sub(r, raw)


def _calls_outside(raw: str) -> list[str]:
    """The calls written outside every block, in order: `[op …]` / `[~op …]` / `<op …>` (N2 T1 r4: `</lines>
    [combat 苔原狼×2]…` never fought; M r2: `</lines> [~move player D001]` — the prose went in, the player stayed out).
    Blocks left open run to the next block or the end, as ``_block`` reads them; nothing in <cot> is a call."""
    names = "|".join(re.escape(n) for n in (*_STRUCT_TAGS, *sorted(PANEL_TAGS)))
    rest = re.sub(rf"<({names})\s*>.*?</\1\s*>", "\n", raw, flags=re.DOTALL | re.IGNORECASE)
    rest = re.sub(rf"<({names})\s*>.*?(?=<(?:{names})\s*>|\Z)", "\n", rest, flags=re.DOTALL | re.IGNORECASE)
    rest = re.sub(rf"</({names})\s*>", "\n", rest, flags=re.IGNORECASE)
    out = []
    for m in re.finditer(r"\[~?\s*[A-Za-z_][\w.\-]*[^\[\]\n]*\]|<([A-Za-z_][\w.\-]*)(?:\s[^<>\n]*)?/?>", rest):
        if m.group(1) and (m.group(1).lower() in _STRUCT_TAGS or m.group(1) in PANEL_TAGS):
            continue
        out.append(m.group(0))
    return out


def _lift_bodies(raw: str) -> tuple[str, list[str], list[str]]:
    """``[dice 1d20+2 vs 12]reason[/dice]`` → ``[dice 1d20+2 vs 12]`` (+ the reason, kept for the record, not the screen);
    ``<combat …>note</combat>`` (a mode tag) → ``[combat]`` (+ the hand-off note). Order-stable side lists."""
    reasons: list[str] = []
    notes: list[str] = []

    def d(m: re.Match[str]) -> str:
        reasons.append(" ".join(m.group(2).split())[:400])
        return f"[dice {m.group(1).strip()}]"

    raw = _DICE_BODY_RE.sub(d, raw)
    for tag in sorted(SWITCH_TAGS):
        def sw(m: re.Match[str], tag: str = tag) -> str:
            args = " ".join((m.group(1) or "").split())
            notes.append({"note": " ".join((m.group(2) or "").split())[:400], "roster": args[:200]})
            return f"\n[{tag}]\n"

        raw = re.sub(rf"<{re.escape(tag)}(\s[^>]*)?>(.*?)</{re.escape(tag)}\s*>", sw, raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(rf"\[~?\s*{re.escape(tag)}(\s[^\]\n]*)?\](.*?)\[/{re.escape(tag)}\s*\]", sw, raw, flags=re.DOTALL | re.IGNORECASE)  # [combat 山贼×3]交接[/combat]
        raw = re.sub(rf"\[\s*{re.escape(tag)}\s+([^\]\n]+)\]", lambda m, tag=tag: (notes.append(_one_bracket(m.group(1))) or f"[{tag}]"), raw, flags=re.IGNORECASE)
    return raw, reasons, notes


def parse_adv(text: str) -> SolveOutput:
    """The ADV shape: <cot>…</cot> <lines>one message per line</lines> <ops>one op per line</ops> <options>2–4</options>."""
    raw = _labels_to_tags(text or "")
    marks: list[dict[str, Any]] = []
    raw, _writes = _lift_writes(raw)
    raw = _tilde_wait_prepass(raw, marks)
    raw, _reasons, _notes = _lift_bodies(raw)
    raw = _headers_to_tags(raw)
    lines_b = _block("lines", raw)
    if lines_b is None:
        lines_b = _block("narration", raw)
    if lines_b is not None:  # another section opened before </lines> (`[options]` written inside it): the prose ends there
        lines_b = re.split(r"<(?:cot|ops|options|fields)\s*>", lines_b, maxsplit=1, flags=re.IGNORECASE)[0]
    ops_b = _block("ops", raw)
    opt_b = _block("options", raw)
    cot_b = _block("cot", raw) or ""
    panels: dict[str, str] = {}
    for tag in sorted(PANEL_TAGS):
        pb = _block(tag, raw)
        if pb is not None and pb.strip():
            panels[tag] = "\n".join(ln.rstrip() for ln in pb.strip("\n").splitlines())
        raw = re.sub(rf"<{re.escape(tag)}\s*>.*?</{re.escape(tag)}\s*>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    if lines_b is not None:
        # the blocks say what is on screen, not what is read: a call written outside them (after </lines>, between
        # blocks) is still the call — it joins the stream after the prose, where the model wrote it
        lines_b = "\n".join([lines_b, *_calls_outside(raw)])
        narration = "\n".join(ln.strip() for ln in lines_b.splitlines() if ln.strip())
    else:  # no <lines>: the prose is whatever is outside the other blocks
        narration = re.sub(r"<(cot|ops|options)\s*>.*?</\1\s*>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
    narration = _drop_answer_echoes(narration)
    narration = _normalize_marks(narration, marks)
    narration, tag_ops = _lift_action_tags(narration)  # <move player inn>…</move> inline = an op + a line
    request_at: int | None = None
    kept: list[str] = []
    lines_iter = [x.strip() for x in narration.splitlines() if x.strip()]
    for i, ln in enumerate(lines_iter):  # the first bracketed request is the stop point: lines after it were written blind …
        m_req = _REQUEST_RE.search(ln)
        if request_at is None and m_req and _adv_line_op(m_req.group(0)) not in (None, {"op": "noop"}):
            request_at = len(kept)
            # … and so is the rest of its own line (niko 10-17: 「你摸着砖缝[dice 侦查]——大成功!」 then the engine rolled 64):
            # the request and any requests right after it stay, the words after them were written before the answer
            end = m_req.end()
            while (m_nx := _REQUEST_RE.match(ln, len(ln) - len(ln[end:].lstrip()))) is not None:
                end = m_nx.end()
            kept.append(ln[:end])
            # … except a run of request-only lines right after it (niko 10-01 #3: several [dice] at one stop point,
            # the engine answers them all in one reply and the model continues once)
            for nxt in lines_iter[i + 1:]:
                if _REQUEST_RE.fullmatch(nxt) or (nxt.startswith("[") and nxt.endswith("]") and _REQUEST_RE.search(nxt)):
                    kept.append(nxt)
                else:
                    break
            break
        kept.append(ln)
    narration = "\n".join(kept)
    narration, lifted = _lift_requests(narration)  # [ask 艾琳娜] / [roll 1d6] inline = a request (方括号 = 要回包)
    narration = "\n".join(ln.strip() for ln in narration.splitlines() if ln.strip())
    prefix = narration if request_at is not None else ""
    ops: list[dict[str, Any]] = tag_ops + lifted
    for ln in (ops_b or "").splitlines():
        o = _adv_line_op(ln)
        if o is not None and o.get("op") != "noop":
            ops.append(o)
    options = [re.sub(r"^\s*(?:[-*•]|\d+[.、)]|[▸>])\s*", "", ln).strip() for ln in (opt_b or "").splitlines() if ln.strip()]
    options = [o for o in options if not re.fullmatch(r"[^\W\d_]{1,8}\s*\d", o)]  # the template copied back ("option 1", M3 r6)
    fmt = "adv" if (ops_b is not None or tag_ops or lifted) else "adv-noops"
    ops = _normalize_ops(ops)
    for o in ops:  # bodies back onto their ops, in order
        if o.get("op") == "write" and o.get("path") in _writes:
            o["body"] = _writes[o["path"]]
        if o.get("op") == "dice":
            if isinstance(o.get("args"), list):
                o["args"] = [a for a in o["args"] if str(a).lower() != "vs"]  # [dice 1d20+2 vs 12]: `vs` is grammar, not an argument
            if _reasons:
                o["reason"] = _reasons.pop(0)
        elif o.get("op") in SWITCH_TAGS:
            o["await"] = True
            if _notes:
                n = _notes.pop(0)
                o["note"], o["roster"] = n["note"], n["roster"]
                o["args"] = []
    return SolveOutput(narration, ops, fmt, text or "", options=[o for o in options if o][:6], cot=cot_b.strip(),  # raw = what the model wrote, not the normalised form
                       request_at=request_at, prefix=prefix, panels=panels, marks=marks)


_TAG_RE = re.compile(r"⟦STATE⟧(.*?)⟦/STATE⟧", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_solve_output(text: str) -> SolveOutput:
    """Accept ``{"narration","ops"}`` (bare or fenced) or narration + ⟦STATE⟧ block."""
    raw = text or ""
    s = raw.strip()
    if re.search(r"<(lines|ops|options)\s*>", s, re.IGNORECASE) or _LABEL_RE.search(s) or _DIVIDER_RE.search(s) or _SEC_FENCE_RE.search(s):
        return parse_adv(s)
    obj = _try_json(s)
    if obj is None:
        m = _FENCE_RE.search(s)
        if m:
            obj = _try_json(m.group(1))
            if obj is not None and "narration" not in obj:
                obj["narration"] = (s[: m.start()] + s[m.end():]).strip()
    if obj is None and "narration" not in s[:80] and s.startswith("{") is False:
        # narration followed by a bare JSON object
        i = s.rfind("\n{")
        if i > 0:
            tail = _try_json(s[i + 1:])
            if tail is not None:
                tail.setdefault("narration", s[:i].strip())
                obj = tail
    if isinstance(obj, dict) and ("ops" in obj or "narration" in obj or "vars" in obj):
        ops = _normalize_ops(list(obj.get("ops") or []))
        vs = obj.get("vars")
        if isinstance(vs, dict):  # {"vars": {"player.gold": "-3", "time.day": 4}} — the compact form
            ops += [var_op(k, v) for k, v in vs.items()]
        narr, lifted = _lift_mvu_tags(str(obj.get("narration") or "").strip())
        return SolveOutput(narr, ops + [o for o in lifted if o.get("op") != "noop"], "json", raw)
    m = _TAG_RE.search(s)
    if m:
        narr = (s[: m.start()] + s[m.end():]).strip()
        return SolveOutput(narr, _parse_tag_lines(m.group(1)), "tags", raw)
    narr, lifted = _lift_mvu_tags(s)
    if lifted and not s.startswith("{"):
        return SolveOutput(narr, [o for o in lifted if o.get("op") != "noop"], "brackets", raw)
    if s.startswith("{") and '"narration"' in s:
        # unparseable object: salvage the prose so the player never sees JSON
        m2 = re.search(r'"narration"\s*:\s*"(.*)', s, re.DOTALL)
        if m2:
            prose = m2.group(1).split('"ops"')[0].rstrip().rstrip(',').rstrip().rstrip('"')
            return SolveOutput(prose.replace("\\n", "\n").strip(), [], "salvaged", raw)
    return SolveOutput(s, [], "none", raw)


_NARR_RE = re.compile(r'"narration"\s*:\s*"(.*?)"\s*,\s*"ops"\s*:\s*(\[.*\])\s*\}?\s*$', re.DOTALL)


def _try_json(s: str) -> dict[str, Any] | None:
    """Parse the model's object; models write literal newlines inside the
    narration string (invalid JSON) — ``strict=False`` accepts control chars,
    and a last-resort regex splits narration / ops (E1 v3-speak: 7/8 turns
    would otherwise have lost their ops)."""
    if not s.startswith("{"):
        return None
    for strict in (True, False):
        try:
            v = json.loads(s, strict=strict)
            return v if isinstance(v, dict) else None
        except ValueError:
            continue
    m = _NARR_RE.search(s)
    if m:
        narr = m.group(1).replace("\\n", "\n").replace('\\"', '"')
        try:
            ops = json.loads(m.group(2), strict=False)
        except ValueError:
            ops = []
        return {"narration": narr, "ops": ops if isinstance(ops, list) else []}
    return None


def _parse_tag_lines(block: str) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        op = parts[0]
        if op == "move_to" and len(parts) == 3:
            ops.append({"op": op, "who": parts[1], "to": parts[2].strip()})
        elif op in ("engage", "need"):
            body = line[len(op):].strip()
            who, _, note = body.partition(":")
            ops.append({"op": op, "who": who.strip(), **({"note": note.strip()} if op == "engage" else {})})
        elif op == "set" and len(parts) == 3:
            ops.append(var_op(parts[1], parts[2].strip()))
        elif op == "add" and len(parts) == 3:
            v = parts[2].strip()
            ops.append(var_op(parts[1], v if v.startswith(("+", "-")) else "+" + v))
        elif op == "flag" and len(parts) >= 2:
            ops.append({"op": "flag", "key": parts[1].strip()})
        elif op == "mood" and len(parts) == 3:
            ops.append({"op": op, "who": parts[1], "value": parts[2].strip()})
        elif op == "new_location":
            mm = re.match(r'new_location\s+"([^"]+)"(?:\s+parent=(\S+))?(?:\s+links=(\S+))?', line)
            if mm:
                ops.append({"op": op, "name": mm.group(1), "parent": mm.group(2) or "",
                            "links": [x for x in (mm.group(3) or "").split(",") if x]})
            else:
                ops.append({"op": op, "raw": line, "malformed": True})
        elif op == "new_npc":
            mm = re.match(r'new_npc\s+"([^"]+)"(?:\s+at=(\S+))?(?:\s+role=(.+))?', line)
            if mm:
                ops.append({"op": op, "name": mm.group(1), "at": mm.group(2) or "", "role": (mm.group(3) or "").strip()})
            else:
                ops.append({"op": op, "raw": line, "malformed": True})
        elif op == "flag" and len(parts) >= 2:
            ops.append({"op": op, "key": parts[1]})
        else:
            ops.append({"op": op, "raw": line, "malformed": True})
    return ops


_SIGNED_RE = re.compile(r"^\s*([+-])\s*(\d+(?:\.\d+)?)\s*$")
_VARLINE_RE = re.compile(r"^\s*([A-Za-z_][\w.\-]*)\s*(?:=|:)?\s*([+-]?\s*\d+(?:\.\d+)?|\S.*?)\s*$")
# Bracket tags in / after the prose (「[player.gold -3] 会不会稳一点」):
#   [player.gold -3] [player.gold: -3] [time.day 4] [flag paid] [move player inn] [move 艾琳娜 inn] [ask 艾琳娜] [new quest 找罗文]
# Anything else in brackets (e.g. 门上刻着[禁入]) is prose and stays.
_BRACKET_RE = re.compile(r"\[\s*([^\[\]\n]{1,120}?)\s*\]")
_MVU_TAG_RE = re.compile(r"\[\s*([A-Za-z_][\w.\-]*)\s*:\s*([+-]?\s*\d+(?:\.\d+)?|true|false)\s*\]")
_VAR_TAG_RE = re.compile(r"^([A-Za-z_][\w.\-]*)\s*[:=]?\s*([+-]?\s*\d+(?:\.\d+)?|true|false)$")


_SIGNED_NUM = re.compile(r"^[+-]\d+(?:\.\d+)?$")
_VAR_PATH = re.compile(r"^[A-Za-z_][\w.\-]*:?$")
_NUMERIC = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def _glue_kv_tokens(parts: list[str]) -> list[str]:
    """``each=player.hp -1`` / ``each=player.hp: -1`` → ``each=player.hp:-1``: a signed number right after a k=v whose value is
    a variable path belongs to that value (the -1 fell into the status name and its per-turn hp loss was lost)."""
    out: list[str] = []
    for t in parts:
        if out and "=" in out[-1] and "=" not in t:
            k, v = out[-1].split("=", 1)
            if _SIGNED_NUM.match(t) and _VAR_PATH.match(v):
                out[-1] = f"{k}={v.rstrip(':')}:{t}"
                continue
            if v and not _NUMERIC.match(v) and not ("." in v and _VAR_PATH.match(v)) and not v.endswith(":"):
                out[-1] = f"{k}={v} {t}"  # a text value runs on (note=持续 2 次结算 · …) — 10-05: it leaked into the name
                continue
        out.append(t)
    return out


def _bracket_op(inner: str) -> dict[str, Any] | None:
    parts = inner.split()
    if parts and parts[0].lower() in ("new", "patch"):
        parts = _glue_kv_tokens(parts)
    if not parts:
        return None
    head = parts[0].lower()
    if inner.strip().lower() in ("无变化", "none", "no change", "无", "变化なし", "変化なし") and len(parts) <= 2:
        return {"op": "noop"}  # the explicit "nothing changed" marker (bracket mode); never reaches verify
    if head in ("move", "move_to") and len(parts) == 3:
        return {"op": "move_to", "who": parts[1], "to": parts[2]}
    if head == "flag" and len(parts) == 2:
        return {"op": "flag", "key": parts[1]}
    if head in ("ask", "need") and len(parts) == 2:
        return {"op": "need", "who": parts[1]}
    if head == "new" and len(parts) >= 3:  # new <class> <name …> [k=v …] — the open schema's create (10-01: props were swallowed into the name)
        kv = {k: v for k, v in (p.split("=", 1) for p in parts[2:] if "=" in p)}
        name = " ".join(p for p in parts[2:] if "=" not in p)
        parent = kv.pop("parent", None)
        return {"op": "new", "class": parts[1], "name": name, **({"parent": parent} if parent else {}), **({"props": kv} if kv else {})}
    if head == "patch" and len(parts) >= 3 and any("=" in p for p in parts[2:]):  # patch <who …> k=v …
        kv = {k: v for k, v in (p.split("=", 1) for p in parts[2:] if "=" in p)}
        who = " ".join([parts[1]] + [p for p in parts[2:] if "=" not in p])
        return {"op": "patch", "who": who, "props": kv}
    if head in ("rm", "mkdir", "rmdir", "write") and len(parts) == 2:  # world-folder file ops (core/worldfiles.py)
        return {"op": head, "path": parts[1]}
    if head == "edit" and len(parts) >= 3:
        return {"op": "edit", "path": parts[1], "set": {k: v for k, v in (p.split("=", 1) for p in parts[2:] if "=" in p)}}
    if head == "define" and len(parts) >= 3 and parts[1].lower() in ("class", "var"):
        return _define_op(parts)
    if head == "remove" and len(parts) >= 2:  # remove <who …> — an open-schema instance leaves the world (used up, expired)
        return {"op": "remove", "who": " ".join(parts[1:])}
    m = _VAR_TAG_RE.match(inner)
    if m:
        return var_op(m.group(1), m.group(2).replace(" ", ""))
    if len(parts) == 2 and "." in parts[0] and re.match(r"^[A-Za-z_][\w.\-]*$", parts[0]):
        return var_op(parts[0], parts[1])  # [time.clock 09:55] — a dotted name with a non-numeric value is a set
    return None


def var_op(name: str, value: Any) -> dict[str, Any]:
    """The compact variable syntax: a name and a number — a leading + / − means
    add, no sign means set. ``var_op("player.gold", "-3")`` → add −3; ``var_op("time.day", 4)`` → set 4."""
    name = str(name).strip()
    if isinstance(value, str):
        m = _SIGNED_RE.match(value)
        if m:
            num = float(m.group(2))
            delta = int(num) if num.is_integer() else num
            return {"op": "add", "var": name, "delta": -delta if m.group(1) == "-" else delta}
        v = value.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'", "「", "“"):  # set foe.x.status "wounded" → wounded
            v = v[1:-1].strip()
        if v.lower() in ("true", "false"):
            return {"op": "set", "var": name, "value": v.lower() == "true"}
        try:
            f = float(v)
            return {"op": "set", "var": name, "value": int(f) if f.is_integer() else f}
        except ValueError:
            return {"op": "set", "var": name, "value": v}
    return {"op": "set", "var": name, "value": value}


def _normalize_ops(ops: list[Any]) -> list[dict[str, Any]]:
    out = []
    for o in ops:
        if isinstance(o, str):
            # "player.gold -3" · "time.day = 4" · "flag met_guard" · "move_to player inn"
            parsed = _parse_tag_lines(o)
            if parsed and not all(x.get("malformed") for x in parsed):
                out.extend(parsed)
                continue
            m = _VARLINE_RE.match(o)
            if m:
                out.append(var_op(m.group(1), m.group(2).replace(" ", "")))
            elif parsed:
                out.extend(parsed)
            continue
        if not isinstance(o, dict):
            continue
        d = dict(o)
        if not d.get("op"):
            if "var" in d and ("value" in d or "delta" in d):
                out.append(var_op(d["var"], d.get("value") if "value" in d else f"+{d['delta']}" if not str(d["delta"]).startswith(("+", "-")) else str(d["delta"])))
                continue
            if len(d) == 1:  # {"player.gold": "-3"}
                (k, v), = d.items()
                out.append(var_op(k, v))
                continue
        d["op"] = str(d.get("op") or "").strip()
        if d["op"] == "var" and "var" in d:
            out.append(var_op(d["var"], d.get("value", d.get("delta"))))
            continue
        if d["op"] == "vars":  # {"op": "vars", "player.gold": "-3"} or {"op": "vars", "vars": {...}} — the compact form misplaced into an op
            body = d.get("vars") if isinstance(d.get("vars"), dict) else {k: v for k, v in d.items() if k != "op"}
            out.extend(var_op(k, v) for k, v in body.items())
            continue
        # tolerate the experiment-era spellings
        if "val" in d and "value" not in d and d["op"] == "set":
            d["value"] = d.pop("val")
        if "val" in d and "delta" not in d and d["op"] == "add":
            d["delta"] = d.pop("val")
        if d["op"] == "set" and isinstance(d.get("value"), str) and _SIGNED_RE.match(d["value"]):
            d = var_op(d["var"], d["value"])  # "set gold +3" is an add
        if d["op"] == "move" :
            d["op"] = "move_to"
        if d["op"] == "ask":
            d["op"] = "need"
        out.append(d)
    return out


def _lift_mvu_tags(narration: str) -> tuple[str, list[dict[str, Any]]]:
    """Bracket tags in the prose are lifted out as ops and removed from the text, so the player
    never sees them (酒馆 MVU style; also the ``structured=tags`` output mode). Brackets that are
    not a known tag stay in the prose."""
    ops: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    for m in _BRACKET_RE.finditer(narration):
        op = _bracket_op(m.group(1))
        if op is not None:
            ops.append(op)
            spans.append(m.span())
    if not ops:
        return narration, []
    clean = "".join(narration[a:b] for a, b in zip([0] + [e for _s, e in spans], [s_ for s_, _e in spans] + [len(narration)]))
    ops = [o for o in ops if o.get("op") != "noop"] or [{"op": "noop"}] if any(o.get("op") == "noop" for o in ops) else ops
    clean = re.sub(r"[ \t]+\n", "\n", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, ops


# ── verify (L1) ──────────────────────────────────────────────────────────────


@dataclass
class Refusal:
    index: int
    op: dict[str, Any]
    scope: str  # field | entity | world
    field: str
    why: str
    allowed: list[str] = field(default_factory=list)
    fixable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "op": self.op, "scope": self.scope, "field": self.field,
                "why": self.why, "allowed": self.allowed[:12], "fixable": self.fixable}


@dataclass
class VerifyResult:
    accepted: list[dict[str, Any]]
    refused: list[Refusal]

    @property
    def ok(self) -> bool:
        return not self.refused

    def to_dict(self) -> dict[str, Any]:
        return {"accepted": self.accepted, "refused": [r.to_dict() for r in self.refused]}


def _entity_location(reg: Registry, eid: str) -> str | None:
    e = reg.entries.get(eid)
    return e.parent if e else None


def _new_place_name(o: dict[str, Any]) -> str:
    args = o.get("args") or []
    return str(o.get("name") or (args[0] if isinstance(args, list) and args else "") or "").strip()


def bind_moves_to_new_place(reg: Registry, ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A move to an id the map does not have, in a batch that also names exactly one new place: the move means that
    place (N2 watch4 10-17: a new place by its name plus moves into an invented id grew two places, the player standing
    in the invented one). The new place goes first so the moves walk into it."""
    def unknown(to: Any) -> bool:
        t = str(to or "").strip()
        return bool(t) and not t.startswith("~pending:") and not any(reg.resolve(t, cls=c) for c in LOCATION_CLASSES)

    news = [o for o in ops if o.get("op") == "new_location" and unknown(_new_place_name(o))]
    if len(news) != 1:
        return ops
    nl, name = news[0], _new_place_name(news[0])
    from neonrp.core.place_nav import split_location

    def here_town(to: Any) -> bool:  # another town's id is new_town's job, as in _grow_place
        t = str(to).strip()
        return "/" not in t or split_location(t)[0] == reg.current_town

    moves = [i for i, o in enumerate(ops) if o.get("op") == "move_to" and unknown(o.get("to")) and here_town(o.get("to")) and str(o.get("to")).strip() != name]
    if not moves:
        return ops
    out = [o for o in ops if o is not nl]
    first = next(i for i, o in enumerate(out) if o is ops[moves[0]])
    out.insert(first, nl)
    bound = {id(ops[i]) for i in moves}
    return [{**o, "to": name, "_bound": str(o.get("to"))} if id(o) in bound else o for o in out]


_PENDING = re.compile(r"^(?:~pending:[a-z_]+:)+")


def _unpend(o: Any) -> Any:
    """A placeholder id handed back by a re-proposal (``~pending:place:苔径``, even nested) is its name again: last
    attempt's placeholders are gone, and the prefix must never grow a place of its own (N2 M10 r6)."""
    if not isinstance(o, dict):
        return o
    return {k: (_PENDING.sub("", v) if isinstance(v, str) and v.startswith("~pending:") else v) for k, v in o.items()}


# A beat with the player away (10-21, TEMPLATE-LAYERS-1019 §2.2: a character's own action settled off the player's
# screen): nothing may land on the player — not a move, not a value of theirs, not a thing they carry. Set by
# turn_v3.solve_turn(player_present=False) for the beat it runs; read by :func:`verify`.
PLAYER_AWAY: contextvars.ContextVar[bool] = contextvars.ContextVar("neonrp_player_away", default=False)
_FREE_TEXT = ("note", "text", "reason", "why", "outcome", "roster", "links", "role", "name", "desc", "summary")


def touches_player(reg: Registry, o: dict[str, Any], fields: Any = None) -> str | None:
    """The field of op ``o`` that lands it on the player (their id or name, a variable of theirs, a thing they hold),
    else None. Free-text fields are not read."""
    keys = [k for k in (fields or o.keys()) if not str(k).startswith("_") and k not in _FREE_TEXT]
    for k in keys:
        v = o.get(k)
        if not isinstance(v, str) or not v.strip():
            continue
        if k == "var":
            spec = reg.variables.get(v)
            if v.startswith("player.") or (spec is not None and "/player/" in "/" + str(spec.path)):
                return k
            continue
        hit = v if v in reg.entries else reg.resolve(v)
        if hit == "player":
            return k
        e = reg.entries.get(hit or "")
        if e is not None and e.parent == "player":
            return k
    return None


from neonrp.core.registry import SOUL_OWN  # noqa: E402 — a character's own side (who writes what)


def class_slug(name: str) -> str:
    """A class handle from whatever was written: `Ghoul` → `ghoul`, `Sea Wolf` → `sea_wolf`; a name with no Latin letters
    gets a stable `c_` handle (its own words stay the title)."""
    s = re.sub(r"[^a-z0-9_]+", "_", str(name or "").strip().lower()).strip("_")
    if _DEF_NAME.match(s or ""):
        return s
    import hashlib

    return "c_" + hashlib.sha1(str(name).encode("utf-8")).hexdigest()[:6]


def _soft_classes(root: Path, reg: Registry, ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Open schema (niko 10-20: 「class 只是给我们辅助,而不是让我们 refuse 所有不在 class list 里面的 entity」): a class
    written in any spelling is the same handle, and `new <class> …` of a class nobody defined defines it first, its props
    taken as written. Only a world that forbids defining (turn.schema.define=forbid) keeps the refusal."""
    from neonrp.core import engine_config as _ec

    soft = str(_ec.get(root, "turn.schema.define", "auto")) != "forbid"
    out: list[dict[str, Any]] = []
    made: set[str] = set()
    for o in ops:
        if o.get("op") == "define" and str(o.get("kind") or "") == "class" and o.get("name"):
            o = {**o, "name": class_slug(str(o["name"])), "title": o.get("title") or str(o["name"])}
            made.add(o["name"])
        elif o.get("op") == "new" and o.get("class") and soft:
            raw = str(o["class"])
            cls = raw if raw in reg.classes else class_slug(raw)
            o = {**o, "class": cls}
            if cls not in reg.classes and cls not in made:
                props = {k: ("int" if re.fullmatch(r"-?\d+", str(v)) else "str") for k, v in dict(o.get("props") or {}).items() if k != "on"}
                out.append({"op": "define", "kind": "class", "name": cls, "title": raw, "props": props, "mutable": list(props),
                            "effect": False, "scope": "world"})
                made.add(cls)
        out.append(o)
    return out


def verify(root: Path, ops: list[dict[str, Any]], reg: Registry, *, max_ops: int = 24) -> VerifyResult:
    """L1: field scope (grammar) → entity scope (names / vars / types) → world scope (judges). While
    :data:`PLAYER_AWAY` is set, an op that lands on the player is refused (world scope)."""
    accepted: list[dict[str, Any]] = []
    refused: list[Refusal] = []
    for pid in [k for k in reg.entries if k.startswith("~pending:")]:  # a re-proposal starts clean: last attempt's placeholders go (10-02 J3)
        reg.remove(pid)
    ops = [_unpend(o) for o in ops]
    ops = _soft_classes(root, reg, ops)
    ops = bind_moves_to_new_place(reg, ops)
    # Where everyone will stand once the ops *before* this one land. E7 A2b/A5a:
    # the solver moved the player to Elena's spot and asked her in the same
    # batch; judging co-location against the pre-turn map refused a good ask.
    pending: dict[str, str] = {}
    reg.batch_gone = set()  # removed earlier in this batch: a new one of that name may take its place (remove → new)
    reg.batch_up = _raised_in(reg, ops)  # a day moved on in this batch: its clock may start again in the morning
    for i, o in enumerate(ops):
        if i >= max_ops:
            refused.append(Refusal(i, o, "field", "op", f"more than {max_ops} ops", fixable=False))
            continue
        if o.get("malformed"):
            refused.append(Refusal(i, o, "field", "op", "malformed line"))
            continue
        if o.get("op") == "ask":  # the op's name since 09-27; `need` is the stored spelling
            o = {**o, "op": "need"}
        spec = reg.actions.get(str(o.get("op") or ""))
        if spec is None or not spec.enabled:
            refused.append(Refusal(i, o, "field", "op", f"unknown op {o.get('op')!r}", sorted(k for k, a in reg.actions.items() if a.scope == "world" and a.enabled)))
            continue
        if spec.scope == "souls":
            refused.append(Refusal(i, o, "field", "op", f"{spec.op} is a soul-side op, not world-side", fixable=False))
            continue
        if isinstance(o.get("args"), list):  # ADV positional form: `vote S01 S02` → who / target by the op's field order
            args = list(o["args"])
            o = {k: v for k, v in o.items() if k != "args"}
            for f, v in zip(spec.fields, args):
                o.setdefault(f, v)
        awaiting = bool(o.pop("await", False))
        missing = [f for f in spec.fields if f not in o and f not in ("links", "role", "note", "parent", "vs", "outcome", "roster")]  # optional tails (roster: a fight under way has one)
        if missing:
            refused.append(Refusal(i, o, "field", missing[0], f"missing field {missing[0]!r}"))
            continue
        try:  # the run's orchestration graph: an op some edge keys on lands only where an edge allows it (O3, 10-05)
            from neonrp.core import orchestration as _orch

            _why = _orch.refuses_op(root, reg, o)
        except Exception:  # noqa: BLE001 — a broken graph never blocks the turn
            logger.debug("orchestration check failed", exc_info=True)
            _why = None
        if _why:
            refused.append(Refusal(i, o, "world", "op", _why))
            continue
        if spec.kind in ("tool", "mode"):  # a registered tool / a layer switch: fields checked, run in ④ by the caller, never applied as state
            if spec.validator:  # a switch / a one-shot layer may need grounds (rpg [combat]: someone to fight)
                from neonrp.core.handlers import resolve as _resolve_v

                try:
                    v = _resolve_v(spec.validator)(root, reg, dict(o))
                except Exception as exc:  # noqa: BLE001 — a broken validator never blocks the turn
                    logger.debug("mode validator %s failed: %s", spec.validator, exc)
                    v = None
                if v is not None and not v.ok:
                    refused.append(Refusal(i, o, v.scope or "world", v.field or "op", v.reason or "refused", list(v.allowed), fixable=v.fixable))
                    continue
            accepted.append({**o, "_await": True})
            continue
        if spec.op == "move_to":
            g = _grow_place(root, i, o, reg, pending, accepted)
            if isinstance(g, Refusal):  # the judge found the new place does not fit here
                refused.append(g)
                continue
            o = g
        r = _verify_entity_and_world(root, i, o, spec.op, reg, pending)
        if isinstance(r, dict) and isinstance(r.get("_dropped"), Refusal):  # part of the op was not the world's to write
            refused.append(r.pop("_dropped"))
        if not isinstance(r, Refusal) and PLAYER_AWAY.get():
            f = touches_player(reg, r, [*spec.fields, *(k for k in r if k not in spec.fields)])
            if f:
                r = Refusal(i, o, "world", f, "the player is not here: this beat settles only what someone in the world does", fixable=False)
        if isinstance(r, Refusal):
            refused.append(r)
        else:
            if awaiting:
                r["_await"] = True
            accepted.append(r)
            if spec.op == "move_to" and r.get("to"):
                pending[str(r["who"])] = str(r["to"])
            if spec.op == "remove" and r.get("who"):
                reg.batch_gone.add(str(r["who"]))
            if spec.op == "define":  # later ops of this batch may use what was just defined (define → new in one turn)
                _provisional_define(root, reg, r)
            elif spec.op in ("new", "new_npc", "new_location") and r.get("name"):  # … and a just-created one can be patched in the same turn
                _provisional_entry(reg, r)
    return VerifyResult(_one_intent(accepted), refused)


def _one_intent(accepted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The same change written twice in one batch lands once (10-20 全线 ID1: `remove {{user}}/中毒` ×2); and a bare
    name read as the actor's own gives way when the batch names someone else's thing of that name for the same op
    (ID5: the prose's `remove 流血` took the player's bleed while the transition wrote `{{elena}}/流血`)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for o in accepted:
        if o.get("op") in ("remove", "patch", "move_to", "new", "new_npc", "new_location"):
            key = json.dumps({k: v for k, v in o.items() if not k.startswith("_")}, sort_keys=True, ensure_ascii=False, default=str)
            if key in seen:
                continue
            seen.add(key)
        out.append(o)
    named = {(o.get("op"), o.get("who")) for o in out if (o.get("_identity") or {}).get("how") == "path"}
    return [o for o in out if not ((o.get("_identity") or {}).get("how") == "actor"
                                   and any((o.get("op"), c) in named for c in (o["_identity"].get("of") or []) if c != o.get("who")))]


def _grow_place(root: Path, i: int, o: dict[str, Any], reg: Registry, pending: dict[str, str], accepted: list[dict[str, Any]]) -> "dict[str, Any] | Refusal":
    """A move to a place the map does not have yet: the place is grown first (new_location, linked to where the player
    stands), then walked into — an unknown place is created, not refused. Another town's id, or an id under
    a town nobody knows, is left to the refusal (that is new_town's job)."""
    nl = reg.actions.get("new_location")
    to = str(o.get("to") or "").strip()
    from neonrp.core.place_nav import split_location

    if not to or nl is None or not nl.enabled:
        return o
    have = next((x for x in (reg.resolve(to, cls=c) for c in LOCATION_CLASSES) if x), None)
    if have and not _only_elsewhere(reg, to, have):
        return o

    town, node = split_location(to) if "/" in to else ("", to)
    if town and town != reg.current_town:
        return o
    r = _verify_entity_and_world(root, i, {"op": "new_location", "name": node or to, "by": "move"}, "new_location", reg, pending)
    if isinstance(r, Refusal):
        if r.allowed and r.allowed[0] in reg.entries:  # the validator named a place we have (another name for it): walk there
            return {**o, "to": r.allowed[0]}
        return Refusal(i, o, r.scope, "to", r.why, r.allowed, fixable=r.fixable) if r.scope == "world" else o
    accepted.append(r)
    _provisional_entry(reg, r)
    return {**o, "to": f"~pending:place:{r['name']}" if have else node or to}


def _only_elsewhere(reg: Registry, to: str, have: str) -> bool:
    """10-21 PL4: in a second town the prose said "back to the north gate" — a bare place name only another town has is
    a place here the map lacks, not a journey back to that town's gate (a full path, `T001/gate_north`, still means it)."""
    from neonrp.core.place_nav import split_location

    env = reg.entries.get(have)
    town = reg.current_town
    return ("/" not in to and env is not None and env.cls == "place" and bool(town)
            and split_location(have)[0] not in (town, None) and reg.player_location != have)


LOCATION_CLASSES = ("place", "town", "room", "dungeon", "region", "road")  # what a move_to target may resolve to (a pack's own place-like classes included)
CORE_OPS = ("move_to", "engage", "need", "set", "add", "flag", "new", "patch", "mood", "remove", "define", "write", "edit", "rm", "mkdir", "rmdir")


def _template_op(reg: Registry, op: str) -> bool:
    """An op the template registered with its own handler (not one the core lands itself)."""
    spec = reg.actions.get(op)
    return bool(spec and op not in CORE_OPS and ":" in (spec.handler or ""))


def _verify_entity_and_world(root: Path, i: int, o: dict[str, Any], op: str, reg: Registry, pending: dict[str, str] | None = None) -> dict[str, Any] | Refusal:
    if _template_op(reg, op):
        # template op: the registered validator judges it — fn(root, reg, op_dict) -> Verdict (or None = accept)
        spec = reg.actions[op]
        if spec.validator:
            from neonrp.core.handlers import HandlerError, resolve as _resolve

            try:
                v = _resolve(spec.validator)(root, reg, dict(o))
            except HandlerError as exc:
                return Refusal(i, o, "world", "op", f"validator error: {exc}"[:200], fixable=False)
            if v is not None and not v.ok:
                return Refusal(i, o, v.scope or "world", v.field or "op", v.reason or "refused by the template", list(v.allowed), fixable=v.fixable)
            if v is not None and isinstance(getattr(v, "data", None), dict):
                return {**o, **v.data}
        return dict(o)
    n = dict(o)
    pending = pending or {}
    player_here = pending.get("player", reg.player_location)
    if op in ("move_to", "engage", "need"):
        who = str(o.get("who") or "")
        wid = "player" if who.strip().casefold() in {"player", "玩家", "you", "你"} else reg.resolve(who)
        if wid is None:
            cands = [e.name for e in [*reg.of_class("soul"), *reg.of_class("npc")]][:12]
            return Refusal(i, o, "entity", "who", f"unknown entity {who!r}", cands)
        n["who"] = wid
        if op in ("engage", "need") and (wid == "player" or reg.entries.get(wid, Envelope(wid, "npc")).cls != "soul"):
            return Refusal(i, o, "entity", "who", f"{op} needs a soul, {who!r} is not one", [e.name for e in reg.of_class("soul")], fixable=False)
        if op in ("engage", "need"):
            soul_here = pending.get(wid, reg.entries[wid].parent)
            if soul_here != player_here:
                # E5 C4c: the model asked Rowan (in T004) while the player stood at T001's gate
                here = [e.name for e in reg.of_class("soul") if pending.get(e.id, e.parent) == player_here]
                return Refusal(i, o, "world", "who", f"{reg.entries[wid].name} is not here ({soul_here}); only present souls can be asked", here, fixable=False)
        if op == "move_to":
            to = str(o.get("to") or "")
            cur = pending.get(wid) or _entity_location(reg, wid)
            hits = next((lk.ids for lk in (reg.lookup(to, cls=c) for c in LOCATION_CLASSES) if lk.ids), [])
            allowed = [f"{e.id}({e.name})" for e in reg.exits(cur)] if cur else []
            if len(hits) > 1:  # `guild` in two towns, and the player stands in neither: never a silent pick (10-13)
                return Refusal(i, o, "entity", "to", f"{to!r} could be any of these; write the full path", [f"{x}({reg.entries[x].name})" for x in hits])
            tid = hits[0] if hits else None
            if tid is None:
                return Refusal(i, o, "entity", "to", f"unknown place {to!r}", allowed)
            n["to"] = tid
            if cur is None or tid.startswith("~pending:"):  # grown this batch, linked to here by construction
                return n
            # world scope = the registered validator (default: the engine's graph, builtin:map.judge)
            from neonrp.core.handlers import HandlerError, resolve as _resolve

            spec = reg.actions.get("move_to")
            try:
                judge = _resolve(spec.validator if spec and spec.validator else "builtin:map.judge")
                v = judge(root, reg, wid, cur, tid)
            except HandlerError as exc:
                return Refusal(i, o, "world", "to", f"validator error: {exc}", allowed, fixable=False)
            if not v.ok:
                return Refusal(i, o, "world", v.field or "to", v.reason or "move refused", v.allowed or allowed, fixable=v.fixable)
            from neonrp.core.triggers import enter_refused

            shut = enter_refused(root, reg, wid, cur, v.to or tid)  # the place's own way in (location.json enter_if)
            if shut:
                return Refusal(i, o, "world", "to", shut, allowed, fixable=False)
            if v.clamped:
                # two-beat travel or the SDK's own clamp: land where it says this turn (a repair, not a refusal)
                n["to"] = v.to or tid
                n["_clamped"] = {"wanted": tid, "why": v.reason or ""}
            elif v.to:
                n["to"] = v.to
        return n
    if op in ("set", "add"):
        var = str(o.get("var") or "")
        spec = reg.variables.get(var)
        if spec is None:  # a member of a family that is not there (a fight's foe after it ended): no rewrite round
            return Refusal(i, o, "entity", "var", f"unknown variable {var!r}",
                           sorted(reg.variables, key=lambda k: (reg.variables[k].about is not None, k))[:20],
                           fixable=not _gone_member(reg, var))
        if spec.readonly:
            return Refusal(i, o, "entity", "var", f"variable {var!r} is engine-owned (use move_to / turn)", fixable=False)
        if op == "add":
            try:
                n["delta"] = int(o.get("delta"))
            except (TypeError, ValueError):
                return Refusal(i, o, "field", "delta", f"delta must be int, got {o.get('delta')!r}")
            if spec.type not in ("int", "float"):
                return Refusal(i, o, "entity", "var", f"cannot add to {spec.type} variable {var!r}", fixable=False)
            if spec.max_step is not None and abs(n["delta"]) > spec.max_step:
                return Refusal(i, o, "world", "delta", _step_why(var, spec), [f"{var} {spec.max_step:+g}"])
            if spec.monotonic and n["delta"] < 0:
                return Refusal(i, o, "world", "delta", _back_why(var, spec.value), fixable=False)
        else:
            val = o.get("value")
            try:
                n["value"] = _coerce(spec.type, val)
            except (TypeError, ValueError):
                return Refusal(i, o, "field", "value", f"value {val!r} is not {spec.type}")
            if spec.max_step is not None and isinstance(spec.value, (int, float)) and isinstance(n["value"], (int, float)) and abs(n["value"] - spec.value) > spec.max_step:
                return Refusal(i, o, "world", "value", _step_why(var, spec), [f"{var} {spec.value + spec.max_step:g}"])
            if spec.monotonic and isinstance(spec.value, (int, float)) and isinstance(n["value"], (int, float)) and n["value"] < spec.value:
                return Refusal(i, o, "world", "value", _back_why(var, spec.value), fixable=False)
            wrap = _clock_back(spec, spec.value, n["value"]) if spec.monotonic else None
            if wrap and spec.carry and spec.carry in getattr(reg, "batch_up", ()):
                n["_next_day"] = True  # slept the night: day +1 and 07:10 in one batch (PL12/S4, 25 runs since 10-14); the day op moves it
            elif wrap == "back":
                return Refusal(i, o, "world", "value", _back_why(var, spec.value), fixable=False)
            if spec.type in ("int", "float"):
                if spec.min is not None and n["value"] < spec.min:
                    return Refusal(i, o, "entity", "value", f"{var} below min {spec.min}", fixable=False)
                if spec.max is not None and n["value"] > spec.max:
                    return Refusal(i, o, "entity", "value", f"{var} above max {spec.max}", fixable=False)
        return n
    if op == "flag":
        key = str(o.get("key") or "").strip()
        if not re.match(r"^[\w.\-]+$", key):
            return Refusal(i, o, "field", "key", f"bad flag key {key!r}")
        n["key"] = key
        return n
    if op == "new":
        cls = str(o.get("class") or "")
        spec = reg.classes.get(cls)
        if spec is None or not spec.custom:
            return Refusal(i, o, "entity", "class", f"class {cls!r} is not a registrable class", [c.name for c in reg.classes.values() if c.custom])
        name = str(o.get("name") or "").strip()
        if not name:
            return Refusal(i, o, "field", "name", "name required")
        owned = _owned_class(reg, spec)
        oprops = dict(o.get("props") or {})
        owner, name, how = _owner_of_new(reg, name, oprops.get("on") or (o.get("parent") if owned else None), owned)
        if owner == "":
            return Refusal(i, o, "entity", "name", f"unknown owner in {str(o.get('name'))!r}", _people(reg))
        if owned:  # names are unique per owner: two people can each have one (10-13)
            if any(reg.owner_of(reg.entries[x]) == owner and x not in getattr(reg, "batch_gone", ()) for x in reg.lookup(name, cls=cls).ids):
                return Refusal(i, o, "world", "name", f"{cls} {name!r} already exists on {_who_name(reg, owner)}", fixable=False)
            if spec.effect:
                oprops["on"] = owner
            if how:
                n["_identity"] = {"owner": owner, "how": how}
        elif reg.resolve(name, cls=cls):
            return Refusal(i, o, "world", "name", f"{cls} {name!r} already exists", fixable=False)
        parent = str(o.get("parent") or "") if not (owned and spec.effect) else ""
        pid = reg.resolve(parent) if parent else None
        if parent and pid is None:
            return Refusal(i, o, "entity", "parent", f"unknown parent {parent!r}")
        if owned and not spec.effect and owner != "player":
            pid = owner
        probs, props, repairs = check_props(spec, {**oprops, "name": name})
        if probs:
            return Refusal(i, o, "entity", "props", "; ".join(probs), [f"{k}:{v.get('type')}" + (f"{v.get('values')}" if v.get("values") else "") for k, v in spec.props.items()])
        n.update({"class": cls, "name": name, "parent": pid, "props": props, "_repairs": repairs})
        policy = getattr(spec, "policy", "auto") or "auto"
        if policy == "forbid":
            return Refusal(i, o, "world", "class", f"{cls} does not grow any more (the class's growth policy = forbid)", fixable=False)
        if policy == "creator" and not o.get("_approved"):
            return Refusal(i, o, "world", "class", f"{cls} is added by the creator only (growth policy = creator)", fixable=False)
        if policy == "approve" and not o.get("_approved"):
            from neonrp.core import approvals as _approvals

            row = _approvals.queue(root, {**o, "class": cls, "name": name})
            return Refusal(i, o, "world", "class", f"{cls} '{name}' waits for the creator's approval (pending {row['id']})", fixable=False)
        return n
    if op == "define":
        return _verify_define(root, i, o, reg, n)
    if op in ("write", "edit", "rm", "mkdir", "rmdir"):
        from neonrp.core import worldfiles as _wf

        why = _wf.check(root, reg, o)
        if why:
            return Refusal(i, o, "world", "path", why, fixable=True)
        n.update({k: o[k] for k in ("path", "body", "set") if k in o})
        return n
    if op == "remove":
        who = str(o.get("who") or "")
        wid = _identify(reg, who, n)
        if isinstance(wid, list):
            return Refusal(i, o, "entity", "who", f"{who!r} could be any of these; write owner/name", wid)
        env = reg.entries.get(wid or "")
        spec = reg.classes.get(env.cls) if env is not None else None
        if env is None:  # someone's thing that is not there (ended, used up, never was): the world is behind, no rewrite round
            if _owner_known(reg, who):  # 10-21 ID1/ID5: the prose said it again and it was already gone — nothing to do, as a move to where one stands
                n.update({"who": who, "_gone": True})
                return n
            return Refusal(i, o, "entity", "who", f"unknown entity {who!r}", fixable=True)
        if spec is None or not spec.custom or (getattr(spec, "policy", "auto") or "auto") == "forbid":
            return Refusal(i, o, "entity", "who", f"{env.cls} {env.name} cannot be removed in play", [c.name for c in reg.classes.values() if c.custom], fixable=False)
        n.update({"who": wid})
        return n
    if op == "patch":
        who = str(o.get("who") or "")
        wid = _identify(reg, who, n)
        if isinstance(wid, list):
            return Refusal(i, o, "entity", "who", f"{who!r} could be any of these; write owner/name", wid)
        env = reg.entries.get(wid or "")
        if env is None:  # someone's thing that is not there (ended, used up, never was): the world is behind, no rewrite round
            return Refusal(i, o, "entity", "who", f"unknown entity {who!r}", fixable=not _owner_known(reg, who))
        spec = reg.classes.get(env.cls)
        props = o.get("props")
        if not isinstance(props, dict) or not props:
            return Refusal(i, o, "field", "props", "props must be a non-empty object")
        mind = [k for k in props if k in SOUL_OWN] if env.cls == "soul" else []
        if mind:  # three-party isolation, by what the field is: the world decides her body, gear and things; her mind is hers
            why = f"{env.name} is a character: {mind} come only from her own reply; the world writes what happens to her (hp, things, gear …), not what she feels or means"
            if len(mind) == len(props):
                return Refusal(i, o, "world", "props", why, fixable=False)
            n["_dropped"] = Refusal(i, o, "world", "props", why, fixable=False)  # her body lands now; no rewrite round for the rest
            props = {k: v for k, v in props.items() if k not in SOUL_OWN}
        # 10-02 niko「新增属性是一个基本操作」: an undeclared prop is simply added (to that entity's own file); a declared
        # prop must be one the class lets change in play; identity never changes.
        from neonrp.core import engine_config as _ec

        open_props = str(_ec.get(root, "turn.schema.props", "auto")) != "forbid"
        fixed = {"id", "name", "class", "parent", "full_name", "sid", "iid", "provenance", "location", "位置", "所在地"}
        if any(k in ("location", "位置", "所在地", "parent") for k in props):  # 10-02 N7: a patched 「location」 moved nobody
            return Refusal(i, o, "entity", "props", f"{env.name}'s place cannot be patched: to move someone write move {env.name} <place id>", ["move"])
        declared = set(spec.props) if spec else set()
        world_side = env.cls == "soul"  # her declared body (hp …) is the world's to change, like anything else on her but her mind
        bad = [k for k in props if k in fixed or (k in declared and not world_side and k not in (spec.mutable if spec else [])) or (k not in declared and not open_props)]
        if bad:
            return Refusal(i, o, "entity", "props", f"{env.cls} {env.name}: {bad} cannot change in play", list(spec.mutable) if spec else [], fixable=bool(spec and spec.mutable))
        probs, coerced, repairs = check_props(spec, props, partial=True) if spec else ([], dict(props), [])
        if probs:
            return Refusal(i, o, "entity", "props", "; ".join(probs), [f"{k}:{spec.props[k].get('type')}" + (f"{spec.props[k].get('values')}" if spec.props[k].get("values") else "") for k in props if k in spec.props])
        st = env.props.get("state") if isinstance(env.props.get("state"), dict) else {}  # an NPC's own props live in its state
        same = {k: v for k, v in coerced.items() if (k in env.props and str(env.props.get(k)) == str(v)) or (k in st and str(st.get(k)) == str(v))}
        if same and len(same) == len(coerced):  # 10-14 V4 ID2: 「another bundle」 written as qty 1 → 1 changed nothing
            hint = [f"{k} {int(v) + 1}" for k, v in same.items() if str(v).lstrip("-").isdigit()]
            return Refusal(i, o, "field", "props", _same_why(env.name, same), hint)
        n.update({"who": wid, "props": coerced, "_repairs": repairs})
        return n
    return n


def _same_why(name: str, same: dict[str, Any]) -> str:
    now = ", ".join(f"{k} is already {v}" for k, v in same.items())
    return f"nothing changes on {name}: {now}; write the new value (one more = the new total)"


# ── identity: which entry a name in an op means ─────────────────────────────
# Names are written `owner/name` (`{{user}}/…`, `{{char}}/…`, someone's id); a bare name of someone's thing means the
# beat's actor's (the player's) when the player has one, and is refused with the candidates when several others do.

def _owned_class(reg: Registry, spec: ClassSpec) -> bool:
    """Instances that belong to someone: effects, and the instances kept in a list file (a bag)."""
    return bool(spec.effect or spec.list_store) and "player" in reg.entries


def _people(reg: Registry) -> list[str]:
    return [f"{e.id}({e.name})" for e in reg.entries.values() if reg.is_person(e.cls)][:12]


def _who_name(reg: Registry, eid: str) -> str:
    e = reg.entries.get(eid)
    return f"{e.id}({e.name})" if e else eid


def _owner_of_new(reg: Registry, name: str, owner_tok: Any, owned: bool) -> tuple[str | None, str, str]:
    """(owner id — "" when named but unknown, None when the class has none; the bare name; how the owner was found)."""
    if not owned:
        return None, name, ""
    if "/" in name:
        head, _, tail = name.rpartition("/")
        o = reg.resolve(head)
        if o is not None and reg.is_person(reg.entries[o].cls) and tail.strip():
            return o, tail.strip(), "path"
    if owner_tok not in (None, ""):
        o = reg.resolve(str(owner_tok))
        return (o, name, "named") if o is not None else ("", name, "")
    return "player", name, "actor"  # no owner written: the beat's actor (recorded, so the trace shows it was filled in)


def _gone_member(reg: Registry, var: str) -> bool:
    """`a.<x>.c` where other `a.<y>.c` exist: one of a per-instance family (a fight's foe) that is not there now."""
    p = var.split(".")
    return len(p) == 3 and any(k.split(".")[0] == p[0] and k.split(".")[-1] == p[2] and len(k.split(".")) == 3 for k in reg.variables)


def _owner_known(reg: Registry, token: str) -> bool:
    """`owner/name` whose owner is someone we know (`{{user}}/轻伤`, `elena/herb`)."""
    head = token.rpartition("/")[0].strip()
    o = reg.resolve(head) if head else None
    return o is not None and reg.is_person(reg.entries[o].cls)


def _identify(reg: Registry, token: str, n: dict[str, Any]) -> "str | None | list[str]":
    """The one entry `token` means; a list of candidates when it could be several; None when nothing matches."""
    lk = reg.lookup(token)
    if not lk.ids:
        return None
    if not lk.ambiguous:
        if lk.how not in ("exact", "macro") or lk.owner:
            n["_identity"] = {"from": token, "to": lk.ids[0], "how": "path" if lk.owner else lk.how}
        return lk.ids[0]
    mine = [x for x in lk.ids if reg.owner_of(reg.entries[x]) == "player"]
    if len(mine) == 1 and "/" not in token:  # a bare name of someone's thing: the actor's own (an owner written but not
        # recognised is never read as the player — V4 10-13: `status {{si-elena0001}}/中毒` removed the player's poison)
        n["_identity"] = {"from": token, "to": mine[0], "how": "actor", "of": list(lk.ids)}
        return mine[0]
    return [f"{_who_name(reg, reg.owner_of(reg.entries[x]) or '')}/{reg.entries[x].name}" if reg.owner_of(reg.entries[x]) else _who_name(reg, x) for x in lk.ids]


def _gate_candidates(reg: Registry, r: Refusal) -> tuple[str, dict[str, str]]:
    """(the name as written, {entry id: how it reads}) for an identity refusal the gate may settle; ("", {}) otherwise."""
    o = r.op if isinstance(r.op, dict) else {}
    if o.get("op") == "move_to" and r.field == "to" and "could be any" in r.why:  # a place several folders share
        tok = str(o.get("to") or "").strip()
        ids = next((lk.ids for lk in (reg.lookup(tok, cls=c) for c in LOCATION_CLASSES) if lk.ids), [])
        return tok, {x: f"{x} {reg.entries[x].name}: {str(reg.entries[x].props.get('description') or '')[:80]}".rstrip(": ") for x in ids}
    if o.get("op") not in ("remove", "patch") or r.field != "who" or not (r.why.startswith("unknown entity") or "could be any" in r.why):
        return "", {}
    tok = str(o.get("who") or "").strip()
    ids = reg.lookup(tok).ids
    if not ids:  # nothing by that spelling: someone's things (theirs first), then the template's own registrable instances
        mine = [e for e in reg.entries.values() if not e.id.startswith("~pending:") and reg.owner_of(e) and not reg.is_person(e.cls)]
        rest = [e for e in reg.entries.values() if e not in mine and (reg.classes.get(e.cls) is not None and reg.classes[e.cls].custom)]
        ids = [e.id for e in (mine + rest)][:30]
    out: dict[str, str] = {}
    for x in ids:
        e = reg.entries[x]
        own = reg.owner_of(e)
        out[x] = f"{reg.entries[own].name if own in reg.entries else ''}/{e.name} ({e.cls})".lstrip("/")
    return tok, out


def identity_gate(root: Path, reg: Registry, vr: "VerifyResult", narration: str = "") -> tuple["VerifyResult", list[dict[str, Any]]]:
    """Identity step ②: the ops refused only because the name did not settle on one entry
    (nothing / several) — one Jev call picks among the candidates; a pick at or above the bar is re-verified with the id
    and lands, the rest stay refused as before. No fast Jev → nothing changes. Returns (result, what the gate did)."""
    from neonrp.core import system_one as s1
    from neonrp.prompts import strings

    if not vr.refused or not s1.fast_judge_available():
        return vr, []
    T = strings("identity", _pack_lang(root))
    qs: dict[str, Any] = {}
    asked: dict[str, tuple[Refusal, str, dict[str, str]]] = {}
    for k, r in enumerate(vr.refused):
        tok, cands = _gate_candidates(reg, r)
        if not tok or not cands:
            continue
        line = " ".join(str(v) for kk, v in r.op.items() if not str(kk).startswith("_") and not isinstance(v, (dict, list)))
        qs[f"id{k}"] = s1.choice(T["q_which"].replace("{line}", line), {**cands, "none": T["none"]})
        asked[f"id{k}"] = (r, tok, cands)
    if not qs:
        return vr, []
    ans = s1.ask(narration[-3000:], qs) or {}
    bar = float(os.environ.get("NEONRP_ID_GATE_P", "0.6") or 0.6)
    log: list[dict[str, Any]] = []
    accepted, refused = list(vr.accepted), [r for r in vr.refused if not any(r is a[0] for a in asked.values())]
    for qid, (r, tok, cands) in asked.items():
        a = ans.get(qid)
        pick = str(a.value) if a is not None else "none"
        p = float((a.probabilities or {}).get(pick, a.confidence) if a is not None else 0.0)
        row = {"from": tok, "to": pick if pick in cands else None, "p": round(p, 3), "by": "jev", "candidates": len(cands)}
        if pick in cands and p >= bar:
            again = _verify_entity_and_world(root, r.index, {**r.op, ("to" if r.op.get("op") == "move_to" else "who"): pick}, str(r.op.get("op")), reg)
            if not isinstance(again, Refusal):
                accepted.append({**again, "_identity": {k: v for k, v in row.items() if k != "candidates"}})
                log.append({**row, "landed": True})
                continue
        refused.append(r)
        log.append({**row, "landed": False})
    return VerifyResult(accepted, refused), log


_ROLE_SUFFIX_RE = re.compile(r"[((][^))]*[))]\s*$")  # 「赫伦(公会管事)」 → 「赫伦」


def _props_slot(data: Any, env: Envelope, src: str) -> tuple[dict[str, Any], bool]:
    """Where an entity's props live in its own file: ``entries.json`` → its slot; a file listing many (``npcs.json``)
    → its own item (its ``state`` block when it has one); an envelope file → ``props``; the entity's own plain file
    (``profile.json``) → top level. Returns (the dict to write into, whether it is a ``state`` block)."""
    if src.endswith("entries.json"):
        return data.setdefault(env.id, {"class": env.cls}).setdefault("props", {}), False
    if isinstance(data, dict):
        ids = {env.id, env.id.rsplit("/", 1)[-1], *env.aliases, env.name}
        listed = False
        for v in data.values():
            if isinstance(v, list):
                for it in v:
                    if not isinstance(it, dict):
                        continue
                    listed = True
                    keys = {str(it.get(k)) for k in ("id", "qid", "name", "title") if it.get(k)}
                    if keys & ids or any(_ROLE_SUFFIX_RE.sub("", k) in ids for k in keys):
                        if isinstance(it.get("state"), dict):
                            return it["state"], True
                        return it, False
        if listed:  # a file of many entries where this one is not found: never write to the file's top level (10-02 N2)
            raise LookupError(f"{env.id} not found in {src}")
        if isinstance(data.get("props"), dict) or ("id" in data and "provenance" in data):  # an engine envelope file
            return data.setdefault("props", {}), False
        return data, False
    return {}, False


def _new_in_list(root: Path, reg: Registry, res: "ApplyResult", o: dict[str, Any], spec: ClassSpec) -> None:
    """``new`` for a list-backed class: one more item in that file's list (id = <prefix><NNN>, unique in the list)."""
    f, key = spec.list_store or ("", "items")
    path = root / f
    data = _load_json(path) if path.exists() else {}
    items = data.setdefault(key, [])
    taken = {str(x.get("id")) for x in items if isinstance(x, dict)} | set(reg.entries)
    n = len(items) + 1
    pre = spec.id_prefix or o["class"][:1].upper()
    eid = f"{pre}{n:03d}"
    while eid in taken:
        n += 1
        eid = f"{pre}{n:03d}"
    item = {"id": eid, "name": o["name"], **{k: v for k, v in dict(o["props"]).items() if k != "name"}, **({"parent": o["parent"]} if o.get("parent") else {})}
    items.append(item)
    _save_json(path, data)
    props = {k: v for k, v in item.items() if k not in ("id", "parent")}
    env = Envelope(eid, o["class"], o.get("parent"), [], props, {"turn": res.turn, "by": "writer.new"}, set(), f"{f}#{key}")
    reg.add(env)
    res.created.append({"op": "new", "class": o["class"], "id": eid, "name": o["name"], "path": env.source})
    res.applied.append({"op": "new", "class": o["class"], "id": eid, "handler": "writer.new"})
    for r in o.get("_repairs") or []:
        res.repaired.append({"op": "new", "id": eid, **r})


def _patch_in_list(root: Path, env: Envelope, o: dict[str, Any], res: "ApplyResult") -> None:
    f, _, key = (env.source or "").partition("#")
    path = root / f
    data = _load_json(path)
    changes: dict[str, dict[str, Any]] = {}
    for it in data.get(key) or []:
        if isinstance(it, dict) and str(it.get("id")) == env.id:
            for k, v in o["props"].items():
                changes[k] = {"from": env.props.get(k), "to": v}
                it[k] = v
                env.props[k] = v
    _save_json(path, data)
    res.applied.append({"op": "patch", "who": env.id, "props": changes, "handler": "patch_props"})
    for r in o.get("_repairs") or []:
        res.repaired.append({"op": "patch", "who": env.id, **r})


# ── define: the schema itself grows in play (「建立状态不是证明 open schema」) ─────────────────────────
# A kind of thing the template never declared — a class (its instances are files in a new folder) or a variable — is
# defined by the narrator, written into the world's meta overlays, packed from the next turn, and usable at once.

_DEF_NAME = re.compile(r"^[a-z_][a-z0-9_]{1,31}$")
_DEF_VAR = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z0-9_]+){0,3}$")
_OPEN_FOLDER = "open"  # <data>/open/<class>/<id>.json


_PROPS_KEYS = ("props", "属性", "fields", "attrs", "プロパティ")


def _props_list(parts: list[str]) -> list[str]:
    """10-02 J6: the narrator also writes the props as one list — 属性=species:str,mood:str or 属性=species str,hp int
    (spaces split it across tokens). Fold that run back into prop=type tokens; everything else is left as it was."""
    out: list[str] = []
    i = 0
    while i < len(parts):
        head, eq, rest = parts[i].partition("=")
        if eq and head.strip().lower() in _PROPS_KEYS:
            run = [rest]
            while i + 1 < len(parts) and "=" not in parts[i + 1]:
                i += 1
                run.append(parts[i])
            for item in " ".join(run).replace("，", ",").split(","):
                bits = item.replace(":", " ").split()
                if bits:
                    out.append(f"{bits[0]}={bits[1] if len(bits) > 1 else 'str'}")
        else:
            out.append(parts[i])
        i += 1
    return out


def _define_op(parts: list[str]) -> dict[str, Any]:
    kind = parts[1].lower()
    parts = parts[:2] + _props_list(parts[2:])
    if kind == "class":  # `hp:int kind:str` (N2 1019) is the same as hp=int kind=str
        parts = parts[:2] + [re.sub(r"^([A-Za-z_][\w]*)[:：]([A-Za-z]+|\S*\|\S*)$", r"\1=\2", p) for p in parts[2:]]
    kv = {k: v for k, v in (p.split("=", 1) for p in parts[2:] if "=" in p)}
    pos = [p for p in parts[2:] if "=" not in p]
    if kind == "var":  # define var <name> <type> <initial> [min= max= note=]
        return {"op": "define", "kind": "var", "name": pos[0] if pos else "", "type": pos[1] if len(pos) > 1 else "int",
                "initial": " ".join(pos[2:]) if len(pos) > 2 else None, **{k: kv[k] for k in ("min", "max", "note") if k in kv}}
    # define class <name> [title …] prop=type … [mutable=a,b] [effect=yes] [scope=place|town|world]
    special = {k: kv.pop(k) for k in ("mutable", "effect", "scope", "title") if k in kv}
    return {"op": "define", "kind": "class", "name": pos[0] if pos else "", "title": special.get("title") or " ".join(pos[1:]),
            "props": kv, "mutable": [x for x in str(special.get("mutable") or "").split(",") if x],
            "effect": str(special.get("effect") or "").lower() in ("1", "yes", "true", "是"), "scope": special.get("scope") or "world"}


def _verify_define(root: Path, i: int, o: dict[str, Any], reg: Registry, n: dict[str, Any]) -> dict[str, Any] | Refusal:
    from neonrp.core import engine_config as _ec

    if str(_ec.get(root, "turn.schema.define", "auto")) == "forbid":
        return Refusal(i, o, "world", "op", "this world does not allow defining new classes / variables in play", fixable=False)
    kind, name = str(o.get("kind") or ""), str(o.get("name") or "").strip()
    if kind == "var":
        if not _DEF_VAR.match(name):
            return Refusal(i, o, "field", "name", f"variable name {name!r}: lowercase letters, digits, underscores and dots (e.g. town.watch)")
        if name in reg.variables:
            return Refusal(i, o, "world", "name", f"variable {name} already exists: write it directly", fixable=False)
        typ = str(o.get("type") or "int")
        if typ not in ("int", "float", "str", "bool"):
            return Refusal(i, o, "field", "type", f"unknown type {typ!r}", ["int", "float", "str", "bool"])
        init = o.get("initial")
        try:
            init = _coerce(typ, init) if init not in (None, "") else ({"int": 0, "float": 0.0, "bool": False}.get(typ, ""))
        except (TypeError, ValueError):
            return Refusal(i, o, "field", "initial", f"initial value {init!r} is not a {typ}")
        n.update({"kind": "var", "name": name, "type": typ, "initial": init,
                  **{k: float(o[k]) for k in ("min", "max") if o.get(k) not in (None, "") and re.match(r"^-?\d+(\.\d+)?$", str(o[k]))},
                  **({"note": str(o["note"])} if o.get("note") else {})})
        return n
    if kind != "class":
        return Refusal(i, o, "field", "kind", "define class … or define var …", ["class", "var"])
    name = class_slug(name)  # the schema is open: a class name is a handle, written however the model wrote it (Ghoul → ghoul)
    if name in reg.classes:
        return Refusal(i, o, "world", "name", f"class {name} already exists: write new {name} … directly", fixable=False)
    props: dict[str, dict[str, Any]] = {}
    for k, t in dict(o.get("props") or {}).items():
        t = str(t)
        if "|" in t:
            props[k] = {"type": "enum", "values": [x for x in t.split("|") if x]}
        else:  # a type the engine does not know is text: the declared schema helps, it does not gate (soft schema)
            props[k] = {"type": t if t in ("int", "float", "str", "bool", "list") else "str"}
    mutable = [m for m in o.get("mutable") or [] if m in props] or list(props)  # none named: what the world grows can change
    scope = str(o.get("scope") or "world")
    n.update({"kind": "class", "name": name, "title": str(o.get("title") or name), "props": props, "mutable": mutable,
              "effect": bool(o.get("effect")), "scope": scope if scope in ("place", "town", "world") else "world"})
    return n


def _class_spec_of(root: Path, d: dict[str, Any]) -> dict[str, Any]:
    props = d["props"]
    shown = [k for k in props if k not in ("name",)][:4]
    return {"folder": f"{get_data_dir_name(root)}/{_OPEN_FOLDER}/{d['name']}", "scope": d["scope"], "title": d["title"], "props": props,
            "mutable": d["mutable"], "effect": d["effect"], "policy": "auto", "id_prefix": d["name"][:2].upper(),
            "render": "- {id} {name}" + "".join(f" · {k} {{{k}}}" for k in shown)}


def _provisional_define(root: Path, reg: Registry, d: dict[str, Any]) -> None:
    from neonrp.core.registry import VarSpec as _VS, class_from_dict

    if d.get("kind") == "class":
        reg.classes[d["name"]] = class_from_dict(d["name"], _class_spec_of(root, d))
    elif d.get("kind") == "var":
        reg.variables[d["name"]] = _VS(d["name"], d["type"], "", d["name"], d.get("initial"), d.get("min"), d.get("max"), doc=str(d.get("note") or ""))


def _provisional_entry(reg: Registry, r: dict[str, Any]) -> None:
    """A placeholder so a later op of the same batch resolves the name; apply re-reads the real entry by name."""
    cls = {"new_npc": "npc", "new_location": "place"}.get(str(r.get("op")), str(r.get("class") or ""))
    pid = f"~pending:{cls}:{r['name']}"
    if pid not in reg.entries:
        reg.add(Envelope(pid, cls, r.get("parent") or r.get("at"), [], {"name": r["name"], **dict(r.get("props") or {})}))


def _apply_define(root: Path, reg: Registry, res: "ApplyResult", d: dict[str, Any]) -> None:
    from neonrp.core.registry import VarSpec as _VS, class_from_dict, register

    data = get_data_dir_name(root)
    if d["kind"] == "class":
        spec = _class_spec_of(root, d)
        register(root, "classes", d["name"], spec)
        (root / spec["folder"]).mkdir(parents=True, exist_ok=True)
        reg.classes[d["name"]] = class_from_dict(d["name"], spec)
        res.created.append({"op": "define", "kind": "class", "id": d["name"], "name": d["title"], "path": spec["folder"]})
        res.applied.append({"op": "define", "kind": "class", "name": d["name"], "props": list(d["props"]), "handler": "writer.define"})
        return
    path = f"{data}/meta/world_vars.json"
    store = _load_json(root / path) if (root / path).exists() else {}
    cur = store
    parts = d["name"].split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = d["initial"]
    _save_json(root / path, store)
    spec = {"type": d["type"], "path": path, "key": d["name"], **{k: d[k] for k in ("min", "max") if d.get(k) is not None},
            **({"doc": d["note"]} if d.get("note") else {})}
    register(root, "variables", d["name"], spec)
    reg.variables[d["name"]] = _VS(d["name"], d["type"], path, d["name"], d["initial"], d.get("min"), d.get("max"), doc=str(d.get("note") or ""))
    res.created.append({"op": "define", "kind": "var", "id": d["name"], "name": d["name"], "path": path})
    res.applied.append({"op": "define", "kind": "var", "name": d["name"], "value": d["initial"], "handler": "writer.define"})


def _loc(v: Any, lang: str) -> str:
    """A class's render / title in the run's language: a string as is, {lang: text} picked (ko → en → zh, 10-06)."""
    if isinstance(v, dict):
        from neonrp.core.output_lang import pick_lang

        return str(pick_lang(v, lang) or "")
    return str(v or "")


def _registrable_line(c: ClassSpec, lang: str = "zh") -> str:
    """How the narrator writes this class (one line per open-schema class in the pack, 10-01)."""
    def one(k: str, v: dict[str, Any]) -> str:
        t = str(v.get("type") or "str")
        return f"{k}={'|'.join(map(str, v['values']))}" if t == "enum" and v.get("values") else f"{k}=<{t}>"
    props = " ".join(one(k, v) for k, v in c.props.items() if k != "name")
    L = _PL(lang)
    nm = L.get("name_placeholder", "<名字>")
    s = f"- {_loc(c.title, lang) or c.name}:new {c.name} {nm} {props}".rstrip()
    if c.mutable:
        s += f" · patch {nm} {' '.join(f'{k}=…' for k in c.mutable)}"
    s += f" · remove {nm}"
    if c.effect:
        s += L.get("registrable_effect", "")
    return s


def _coerce(typ: str, val: Any) -> Any:
    if typ == "int":
        if isinstance(val, bool):
            raise ValueError
        return int(val)
    if typ == "float":
        return float(val)
    if typ == "bool":
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "是")
        return bool(val)
    return str(val)


# ── apply ────────────────────────────────────────────────────────────────────


@dataclass
class ApplyResult:
    turn: int
    commit: str | None = None
    applied: list[dict[str, Any]] = field(default_factory=list)
    refused: list[dict[str, Any]] = field(default_factory=list)
    created: list[dict[str, Any]] = field(default_factory=list)
    repaired: list[dict[str, Any]] = field(default_factory=list)
    advice: list[dict[str, Any]] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)  # engage / need for the loop; tool requests from triggers
    variables: dict[str, Any] = field(default_factory=dict)
    triggered: list[dict[str, Any]] = field(default_factory=list)  # fired triggers with reason chains
    events: list[dict[str, Any]] = field(default_factory=list)  # ledger lines this apply wrote (seq'd)
    ended: dict[str, Any] | None = None  # an ending fired this turn (id · title · turn · trigger)
    settled: dict[str, Any] | None = None  # the run reached its exit this turn: game/meta/settlement.json (core/settlement.py)
    writers: str = "on"  # on | stub | off — template writer handlers read it
    ms: float = 0.0
    ms_triggers: float = 0.0
    request_ids: list[dict[str, Any]] = field(default_factory=list)  # upstream x-request-id of every model / Jev call this turn (chronicle runs.request_ids)
    s1_fallback: str | None = None  # "quota" when System One's allowance was spent and judgments took the no-Jev path
    # 10-14 (the standard front end): what changed hands, who walks with the player, a plot stage reached, a picture to show
    gained: list[dict[str, Any]] = field(default_factory=list)  # core/holdings.diff: {who, id, cls, name, kind, from, how}
    lost: list[dict[str, Any]] = field(default_factory=list)  # {who, id, cls, name, kind, to, how}
    joined: list[dict[str, Any]] = field(default_factory=list)  # core/holdings.party: {iid, sid, name, why}
    left: list[dict[str, Any]] = field(default_factory=list)
    stages: list[dict[str, Any]] = field(default_factory=list)  # a plot's stage variable moved: {plot, var, from, to, name, cg?}
    shows: list[dict[str, Any]] = field(default_factory=list)  # pictures the world shows on its own (core/show.arrivals)
    discovered: list[dict[str, Any]] = field(default_factory=list)  # 10-15: places the player learned of {addr, name, parent, by}
    achievements: list[dict[str, Any]] = field(default_factory=list)  # 10-15: unlocked this beat {id, title, desc, scope, points} (core/achievements)
    milestones: list[dict[str, Any]] = field(default_factory=list)  # 10-15: open-adventure milestones reached {id, kind, …} (core/milestones)
    rewards: list[dict[str, Any]] = field(default_factory=list)  # 10-18: the world's reward cards earned this beat {id, kind, title, …} (core/rewards)
    audio: dict[str, Any] | None = None  # 10-15: what plays now, when it changed this beat {music, ambient, mood, by, fade_ms} (core/audio)

    def to_dict(self) -> dict[str, Any]:
        return {"request_ids": self.request_ids, **({"s1_fallback": self.s1_fallback} if self.s1_fallback else {}),
                "turn": self.turn, "commit": self.commit, "applied": self.applied, "refused": self.refused,
                "created": self.created, "repaired": self.repaired, "advice": self.advice,
                "requests": self.requests, "variables": self.variables, "triggered": self.triggered,
                "events": [e["seq"] for e in self.events], "ended": self.ended, "ms": self.ms,
                **({"settled": self.settled} if self.settled else {}),
                **({"audio": self.audio} if self.audio else {}),
                **{k: getattr(self, k) for k in ("gained", "lost", "joined", "left", "stages", "shows", "discovered", "achievements", "milestones", "rewards")
                   if getattr(self, k)}}


# ── hooks / ledger faces (thin re-exports so callers only import sdk) ────────

def on(pattern: str, fn: Any) -> Any:
    """Subscribe to landed events: sdk.on("var.changed:player.gold", fn) → off()."""
    from neonrp.core.ledger import on as _on

    return _on(pattern, fn)


def enqueue(root: Path, op: dict[str, Any], *, by: str = "hook") -> int:
    """The only write a hook may do: queue an op for the next turn's verify."""
    from neonrp.core.ledger import enqueue as _enqueue

    return _enqueue(root, op, by=by)


def events(root: Path, *, since: int = 0, type: str | None = None, limit: int = 500) -> list[dict[str, Any]]:  # noqa: A002
    from neonrp.core.ledger import events as _events

    return _events(root, since=since, type=type, limit=limit)


def history(root: Path, var: str, *, since_turn: int = 0) -> list[dict[str, Any]]:
    from neonrp.core.ledger import history as _history

    return _history(root, var, since_turn=since_turn)


def _names_back(reg: Registry, o: dict[str, Any]) -> dict[str, Any]:
    """`{{user}}` / `{{elena}}` inside free text an op writes (a note, a file body) → the names, once the op is settled
    (handles while working, names when written down). Identity fields (who / on / to) keep their ids."""
    out = dict(o)
    if isinstance(out.get("props"), dict):
        out["props"] = {k: (reg.render_refs(v) if isinstance(v, str) and k not in ("on", "name") else v) for k, v in out["props"].items()}
    if isinstance(out.get("body"), str):
        out["body"] = reg.render_refs(out["body"])
    return out


def apply(root: Path, ops: list[dict[str, Any]], reg: Registry, *, turn: int = 0,
          refused: list[Refusal] | None = None, writers: str = "on", narration: str = "", player_says: str = "",
          ticks: bool = True) -> ApplyResult:
    """Run accepted ops: action handlers first (map / writers), then updates (single writer). ``ticks=False``: a second
    apply inside the same turn (the background write-down's correction) — the world's per-turn ticks ran already."""
    from neonrp.core import triggers as _triggers

    t0 = time.perf_counter()
    res = ApplyResult(turn=turn, refused=[r.to_dict() for r in (refused or [])])
    before = _triggers.snapshot(reg)
    for pid in [k for k in reg.entries if k.startswith("~pending:")]:  # verify's same-batch placeholders: patch maps them by name
        reg.remove(pid)
    from neonrp.core import holdings as _holdings

    held = _holdings.snapshot(reg)
    ops = [_names_back(reg, o) for o in ops]
    actions = [o for o in ops if reg.actions.get(o["op"], None) and reg.actions[o["op"]].kind == "action"]
    actions.sort(key=lambda o: 0 if o.get("op") == "define" else 1)  # the schema grows before anything is created in it
    updates = [o for o in ops if reg.actions.get(o["op"], None) and reg.actions[o["op"]].kind == "update"]
    for o in actions:
        try:
            _apply_action(root, o, reg, res, writers=writers)
        except Exception as exc:  # noqa: BLE001 — one handler failing never kills the turn
            logger.warning("v3 apply %s failed: %s", o.get("op"), exc, exc_info=True)
            res.refused.append({"op": o, "scope": "world", "field": "op", "why": f"handler error: {exc}"[:200]})
    for o in updates:
        try:
            _apply_update(root, o, reg, res)
        except Exception as exc:  # noqa: BLE001
            logger.warning("v3 apply %s failed: %s", o.get("op"), exc, exc_info=True)
            res.refused.append({"op": o, "scope": "entity", "field": "var", "why": f"handler error: {exc}"[:200]})
    if ticks:
        _run_ticks(root, reg, res, turn=turn, writers=writers)
    try:
        res.triggered = _triggers.run(root, reg, before, res, turn=turn, narration=narration, player_says=player_says)
    except Exception as exc:  # noqa: BLE001 — a bad rule never kills the turn
        logger.warning("v3 triggers failed: %s", exc, exc_info=True)
    try:  # deaths recorded; an exit reached (ending / the player's death / insanity / a segment) settles the run (R5)
        from neonrp.core import settlement as _settlement

        _settlement.after_apply(root, reg, res, turn=turn)
    except Exception as exc:  # noqa: BLE001 — settling never kills the turn
        logger.warning("settlement failed: %s", exc, exc_info=True)
    res.variables = {k: v.value for k, v in reg.variables.items()}
    after_landed(root, reg, res, held, before.get("vars") or {}, narration=narration)
    res.ms = round((time.perf_counter() - t0) * 1000, 1)
    # the one outlet: everything that landed becomes ledger events, then hooks are pushed
    try:
        from neonrp.core import ledger as _ledger

        res.events = _ledger.append(root, turn, _ledger.from_apply(res))
    except Exception as exc:  # noqa: BLE001
        logger.warning("v3 ledger failed: %s", exc, exc_info=True)
    return res


def after_landed(root: Path, reg: Registry, res: ApplyResult, held: dict[str, Any], vars0: dict[str, Any], *, narration: str = "") -> None:
    """What the front end is told after everything landed (10-14): things that changed hands (gained / lost), who joined
    or left the player's side, a plot stage reached, the plot pictures hung where the player just arrived. Read off the
    registry before / after — whoever made the change (op, handler, tick, trigger). Never fails the apply."""
    try:
        from neonrp.core import holdings as _holdings

        res.gained, res.lost = _holdings.diff(held, _holdings.snapshot(reg))
        res.joined, res.left = _holdings.party(root, reg, held)
    except Exception as exc:  # noqa: BLE001
        logger.warning("holdings diff failed: %s", exc, exc_info=True)
    try:  # whoever shares a place with the player has met them, and was last seen there (core/people, 10-15)
        from neonrp.core import people as _people

        _people.mark_met(root, reg, turn=res.turn, before=held)
        if isinstance(res.ended, dict) and res.ended.get("id"):  # the player's record: this ending, the companions with them
            from neonrp.core import player_data as _pd

            _pd.after_ending(root, reg, res.ended)
            try:  # and chronicle's record of it (achievement attachments point at it; spooled, sent in the background)
                from neonrp.core import chronicle as _chron

                _chron.ending(root, res.ended)
            except Exception:  # noqa: BLE001
                logger.debug("chronicle ending not spooled", exc_info=True)
        _new = _people.mark_seen(root, reg, before=held, narration=narration)  # what was in view or named stays known
        res.discovered = _people.discovered(root, reg, newly_seen=_new, created=res.created, turn=res.turn,
                                            moved=bool(held.get("player")) and held.get("player") != reg.player_location)
    except Exception as exc:  # noqa: BLE001
        logger.warning("met_player not marked: %s", exc, exc_info=True)
    try:
        from neonrp.core import stages as _stages

        res.stages = _stages.changes(root, vars0, res.variables)
    except Exception as exc:  # noqa: BLE001
        logger.warning("stage changes failed: %s", exc, exc_info=True)
    try:
        from neonrp.core import show as _show

        res.shows = _show.arrivals(root, reg, held.get("player"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("arrival pictures failed: %s", exc, exc_info=True)
    try:  # 10-15: open-adventure milestones (places · commissions · days), then what this beat unlocked
        from neonrp.core import achievements as _ach
        from neonrp.core import milestones as _ms

        res.milestones = _ms.after_apply(root, reg, res, vars0)
        if res.settled:  # 10-18: 打完一局 — the player's record has one row per run that reached its exit
            from neonrp.core import player_data as _pd

            _pd.note_run(root, res.settled.get("exit") if isinstance(res.settled, dict) else None)
            if isinstance(res.settled, dict):  # who the plots' collect rules let the player take (settlement.collected) go into the record
                _pd.collect(root, res.settled.get("collected"))
        res.achievements = _ach.after_apply(root, reg, res)
    except Exception as exc:  # noqa: BLE001
        logger.warning("milestones / achievements failed: %s", exc, exc_info=True)
    try:  # 10-18: the world's reward cards (template rewards, allowed by the contract)
        from neonrp.core import rewards as _rewards

        res.rewards = _rewards.after_apply(root, reg, res)
    except Exception as exc:  # noqa: BLE001
        logger.warning("rewards failed: %s", exc, exc_info=True)
    try:  # 10-15: the music / ambient bed for where the world is now (core/audio) — only when it changed
        from neonrp.core import audio as _audio

        res.audio = _audio.after_apply(root, reg, res)
    except Exception as exc:  # noqa: BLE001
        logger.warning("audio cue failed: %s", exc, exc_info=True)


def _run_ticks(root: Path, reg: Registry, res: ApplyResult, *, turn: int, writers: str) -> None:
    """The pack's world ticks (``Pack.ticks``, mixins add theirs): after the turn's own ops, before the
    triggers, each tick proposes ops that land like any other (so they reach triggers and the ledger).
    Tick ops are the world's own rules — not the model's — and carry ``by: tick:<name>``.
    First the core's own tick: open-schema effects (core/effects.py) count down and apply their per-turn changes."""
    from neonrp.core import effects as _effects

    for o in _effects.tick_ops(reg, skip={str(c.get("id")) for c in res.created}):
        spec = reg.actions.get(str(o.get("op")))
        if spec is None:
            continue
        o = {**o, "by": "tick:effects"}
        try:
            if spec.kind == "action":
                _apply_action(root, o, reg, res, writers=writers)
            else:
                _apply_update(root, o, reg, res)
        except Exception as exc:  # noqa: BLE001
            res.refused.append({"op": o, "scope": "world", "field": "op", "why": f"tick effects: {exc}"[:200]})
    try:
        from neonrp.packs import resolve as _resolve_pack

        names = list(_resolve_pack(root).ticks)
    except Exception:  # noqa: BLE001
        return
    if not names:
        return
    from neonrp.core.handlers import resolve as _resolve

    for name in names:
        try:
            ops = _resolve(name)(root, reg, turn=turn, res=res) or []
        except Exception as exc:  # noqa: BLE001 — a bad tick never kills the turn
            logger.warning("tick %s failed: %s", name, exc, exc_info=True)
            continue
        try:
            from neonrp.core import orchestration as _orch

            _unit = _orch.unit_of(name)
        except Exception:  # noqa: BLE001
            _orch, _unit = None, None
        for o in ops:
            spec = reg.actions.get(str(o.get("op")))
            if spec is None:
                res.refused.append({"op": o, "scope": "world", "field": "op", "why": f"tick {name}: unregistered op"})
                continue
            if _orch is not None and not _orch.in_scope(_unit, o):  # O7: a unit writes only what it declared
                res.refused.append({"op": o, "scope": "world", "field": "unit", "why": f"tick {name}: outside its declared writes"})
                continue
            o = {**o, "by": f"tick:{name.partition(':')[0].rsplit('.', 1)[-1]}"}
            try:
                if spec.kind == "action":
                    _apply_action(root, o, reg, res, writers=writers)
                else:
                    _apply_update(root, o, reg, res)
            except Exception as exc:  # noqa: BLE001
                res.refused.append({"op": o, "scope": "world", "field": "op", "why": f"tick {name}: {exc}"[:200]})


def tick(root: Path, *, turns: int = 1, start: int | None = None) -> list[ApplyResult]:
    """Advance the world with no player and no model: each step = an empty apply, so the pack's ticks
    and the triggers run (the world lives on between turns — observatory / auto-tick)."""
    out: list[ApplyResult] = []
    for i in range(max(1, int(turns))):
        reg = load_registry(root)
        t = (start if start is not None else int(reg.variables["turn"].value if "turn" in reg.variables else 0)) + i
        out.append(apply(root, [], reg, turn=t))
    return out


def _apply_template_op(root: Path, o: dict[str, Any], reg: Registry, res: ApplyResult) -> None:
    """Land a template-registered op through its handler — fn(root, reg, op_dict, res) -> dict | bool | None."""
    from neonrp.core.handlers import HandlerError, resolve as _resolve

    spec = reg.actions[o["op"]]
    try:
        out = _resolve(spec.handler)(root, reg, dict(o), res)
    except HandlerError as exc:
        res.refused.append({"op": o, "scope": "world", "field": "op", "why": f"handler error: {exc}"[:200]})
        return
    if out is False:
        res.refused.append({"op": o, "scope": "world", "field": "op", "why": "handler refused"})
        return
    if out is None:  # the handler recorded its own result (writers append to res.created)
        return
    rec = {k: v for k, v in o.items() if not k.startswith("_")}
    if isinstance(out, dict):
        rec.update(out)
    res.applied.append({**rec, "handler": spec.handler})


def _apply_action(root: Path, o: dict[str, Any], reg: Registry, res: ApplyResult, *, writers: str) -> None:
    op = o["op"]
    if _template_op(reg, op):
        res.writers = writers
        _apply_template_op(root, o, reg, res)
        return
    if op == "move_to":
        who, to = o["who"], o["to"]
        if str(to).startswith("~pending:"):  # a place grown earlier in this batch: the real one, by name
            _, cls, name = str(to).split(":", 2)
            named = [e for e in reg.entries.values() if e.cls == cls and e.name == name and not e.id.startswith("~pending:")]
            real = next((e for e in named if reg.current_town and e.id.startswith(reg.current_town + "/")), None) or (named[-1] if named else None)
            if real is None:
                res.refused.append({"op": o, "scope": "entity", "field": "to", "why": f"{name} was not created"})
                return
            to = real.id
            o = {**o, "to": to}
        here = reg.player_location if who == "player" else (reg.entries[who].parent if who in reg.entries else None)
        if here and str(here) == str(to):  # 10-14 V4: already there — nothing to do, not a refusal with no reason
            res.repaired.append({"op": "move_to", "who": who, "from": to, "to": to, "why": "already there"})
            return
        from neonrp.core.handlers import HandlerError, resolve as _resolve

        spec = reg.actions.get("move_to")
        handler = spec.handler if spec and spec.handler else "builtin:map.move"
        try:
            ok = bool(_resolve(handler)(root, reg, who, to))
        except HandlerError as exc:
            res.refused.append({"op": o, "scope": "world", "field": "op", "why": f"handler error: {exc}"[:200]})
            return
        if ok:
            if who in reg.entries:
                reg.entries[who].parent = to
            if who == "player":
                reg.player_location = to
                if "location" in reg.variables:
                    reg.variables["location"].value = to
            res.applied.append({"op": "move_to", "who": who, "to": to, "handler": handler})
            if o.get("_clamped"):
                res.repaired.append({"op": "move_to", "who": who, "from": o["_clamped"]["wanted"], "to": to, "why": o["_clamped"]["why"]})
        else:
            res.refused.append({"op": o, "scope": "world", "field": "to", "why": f"could not move {_who_name(reg, who)} to {to} (the map has no way there)"})
    elif op in ("inspect", "pick"):  # the player's structured action from a front end (core/player_action.py)
        from neonrp.core import player_action as _pa

        _pa.land(root, reg, res, o)
    elif op in ("engage", "need"):
        res.requests.append({"op": op, "who": o["who"], "note": o.get("note", "")})
        res.applied.append({"op": op, "who": o["who"], "handler": op})
    elif op == "define":
        _apply_define(root, reg, res, o)
    elif op in ("write", "edit", "rm", "mkdir", "rmdir"):
        from neonrp.core import worldfiles as _wf

        rec = _wf.apply(root, o, res.turn)
        res.applied.append({**rec, "handler": "worldfiles"})
        if rec.get("new") or op == "mkdir":
            res.created.append({"op": op, "id": rec.get("path"), "name": rec.get("path"), "path": rec.get("path")})
    elif op == "new":
        if writers == "off":
            res.refused.append({"op": o, "scope": "world", "field": "op", "why": "writers disabled"})
            return
        spec = reg.classes[o["class"]]
        if getattr(spec, "effect", False):  # an effect: completed from its one-line rule (core/effect_rules.py)
            try:
                from neonrp.core import effect_rules as _er

                o = _er.fill(root, o)
            except Exception:  # noqa: BLE001 — a rule that does not read leaves the op as written
                logger.debug("effect rule fill skipped", exc_info=True)
        if spec.list_store is not None:
            _new_in_list(root, reg, res, o, spec)
            return
        folder = root / spec.folder
        folder.mkdir(parents=True, exist_ok=True)
        n = len(reg.of_class(o["class"])) + 1
        eid = f"{spec.id_prefix or o['class'][:1].upper()}{n:03d}"
        while eid in reg.entries or (folder / f"{eid}.json").exists():
            n += 1
            eid = f"{spec.id_prefix or o['class'][:1].upper()}{n:03d}"
        data = {"id": eid, "class": o["class"], "parent": o.get("parent"), "links": [], "props": dict(o["props"]), "rels": {},
                "provenance": {"turn": res.turn, "by": "writer.new"}}
        _save_json(folder / f"{eid}.json", data)
        env = Envelope(eid, o["class"], o.get("parent"), [], dict(o["props"]), dict(data["provenance"]), set(), str((folder / f"{eid}.json").relative_to(root)))
        reg.add(env)
        res.created.append({"op": "new", "class": o["class"], "id": eid, "name": o["name"], "path": env.source})
        res.applied.append({"op": "new", "class": o["class"], "id": eid, "handler": "writer.new"})
        for r in o.get("_repairs") or []:
            res.repaired.append({"op": "new", "id": eid, **r})


def _apply_update(root: Path, o: dict[str, Any], reg: Registry, res: ApplyResult) -> None:
    op = o["op"]
    if _template_op(reg, op):
        _apply_template_op(root, o, reg, res)
        return
    if op in ("set", "add"):
        spec = reg.variables[o["var"]]
        path = root / spec.path
        data = _load_json(path)
        cur = _get(data, spec.key)
        if op == "add":
            base = cur if isinstance(cur, (int, float)) and not isinstance(cur, bool) else (spec.value or 0)
            new = base + o["delta"]
        else:
            new = o["value"]
        if spec.monotonic and isinstance(cur, (int, float)) and isinstance(new, (int, float)) and new < cur:
            # checked against the value before the batch; something earlier in it (a journey) has moved it on since
            res.refused.append({"op": o, "scope": "world", "field": "value", "why": _back_why(spec.name, cur)})
            return
        wrap = _clock_back(spec, cur, new) if spec.monotonic else None
        if wrap == "back" and not o.get("_next_day"):
            res.refused.append({"op": o, "scope": "world", "field": "value", "why": _back_why(spec.name, cur)})
            return
        clamped = _clamp(spec, data, new)
        if clamped != new:
            res.repaired.append({"op": op, "var": spec.name, "from": new, "to": clamped, "why": "range"})
            new = clamped
        _set(data, spec.key, new)
        _save_json(path, data)
        spec.value = new
        res.applied.append({"op": op, "var": spec.name, "from": cur, "to": new, "handler": f"{op}_variable",
                            **({"by": o["by"]} if o.get("by") else {})})
        if wrap == "next" and spec.carry in reg.variables and not o.get("_next_day"):  # after the save: the carry may live in the same file
            raised = any(a.get("var") == spec.carry and isinstance(a.get("to"), (int, float)) and isinstance(a.get("from"), (int, float))
                         and a["to"] > a["from"] for a in res.applied)
            if not raised:  # the clock went past midnight and nothing in this batch moved the day on: it does now
                _apply_update(root, {"op": "add", "var": spec.carry, "delta": 1}, reg, res)
                res.repaired.append({"op": op, "var": spec.name, "from": cur, "to": new, "why": f"past midnight: {spec.carry} +1"})
    elif op == "patch":
        if str(o["who"]).startswith("~pending:"):  # created earlier in this batch: the real entry, by name
            _, cls, name = str(o["who"]).split(":", 2)
            real = next((e for e in reg.entries.values() if e.cls == cls and e.name == name and not e.id.startswith("~pending:")), None)
            if real is None:
                res.refused.append({"op": o, "scope": "entity", "field": "who", "why": f"{name} was not created"})
                return
            o = {**o, "who": real.id}
        env = reg.entries.get(o["who"])
        if env is None:  # removed earlier in this batch (10-02 N4: remove lantern, then patch lantern)
            res.refused.append({"op": o, "scope": "entity", "field": "who", "why": f"{o['who']} is gone"})
            return
        src = env.source or ""
        if env.cls == "soul" and env.props.get("sheet"):  # a character: the world writes her sheet (character/), not her soul file
            src = str(env.props["sheet"])
        path = root / src.partition("#")[0] if src else None
        if path is not None and path.is_dir():  # a folder entry (older saves: a grown place pointed at its folder)
            path = next((path / n for n in ("location.json", "index.json", "entity.json") if (path / n).is_file()), path)
        if path is None or not path.is_file():
            res.refused.append({"op": o, "scope": "entity", "field": "who", "why": f"{env.id} has no writable source file"})
            return
        if "#" in src:
            _patch_in_list(root, env, o, res)
            return
        data = _load_json(path)
        changes: dict[str, dict[str, Any]] = {}
        try:
            props, in_state = _props_slot(data, env, src)
        except LookupError as exc:
            res.refused.append({"op": o, "scope": "entity", "field": "who", "why": str(exc)})
            return
        for k, v in o["props"].items():
            changes[k] = {"from": (env.props.get("state") or {}).get(k) if in_state else env.props.get(k), "to": v}
            props[k] = v
            if in_state:
                env.props.setdefault("state", {})
                if isinstance(env.props["state"], dict):
                    env.props["state"][k] = v
            else:
                env.props[k] = v
        _save_json(path, data)
        res.applied.append({"op": "patch", "who": env.id, "props": changes, "handler": "patch_props"})
        for r in o.get("_repairs") or []:
            res.repaired.append({"op": "patch", "who": env.id, **r})
    elif op == "remove":
        env = reg.entries.get(o["who"])
        if env is None:  # gone already (earlier in this batch, or before it): nothing to do, not a refusal
            res.repaired.append({"op": "remove", "who": o["who"], "why": "already gone"})
            return
        src = env.source or ""
        f, _, key = src.partition("#")
        path = root / f if f else None
        if path is None or not path.exists():
            res.refused.append({"op": o, "scope": "entity", "field": "who", "why": f"{env.id} has no writable source file"})
            return
        if key:
            data = _load_json(path)
            data[key] = [x for x in (data.get(key) or []) if not (isinstance(x, dict) and str(x.get("id")) == env.id)]
            _save_json(path, data)
        else:
            path.unlink()
        reg.remove(env.id)
        res.applied.append({"op": "remove", "who": env.id, "class": env.cls, "name": env.name, "handler": "writer.remove"})
    elif op == "flag":
        from neonrp.packs import resolve as _resolve_pack

        fl = dict(_resolve_pack(root).flags or {})
        rel, key = str(fl.get("path") or f"{get_data_dir_name(root)}/meta/flags.json"), str(fl.get("key") or "flags")
        path = root / rel
        data = _load_json(path)
        sf = data
        for part in key.split("."):
            sf = sf.setdefault(part, {})
        prev = sf.get(o["key"])
        sf[o["key"]] = True
        _save_json(path, data)
        vname = f"flag.{o['key']}"
        if vname not in reg.variables:
            reg.variables[vname] = VarSpec(vname, "bool", rel, f"{key}.{o['key']}", True)
        reg.variables[vname].value = True
        res.applied.append({"op": "flag", "key": o["key"], "from": prev, "to": True, "handler": "set_flag"})


def _clamp(spec: Any, data: dict[str, Any], v: Any) -> Any:
    if spec.type not in ("int", "float") or isinstance(v, bool):
        return v
    lo = spec.min
    hi = spec.max
    if spec.max_key:
        mk = _get(data, spec.max_key)
        if isinstance(mk, (int, float)):
            hi = mk if hi is None else min(hi, mk)
    if lo is not None and v < lo:
        return lo
    if hi is not None and v > hi:
        return hi
    return v


def _load_json(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _get(d: Any, dotted: str, default: Any = None) -> Any:
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _set(d: dict[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[keys[-1]] = value
