"""Engine v3 registries — the closed schema (SCHEMA-AND-SDK §1–§3).

Four tables, all **derived at read time** from the files a world already has
(读时归一), with optional overlays in ``game/meta/{variables,entries,classes,
actions}.json``. Nothing here writes; the SDK does.

* ``variables`` — typed, ranged, each bound to a (file, dotted key).
* ``entries``   — every entity as an :class:`Envelope` (id / class / parent /
  links / props / aliases), whatever shape the source file has.
* ``classes``   — required props, invariants, render template per class.
* ``actions``   — the ops grammar: op → handler, kind (action | update),
  scope, removable.

Two id conventions coexist in the shipped worlds (``north-gate`` in
``game/locations``, ``gate_north`` in ``towns/T001/town_map.json``); places are
keyed by the **scoped town node** (``T001/gate_north``) and every other
spelling becomes an alias, so ``resolve()`` is the one chokepoint.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name
from neonrp.core.place_nav import canonical_node, join_location, split_location

logger = logging.getLogger(__name__)

_ROLE_SUFFIX = re.compile(r"[\(（][^)）]*[\)）]\s*$")


# ── envelopes & specs ────────────────────────────────────────────────────────


# A character's own side (10-20): what she feels, means, wants and is — set by her reply, never by the world. Everything
# else on her (hp, wounds, things, gear, what the world added) is the world's to write; where she is goes through move.
SOUL_OWN = frozenset({"mood", "trust", "intention", "goals", "relationships", "persona", "personality", "traits", "rules",
                      "recent", "role", "sid", "name_en", "memory", "memories", "thoughts", "feelings"})


@dataclass
class Envelope:
    id: str
    cls: str
    parent: str | None = None
    links: list[str] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    aliases: set[str] = field(default_factory=set)
    source: str | None = None  # relative path of the file it was read from
    rels: dict[str, str] = field(default_factory=dict)  # typed cross-class references: rel name → entry id (class.rels says what is allowed)

    @property
    def name(self) -> str:
        return str(self.props.get("name") or self.id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "class": self.cls, "parent": self.parent, "links": list(self.links),
            "props": dict(self.props), "provenance": dict(self.provenance),
            "aliases": sorted(self.aliases), "source": self.source, "rels": dict(self.rels),
        }


@dataclass
class VarSpec:
    name: str
    type: str  # int | str | bool | float
    path: str  # file relative to root
    key: str  # dotted key inside the JSON
    value: Any = None
    min: float | None = None
    max: float | None = None
    max_key: str | None = None  # dotted key holding the dynamic max (hp.max)
    readonly: bool = False
    doc: str = ""  # the rule the model sees next to the value (酒馆 <behavior-rules>): 「受伤 −10~30,休息 +5~15」
    max_step: float | None = None  # 10-02: the most one turn's ops may move it (time.day 1: 「三天后」 is an intent, not a jump)
    monotonic: bool = False  # 10-14: never goes down (the calendar: V4 B1 travel moved it to 4, then the batch's own set put it back to 2)
    carry: str | None = None  # 10-14: a monotonic HH:MM clock set hours earlier is the next day — this variable goes up by one
    # 10-05: a variable about one entry (a character's hp): shown to the model only when that entry is with the player or
    # the value is off its `rest` — dozens of NPC hp bars do not crowd the list
    about: str | None = None
    rest: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None and v is not False and v != ""}


@dataclass
class ClassSpec:
    """A class of entries. The built-in eight are fixed; a world author registers more
    (quest, faction, clue, …) and the engine then loads / checks / packs / writes them
    with no code: that is the open schema's extension face (SCHEMA-AND-SDK §2b)."""
    name: str
    parent_class: str | None = None
    required: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    render: str = ""  # pack line template, e.g. "- {id} {name} 阶段{stage}" (props by name)
    folder: str = ""  # where instances live, e.g. "game/quests" (one JSON per entry); "" = built-in loader
    scope: str = "place"  # which instances the pack shows: place (parent == here) | town | world
    tier: int = 2  # pack tier (0 never cut … 3 cut first)
    id_prefix: str = ""  # new instances: <prefix><NNN>
    props: dict[str, dict[str, Any]] = field(default_factory=dict)  # typed props: {"stage": {"type": "int", "min": 0, "max": 5}, "status": {"type": "enum", "values": [...]}}
    mutable: list[str] = field(default_factory=list)  # props the `patch` op may change in play
    rels: dict[str, str] = field(default_factory=dict)  # rel name → allowed classes "npc|soul"
    title: str = ""  # pack heading for the class's section ("本镇委托"); "" = the class name
    packed: bool = False  # the core pack renders this class's instances by `scope` even when it is not author-registered (a pack's own classes)
    policy: str = "auto"  # growth policy for `new` from the narration: auto | approve | creator | forbid (core/approvals.py)
    # 10-01: an effect class (a state on someone that runs by itself): props on · turns · check · each — core/effects.py ticks it
    effect: bool = False
    person: bool = False  # 10-13: its instances are someone — they can own things (a pack's seats); player / soul / npc always are
    clue: bool = False  # 10-15: its instances are clues (gained as kind "clue"; entities?clue=1); an entry may say so itself (props.clue)

    @property
    def list_store(self) -> tuple[str, str] | None:
        """``folder = "game/player/inventory.json#items"`` → instances are the items of that list (one file, many
        entries — no migration of existing files); ``None`` = one JSON per entry under the folder."""
        if "#" not in self.folder:
            return None
        f, _, key = self.folder.partition("#")
        return f, key or "items"

    @property
    def custom(self) -> bool:
        return bool(self.folder)


PROP_TYPES = ("int", "float", "str", "bool", "enum", "list")


def check_props(spec: ClassSpec, props: dict[str, Any], *, partial: bool = False) -> tuple[list[str], dict[str, Any], list[dict[str, Any]]]:
    """Typed-prop check for one class: (problems, coerced props, repairs). ``partial`` = a patch
    (missing required props are fine). Unknown props are allowed — the schema is open — only
    declared ones are typed."""
    problems: list[str] = []
    out: dict[str, Any] = {}
    repairs: list[dict[str, Any]] = []
    for k, v in props.items():
        ps = spec.props.get(k)
        if not isinstance(ps, dict):
            out[k] = v
            continue
        t = str(ps.get("type") or "str")
        try:
            if t == "int":
                if isinstance(v, bool):
                    raise ValueError
                nv: Any = int(v)
            elif t == "float":
                nv = float(v)
            elif t == "bool":
                nv = v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes", "是")
            elif t == "enum":
                nv = str(v)
                if nv not in [str(x) for x in ps.get("values") or []]:
                    problems.append(f"{k}={v!r} not in {ps.get('values')}")
                    continue
            elif t == "list":
                nv = list(v) if isinstance(v, (list, tuple)) else [v]
            else:
                nv = str(v)
        except (TypeError, ValueError):
            problems.append(f"{k}={v!r} is not {t}")
            continue
        if t in ("int", "float"):
            lo, hi = ps.get("min"), ps.get("max")
            cl = nv
            if lo is not None and cl < lo:
                cl = lo
            if hi is not None and cl > hi:
                cl = hi
            if cl != nv:
                repairs.append({"prop": k, "from": nv, "to": cl, "why": "range"})
                nv = cl
        out[k] = nv
    if not partial:
        for k, ps in spec.props.items():
            if isinstance(ps, dict) and ps.get("required") and out.get(k) in (None, ""):
                problems.append(f"missing required prop {k!r}")
    return problems, out, repairs


@dataclass
class ActionSpec:
    op: str
    kind: str  # action(落地的动作)| update(变量 / 属性)| tool(请求:引擎执行后回包)| request(请求:要某人回话)| mode(切层:换整份提示词再续写)
    handler: str  # what lands it: "builtin:map.move" or "module:function" (core/handlers.py)
    fields: list[str]
    scope: str = "world"  # world | souls | plugin
    parallel: bool = False
    removable: bool = True
    enabled: bool = True
    doc: str = ""
    validator: str = ""  # world-scope check before apply: "builtin:map.judge" or "module:function"
    doc_i18n: dict[str, str] = field(default_factory=dict)  # {"en": …, "ja": …}; `doc` is the zh / default line
    alias: str = ""  # how the model writes it in the ADV line grammar when that differs from the op name (move_to → move)
    wait: bool | None = None  # does the turn wait for this op's answer? None = by kind (tool / request / mode wait)

    def doc_for(self, lang: str) -> str:
        """lang → en → the zh doc (10-05: a ko run reads the en doc where the op has no ko one)."""
        return self.doc_i18n.get(lang) or (self.doc_i18n.get("en") if lang != "zh" else None) or self.doc

    def waits(self) -> bool:
        """Sync ([dice] — the prose stops until the engine answers) or async (<map> — fired, shown, never awaited).
        The registry decides; how the model marked it is only a hint (a mismatch is logged, not obeyed)."""
        return self.wait if self.wait is not None else self.kind in ("tool", "request", "mode")


@dataclass
class TriggerSpec:
    """A world author's rule over the closed schema: WHEN → IF → THEN / ELSE (core/triggers.py)."""
    id: str
    when: dict[str, Any]
    cond: list[dict[str, Any]]  # the `if` list (all must hold)
    then: list[dict[str, Any]]
    else_: list[dict[str, Any]] = field(default_factory=list)
    once: bool = False
    cooldown: int = 0
    edge: bool = True  # fire only when `if` turns true (false = every time the watched thing changes while true)
    enabled: bool = True
    doc: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "when": self.when, "if": self.cond, "then": self.then, "else": self.else_, "once": self.once,
                "cooldown": self.cooldown, "edge": self.edge, "enabled": self.enabled, "doc": self.doc, "source": self.source}


def _text_or_langs(v: Any) -> Any:
    """A render / title: a string, or {lang: text} kept as is (the pack picks the run's language when it renders, 10-06)."""
    return {str(k): str(x) for k, x in v.items()} if isinstance(v, dict) else str(v or "")


def class_from_dict(name: str, spec: dict[str, Any], base: ClassSpec | None = None) -> ClassSpec:
    """A ClassSpec from its JSON shape (pack.json / game/meta/classes.json), layered over ``base``."""
    base = base or ClassSpec(name)
    return ClassSpec(name, spec.get("parent_class", base.parent_class),
                     list(spec.get("required", base.required)), list(spec.get("invariants", base.invariants)),
                     _text_or_langs(spec.get("render", base.render)),
                     folder=str(spec.get("folder", base.folder) or ""), scope=str(spec.get("scope", base.scope) or "place"),
                     tier=int(spec.get("tier", base.tier) or 0), id_prefix=str(spec.get("id_prefix", base.id_prefix) or ""),
                     props=dict(spec.get("props", base.props) or {}), mutable=list(spec.get("mutable", base.mutable) or []),
                     rels=dict(spec.get("rels", base.rels) or {}),
                     policy=str(spec.get("policy", base.policy) or "auto"), effect=bool(spec.get("effect", base.effect)),
                     title=_text_or_langs(spec.get("title", base.title)), packed=bool(spec.get("packed", base.packed)),
                     person=bool(spec.get("person", base.person)), clue=bool(spec.get("clue", base.clue)))


def action_from_dict(op: str, spec: dict[str, Any], base: ActionSpec | None = None) -> ActionSpec:
    """An ActionSpec from its JSON shape (pack.json / game/meta/actions.json), layered over ``base``."""
    base = base or ActionSpec(op, "action", "", [])
    doc = spec.get("doc", base.doc)
    doc_i18n = dict(base.doc_i18n)
    if isinstance(doc, dict):  # pack.json: "doc": {"zh": …, "en": …, "ja": …}
        doc_i18n.update({str(k): str(v) for k, v in doc.items()})
        doc = doc_i18n.get("zh") or next(iter(doc_i18n.values()), "")
    doc_i18n.update({str(k): str(v) for k, v in (spec.get("doc_i18n") or {}).items()})
    return ActionSpec(op, str(spec.get("kind", base.kind)), str(spec.get("handler", base.handler)),
                      list(spec.get("fields", base.fields)), str(spec.get("scope", base.scope)),
                      bool(spec.get("parallel", base.parallel)), bool(spec.get("removable", base.removable)),
                      bool(spec.get("enabled", base.enabled)), str(doc or ""),
                      validator=str(spec.get("validator", base.validator) or ""), doc_i18n=doc_i18n, alias=str(spec.get("alias", base.alias) or ""),
                      wait=(bool(spec["wait"]) if spec.get("wait") is not None else base.wait))


def __getattr__(name: str) -> Any:  # DEFAULT_CLASSES / DEFAULT_ACTIONS now live in the RPG template pack (packs/rpg/pack.py)
    if name == "DEFAULT_CLASSES":
        from neonrp.packs.rpg.pack import CLASSES

        return CLASSES
    if name == "DEFAULT_ACTIONS":
        from neonrp.packs.rpg.pack import ACTIONS

        return ACTIONS
    raise AttributeError(name)



# ── registry ─────────────────────────────────────────────────────────────────


@dataclass
class Registry:
    root: Path
    variables: dict[str, VarSpec] = field(default_factory=dict)
    entries: dict[str, Envelope] = field(default_factory=dict)
    classes: dict[str, ClassSpec] = field(default_factory=dict)
    actions: dict[str, ActionSpec] = field(default_factory=dict)
    triggers: dict[str, TriggerSpec] = field(default_factory=dict)
    current_town: str | None = None
    player_location: str | None = None
    reads: int = 0
    _alias: dict[str, str] = field(default_factory=dict, repr=False)
    _names: dict[str, list[str]] = field(default_factory=dict, repr=False)
    focus_char: str | None = None  # who `{{char}}` means this beat when the caller knows (else: the one soul with the player)
    template: str = "rpg"  # the template pack the tables were seeded from
    timeline: dict[str, Any] = field(default_factory=dict)  # filled by a pack's load seam (rpg: game/timeline)
    texts: dict[str, str] = field(default_factory=dict)  # lore / notes / rumors heads (rpg)

    # -- lookup ---------------------------------------------------------
    # Identity: every spelling of an entry — id, name, sid, iid, names in other
    # languages, declared aliases — is a key; a key that more than one entry shares is *ambiguous* and `lookup` says so
    # instead of picking one. `_alias` keeps the first registration (what `resolve` has always returned); `_names` keeps
    # every entry under the key.
    def add(self, env: Envelope) -> Envelope:
        self.entries[env.id] = env
        for a in {env.id, env.name, *env.aliases}:
            key = _norm(a)
            if not key:
                continue
            if key not in self._alias:
                self._alias[key] = env.id
            ids = self._names.setdefault(key, [])
            if env.id not in ids:
                ids.append(env.id)
        return env

    def remove(self, entry_id: str) -> None:
        """Drop an entry and every name / alias that points at it (10-02: a stale alias kept a removed placeholder
        「alive」 and stole the real entry's name)."""
        self.entries.pop(entry_id, None)
        for k in [k for k, v in self._alias.items() if v == entry_id]:
            del self._alias[k]
            rest = [x for x in self._names.get(k, []) if x != entry_id and x in self.entries]
            if rest:
                self._alias[k] = rest[0]
        for k in list(self._names):
            if entry_id in self._names[k]:
                self._names[k] = [x for x in self._names[k] if x != entry_id]
                if not self._names[k]:
                    del self._names[k]

    def resolve(self, token: str | None, *, cls: str | None = None, owner: str | None = None) -> str | None:
        """Entry id for a free-text token (id / name / alias / role-suffixed name). When several entries share the
        spelling, the first registered one (as always); `lookup` is the call that reports the ambiguity."""
        hits = self.lookup(token, cls=cls, owner=owner).ids
        if not hits:
            return None
        if len(hits) > 1 and isinstance(token, str):
            first = self._alias.get(_norm(token))
            if first in hits:
                return first
        return hits[0]

    def lookup(self, token: str | None, *, cls: str | None = None, owner: str | None = None) -> "Lookup":
        """Every live entry a token may mean, narrowed by class and by owner. ``owner/name`` scopes the name to the owner's
        things; ``{{user}}`` is the player and ``{{char}}`` the one character in the scene (the SillyTavern macros)."""
        if not isinstance(token, str) or not token.strip():
            return Lookup([], "none")
        token = token.strip()
        typed = re.match(r"^([a-z][a-z0-9_]*)\s+(\S.*)$", token)  # the class written in front: "status {{elena}}/<name>"
        if typed and typed.group(1) in self.classes and cls in (None, typed.group(1)):
            cls, token = typed.group(1), typed.group(2).strip()
        braced = _BRACED.match(token)
        if braced and _norm(braced.group(1)) not in ("user", "char"):  # `{{elena}}`, `{{T001/guild}}`: a handle, written as one
            token = braced.group(1).strip()
        var_form = re.match(r"^char\.([^/.\s]+)(/.*)?$", token)  # the variable table's name for her (`char.<id>.hp`) used for her
        if var_form and token not in self.entries and var_form.group(1) in self.entries:  # 10-14 pct-house: `move char.si-chara0001 T001/study`
            token = var_form.group(1) + (var_form.group(2) or "")
        macro = self._macro(token)
        if macro is not None:
            return Lookup([macro] if macro in self.entries and (cls is None or self.entries[macro].cls == cls) else [], "macro")
        own = self.resolve(owner) if owner else None
        if re.search(r"\.(md|json|ya?ml)$", token) and token not in self.entries:  # a file written for its entry (N2 M12 r3: `towns/T001/contracts/Q002.md`)
            by_file = [e.id for e in self.entries.values() if e.source and e.source.partition("#")[0].endswith(token.lstrip("./"))]
            if len(by_file) == 1:
                return Lookup(by_file, "path")
            token = re.sub(r"\.(md|json|ya?ml)$", "", token).rpartition("/")[2]
        if "/" in token and token not in self.entries:  # `elena/herb`: the name, among that one's things
            head, _, tail = token.rpartition("/")
            o = self.resolve(head)
            if o is not None and self.is_person(self.entries[o].cls) and tail.strip():
                if own is not None and o != own:
                    return Lookup([], "none")
                ids, how = self._match(tail.strip(), cls, o, True)
                return Lookup(ids, how, owner=o)
        ids, how = self._match(token, cls, own, owner is not None)
        return Lookup(ids, how)

    def _match(self, token: str, cls: str | None, own: str | None, scoped: bool) -> tuple[list[str], str]:
        def keep(ids: list[str]) -> list[str]:
            out = [x for x in ids if x in self.entries and (cls is None or self.entries[x].cls == cls)]
            if scoped:
                out = [x for x in out if self.owner_of(self.entries[x]) == own]
            return out

        cands = [token, _ROLE_SUFFIX.sub("", token), token.split("/")[-1], canonical_node(token) or token]
        if self.current_town and "/" not in token:
            cands.append(join_location(self.current_town, canonical_node(token) or token))
        for c in cands:
            ids = keep(self._names.get(_norm(c), []))
            if len(ids) > 1 and "/" not in c:  # `guild` in two towns: a relative path, read from where the player stands
                ids = self._nearest(ids)
            if ids:
                return ids, "exact"
        first = re.split(rf"[\s{_DOTS},，:：]", token)[0]  # first word of a name ("艾琳娜·维尔" → "艾琳娜")
        ids = keep(self._names.get(_norm(first), []))
        if ids:
            return ids, "first_word"
        if "/" not in token:  # a short id away from its town (N2 M12 r3: `Q002` in the dungeon for `T001/Q002`)
            ids = keep([x for x in self.entries if x.endswith("/" + token)])
            if len(ids) == 1:
                return ids, "exact"
        stem = _NUM_SUFFIX.sub("", token)  # a numbered spelling of a stable id: elena-0001 → elena
        if stem and stem != token:
            ids = keep(self._names.get(_norm(stem), []))
            if ids:
                return ids, "stem"
        return [], "none"

    def _nearest(self, ids: list[str]) -> list[str]:
        """A bare name that several entries share, read like a relative path: up the player's chain (room → place →
        town → world), the first level under which exactly one of them sits wins; none / a tie there → all of them."""
        here = self.player_location or self.current_town
        chain = [e.id for e in self.chain(here)] if here else []
        if not chain and self.current_town:
            chain = [self.current_town]
        for anc in chain:
            under = [x for x in ids if x == anc or anc in {c.id for c in self.chain(x)[1:]} or x.startswith(f"{anc}/")]
            if under:  # one → it; several under the same nearest level → still ambiguous, but only among these
                return under
        return ids

    def handle(self, eid: str) -> str:
        """What the model sees and writes for an entry: a character by its stable id (`elena`, not this run's
        `si-elena0001`) unless two of them share it; everything else by its id (a path: `T001/guild`)."""
        e = self.entries.get(eid)
        sid = str((e.props.get("sid") if e is not None else "") or "")
        if e is not None and e.cls == "soul" and sid and sum(1 for x in self.entries.values() if x.cls == "soul" and x.props.get("sid") == sid) == 1:
            return sid
        return eid

    def render_refs(self, text: str) -> str:
        """Back from handles to names for whatever is shown or written down: `{{user}}` → the player's name, `{{elena}}` →
        艾琳娜; a brace that names nothing stays as it is."""
        if not isinstance(text, str) or "{{" not in text:
            return text

        def one(m: re.Match[str]) -> str:
            hit = self.lookup(m.group(0)).unique
            return self.entries[hit].name if hit else m.group(0)

        return _BRACED_ANY.sub(one, text)

    def _macro(self, token: str) -> str | None:
        t = _norm(token)
        if t in ("{{user}}", "<user>"):
            return "player"
        if t in ("{{char}}", "<char>"):
            if self.focus_char:
                return self.focus_char
            here = [e.id for e in self.entries.values() if e.cls == "soul" and e.parent and e.parent == self.player_location]
            return here[0] if len(here) == 1 else ""
        return None

    def owner_of(self, env: Envelope) -> str | None:
        """Whose thing an entry is: its ``on`` prop (an effect), else its parent when that is someone, else — for the
        instances kept in a list file (the player's bag, the player's effects) — the player."""
        on = env.props.get("on")
        if on not in (None, ""):
            hit = self._macro(str(on))
            if hit is None:
                hit = self._alias.get(_norm(on))
            return hit or str(on)
        if env.parent and env.parent in self.entries and self.is_person(self.entries[env.parent].cls):
            return env.parent
        spec = self.classes.get(env.cls)
        if spec is not None and (spec.list_store or spec.effect) and "player" in self.entries:
            return "player"
        return None

    def things_of(self, owner: str, cls: str | None = None) -> list[Envelope]:
        """What someone has (their effects, their carried things …), for the pack and for scoped lookups."""
        return [e for e in self.entries.values() if (cls is None or e.cls == cls) and not self.is_person(e.cls) and self.owner_of(e) == owner]

    def is_clue(self, env: Envelope) -> bool:
        """A clue: the entry says so (``props.clue``) or its class does (``clue: true``) — 10-15."""
        if env.props.get("clue") is not None:
            return bool(env.props.get("clue"))
        spec = self.classes.get(env.cls)
        return bool(spec is not None and spec.clue)

    def is_person(self, cls: str) -> bool:
        spec = self.classes.get(cls)
        return cls in OWNER_CLASSES or bool(spec is not None and spec.person)

    def of_class(self, cls: str) -> list[Envelope]:
        return [e for e in self.entries.values() if e.cls == cls]

    def exits(self, place_id: str) -> list[Envelope]:
        env = self.entries.get(place_id)
        if env is None:
            return []
        return [self.entries[x] for x in env.links if x in self.entries]

    def chain(self, entry_id: str) -> list[Envelope]:
        """Entry, its parent, its parent's parent … (place → town → world)."""
        out: list[Envelope] = []
        seen: set[str] = set()
        cur = self.entries.get(entry_id)
        while cur is not None and cur.id not in seen:
            out.append(cur)
            seen.add(cur.id)
            cur = self.entries.get(cur.parent or "")
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "variables": {k: v.to_dict() for k, v in self.variables.items()},
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
            "classes": {k: v.__dict__ for k, v in self.classes.items()},
            "actions": {k: v.__dict__ for k, v in self.actions.items()},
            "current_town": self.current_town,
            "player_location": self.player_location,
        }


_BRACED = re.compile(r"^\{\{\s*([^{}]+?)\s*\}\}$")
_BRACED_ANY = re.compile(r"\{\{\s*[^{}\s]+?\s*\}\}")
_DOTS = "·・•"  # the dots between the parts of a name
_SPACES = re.compile(rf"[\s{_DOTS}]+")
_NUM_SUFFIX = re.compile(r"[-_ ]?\d{2,}$")
# who can own things (a status sits on one, a bag belongs to one); a pack marks its own people classes `person`
OWNER_CLASSES: set[str] = {"player", "soul", "npc"}


@dataclass
class Lookup:
    ids: list[str]
    how: str  # exact | first_word | stem | macro | none
    owner: str | None = None

    @property
    def unique(self) -> str | None:
        return self.ids[0] if len(self.ids) == 1 else None

    @property
    def ambiguous(self) -> bool:
        return len(self.ids) > 1


def _norm(s: Any) -> str:
    """One key for every spelling: full / half width (NFKC), case, spaces and the dots between name parts."""
    t = unicodedata.normalize("NFKC", str(s or "")).strip().casefold()
    return _SPACES.sub("", t)


def _read(reg: Registry, path: Path) -> Any:
    reg.reads += 1
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _get(d: Any, dotted: str, default: Any = None) -> Any:
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _head(reg: Registry, path: Path, n: int) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    reg.reads += 1
    return text[:n]


# ── loading ──────────────────────────────────────────────────────────────────


def load_registry(root: Path) -> Registry:
    """Build the five tables for ``root`` (a few ms; no LLM, no writes).

    Order: the template pack seeds classes / actions → the core's own variables (``turn``, ``flag.*``)
    → the pack's ``load`` seam reads the template's own world layout (rpg: towns / souls / player …;
    a pack without one relies on the generic class folders) → overlays in ``game/meta`` → link fix-up."""
    root = Path(root)
    game = root / get_data_dir_name(root)
    reg = Registry(root=root)
    from neonrp.packs import resolve as _resolve_pack

    pack = _resolve_pack(root)  # the template: its classes / actions / mechanics / rules seed the tables
    reg.template = pack.name
    reg.classes = dict(pack.classes)
    reg.actions = {a.op: a for a in pack.actions}
    _core_actions(reg, root)
    g = get_data_dir_name(root)
    run_state = _read(reg, game / "meta" / "run_state.json") or {}
    reg.variables["turn"] = VarSpec("turn", "int", f"{g}/meta/run_state.json", "turn_count", run_state.get("turn_count", 0), readonly=True)
    _load_flags(reg, pack)
    loader = pack.mechanics.get("load")
    if loader:
        from neonrp.core.handlers import resolve as _resolve_handler

        _resolve_handler(loader)(reg, root)
    _apply_overlays(reg, game)
    _resolve_links(reg)
    _ensure_player(reg, game)
    return reg


# the player's structured actions from a front end (core/player_action.py): landed by the engine, never written by the
# model (disabled = not in the prompt's op list, refused by verify); a pack's own op of the same name wins
PLAYER_ACTIONS = (
    ActionSpec("inspect", "action", "player.inspect", ["what"], enabled=False, doc="the player looks at a thing (a front end's click)"),
    ActionSpec("pick", "action", "player.pick", ["what"], enabled=False, doc="the player takes a thing into their hands (a front end's click)"),
)


def _core_actions(reg: Registry, root: Path) -> None:
    """Ops the engine adds to every pack: the player's structured actions, and ``show`` when the run's template has
    pictures a host would show at a moment (core/show.py) — a pack's own op of the same name is kept."""
    for a in PLAYER_ACTIONS:
        reg.actions.setdefault(a.op, a)
    try:
        from neonrp.core import show as _show

        sh = _show.action(root)
    except Exception:  # noqa: BLE001 — a run without a template record has nothing to show
        sh = None
    if sh is not None:
        reg.actions.setdefault("show", sh)


def _ensure_player(reg: Registry, game: Path) -> None:
    """Every run has a player entry (every object needs one): a template that has none (a table of seats) gets one
    from the engine, so the player's things have an owner. Its spellings in every language and ``{{user}}`` point at it."""
    from neonrp.prompts import LANGS, strings

    names = {"player", "{{user}}"}
    for lg in LANGS:
        names.update(str(x) for x in strings("identity", lg).get("player_aliases") or [])
    env = reg.entries.get("player")
    if env is None:
        prof = _read(reg, game / "player" / "profile.json") or {}
        name = str(prof.get("name") or prof.get("display_name") or "player")
        env = Envelope("player", "player", reg.player_location, [], {"name": name}, source="engine")
        names.add(name)
        if "player" not in reg.classes:
            reg.classes["player"] = ClassSpec("player", None, ["name"], [])
    env.aliases |= names
    reg.add(env)


def _load_flags(reg: Registry, pack: Any) -> None:
    """``flag.*`` booleans live where the pack says (``pack.flags`` = {path, key}); the `flag` op writes there too."""
    fl = dict(getattr(pack, "flags", None) or {})
    path, key = str(fl.get("path") or ""), str(fl.get("key") or "flags")
    if not path:
        return
    data = _read(reg, reg.root / path) or {}
    for k, v in (_get(data, key) or {}).items() if isinstance(_get(data, key), dict) else []:
        reg.variables[f"flag.{k}"] = VarSpec(f"flag.{k}", "bool", path, f"{key}.{k}", bool(v))


def _resolve_links(reg: Registry) -> None:
    """Turn raw link tokens (``north-gate``) into registered ids where an alias exists."""
    for e in reg.entries.values():
        if e.cls not in ("place", "town", "region"):
            continue
        fixed: list[str] = []
        for lk in e.links:
            if lk in reg.entries:
                fixed.append(lk)
                continue
            hit = reg.resolve(lk, cls="place") or reg.resolve(lk, cls="town")
            fixed.append(hit or lk)
        e.links = fixed


def _load_triggers(reg: Registry, game: Path) -> None:
    """Fifth table: game/meta/triggers.json (id → spec) and/or <root>/manifest.json "triggers"."""
    found: dict[str, tuple[dict[str, Any], str]] = {}
    from neonrp.packs import resolve as _resolve_pack

    pk = _resolve_pack(reg.root)
    for tid, spec in pk.triggers.items():
        found[str(tid)] = (spec, f"pack:{pk.name}")
    man = _read(reg, reg.root / "manifest.json")
    if isinstance(man, dict) and man.get("triggers"):
        tr = man["triggers"]
        items = tr.items() if isinstance(tr, dict) else [(t.get("id"), t) for t in tr if isinstance(t, dict)]
        for tid, spec in items:
            if tid and isinstance(spec, dict):
                found[str(tid)] = (spec, "manifest.json")
    ov = _read(reg, game / "meta" / "triggers.json")
    if isinstance(ov, dict):
        for tid, spec in ov.items():
            if isinstance(spec, dict):
                found[str(tid)] = (spec, "game/meta/triggers.json")
    from neonrp.core.triggers import normalize as _normalize_trigger

    for tid, (spec, src) in found.items():
        n = _normalize_trigger(spec)
        reg.triggers[tid] = TriggerSpec(tid, n["when"], n["if"], n["then"], n["else"], bool(n.get("once", False)),
                                        int(n.get("cooldown", 0) or 0), bool(n.get("edge", True)), bool(n.get("enabled", True)),
                                        str(n.get("doc") or ""), src)


def _load_class_folders(reg: Registry) -> None:
    """Instances of author-registered classes: one JSON per entry under ``class.folder``."""
    for cls, spec in reg.classes.items():
        if not spec.folder:
            continue
        ls = spec.list_store
        if ls is not None:
            _load_list_store(reg, cls, ls)
            continue
        d = reg.root / spec.folder
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            data = _read(reg, f)
            if not isinstance(data, dict):
                continue
            eid = str(data.get("id") or f.stem)
            env = Envelope(eid, cls, data.get("parent"), [str(x) for x in data.get("links") or []], dict(data.get("props") or {}),
                           dict(data.get("provenance") or {}), {str(a) for a in data.get("aliases") or []},
                           str(f.relative_to(reg.root)), {str(k): str(v) for k, v in (data.get("rels") or {}).items()})
            if not env.props.get("name") and data.get("name"):
                env.props["name"] = data["name"]
            reg.add(env)


def _load_list_store(reg: Registry, cls: str, ls: tuple[str, str]) -> None:
    """Instances kept as the items of one list in one file (``inventory.json#items``): each item is an entry,
    its keys (but ``id``) its props. ``source`` = ``<file>#<key>`` so patch / remove write back in place."""
    f, key = ls
    data = _read(reg, reg.root / f)
    items = (data or {}).get(key) if isinstance(data, dict) else None
    for i, it in enumerate(items or []):
        if not isinstance(it, dict):
            continue
        eid = str(it.get("id") or f"{cls}-{i + 1}")
        props = {k: v for k, v in it.items() if k not in ("id", "parent")}
        env = Envelope(eid, cls, it.get("parent"), [], props, {}, set(), f"{f}#{key}")
        reg.add(env)


def _apply_overlays(reg: Registry, game: Path) -> None:
    _load_triggers(reg, game)
    meta = game / "meta"
    from neonrp.packs import resolve as _resolve_pack

    ov = dict(_resolve_pack(reg.root).variables)
    ov.update(_read(reg, meta / "variables.json") or {})
    if isinstance(ov, dict):
        lang = None
        for name, spec in ov.items():
            if not isinstance(spec, dict):
                continue
            doc = spec.get("doc")
            if isinstance(doc, dict):  # a pack's {zh, en, ja, ko} doc: the run's language (10-16)
                from neonrp.core.output_lang import pick_lang, prompt_lang

                lang = lang or prompt_lang(reg.root)
                spec = {**spec, "doc": pick_lang(doc, lang)}
            path = str(spec.get("path") or "")
            key = str(spec.get("key") or name)
            cur = _read(reg, reg.root / path) if path else None
            reg.variables[name] = VarSpec(name, str(spec.get("type") or "str"), path, key,
                                          _get(cur, key, spec.get("default")), min=spec.get("min"),
                                          max=spec.get("max"), max_key=spec.get("max_key"),
                                          readonly=bool(spec.get("readonly")), doc=str(spec.get("doc") or ""), max_step=spec.get("max_step"),
                                          monotonic=bool(spec.get("monotonic")), carry=spec.get("carry"))
    ov = _read(reg, meta / "classes.json")
    if isinstance(ov, dict):
        for name, spec in ov.items():
            if isinstance(spec, dict):
                reg.classes[name] = class_from_dict(name, spec, reg.classes.get(name))
    _load_class_folders(reg)
    ov = _read(reg, meta / "actions.json")
    if isinstance(ov, dict):
        for op, spec in ov.items():
            if spec is None or spec is False:
                reg.actions.pop(op, None)
                continue
            if not isinstance(spec, dict):
                continue
            reg.actions[op] = action_from_dict(op, spec, reg.actions.get(op))
    ov = _read(reg, meta / "entries.json")
    if isinstance(ov, dict):
        for eid, spec in ov.items():
            if not isinstance(spec, dict):
                continue
            env = reg.entries.get(eid) or Envelope(eid, str(spec.get("class") or "place"))
            env.cls = str(spec.get("class") or env.cls)
            env.parent = spec.get("parent", env.parent)
            env.links = list(spec.get("links", env.links))
            env.props.update(spec.get("props") or {})
            env.rels.update({str(k): str(v) for k, v in (spec.get("rels") or {}).items()})
            env.aliases |= {str(a) for a in spec.get("aliases") or []}
            env.source = env.source or "game/meta/entries.json"
            reg.add(env)


# ── envelope verification (field / entity scopes) ────────────────────────────


def check_envelope(reg: Registry, env: Envelope) -> list[str]:
    """Field + entity scope problems for one envelope (empty = ok)."""
    problems: list[str] = []
    spec = reg.classes.get(env.cls)
    if spec is None:
        return [f"unknown class {env.cls!r}"]
    for r in spec.required:
        if env.props.get(r) in (None, ""):
            problems.append(f"missing required prop {r!r}")
    for inv in spec.invariants:
        if inv == "parent_exists" and env.parent and env.parent not in reg.entries:
            problems.append(f"parent {env.parent!r} not registered")
        elif inv == "links_symmetric":
            for link in env.links:
                other = reg.entries.get(link)
                if other is not None and env.id not in other.links:
                    problems.append(f"link {link!r} not symmetric")
        elif inv == "location_exists" and env.parent and env.parent not in reg.entries:
            t, _n = split_location(env.parent)
            if not (t and t in reg.entries):
                problems.append(f"location {env.parent!r} not registered")
    if spec.props:
        problems += check_props(spec, env.props)[0]
    for rel, target in env.rels.items():
        allowed = spec.rels.get(rel)
        if allowed is None:
            problems.append(f"rel {rel!r} not declared on class {spec.name!r}")
            continue
        tid = reg.resolve(target)
        other = reg.entries.get(tid or "")
        if other is None:
            problems.append(f"rel {rel!r} → {target!r} not registered")
        elif allowed != "*" and other.cls not in allowed.split("|"):
            problems.append(f"rel {rel!r} → {target!r} is {other.cls}, allowed {allowed}")
    return problems


# ── register (build-time write face of the closed schema) ────────────────────

TABLES = ("variables", "entries", "classes", "actions", "triggers")


class RegisterError(ValueError):
    pass


def register(root: Path, table: str, entry_id: str, spec: dict[str, Any] | None, *, replace: bool = True,
             reg: "Registry | None" = None, staged: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Write one overlay entry to ``game/meta/<table>.json`` after validating it.

    ``spec=None`` removes the entry (for ``actions`` this disables the op). The
    caller reloads the registry; nothing else is touched. This is the only
    write path for the closed schema — build mode, world packs and soul packs
    all go through it.

    ``reg``: the registry to validate against, when the caller already has a current one (a plot registering its
    triggers one after another — a trigger changes nothing another trigger is checked against). Only entries, classes
    and triggers are validated against the registry; variables and actions are not, so they never load it.

    ``staged``: the caller writes the table itself once it has registered a run of entries (``write_staged``) — the
    table is read from / kept in this dict instead of being rewritten whole for every entry (10-19: a plot's 60 triggers
    rewrote triggers.json 60 times). Same file in the end.
    """
    if table not in TABLES:
        raise RegisterError(f"unknown table {table!r}; one of {TABLES}")
    if not isinstance(entry_id, str) or not entry_id.strip():
        raise RegisterError("entry id required")
    path = root / get_data_dir_name(root) / "meta" / f"{table}.json"
    if staged is not None and str(path) in staged:
        data = staged[str(path)]
    else:
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
    if spec is not None:
        if not isinstance(spec, dict):
            raise RegisterError("spec must be an object")
        if entry_id in data and not replace:
            raise RegisterError(f"{table}/{entry_id} already registered")
        if table in ("entries", "classes", "triggers") and reg is None:
            reg = load_registry(root)
        if table == "variables":
            if str(spec.get("type") or "str") not in ("int", "float", "str", "bool"):
                raise RegisterError("variable type must be int|float|str|bool")
            if not spec.get("path") or not spec.get("key"):
                raise RegisterError("variable needs path + key")
        elif table == "entries":
            cls = str(spec.get("class") or "")
            if cls not in reg.classes:
                raise RegisterError(f"unknown class {cls!r}; register it in classes first")
            env = Envelope(entry_id, cls, spec.get("parent"), list(spec.get("links") or []), dict(spec.get("props") or {}),
                           rels={str(k): str(v) for k, v in (spec.get("rels") or {}).items()})
            probs = [pr for pr in check_envelope(reg, env) if not pr.startswith("link ")]
            if probs:
                raise RegisterError("; ".join(probs))
        elif table == "actions":
            if str(spec.get("kind") or "action") not in ("action", "update", "tool", "request", "mode"):
                raise RegisterError("action kind must be action|update|tool|request")
            if not isinstance(spec.get("fields", []), list):
                raise RegisterError("action fields must be a list")
        elif table == "classes":
            for k in ("required", "invariants", "mutable"):
                if k in spec and not isinstance(spec[k], list):
                    raise RegisterError(f"class {k} must be a list")
            if entry_id in reg.classes and not reg.classes[entry_id].custom and spec.get("folder"):
                raise RegisterError(f"template class {entry_id!r} cannot be given a folder")
            if "scope" in spec and str(spec["scope"]) not in ("place", "town", "world"):
                raise RegisterError("class scope must be place|town|world")
            if "policy" in spec and str(spec["policy"]) not in ("auto", "approve", "creator", "forbid"):
                raise RegisterError("class policy must be auto|approve|creator|forbid")
            for pk, ps in (spec.get("props") or {}).items():
                if not isinstance(ps, dict) or str(ps.get("type") or "str") not in PROP_TYPES:
                    raise RegisterError(f"prop {pk!r}: type must be one of {PROP_TYPES}")
                if ps.get("type") == "enum" and not isinstance(ps.get("values"), list):
                    raise RegisterError(f"prop {pk!r}: enum needs values[]")
            for rk, rv in (spec.get("rels") or {}).items():
                if not isinstance(rv, str) or not rv:
                    raise RegisterError(f"rel {rk!r}: allowed classes must be a string like 'npc|soul' or '*'")
                for c in rv.split("|"):
                    if c != "*" and c not in reg.classes and c != entry_id:
                        raise RegisterError(f"rel {rk!r}: unknown class {c!r}")
            for mk in spec.get("mutable") or []:
                if spec.get("props") and mk not in spec["props"]:
                    raise RegisterError(f"mutable prop {mk!r} is not declared in props")
        elif table == "triggers":
            from neonrp.core.triggers import validate as _validate_trigger

            probs = _validate_trigger(reg, spec)
            if probs:
                raise RegisterError("; ".join(probs))
        data[entry_id] = spec
    else:
        if table == "actions":
            data[entry_id] = None  # tombstone = op removed
        else:
            data.pop(entry_id, None)
    if staged is not None:
        staged[str(path)] = data
    else:
        _write_table(path, data)
    return {"table": table, "id": entry_id, "path": str(path.relative_to(root)), "removed": spec is None}


def _write_table(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_staged(staged: dict[str, dict[str, Any]]) -> None:
    """Write the tables ``register(..., staged=…)`` kept back."""
    for p, data in staged.items():
        _write_table(Path(p), data)
