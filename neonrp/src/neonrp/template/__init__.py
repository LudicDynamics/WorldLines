"""Template — the layer above a world (docs/TEMPLATE-PROTOCOL.md).

A template picks and binds the layers, so one engine plays RPG / 狼人杀 / 剧本杀 / 海龟汤 / 阿瓦隆 /
AI 文明 by recombination:

    world    data  — places, NPCs, items, entries, registry (Open Schema; grows as it is played)
    souls    data  — who plays (world-native souls, or souls brought in from elsewhere)
    pack     engine layer — agent loop, base rules, base prompts (``neonrp.packs``)
    prompts  prompt layer — world-rule and character prompts, abstracted OUT of world / soul data
    plots    plot layer — stages, if/else triggers, keywords, appended prompts, endings, reveal
    lint     constraints — assets, references, game loop
    meta     card (title / pitch / cover) + mode (ending × freedom)

Folder::

    <id>.template/
      template.json
      world/ | (template.json world.builtin / world.path)
      souls/<sid>/                  a soul brought in (data)
      prompts/world.json|*.md       world prompt layer (prompt-spec shape; .md = one "always" entry)
      prompts/souls/<sid>/…         character prompt layer: overlays soul.md / persona/ / rules/
      plots/<id>/plot.json          plot packs (``neonrp.packs.rpg.plot``) + optional "prompt" (appended)
      assets/                       card cover etc.

``build`` materializes a playable run directory; ``lint`` aggregates every check into
``[{level: block|warn, code, where, msg}]``. Nothing here changes the engine core: a built run is an
ordinary world that the current engine already plays.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "worldlines.template/1"
ENDING_MODES = ("open", "single", "multi")
ZONES = ("reviewed", "open")  # 10-15: where a work sits — reviewed (checked before it reaches Hub / iOS) · open (the open zone)
FREEDOM_MODES = ("free", "semi", "guided")
# which paths inside a soul folder are PROMPT (swappable by the prompt layer) vs DATA (stay with the soul)
SOUL_PROMPT_PATHS = ("soul.md", "persona", "rules", "agents")
# …plus what the author tools write there and the engine reads from the template itself, never copied into the run's soul
# folder: the character's orchestration patch (core/soul_orchestration) and its routine (core/soul_ambient) — 10-24
SOUL_TEMPLATE_FILES = ("orchestration.json", "ambient")
# pack-level default asset requirements; the template adds to them ("a|b" = either one)
DEFAULT_ASSET_RULES: dict[str, list[str]] = {"soul": ["portrait"], "ending": [], "card": ["cover"]}
PROMPT_FILE_EXTS = (".json", ".md", ".txt")


class TemplateError(ValueError):
    pass


@dataclass
class Problem:
    level: str  # block | warn
    code: str  # e.g. "ref.world", "loop.multi", "asset.soul"
    where: str
    msg: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.code} {self.where}: {self.msg}"


@dataclass
class Template:
    dir: Path
    data: dict[str, Any]
    id: str = ""
    version: str = ""
    card: dict[str, Any] = field(default_factory=dict)
    mode: dict[str, Any] = field(default_factory=dict)
    world: dict[str, Any] = field(default_factory=dict)
    pack: dict[str, Any] = field(default_factory=dict)
    souls: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    plots: list[str] = field(default_factory=list)
    lint_rules: dict[str, Any] = field(default_factory=dict)
    models: dict[str, Any] = field(default_factory=dict)
    play_contract: str = ""  # "<id>@<version>" (template/contract.py) — the experience the template promises
    lang: str = ""  # set on a localized copy (template/i18n.py): the language its i18n/<lang>/ layer was laid in
    origin: Path | None = None  # a localized copy: the template folder it was made from
    localized_files: list[str] = field(default_factory=list)

    @property
    def pack_name(self) -> str:
        """The name the engine resolves: ``rpg`` or ``rpg+economy+factions`` (packs.compose)."""
        base = str(self.pack.get("name") or "rpg")
        mix = [str(m) for m in self.pack.get("mixins") or [] if str(m) not in base.split("+")]
        return "+".join([base, *mix])

    @property
    def uses(self) -> dict[str, Any] | None:
        """``template.json`` ``uses``: the orchestration template this world plays (core/orch_templates, 10-19 stage A) —
        ``{template, version, params}``, None when the world names none (it plays as its contract used to say)."""
        from neonrp.core import orch_templates

        return orch_templates.parse_uses(self.data.get("uses"))

    @property
    def ending_mode(self) -> str:
        return str(self.mode.get("ending") or "open")

    @property
    def zone(self) -> str | None:
        """``template.json`` ``zone`` (or ``card.zone``; else the world's ``manifest.json`` ``zone``): reviewed | open |
        None (not said). The template says it itself — the engine keeps no list of whose work is which."""
        z = self.data.get("zone") or self.card.get("zone")
        if not z:
            try:
                z = (json.loads((self.dir / str((self.data.get("world") or {}).get("path") or "world") / "manifest.json")
                                .read_text(encoding="utf-8")) or {}).get("zone")
            except (OSError, ValueError, AttributeError):
                z = None
        return str(z) if z else None

    @property
    def forkable(self) -> bool:
        """``template.json`` ``forkable: true`` (10-17): an official template that offers 「复制一份来改」 — only the
        two the local edition ships (灰橡宅 · 石津镇). The author's own works are always copyable; see ``can_fork``."""
        return self.data.get("forkable") is True

    @property
    def official(self) -> bool:
        """A copy of an official world fetched with a Worldlines account (``template.json`` ``official: true``, written
        by core/template_publish.fetch_official into the official cache): played, never exported or copied."""
        return self.data.get("official") is True

    @property
    def builtin(self) -> bool:
        """One of the worlds the local edition ships (``shipped.json`` beside the product's templates, 10-17)."""
        return self.id in shipped_ids() and any(self.dir.parent == d for d in product_dirs())

    def soul_files(self) -> list[Path]:
        """Every soul.json the template carries: its world's souls, the overlay's, the ones it brings in by path."""
        wdir = world_dir(self) or self.dir / "world"  # a builtin world's own folder too
        out = sorted({*wdir.glob("souls/*/soul.json"), *(self.dir / "world-overlay").glob("souls/*/soul.json"),
                      *(self.dir / str(r.get("path")) / "soul.json" for r in self.souls if isinstance(r, dict) and r.get("path"))})
        return [p for p in out if p.is_file()]

    @property
    def standalone(self) -> list[str]:
        """The characters whose authors let them leave this world (``soul.json`` ``standalone: true``; ``"player"`` when
        the protagonist's ``game/player/profile.json`` says so) — 10-15."""
        out: list[str] = []
        for p in self.soul_files():
            try:
                sj = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(sj, dict) and sj.get("standalone") is True and sj.get("sid") and sj["sid"] not in out:
                out.append(str(sj["sid"]))
        for prof_p in (self.dir / "world-overlay" / "game" / "player" / "profile.json",
                       (world_dir(self) or self.dir / "world") / "game" / "player" / "profile.json"):
            try:
                prof = json.loads(prof_p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(prof, dict) and "standalone" in prof:  # the overlay's word wins over the world's
                if prof["standalone"] is True:
                    out.append("player")
                break
        return out

    @property
    def take(self) -> dict[str, str | None]:
        """sid → the condition a player takes the character home on (``take_when``: companion_at_ending · ending:<id>),
        None = the author keeps it in its world (``takeable: false``) — PLATFORM-PLAY-RULES §5, 10-15."""
        out: dict[str, str | None] = {}
        for p in self.soul_files():
            try:
                sj = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(sj, dict) and sj.get("sid") and sj["sid"] not in out:
                out[str(sj["sid"])] = None if sj.get("takeable") is False else str(sj.get("take_when") or "companion_at_ending")
        return out

    def meta(self) -> dict[str, Any]:
        """What a UI shows before play (the card) and what it needs to frame play (the mode)."""
        return {"schema": SCHEMA, "id": self.id, "version": self.version, "card": self.card, "mode": self.mode, "zone": self.zone,
                "standalone": self.standalone, "take": self.take,
                "pack": self.pack_name, "plots": list(self.plots),
                "souls": [s.get("sid") if s.get("sid") else f"{s.get('pick', 1)}/{len(s.get('pool') or [])}" for s in self.souls],
                "models": self.models, **({"play_contract": self.play_contract} if self.play_contract else {}),
                **({"uses": self.uses} if self.uses else {}),
                "forkable": can_fork(self), **({"builtin": True} if self.builtin else {}),
                # 有没有开放给创作台(template.json 的 creation 块;界面据此给「✎ 在这个模板上创作」·「我的」里的「新的创作」)
                "creation": {"open": isinstance(self.data.get("creation"), dict) and bool(self.data["creation"])},
                # 创作台存的作品(author.fork(creation=True) 记的 forked_from):它是哪个模板上的 —— 一个模板可以有好几份(lead 10-23);
                #   从平台拿下来的(带 hub_ref:别人的社区作品)不算
                **({"work_of": str(ff["id"])} if isinstance(ff := self.data.get("forked_from"), dict) and ff.get("creation") and ff.get("id")
                   and not self.data.get("hub_ref") else {}),
                **({"official": True} if self.official else {}),
                # 平台上拿下来的(官方世界 · 10-21 起也有默认区社区作品):界面据此认「从 Hub 获取的」,社区作品才能举报 / 屏蔽作者
                **({"hub_ref": self.data.get("hub_ref"), "hub_revision": self.data.get("hub_revision")}
                   if self.official or (self.zone == "reviewed" and self.data.get("hub_ref")) else {}),
                **({"milestones": self.data["milestones"]} if isinstance(self.data.get("milestones"), bool) else {}),
                **({"realtime_art": self.data["realtime_art"]} if self.data.get("realtime_art") in REALTIME_ART else {}),
                **({"achievements": self.data["achievements"]} if isinstance(self.data.get("achievements"), list) else {}),
                "pc": pc_meta(self), **_i18n_meta(self)}


def can_fork(t: "Template") -> bool:
    """Whether 「复制一份来改」 is offered (10-17): the author's own work (in the write store) always; an official one
    (fetched with an account, or ``zone: reviewed``) only when it says ``forkable: true``; anything else (a dev fixture
    with no zone) yes."""
    from neonrp.template import author

    if author.writable(t) or t.forkable:
        return True
    return not (t.official or t.zone == "reviewed")


# 「画这一幕」(core/scene_art, 10-16): off = no live drawing (the author's pictures still show) · scene_only = the
# place without people · full = the place and who is in it. Left out = off.
REALTIME_ART = ("off", "scene_only", "full")
PLACEHOLDER_PLAYERS = ("", "player")   # the scaffold's own placeholder name, not a protagonist (any case)


def pc_meta(t: "Template") -> dict[str, bool]:
    """Who the player is in this world (10-15, hub2's 「用我的分身开局」 switch): ``fixed`` = the world names its own
    protagonist (its ``playthrough.json`` ``players[0].name`` is a name, not the scaffold's "Player"); ``builder`` = the
    player makes one on the builder screen (``player.builder``). The switch shows when ``builder`` or not ``fixed``.
    A template may say it outright: ``template.json`` ``player.fixed: true | false``."""
    from neonrp.template import builder as _builder

    made = _builder.declared(t)
    said = (t.data.get("player") or {}).get("fixed") if isinstance(t.data.get("player"), dict) else None
    if isinstance(said, bool):
        return {"fixed": said and not made, "builder": made}
    name = ""
    for base in (overlay_dir(t), world_dir(t)):
        try:
            pt = json.loads((base / "playthrough.json").read_text(encoding="utf-8")) if base is not None else None
        except (OSError, ValueError):
            pt = None
        players = pt.get("players") if isinstance(pt, dict) else None
        if isinstance(players, list) and players and isinstance(players[0], dict):
            name = str(players[0].get("name") or "").strip()
            break
    return {"fixed": name.lower() not in PLACEHOLDER_PLAYERS and not made, "builder": made}


def _i18n_meta(t: "Template") -> dict[str, Any]:
    """The languages a run can be localized in + the card in each (template/i18n.py); nothing when there is no layer."""
    from neonrp.template import i18n as _i18n

    if t.lang or not _i18n.layers(t):
        return {"lang": t.lang} if t.lang else {}
    return {"langs": _i18n.langs(t), "cards": {lg: _i18n.card(t, lg) for lg in _i18n.layers(t)}}


# ── load / resolve ───────────────────────────────────────────────────────────

def load(tdir: Path | str) -> Template:
    tdir = Path(tdir)
    p = tdir / "template.json" if tdir.is_dir() else tdir
    if p.is_file() and p.name != "template.json":
        tdir = p.parent
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise TemplateError(f"{p}: not found") from e
    except ValueError as e:
        raise TemplateError(f"{p}: not JSON ({e})") from e
    if not isinstance(d, dict):
        raise TemplateError(f"{p}: must be an object")
    t = Template(p.parent, d)
    t.id = str(d.get("id") or p.parent.name.removesuffix(".template"))
    t.version = str(d.get("version") or "")
    t.card = dict(d.get("card") or {})
    t.mode = dict(d.get("mode") or {})
    w = d.get("world")
    t.world = {"path": w} if isinstance(w, str) else dict(w or {})
    pk = d.get("pack")
    t.pack = {"name": pk} if isinstance(pk, str) else dict(pk or {})
    t.souls = [{"sid": s} if isinstance(s, str) else dict(s) for s in d.get("souls") or []]
    t.prompts = [str(x) for x in d.get("prompts") or []]
    t.plots = [str(x) for x in d.get("plots") or []]
    t.lint_rules = dict(d.get("lint") or {})
    t.models = dict(d.get("models") or {})
    t.play_contract = str(d.get("play_contract") or "")
    return t


def uses_problems(t: Template) -> list[Problem]:
    """``uses`` (the orchestration template, core/orch_templates): its shape, and a parameter choice the named template
    has no such choice for. A template this engine does not have is no problem — the world falls back to an open one."""
    from neonrp.core import orch_templates

    raw = t.data.get("uses")
    if raw is None:
        return []
    u = orch_templates.parse_uses(raw)
    if u is None:
        return [Problem("block", "uses.shape", "uses", 'must be {"template": "<id>", "version": "<x.y>"}')]
    if orch_templates.get(u["template"]) is None:
        return []
    why = orch_templates.check_ref(orch_templates.ref(u)) if u["params"] else None
    return [Problem("warn", "uses.param", "uses.params", why)] if why else []


def world_dir(t: Template) -> Path | None:
    """The world folder a template binds: ``{"path": rel}`` inside the template, or ``{"builtin": id}``."""
    if t.world.get("path"):
        return (t.dir / str(t.world["path"])).resolve()
    if t.world.get("builtin"):
        from neonrp import templates as _tpls

        return Path(_tpls.__file__).parent / str(t.world["builtin"])
    return None


def overlay_dir(t: Template) -> Path | None:
    """``world.overlay``: a folder copied over the world (data patches); ``world-overlay/`` by default."""
    rel = t.world.get("overlay")
    d = t.dir / str(rel) if rel else t.dir / "world-overlay"
    return d if d.is_dir() else None


def _world_souls(wdir: Path) -> dict[str, dict[str, Any]]:
    """sid → {instance_id, role, dir} for the souls a world ships with."""
    out: dict[str, dict[str, Any]] = {}
    try:
        pt = json.loads((wdir / "playthrough.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pt = {}
    for s in pt.get("souls") or []:
        if isinstance(s, dict) and s.get("sid"):
            iid = str(s.get("instance_id") or "")
            out[str(s["sid"])] = {**s, "dir": wdir / "souls" / f"{s['sid']}-{iid}"}
    return out


def draw_souls(t: Template, *, seed: str, everyone: bool = False) -> list[dict[str, Any]]:
    """The cast of one run. A souls row is a soul, or a pool to draw from (狼人杀 / 阿瓦隆 / 随机组合)::

        {"pool": [{"sid": "a"}, {"sid": "b", "path": "souls/b"}, "c"], "pick": 2, "role": "npc"}

    Draws are seeded by the run (``template.seed`` or the run folder's name): a rebuilt run keeps its cast,
    a new run draws again. A sid never appears twice. ``everyone`` = every candidate (lint's reference build)."""
    import random

    rnd = random.Random(seed)
    out: list[dict[str, Any]] = []
    for row in t.souls:
        if isinstance(row.get("pool"), list):
            pool = [{"sid": x} if isinstance(x, str) else dict(x) for x in row["pool"]]
            pool = [p for p in pool if p.get("sid") and p["sid"] not in {o["sid"] for o in out}]
            n = len(pool) if everyone else max(0, min(int(row.get("pick") or 1), len(pool)))
            for p in rnd.sample(pool, n):
                out.append({**p, **({"role": row["role"]} if row.get("role") and not p.get("role") else {})})
        elif row.get("sid") and row["sid"] not in {o["sid"] for o in out}:
            out.append(row)
    return out


def library_dir(name: str) -> Path:
    """A soul in the character library (``~/.worldlines/souls/<name>``).「角色在世界里面就是 link」——
    a template row ``{"lib": "<name>"}`` only points at the library; the soul is copied in when a run is built."""
    from neonrp.core import souls as _souls

    return _souls.SOUL_HOME / name


def linked_src(t: Template, s: dict[str, Any]) -> Path | None:
    """Where a brought-in soul comes from: ``lib`` (the character library) or ``path`` (inside the template)."""
    if s.get("lib"):
        return library_dir(str(s["lib"])).resolve()
    if s.get("path"):
        return (t.dir / str(s["path"])).resolve()
    return None


def soul_dir(t: Template, s: dict[str, Any], wdir: Path | None) -> Path | None:
    src = linked_src(t, s)
    if src is not None:
        return src
    if wdir is not None:
        native = _world_souls(wdir).get(str(s.get("sid")))
        if native:
            return Path(native["dir"])
    return None


# ── prompt layer ─────────────────────────────────────────────────────────────

def _prompt_files(t: Template) -> list[Path]:
    """World-side prompt files, in the order the template lists them (dirs expand, sorted).
    ``prompts/souls/`` is the character layer and is never read as world prompt."""
    out: list[Path] = []
    for rel in t.prompts:
        p = t.dir / rel
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix in PROMPT_FILE_EXTS and "souls" not in f.relative_to(p).parts[:1])
        else:
            out.append(p)
    return out


def prompt_layer(t: Template) -> dict[str, Any]:
    """The template's world prompt layer as one prompt spec (``neonrp.core.adv`` shape).
    A .json file is a prompt spec; a .md / .txt file is one entry (``when: always``, id = file stem)
    unless it starts with a ``<!-- when: post -->`` / ``<!-- keyword: a, b -->`` line."""
    from neonrp.core.adv import merge_prompt_spec

    spec: dict[str, Any] = {}
    for f in _prompt_files(t):
        if not f.is_file():
            continue
        if f.suffix == ".json":
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                spec = merge_prompt_spec(spec, d.get("prompt") if isinstance(d.get("prompt"), dict) else d)
            continue
        text = f.read_text(encoding="utf-8").strip()
        when: Any = "always"
        first, _, rest = text.partition("\n")
        head = first.strip()
        if head.startswith("<!--") and head.endswith("-->"):
            k, _, v = head[4:-3].strip().partition(":")
            if k.strip() == "when":
                when = v.strip() or "always"
            elif k.strip() == "keyword":
                when = {"keyword": [x.strip() for x in v.split(",") if x.strip()]}
            text = rest.strip()
        spec = merge_prompt_spec(spec, {"entries": [{"id": f.stem, "text": text, "when": when}]})
    return spec


def plot_prompt(plot: dict[str, Any]) -> dict[str, Any]:
    """A plot's appended prompt (``plot.json["prompt"]``, prompt-spec shape). Entries get the plot id as prefix."""
    p = plot.get("prompt")
    if not isinstance(p, dict):
        return {}
    pid = str(plot.get("id") or "plot")
    out = dict(p)
    if isinstance(p.get("entries"), list):
        out["entries"] = [{**e, "id": f"{pid}.{e.get('id') or i}"} for i, e in enumerate(p["entries"]) if isinstance(e, dict)]
    return out


def soul_prompt_dir(t: Template, sid: str) -> Path | None:
    for rel in t.prompts:
        base = t.dir / rel
        for cand in (base / "souls" / sid, base.parent / "souls" / sid if base.is_file() else None):
            if cand is not None and cand.is_dir():
                return cand
    d = t.dir / "prompts" / "souls" / sid
    return d if d.is_dir() else None


# ── build ────────────────────────────────────────────────────────────────────

def _stage_name(s: Any) -> str:
    from neonrp.core.objective import stage_name

    return stage_name(s)


def _j(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _w(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_plot(t: Template, rel: str) -> tuple[Path, dict[str, Any]]:
    from neonrp.packs.rpg import plot as P

    d = t.dir / rel
    return d, P.load(d)


def build(t: Template | Path | str, dest: Path | str, *, install_plots: bool = True, cast_all: bool = False,
          lang: str | None = None) -> dict[str, Any]:
    """Materialize the template into ``dest`` (must not exist): the world copied, souls selected /
    brought in with their prompt overlays, the prompt layer merged, the pack bound, plots installed.
    ``lang`` = the run's language: the template's ``i18n/<lang>/`` layer is laid over it first and every
    ``{zh,en,ja,ko}`` text in the run is narrowed to that language (template/i18n.py).
    Returns the template meta + what was done (also written to ``game/meta/template.json``)."""
    if not isinstance(t, Template):
        t = load(t)
    from neonrp.template import i18n as _i18n

    lg = _i18n.norm_lang(lang)
    if not lg:
        return _build(t, Path(dest), install_plots=install_plots, cast_all=cast_all)
    with _i18n.localized(t, lg) as lt:
        record = _build(lt, Path(dest), install_plots=install_plots, cast_all=cast_all)
    from neonrp.core.output_lang import write_output_lang
    from neonrp.core.paths import get_data_dir_name

    narrowed = _i18n.narrow_run(Path(dest), lg)
    record = _i18n.narrow(record, lg)  # the record lives in the run too: one language (its cards: this run's only)
    if isinstance(record.get("cards"), dict):
        record["cards"] = {k: v for k, v in record["cards"].items() if k == lg}
    record["i18n"] = {"lang": lg, "source": _i18n.source_lang(t), "layer": lt.lang == lg,
                      "files": list(lt.localized_files), "narrowed": narrowed}
    _w(Path(dest) / get_data_dir_name(Path(dest)) / "meta" / "template.json", record)
    write_output_lang(Path(dest), lg)  # the engine's own language follows the run's
    return record


def bring_in(t: Template, s: dict[str, Any], dest: Path) -> dict[str, Any]:
    """Copy a linked soul (a ``{lib}`` / ``{path}`` cast row) into the world folder ``dest`` under its instance of this
    template; returns its playthrough row (the caller lists it). What a run build does for every link."""
    sid = str(s.get("sid") or "")
    src = linked_src(t, s)
    if not sid or src is None or not src.is_dir():
        raise TemplateError(f"soul {sid or '?'}: {src} not found")
    sj = _j(src / "soul.json", {}) or {}
    iid = str(s.get("instance_id") or f"si-{sid}-{t.id}"[:48])
    shutil.copytree(src, Path(dest) / "souls" / f"{sid}-{iid}", dirs_exist_ok=True)
    return {"sid": sid, "instance_id": iid, "version_hash": str((sj.get("source") or {}).get("hash") or t.version or "t"),
            "head_commit": f"seed-soul-{sid}", "role": str(s.get("role") or "npc")}


def bring_in_world(t: Template, s: dict[str, Any], root: Path) -> bool:
    """A link added after a world folder was built from the template (the editor's working copy): the soul copied in
    and listed in its playthrough, as the build would have. False = that sid is already there (nothing changes)."""
    root = Path(root)
    pt_p = root / "playthrough.json"
    pt = _j(pt_p, {}) or {}
    if any(isinstance(r, dict) and str(r.get("sid")) == str(s.get("sid")) for r in pt.get("souls") or []):
        return False
    row = bring_in(t, s, root)
    pt["souls"] = [*(pt.get("souls") or []), row]
    pt["active_souls"] = [*(pt.get("active_souls") or []), row["instance_id"]]
    _w(pt_p, pt)
    if (root / ".neonrp").is_dir():
        _w(root / ".neonrp" / "playthrough.json", pt)
    return True


def _build(t: Template, dest: Path, *, install_plots: bool, cast_all: bool) -> dict[str, Any]:
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise TemplateError(f"{dest}: exists and is not empty")
    wdir = world_dir(t)
    if wdir is None or not wdir.is_dir():
        raise TemplateError(f"world not found: {t.world}")
    shutil.copytree(wdir, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".neonrp", "__pycache__", "*.pyc"))
    ov_dir = overlay_dir(t)
    if ov_dir is not None:  # world data the template adds / replaces (e.g. game/world/economy.json for a mixin)
        shutil.copytree(ov_dir, dest, dirs_exist_ok=True)
    eng_prompts = t.dir / "prompts" / "engine"
    if eng_prompts.is_dir():  # the template's overrides of engine prompt units (R3): the run's own layer
        from neonrp.core.paths import get_data_dir_name as _gdn

        shutil.copytree(eng_prompts, dest / _gdn(dest) / "meta" / "prompts", dirs_exist_ok=True)
    from neonrp.core.paths import get_data_dir_name

    data = get_data_dir_name(dest)
    shuffled = _shuffle(dest, t.world.get("shuffle"), seed=str(t.data.get("seed") or dest.name))
    native = _world_souls(wdir)
    pt_p = dest / "playthrough.json"
    pt = _j(pt_p, {}) or {}
    rows = {str(s.get("sid")): s for s in pt.get("souls") or [] if isinstance(s, dict)}
    done: dict[str, Any] = {"souls": [], "prompt_overlays": [], "plots": [], "shuffled": shuffled}

    # souls: the template's list is authoritative when present (world-native ones not listed stay on disk, inactive)
    cast = draw_souls(t, seed=str(t.data.get("seed") or dest.name), everyone=cast_all)
    done["cast"] = [str(s.get("sid")) for s in cast]
    if cast:
        new_rows: list[dict[str, Any]] = []
        for s in cast:
            sid = str(s.get("sid") or "")
            if not sid:
                continue
            if s.get("path") or s.get("lib"):  # brought in (a link): copy the soul folder under a fresh instance only now
                row = bring_in(t, s, dest)
            else:
                row = dict(rows.get(sid) or {k: v for k, v in (native.get(sid) or {}).items() if k != "dir"})
                if not row:
                    raise TemplateError(f"soul {sid}: not in the world and no path given")
                if s.get("role"):
                    row["role"] = str(s["role"])
            new_rows.append(row)
            done["souls"].append(sid)
        pt["souls"] = new_rows
        pt["active_souls"] = [r["instance_id"] for r in new_rows if r.get("instance_id")]
    else:
        done["souls"] = list(rows)
    # character prompt layer: overlay only the prompt paths of each soul (data stays)
    for r in pt.get("souls") or []:
        sid, iid = str(r.get("sid")), str(r.get("instance_id") or "")
        ov = soul_prompt_dir(t, sid)
        if ov is None:
            continue
        sd = dest / "souls" / f"{sid}-{iid}"
        for f in sorted(ov.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(ov)
            if rel.parts[0] not in SOUL_PROMPT_PATHS:
                continue  # the prompt layer never writes a soul's data (character/, memo, soul.json…)
            (sd / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, sd / rel)
            done["prompt_overlays"].append(f"{sid}:{rel.as_posix()}")
    pt["template"] = t.pack_name
    if "schema_version" not in pt:  # a world that ships no playthrough (a table game): the minimal complete one (10-09)
        tid = str(t.data.get("id") or dest.name)
        pt = {"schema_version": 2, "playthrough_id": f"pt-{tid}",
              "world": {"wid": tid, "instance_id": f"wi-{tid}", "version_hash": str(t.data.get("version") or "1"), "head_commit": "template"},
              "world_agent_team": {"seeded_from": "templates/table", "agents": [{"id": "world-agent", "role": "orchestrator", "singleton": True}]},
              "players": [{"pid": "player", "name": "Player", "state_path": "game/player", "kind": "human"}],
              "created_at": "1970-01-01T00:00:00Z", **pt}
        pt.setdefault("souls", [])
        pt.setdefault("active_souls", [])
    _w(pt_p, pt)
    (dest / ".neonrp").mkdir(exist_ok=True)
    _w(dest / ".neonrp" / "playthrough.json", pt)

    # pack binding (manifest.json["template"] is how the engine resolves the pack) + the pack's loop settings
    man_p = dest / "manifest.json"
    man = _j(man_p, {}) or {}
    man["template"] = t.pack_name
    _w(man_p, man)
    for m in t.pack.get("mixins") or []:  # a mixin seeds its closed schema from the world's data (inert without it)
        try:
            import importlib

            mod = importlib.import_module(f"neonrp.packs.mixins.{m}")
            done.setdefault("mixins", {})[str(m)] = len(mod.install(dest)) if hasattr(mod, "install") else 0
        except ImportError:
            done.setdefault("mixins", {})[str(m)] = 0
    eng = t.pack.get("engine")
    if isinstance(eng, dict) and eng:
        cur = _j(dest / data / "meta" / "engine.json", {}) or {}
        _w(dest / data / "meta" / "engine.json", _deep_merge(cur, eng))

    # prompt layer: world's own (legacy, still mixed into data) < template prompts < plots' appended prompts
    from neonrp.core.adv import merge_prompt_spec

    # world.prompts = "replace": the template's prompt layer IS the world's prompts (they were extracted out of
    # the world data); the world's own game/meta/prompt.json is dropped instead of merged underneath
    own = {} if str(t.world.get("prompts") or "") == "replace" else (_j(dest / data / "meta" / "prompt.json", {}) or {})
    (dest / data / "meta" / "prompt.json").unlink(missing_ok=True)
    spec = merge_prompt_spec(own, prompt_layer(t))
    done["prompts_from_world"] = bool(own)
    plots: list[tuple[Path, dict[str, Any]]] = [_load_plot(t, rel) for rel in t.plots]
    for _d, plot in plots:
        spec = merge_prompt_spec(spec, plot_prompt(plot))
    if spec:
        _w(dest / data / "meta" / "prompt.json", spec)

    if install_plots:
        from neonrp.packs.rpg import plot as P

        from neonrp.core.registry import load_registry

        reg_now = load_registry(dest)
        for rel, (d, plot) in zip(t.plots, plots):
            clean = {k: v for k, v in plot.items() if k not in ("prompt", "reveal")}
            clean, dropped = _drop_absent_soul_emits(clean, reg_now)
            if dropped:
                done.setdefault("dropped_soul_emits", []).extend(dropped)
            tmp = Path(tempfile.mkdtemp(prefix="wl-plot-"))
            try:
                shutil.copytree(d, tmp / d.name, dirs_exist_ok=True)
                _w(tmp / d.name / "plot.json", clean)
                P.install(dest, tmp / d.name)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            if plot.get("reveal"):  # 谜底 / 结局揭晓: kept beside the installed plot for the epilogue UI
                _w(dest / data / "plots" / str(plot["id"]) / "reveal.json", plot["reveal"])
            done["plots"].append(str(plot.get("id")))
            done.setdefault("plot_dirs", {})[str(plot.get("id"))] = rel  # slot ids name the template's folder (plot:<rel>:…)

    if t.card.get("cover") and (t.dir / str(t.card["cover"])).is_file():
        cov = t.dir / str(t.card["cover"])
        (dest / "assets").mkdir(exist_ok=True)
        shutil.copy2(cov, dest / "assets" / f"template-cover{cov.suffix}")
    if t.card.get("title"):  # the run is named by its card (launcher / observatory read game-start.json)
        gs = dest / data / "meta" / "game-start.json"
        g = _j(gs, {}) or {}
        g["name"] = str(t.card["title"])
        _w(gs, g)
    if not (dest / "agents").is_dir():  # a world that ships no play agents (a table game: werewolf) still opens as a session
        try:
            from neonrp.core.template_assets import ensure_playable_runtime_scaffold

            # the engine's minimal table host (templates/table): the pack's contract judges, the turn does the work
            done["scaffold"] = list(ensure_playable_runtime_scaffold(dest, template_name="table", active_agent_id="world-agent",
                                                                     reason="template build: table host").files)
            if not (dest / "runtime_contract.json").exists():  # multi-agent, like the worlds that ship their own
                shutil.copy(Path(__file__).resolve().parents[1] / "templates" / "table" / "runtime_contract.json", dest / "runtime_contract.json")
        except Exception as e:  # noqa: BLE001 — lint / the session report it; the world data is already in place
            done["scaffold_error"] = f"{type(e).__name__}: {e}"
    record = {**t.meta(), "built": done, "source": str(t.origin or t.dir)}
    from neonrp.core import scene_cg as _scg

    if _scg.opening(t.data):  # the opening's fixed CG (10-14): the screen plays them before the first beat
        record["opening"] = {"cg": [{"slot": f"opening.cg:{k}", **{f: v for f, v in cg.items() if f != "prompt"}} for k, cg in _scg.opening(t.data)]}
    if isinstance(t.data.get("audio"), dict):  # the world's music / beds (core/audio reads it off the run, 10-15)
        record["audio"] = t.data["audio"]
    if isinstance(t.data.get("settlement"), dict):  # the template's own settlement amounts over its contract's (core/truth_quiz.points)
        record["settlement"] = t.data["settlement"]
    try:  # the effective presentation (pack + mixins < template): views / panels / slots the run's UI reads
        from neonrp.template import v3 as _v3

        record["ui"] = _v3.ui(t)
    except Exception:  # noqa: BLE001 — a pack that does not load is reported by lint
        pass
    _w(dest / data / "meta" / "template.json", record)
    if t.play_contract:  # the run carries its contract (settlement reads it; the run stays self-contained)
        from neonrp.template import contract as _contract

        try:
            _w(dest / data / "meta" / "play_contract.json", {**_contract.load(t.play_contract), "_ref": t.play_contract})
        except _contract.ContractError:
            pass  # lint reports contract.unknown
    orch = template_orchestration(t)
    if orch:  # the template's edit of the orchestration graph (O1, 10-05): a whole graph or {remove, add}
        _w(dest / data / "meta" / "orchestration.json", orch)
    return record


def template_orchestration(t: Template) -> dict[str, Any]:
    """``template.json["orchestration"]``: inline, or a path (JSON file) inside the template folder."""
    o = t.data.get("orchestration")
    if isinstance(o, str) and o.strip():
        o = _j(t.dir / o, {})
    return dict(o) if isinstance(o, dict) else {}


def _drop_absent_soul_emits(plot: dict[str, Any], reg: Any) -> tuple[dict[str, Any], list[str]]:
    """A cast drawn from a pool may leave out a soul the plot talks to: those ``to: soul`` emits are dropped
    for this run (the trigger still fires its other effects) instead of failing the whole install. A trigger that is
    about one soul only (``"needs": "伊瑟"`` — her hp falling, say) goes with her."""
    import copy

    out = copy.deepcopy(plot)
    dropped: list[str] = []
    trig = out.get("triggers") if isinstance(out.get("triggers"), dict) else {}
    for tid in [k for k, v in trig.items() if isinstance(v, dict) and v.get("needs") and not reg.resolve(str(v["needs"]), cls="soul")]:
        dropped.append(f"{out.get('id')}.{tid}(needs {trig[tid]['needs']})")
        del trig[tid]
    for tid, spec in (out.get("triggers") or {}).items():
        if not isinstance(spec, dict):
            continue
        for branch in ("then", "else"):
            keep = []
            for e in spec.get(branch) or []:
                if isinstance(e, dict) and e.get("to") == "soul" and not reg.resolve(str(e.get("who") or ""), cls="soul"):
                    dropped.append(f"{out.get('id')}.{tid}.{branch}→{e.get('who')}")
                    continue
                keep.append(e)
            if branch in spec:
                spec[branch] = keep
    return out, dropped


def _shuffle(dest: Path, spec: Any, *, seed: str) -> int:
    """``world.shuffle: {"folder": "game/seats", "prop": "role"}`` — deal a prop's values anew among a class
    folder's instances each run (狼人杀发身份 / 阿瓦隆阵营 / 剧本杀分角色). Seeded by the run. Returns the count."""
    import random

    specs = spec if isinstance(spec, list) else [spec] if isinstance(spec, dict) else []
    n = 0
    for sp in specs:
        folder, prop = dest / str(sp.get("folder") or ""), str(sp.get("prop") or "")
        if not prop or not folder.is_dir():
            continue
        files = sorted(folder.glob("*.json"))
        docs = [(f, _j(f, {}) or {}) for f in files]
        vals = [d.get("props", {}).get(prop) for _f, d in docs]
        random.Random(f"{seed}:{sp.get('folder')}:{prop}").shuffle(vals)
        for (f, d), v in zip(docs, vals):
            d.setdefault("props", {})[prop] = v
            _w(f, d)
        n += len(docs)
    return n


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


# ── lint ─────────────────────────────────────────────────────────────────────

def _asset_rules(t: Template) -> dict[str, list[str]]:
    rules = {k: list(v) for k, v in DEFAULT_ASSET_RULES.items()}
    for k, v in ((t.lint_rules.get("assets") or {}) if isinstance(t.lint_rules.get("assets"), dict) else {}).items():
        rules[k] = sorted(set(rules.get(k, [])) | {str(x) for x in (v if isinstance(v, list) else [v])})
    return rules


_SOUL_ASSET_FILES = {"portrait": ("portrait",), "sprite": ("sprite",)}


def _has_soul_asset(sd: Path, kind: str) -> bool:
    stems = _SOUL_ASSET_FILES.get(kind, (kind,))
    ad = sd / "assets"
    return ad.is_dir() and any(f.stem in stems for f in ad.iterdir() if f.is_file())


def _entry_has(spec: dict[str, Any], kind: str) -> bool:
    assets = spec.get("assets") if isinstance(spec.get("assets"), dict) else {}
    props = spec.get("props") if isinstance(spec.get("props"), dict) else {}
    if kind == "prompt":
        return bool(props.get("image_prompt") or spec.get("image_prompt") or assets.get("prompt"))
    return bool(assets.get(kind))


def _lint_audio(t: Template) -> list[tuple[str, str, str, str]]:
    """``audio`` in template.json and location.json (core/audio): every value resolves, files stay small, a template's
    own audio says where it comes from (默认区 / reviewed: block · 自由区 / open: warn)."""
    from neonrp.core import audio as _audio

    out: list[tuple[str, str, str, str]] = []
    rows: list[tuple[str, str, Any]] = []  # (where, kind, value)
    cfg = t.data.get("audio")
    if cfg is not None:
        if not isinstance(cfg, dict):
            return [("block", "audio.schema", "audio", "must be {theme?, ambient?, moods?, places?, credits?}")]
        for k in cfg:
            if k not in ("theme", "ambient", "moods", "places", "credits"):
                out.append(("warn", "audio.schema", f"audio.{k}", "unknown key (known: theme, ambient, moods, places, credits)"))
        rows += [("audio.theme", "music", cfg.get("theme")), ("audio.ambient", "ambient", cfg.get("ambient"))]
        moods = cfg.get("moods") if isinstance(cfg.get("moods"), dict) else {}
        for m, v in moods.items():
            if m not in ("tense", "crisis"):
                out.append(("block", "audio.schema", f"audio.moods.{m}", "moods are tense | crisis (calm is the theme)"))
            rows.append((f"audio.moods.{m}", "music", v))
        for addr, pa in (cfg.get("places") or {}).items() if isinstance(cfg.get("places"), dict) else []:
            if not isinstance(pa, dict):
                out.append(("block", "audio.schema", f"audio.places.{addr}", "{ambient?, bgm?}"))
                continue
            rows += [(f"audio.places.{addr}.ambient", "ambient", pa.get("ambient")), (f"audio.places.{addr}.bgm", "music", pa.get("bgm"))]
    wd = world_dir(t)
    locs = wd / "game" / "locations" if wd is not None else None
    if locs is not None and locs.is_dir():
        for lj in sorted(locs.rglob("location.json")):
            try:
                au = (json.loads(lj.read_text(encoding="utf-8")) or {}).get("audio")
            except (OSError, ValueError, AttributeError):
                continue
            if au is None:
                continue
            w = str(lj.relative_to(t.dir)) if lj.is_relative_to(t.dir) else lj.name
            if not isinstance(au, dict):
                out.append(("block", "audio.schema", w, "audio is {ambient?, bgm?}"))
                continue
            rows += [(f"{w}:audio.ambient", "ambient", au.get("ambient")), (f"{w}:audio.bgm", "music", au.get("bgm"))]
    own: list[Path] = []
    for where, kind, v in rows:
        why = _audio.check_ref(v, kind, t.dir)
        if why:
            out.append(("block", "audio.ref", where, why))
        elif isinstance(v, str) and v.startswith("assets/"):
            own.append(t.dir / v)
    ad = t.dir / "assets" / "audio"
    own += [f for f in sorted(ad.rglob("*")) if f.is_file() and f.suffix.lower() in _audio.AUDIO_EXTS] if ad.is_dir() else []
    for f in sorted(set(own)):
        if f.is_file() and f.stat().st_size > _audio.MAX_BYTES:
            out.append(("warn", "audio.size", str(f.relative_to(t.dir)), f"{f.stat().st_size // 1024} KB — keep a track under {_audio.MAX_BYTES // 1048576} MB (players download it)"))
    if own:
        cr = cfg.get("credits") if isinstance(cfg, dict) else None
        if not (isinstance(cr, str) and cr.startswith("assets/") and (t.dir / cr).is_file()):
            lvl = "block" if t.zone == "reviewed" else "warn"
            out.append((lvl, "audio.credits", "audio.credits", "the template ships its own audio: say whose it is and under what license "
                        "(audio.credits → a file such as assets/audio/CREDITS.md)"))
    return out


def lint(t: Template | Path | str, *, i18n: bool = True, i18n_deep: bool = False) -> dict[str, Any]:
    """Every problem a template has, aggregated: meta / references / pack / souls / prompts / plots /
    game loop / assets. Builds into a scratch directory so plot references are checked against the
    real world the template binds. Returns ``{"problems": [...], "publishable": bool, "meta": …}``."""
    out: list[Problem] = []
    block = lambda c, w, m: out.append(Problem("block", c, w, m))  # noqa: E731
    warn = lambda c, w, m: out.append(Problem("warn", c, w, m))  # noqa: E731
    if not isinstance(t, Template):
        try:
            t = load(t)
        except TemplateError as e:
            return {"problems": [asdict(Problem("block", "schema", "template.json", str(e)))], "publishable": False, "meta": {}}

    # meta
    if t.data.get("schema") not in (None, SCHEMA):
        warn("schema", "schema", f"unknown schema {t.data.get('schema')!r} (expected {SCHEMA})")
    if not str(t.card.get("title") or "").strip():
        block("meta.card", "card.title", "the card needs a title")
    if not str(t.card.get("pitch") or "").strip():
        warn("meta.card", "card.pitch", "no pitch (one line on the card)")
    if t.ending_mode not in ENDING_MODES:
        block("meta.mode", "mode.ending", f"must be one of {', '.join(ENDING_MODES)}")
    if t.zone is not None and t.zone not in ZONES:
        block("meta.zone", "zone", f"must be one of {', '.join(ZONES)} (or left out)")
    if "forkable" in t.data and not isinstance(t.data["forkable"], bool):  # 10-17: 复制按钮 on an official template
        block("meta.forkable", "forkable", "must be true or false")
    elif t.data.get("forkable") is True and t.zone != "reviewed":
        warn("meta.forkable", "forkable", "only means something on a default-zone (official) template — your own works can always be copied")
    mp = t.models.get("play") if isinstance(t.models, dict) else None
    if mp is not None and not (isinstance(mp, str) and "/" in mp):  # 10-24: new_run only takes provider/model, else the user's default
        warn("meta.models", "models.play", f"{mp!r} is not provider/model (e.g. deepseek/deepseek-v4-flash) — ignored, the player's own model is used")
    if "milestones" in t.data and not isinstance(t.data["milestones"], bool):  # 10-15: the author only says yes / no
        block("meta.milestones", "milestones", "must be true or false (the engine finds the milestones itself)")
    if "realtime_art" in t.data and t.data["realtime_art"] not in REALTIME_ART:  # 10-16: 画这一幕 per world (core/scene_art)
        block("meta.realtime_art", "realtime_art", f"must be one of {', '.join(REALTIME_ART)} (left out = off)")
    from neonrp.core import achievements as _ach

    for pr in _ach.validate(t.data.get("achievements")):
        block("meta.achievements", "achievements", pr)
    from neonrp.core import rewards as _rewards  # 10-18: the world's reward cards (warnings unless unreadable)

    for lvl, pr in _rewards.lint(t):
        (block if lvl == "block" else warn)("meta.rewards", "rewards", pr)
    for lvl, code, where, msg in _lint_audio(t):  # 10-15: the world's music / beds (core/audio)
        (block if lvl == "block" else warn)(code, where, msg)
    _wd = world_dir(t) or t.dir / "world"
    for _sf in [*t.soul_files(), _wd / "game" / "player" / "profile.json"]:  # 10-15: standalone is the author's yes / no
        try:
            _sj = json.loads(_sf.read_text(encoding="utf-8")) if _sf.is_file() else {}
        except (OSError, ValueError):
            _sj = {}
        _where = _sf.name if not _sf.is_relative_to(t.dir) else str(_sf.relative_to(t.dir))
        if isinstance(_sj, dict) and "standalone" in _sj and not isinstance(_sj["standalone"], bool):
            block("soul.standalone", _where, "standalone is true or false")
        if isinstance(_sj, dict) and "takeable" in _sj and not isinstance(_sj["takeable"], bool):
            block("soul.takeable", _where, "takeable is true or false")
        if isinstance(_sj, dict) and "take_when" in _sj:
            from neonrp.core.player_data import take_when_ok

            _ends = {str(e) for rel in t.plots for e in ((_j(t.dir / rel / "plot.json", {}) or {}).get("endings") or {})}
            if not take_when_ok(_sj["take_when"], _ends):
                block("soul.take_when", _where, f"take_when is companion_at_ending or ending:<one of {', '.join(sorted(_ends)) or 'no endings'}>")
    if t.mode.get("freedom") and t.mode["freedom"] not in FREEDOM_MODES:
        warn("meta.mode", "mode.freedom", f"unknown freedom {t.mode['freedom']!r} (known: {', '.join(FREEDOM_MODES)})")

    # world
    wdir = world_dir(t)
    if wdir is None:
        block("ref.world", "world", "no world: give world.path or world.builtin")
    elif not wdir.is_dir():
        block("ref.world", "world", f"{wdir} not found")
        wdir = None

    # pack
    try:
        from neonrp import packs

        pk = packs.load(t.pack_name, wdir)
        for mx in t.pack.get("mixins") or []:
            try:
                packs.mixin_spec(str(mx))
            except packs.PackError as e:
                block("pack.mixin", f"pack.mixins.{mx}", str(e))
                continue
            ov = overlay_dir(t)
            has = (ov is not None and (ov / "game" / "world" / f"{mx}.json").is_file()) or \
                  (wdir is not None and (wdir / "game" / "world" / f"{mx}.json").is_file())
            if str(mx) in ("economy", "factions") and not has:
                warn("pack.mixin.data", f"pack.mixins.{mx}", f"the world has no game/world/{mx}.json — the mixin stays inert")
        mode = ((t.pack.get("engine") or {}).get("turn") or {}).get("mode")
        if mode and mode not in ("v2b", "v3"):
            block("pack.engine", "pack.engine.turn.mode", f"unknown turn mode {mode!r}")
    except Exception as e:  # noqa: BLE001
        pk = None
        block("ref.pack", "pack.name", f"pack {t.pack_name!r} does not load: {e}")

    # souls
    rules = _asset_rules(t)
    if not t.souls and wdir is not None and not _world_souls(wdir):
        warn("ref.souls", "souls", "no souls in the template or the world")
    flat: list[tuple[str, dict[str, Any]]] = []
    for i, s in enumerate(t.souls):
        if isinstance(s.get("pool"), list):
            pool = [{"sid": x} if isinstance(x, str) else dict(x) for x in s["pool"]]
            if int(s.get("pick") or 1) > len(pool):
                block("ref.soul.pool", f"souls[{i}].pick", f"pick {s.get('pick')} > pool of {len(pool)}")
            flat += [(f"souls[{i}].pool[{j}]", p) for j, p in enumerate(pool)]
        else:
            flat.append((f"souls[{i}]", s))
    for where, s in flat:
        sid = str(s.get("sid") or "")
        if not sid:
            block("ref.soul", where, "soul needs a sid")
            continue
        sd = soul_dir(t, s, wdir)
        if sd is None or not sd.is_dir():
            block("ref.soul", f"{where}.{sid}", "soul not found (not native to the world, no valid path)")
            continue
    # prompts
    for rel in t.prompts:
        if not (t.dir / rel).exists():
            block("ref.prompt", f"prompts.{rel}", "file not found")
    try:
        spec = prompt_layer(t)
    except ValueError as e:
        spec = {}
        block("prompt.parse", "prompts", str(e))
    for e in spec.get("entries") or []:
        if isinstance(e, dict) and not str(e.get("text") or "").strip():
            warn("prompt.empty", f"prompts.entries.{e.get('id')}", "empty entry")
    sp = t.dir / "prompts" / "souls"
    if sp.is_dir():
        sids = {str(s.get("sid")) for _w, s in flat} | (set(_world_souls(wdir)) if wdir and not t.souls else set())
        for d in sp.iterdir():
            if d.is_dir() and d.name not in sids:
                warn("prompt.soul", f"prompts/souls/{d.name}", "character prompts for a soul the template does not cast")
            if d.is_dir():
                for f in d.rglob("*"):
                    if f.is_file() and f.relative_to(d).parts[0] not in SOUL_PROMPT_PATHS + SOUL_TEMPLATE_FILES:
                        block("prompt.soul.data", f"prompts/souls/{d.name}/{f.relative_to(d).as_posix()}",
                              f"the prompt layer may only overlay {', '.join(SOUL_PROMPT_PATHS + SOUL_TEMPLATE_FILES)} (this is soul data)")

    # plots — checked against a scratch build of the world, so cross refs resolve
    plots: list[dict[str, Any]] = []
    scratch = Path(tempfile.mkdtemp(prefix="wl-tpl-lint-"))
    try:
        root: Path | None = None
        if wdir is not None and pk is not None:  # a broken pack cannot seed the registry the plot lint reads
            try:
                root = scratch / "run"
                build(t, root, install_plots=False, cast_all=True)  # every pool candidate present: refs resolve
            except Exception as e:  # noqa: BLE001
                block("build", "template", f"does not build: {e}")
                root = None
        from neonrp.packs.rpg import plot as P

        for rel in t.plots:
            d = t.dir / rel
            if not (d / "plot.json").is_file():
                block("ref.plot", f"plots.{rel}", "plot.json not found")
                continue
            try:
                plot = P.load(d)
            except ValueError as e:
                block("plot.parse", f"plots.{rel}", str(e))
                continue
            plots.append(plot)
            clean = {k: v for k, v in plot.items() if k not in ("prompt", "reveal")}
            try:
                plot_probs = P.lint(clean, d, root)
            except Exception as e:  # noqa: BLE001
                block("plot.lint", f"plots.{rel}", f"lint crashed: {e}")
                plot_probs = []
            for p in plot_probs:
                if p.where == "truth_quiz":
                    continue  # graded by zone below (core/truth_quiz.lint)
                out.append(Problem("block" if p.level == "error" else "warn", "plot", f"{plot.get('id') or rel}.{p.where}", p.msg))
        # a plot that talks to a soul only a pool may bring: fine when drawn, dead when not
        pooled = {str(p.get("sid") if isinstance(p, dict) else p) for row in t.souls if isinstance(row.get("pool"), list) for p in row["pool"]}
        fixed = {str(row.get("sid")) for row in t.souls if row.get("sid")}
        if root is not None and pooled - fixed:
            from neonrp.core.registry import load_registry

            reg = load_registry(root)
            iid_sid = {str(r.get("instance_id")): str(r.get("sid")) for r in (_j(root / "playthrough.json", {}) or {}).get("souls") or []}
            for plot in plots:
                for tid, spec in (plot.get("triggers") or {}).items():
                    for branch in ("then", "else"):
                        for i, e in enumerate((spec or {}).get(branch) or []):
                            if isinstance(e, dict) and e.get("to") == "soul":
                                iid = reg.resolve(str(e.get("who") or ""), cls="soul")
                                sid = iid_sid.get(str(iid), str(iid))
                                if sid in pooled - fixed:
                                    warn("loop.pool", f"{plot.get('id')}.triggers.{tid}.{branch}[{i}]",
                                         f"talks to {sid}, who is only drawn from a pool — silent in runs that don't cast them")
        # Template v3 (Mock 3.0): schema · asset · prompt · token, against the scratch run with the plots installed
        if root is not None:
            from neonrp.template import v3

            for rel in t.plots:
                d = t.dir / rel
                try:
                    pj = P.load(d)
                    clean = {k: v for k, v in pj.items() if k not in ("prompt", "reveal")}
                    tmpd = scratch / "plots" / d.name
                    shutil.copytree(d, tmpd, dirs_exist_ok=True)
                    _w(tmpd / "plot.json", clean)
                    P.install(root, tmpd)
                except Exception:  # noqa: BLE001 — a broken plot is already reported above
                    pass
            try:
                for q in v3.lint_v3(t, root, publish=t.lint_rules.get("level", "publish") == "publish"):
                    out.append(Problem(q["level"], q["code"], q["where"], q["msg"]))
            except Exception as e:  # noqa: BLE001
                block("v3.lint", "template", f"lint crashed: {e}")
            try:  # the bound world's map (MAP-SCALES-1005 G3) — warnings only
                from neonrp.core.map_lint import lint_map

                for q in lint_map(root):
                    out.append(Problem(q["level"], q["code"], q["where"], q["msg"]))
            except Exception as e:  # noqa: BLE001
                warn("map.lint", "world", f"map lint crashed: {e}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    # card assets
    for need in rules.get("card", []):
        if need == "cover" and not (t.card.get("cover") and (t.dir / str(t.card["cover"])).is_file()):
            (block if t.lint_rules.get("level") == "publish" else warn)("asset.card", "card.cover", "no cover file")

    out += opening_problems(t)
    out += variant_problems(t, plots)
    out += loop_problems(t, plots)
    from neonrp.template import contract as _contract  # the play contract the template promises (R1)

    out += [Problem(lv, code, where, msg) for lv, code, where, msg in _contract.lint(t, plots, wdir)]
    out += uses_problems(t)
    from neonrp.template import creation as _creation  # what the template opens to creators + who can be collected (10-13)

    try:
        _c = _contract.load(t.play_contract) if t.play_contract else None
    except _contract.ContractError:
        _c = None
    out += [Problem(lv, code, where, msg) for lv, code, where, msg in _creation.lint(t, plots, wdir, _c)]
    from neonrp.core import truth_quiz as _tq  # the settlement's three truth questions: required by the contract (10-16)

    out += [Problem(lv, code, where, msg) for lv, code, where, msg in _tq.lint(t, wdir, _c)]
    from neonrp.template import builder as _builder  # the player builder's declaration (面板玩家, 10-14)

    out += [Problem(lv, code, where, msg) for lv, code, where, msg in _builder.problems(t)]
    from neonrp.template import frontends as _fe  # the world's own front ends (frontends/<name>/, 10-17): local only for now —
    # a broken one never blocks publishing (it is not exported); the 前端 desk shows its own levels
    out += [Problem("warn", p["code"], p["where"], p["message"]) for p in _fe.lint(t)]
    report: dict[str, Any] = {}
    if i18n:  # the localization layers (template/i18n.py): structure, coverage per language, names left over
        from neonrp.template import i18n as _i18n

        try:
            probs_i18n, report = _i18n.lint(t, deep=i18n_deep)
            out += [Problem(lv, code, where, msg) for lv, code, where, msg in probs_i18n]
        except Exception as e:  # noqa: BLE001
            out.append(Problem("warn", "i18n.lint", "i18n", f"lint crashed: {e}"))
    probs = [asdict(p) for p in out]
    return {"problems": probs, "publishable": not any(p.level == "block" for p in out), "meta": t.meta(),
            "counts": {"block": sum(p.level == "block" for p in out), "warn": sum(p.level == "warn" for p in out)},
            **({"i18n": report} if report.get("langs") else {})}


def opening_problems(t: Template) -> list[Problem]:
    """``opening.cg`` (10-14): a list of {image | video, caption?, camera?, prompt?}, files inside the template; an entry
    not filled yet is an optional slot (warn), a malformed one blocks."""
    from neonrp.core import scene_cg
    from neonrp.packs.rpg.plot import ASSET_KINDS

    out: list[Problem] = []
    op = t.data.get("opening")
    if op is None:
        return out
    if not isinstance(op, dict) or not isinstance(op.get("cg", []), list):
        return [Problem("block", "schema.opening", "opening", "must be {\"cg\": [ {image, video?, caption?, camera?} … ]}")]
    for i, raw in enumerate(op.get("cg") or [], 1):
        w = f"opening.cg[{i}]"
        cg = scene_cg.norm(raw)
        if cg is None or not (cg.get("image") or cg.get("video")):
            out.append(Problem("block", "schema.opening", w, "needs an image or a video"))
            continue
        for kind in ("image", "video"):
            f = cg.get(kind)
            if not f:
                continue
            if not isinstance(f, str) or Path(f).is_absolute() or ".." in Path(f).parts:
                out.append(Problem("block", "schema.opening", f"{w}.{kind}", "path must be relative and stay inside the template"))
            elif Path(f).suffix.lower() not in ASSET_KINDS[kind]:
                out.append(Problem("block", "schema.opening", f"{w}.{kind}", f"{f!r} is not a {kind} file ({', '.join(ASSET_KINDS[kind])})"))
            elif not (t.dir / f).is_file():
                inst = (raw.get("id") if isinstance(raw, dict) else None) or i
                out.append(Problem("warn", "asset.optional", f"slots.opening.cg:{inst}", f"opening CG {inst}: {kind} not filled yet ({f})"))
    return out


def variant_problems(t: Template, plots: list[dict[str, Any]]) -> list[Problem]:
    """Pictures per companion (10-15): ``variants`` keys are souls of this template (else nobody sees them); an ending
    whose generic image is marked ``image_shows: <sid>`` (it draws one companion) is warned — a run with another companion
    sees that one until a generic picture or its own variant is there."""
    from neonrp.core import scene_cg

    sids = {str(o.get("sid")) for o in draw_souls(t, seed="", everyone=True)}
    out: list[Problem] = []

    def check(where: str, spec: Any) -> None:
        for sid in scene_cg.variants(spec):
            if sid not in sids:
                out.append(Problem("warn", "asset.variant", f"{where}.variants.{sid}", f"{sid!r} is not a soul of this template"))

    for i, (_inst, cg) in enumerate(scene_cg.opening(t.data), 1):
        check(f"opening.cg[{i}]", cg)
    for plot in plots:
        pid = str(plot.get("id") or "")
        for n, cg in scene_cg.stage(plot):
            check(f"{pid}.stage_cg.{n}", cg)
        for eid, spec in (plot.get("endings") or {}).items():
            if not isinstance(spec, dict):
                continue
            check(f"{pid}.endings.{eid}.assets", spec.get("assets"))
            shows = str(spec.get("image_shows") or "")
            if shows:
                own = scene_cg.variants(spec.get("assets"))
                missing = sorted(x for x in sids if x != shows and x not in own and x in _companion_sids(t))
                if missing:
                    out.append(Problem("warn", "asset.variant", f"{pid}.endings.{eid}.assets.image",
                                       f"generic image shows {shows}; {', '.join(missing)} get it too until a generic picture "
                                       "or their own variant is there"))
    return out


def _companion_sids(t: Template) -> set[str]:
    """The souls a player may pick as their companion (the builder's candidates; else every companion-role soul)."""
    try:
        from neonrp.template import builder as _builder

        if _builder.declared(t):
            return {str(o["sid"]) for o in _builder.companions(t)}
    except Exception:  # noqa: BLE001
        pass
    return {str(o.get("sid")) for o in draw_souls(t, seed="", everyone=True) if str(o.get("role") or "") == "companion"}


def run_companion(root: Path) -> str | None:
    """The companion this run's player picked (game/player/card.json; else the run's only companion-role soul) — the
    key a picture's ``variants`` are looked up by."""
    from neonrp.core.paths import get_data_dir_name

    card = _j(Path(root) / get_data_dir_name(Path(root)) / "player" / "card.json")
    picked = (card or {}).get("companion") if isinstance(card, dict) else None
    if isinstance(picked, list) and picked:
        return str(picked[0])
    from neonrp.core.holdings import _souls

    comp = sorted({s["sid"] for s in _souls(Path(root)).values() if s.get("role") == "companion" and s.get("sid")})
    return comp[0] if len(comp) == 1 else None


def variant_slot(slot: str, spec: Any, sid: str | None) -> str:
    """``<slot>@<sid>`` when the picture has a variant for this companion, else the slot itself."""
    from neonrp.core import scene_cg

    return f"{slot}@{sid}" if sid and sid in scene_cg.variants(spec) else slot


def _ending_emitters(plots: list[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    """ending id → [(trigger id, branch)] that emit it."""
    out: dict[str, list[tuple[str, str]]] = {}
    for plot in plots:
        for tid, spec in (plot.get("triggers") or {}).items():
            if not isinstance(spec, dict):
                continue
            for branch in ("then", "else"):
                for e in spec.get(branch) or []:
                    if isinstance(e, dict) and e.get("to") == "end" and e.get("ending"):
                        out.setdefault(str(e["ending"]), []).append((str(tid), branch))
    return out


def _pack_plot(t: Template) -> dict[str, Any]:
    """The pack's own end-of-game rules as a pseudo-plot of triggers (a rule pack — 狼人杀's two sides — ends the game
    without a plot); the loop lint and the contract lint both count it (10-08 E1)."""
    pp: dict[str, Any] = {"id": f"pack:{t.pack_name}", "triggers": {}}
    try:
        from neonrp import packs

        pp["triggers"] = dict(packs.load(t.pack_name, world_dir(t)).triggers)
    except Exception:  # noqa: BLE001 — a broken pack is reported elsewhere
        pass
    return pp


def loop_problems(t: Template, plots: list[dict[str, Any]]) -> list[Problem]:
    """§3 game loop: ending mode, reachability, distinct conditions, guidance, reveal."""
    out: list[Problem] = []
    endings: dict[str, dict[str, Any]] = {}
    for plot in plots:
        for eid, spec in (plot.get("endings") or {}).items():
            endings[str(eid)] = {**(spec if isinstance(spec, dict) else {}), "_plot": plot}
    # the pack's own rules can end the game too (狼人杀: 好人胜 / 狼人胜) — a pseudo-plot of its triggers
    pack_plot = _pack_plot(t)
    for eid, srcs in _ending_emitters([pack_plot]).items():
        spec = next((e for tid, _b in srcs for e in (pack_plot["triggers"][tid].get("then") or []) + (pack_plot["triggers"][tid].get("else") or [])
                     if isinstance(e, dict) and e.get("ending") == eid), {})
        endings.setdefault(eid, {"title": spec.get("title"), "kind": "rule", "_plot": pack_plot})
    emit = _ending_emitters([*plots, pack_plot])
    mode = t.ending_mode
    reachable = [e for e in endings if emit.get(e)]
    if mode == "single" and len(reachable) != 1:
        out.append(Problem("block", "loop.single", "mode.ending", f"single needs exactly one reachable ending (has {len(reachable)})"))
    if mode == "multi" and len(reachable) < 2:
        out.append(Problem("block", "loop.multi", "mode.ending", f"multi needs ≥2 reachable endings (has {len(reachable)})"))
    if mode in ("single", "multi"):
        for e in endings:
            if not emit.get(e):
                out.append(Problem("block", "loop.reach", f"endings.{e}", "no trigger emits this ending"))
        # distinct conditions: two endings from the very same trigger branch are one ending under two names
        seen: dict[tuple[str, str], str] = {}
        for e, srcs in emit.items():
            for src in srcs:
                if src in seen and seen[src] != e:
                    out.append(Problem("block", "loop.distinct", f"triggers.{src[0]}.{src[1]}",
                                       f"emits both {seen[src]} and {e} — endings need different conditions"))
                seen.setdefault(src, e)
        # guidance: a plot that ends the game should have stages (a road, not only a finish line)
        for plot in plots:  # (pack rules are the game's own loop; they need no stages)
            if plot.get("endings") and not plot.get("stages"):
                out.append(Problem("warn", "loop.guide", f"{plot.get('id')}.stages", "has endings but no stages to guide toward them"))
            if plot.get("endings") and not plot_prompt(plot):
                out.append(Problem("warn", "loop.guide", f"{plot.get('id')}.prompt",
                                   "no appended prompt — the narrator gets no hint of where the plot is heading"))
        if not any(str(e.get("kind") or "") in ("fail", "fallback", "rule") for e in endings.values()):
            out.append(Problem("warn", "loop.exit", "endings", "no fallback ending (kind: fail/fallback) — death / timeout has no exit"))
    if mode == "open" and endings and not reachable:
        out.append(Problem("warn", "loop.reach", "endings", "endings declared but none reachable"))
    for e, spec in endings.items():
        if not str(spec.get("title") or "").strip():
            out.append(Problem("warn", "loop.epilogue", f"endings.{e}.title", "ending has no title"))
    # reveal (谜底): if the mode asks for one, every ending (or the plot) must carry it
    if t.mode.get("reveal"):
        for plot in plots:
            if not plot.get("reveal"):
                out.append(Problem("block", "loop.reveal", f"{plot.get('id')}.reveal", "mode.reveal is on but the plot has no reveal"))
    return out


# ── discovery / play-side view ───────────────────────────────────────────────

def bindings_of(lib: str) -> list[dict[str, Any]]:
    """Every template that links this library soul (the character page's「在哪些世界里」): {template, title, sid, role}."""
    out: list[dict[str, Any]] = []
    for tid, tdir in sorted(discover().items()):
        try:
            t = load(tdir)
        except Exception:  # noqa: BLE001 — a broken template never hides the others
            continue
        for r in t.souls or []:
            rows = r.get("pool") if isinstance(r, dict) and isinstance(r.get("pool"), list) else [r]
            for x in rows:
                if isinstance(x, dict) and str(x.get("lib") or "") == lib:
                    out.append({"template": tid, "title": str((t.data.get("card") or {}).get("title") or tid),
                                "sid": str(x.get("sid") or lib), "role": str(x.get("role") or r.get("role") or "npc"),
                                "pool": x is not r})
    return out


SHIPPED_FILE = "shipped.json"   # beside the product's templates: {"builtin": [ids…]} — the worlds the local edition ships


def product_dirs() -> list[Path]:
    """The product's own template folders: from source the repo's ``worldlines/templates`` (dev repo, or the public
    repo's sibling), in an installed release the worldlines wheel's ``worldlines_shim/templates`` (10-08)."""
    from neonrp.core.paths import shell_dir

    repo = Path(__file__).resolve().parents[3]
    out = [d for d in (repo / "worldlines" / "templates", repo.parent / "worldlines" / "templates") if d.is_dir()]
    shipped = shell_dir("templates")
    if shipped is not None and shipped not in out:
        out.append(shipped)
    return out


def shipped_ids() -> list[str]:
    """10-17: the local edition ships only 灰橡宅 and 石津镇 (in this order, at the top of every list); the other
    official worlds come down with a Worldlines account (core/template_publish.fetch_official). ``shipped.json``."""
    for d in product_dirs():
        try:
            ids = json.loads((d / SHIPPED_FILE).read_text(encoding="utf-8")).get("builtin")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(ids, list):
            return [str(x) for x in ids]
    return []


def search_dirs() -> list[Path]:
    """Where ``*.template`` folders are looked up: ``NEONRP_TEMPLATE_PATH`` (os.pathsep-separated;
    WorldLines' template store) then the private layer, the product's own folders (``product_dirs``), and last the
    official worlds fetched with an account (``NEONRP_OFFICIAL_DIR``, core/paths.official_dir) — so from source the
    repo's copy of an official world wins over a downloaded one."""
    import os

    out = [Path(x).expanduser() for x in os.environ.get("NEONRP_TEMPLATE_PATH", "").split(os.pathsep) if x.strip()]
    from neonrp.core.paths import official_dir, private_dir

    priv = private_dir("templates")  # 10-08: our templates (with our orchestration) before the public ones
    if priv is not None and priv not in out:
        out.append(priv)
    for d in product_dirs():
        if d not in out:
            out.append(d)
    off = official_dir()
    if off is not None and off not in out:
        out.append(off)
    return out


def discover() -> dict[str, Path]:
    """template id → folder (first hit wins); the shipped worlds first, in ``shipped.json`` order. From source the
    product folder holds every official template (dev fixtures); ``NEONRP_TEMPLATES=shipped`` shows it the way an
    installed release does — only the shipped ones (the rest come from the official cache)."""
    import os

    only_shipped = os.environ.get("NEONRP_TEMPLATES", "").strip().lower() == "shipped"
    prod = set(product_dirs())
    ship = shipped_ids()
    out: dict[str, Path] = {}
    for d in search_dirs():
        if not d.is_dir():
            continue
        for sub in sorted(d.iterdir()):
            if (sub / "template.json").is_file():
                try:
                    tid = load(sub).id
                except TemplateError:
                    continue
                if only_shipped and d in prod and tid not in ship:
                    continue
                out.setdefault(tid, sub)
    first = [i for i in ship if i in out]
    return {**{i: out[i] for i in first}, **{k: v for k, v in out.items() if k not in first}}


def run_view(root: Path) -> dict[str, Any] | None:
    """What a bound run shows about its template: card / mode / plots with stage, the ending once reached,
    and the reveal (谜底) only after the ending — never before."""
    from neonrp.core.paths import get_data_dir_name

    meta = root / get_data_dir_name(root) / "meta"
    rec = _j(meta / "template.json")
    if not isinstance(rec, dict):
        return None
    ending = _j(meta / "ending.json")
    plots_idx = _j(meta / "plots.json", {}) or {}
    sid = run_companion(root)
    stages = _j(meta / "plot_vars.json", {}) or {}
    plots = []
    for pid, info in plots_idx.items():
        pdef = _j(root / str(info.get("dir") or "") / "plot.json", {}) or {}
        sv = info.get("stage_var")
        st = (stages.get(pid) or {}).get("stage") if isinstance(stages.get(pid), dict) else None
        if sv and sv != f"{pid}.stage":  # the plot names another variable as its stage (plot.json stage_var, 10-14)
            try:
                from neonrp.core.registry import load_registry

                v = load_registry(root).variables.get(str(sv))
                st = v.value if v is not None else st
            except Exception:  # noqa: BLE001
                pass
        from neonrp.core import scene_cg as _scg

        rel = ((rec.get("built") or {}).get("plot_dirs") or {}).get(pid)
        prel = rel or f"plots/{pid}"  # an older build without plot_dirs: the usual folder
        # names only (a stage may be {name, goal}; the goals and what is not reached yet: GET …/objective, core/objective)
        plots.append({"id": pid, "title": info.get("title"), "stages": [_stage_name(x) for x in pdef.get("stages") or []], "stage": st, "stage_var": sv,
                      "stage_cg": [{**_scg.for_companion({f: v for f, v in cg.items() if f != "prompt"}, f"stage.cg:{pid}.{n}", sid),
                                    "stage": n}  # this run's companion's picture (10-15)
                                   for n, cg in _scg.stage(pdef)],
                      **({"dir": rel} if rel else {}),
                      "endings": {k: {"title": (v or {}).get("title"), "kind": (v or {}).get("kind"),
                                      "slot": variant_slot(f"plot:{prel}:ending:{k}", (v or {}).get("assets"), sid)}
                                  for k, v in (pdef.get("endings") or {}).items()}})
    from neonrp.core.output_lang import prompt_lang

    opening = rec.get("opening") if isinstance(rec.get("opening"), dict) else None
    if opening is not None and sid:  # an opening CG with a picture for this run's companion (10-15)
        from neonrp.core import scene_cg as _scg_o

        opening = {**opening, "cg": [_scg_o.for_companion(cg, str(cg.get("slot") or ""), sid) if isinstance(cg, dict) else cg
                                     for cg in opening.get("cg") or []]}
    view: dict[str, Any] = {"template": {k: rec.get(k) for k in ("id", "version", "card", "mode", "pack", "souls")},
                            "lang": prompt_lang(root),  # this run's language: the screen speaks it too (10-14)
                            "companion": sid,
                            "plots": plots, "ending": ending if isinstance(ending, dict) else None,
                            **({"opening": opening} if opening is not None else {})}
    if view["ending"]:
        hit = next((p["endings"][str(view["ending"].get("id"))] for p in plots if str(view["ending"].get("id")) in p["endings"]), None)
        if hit:
            view["ending"] = {**view["ending"], "slot": hit["slot"]}
    if view["ending"]:
        reveals = {}
        for p in plots:
            rv = _j(root / get_data_dir_name(root) / "plots" / p["id"] / "reveal.json")
            if rv:
                reveals[p["id"]] = rv
        view["reveal"] = reveals
    return view


# ── runs ─────────────────────────────────────────────────────────────────────

RUN_SLUG_PREFIX = "tpl--"  # POST /session {slug: "tpl--<id>"} starts a fresh run of a template


def new_run(ref: Template | Path | str, *, model_ref: str | None = None, player: dict[str, Any] | None = None,
            lang: str | None = None) -> Path:
    """A fresh playable run of a template in PLAYS_HOME (the launcher's "new game" for templates):
    build + an initialized manifest + the user's default model. ``ref`` = a folder or a template id.
    ``player`` = the character the player made (``template.builder``): checked first (``BuilderError``, nothing built),
    the cast narrowed to the companion picked, then written into the run's player files before the opening.
    ``lang`` = the player's language: the run is built from the template's localization in it (template/i18n.py)."""
    from neonrp.core.manifest import Manifest
    from neonrp.core.paths import get_manifest_path
    from neonrp.core.storage import atomic_write_json, ensure_dirs
    from neonrp.worlds import create_run_dir, seed_run_model

    if isinstance(ref, str) and not Path(ref).exists():
        hit = discover().get(ref)
        if hit is None:
            raise TemplateError(f"no template {ref!r}")
        ref = hit
    t = ref if isinstance(ref, Template) else load(ref)
    from neonrp.template import builder as _builder
    from neonrp.template import i18n as _i18n

    with _i18n.localized(t, lang) as t:  # the builder's fields and the cast are the localized ones too
        norm: dict[str, Any] | None = None
        if player is not None:
            errs, norm = _builder.check(t, player)
            if errs:
                raise _builder.BuilderError(errs)
            t = _builder.select_cast(t, norm)
        run_dir = create_run_dir(f"tpl-{t.id}")
        try:
            build(t, run_dir, lang=lang)
            if norm is None:  # started without the builder: the portrait field's default face (10-15)
                _builder.apply_default(t, run_dir)
            if norm is not None:
                _builder.apply(t, run_dir, norm)
                if _i18n.norm_lang(lang):
                    _i18n.narrow_run(run_dir, _i18n.norm_lang(lang))
            ensure_dirs(run_dir)
            atomic_write_json(get_manifest_path(run_dir), Manifest().model_dump())
            seed_run_model(run_dir, model_ref or (t.models.get("play") if isinstance(t.models.get("play"), str) and "/" in t.models["play"] else None))
        except Exception:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise
    return run_dir


# ── asset slots (Lint UI: fill a slot by upload or generation) ───────────────

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
MAX_UPLOAD = 8 * 1024 * 1024


def asset_slots(t: Template, *, classes: bool = True) -> list[dict[str, Any]]:
    """Every image slot a template can fill (Template v3, Mock 3.0): the card cover and plot ending art (template-level),
    then every class slot instance (``<cls>.<slot>:<inst>`` — level maps, soul portraits / sprites, place scenes,
    item / faction / caravan icons …; see template/v3.py). ``prompt`` is what generation would use."""
    out: list[dict[str, Any]] = []
    cov = str(t.card.get("cover") or "")
    out.append({"slot": "card:cover", "cls": "card", "name": "cover", "label": t.card.get("title") or t.id, "kind": "image",
                "need": "cover" in _asset_rules(t).get("card", []), "path": cov or None, "have": bool(cov and (t.dir / cov).is_file()),
                "stale": False, "prompt": f"{t.card.get('title', '')}, {t.card.get('pitch', '')}, key art, wide establishing shot".strip(", ")})
    for rel in t.plots:
        pj = _j(t.dir / rel / "plot.json", {}) or {}
        pid = str(pj.get("id") or Path(rel).name)
        for en, spec in (pj.get("endings") or {}).items():
            if not isinstance(spec, dict):
                continue
            img = str((spec.get("assets") or {}).get("image") or "")
            base = {"slot": f"plot:{rel}:ending:{en}", "cls": "ending", "name": "art", "label": str(spec.get("title") or en), "kind": "image",
                    "owner": f"{pid}.endings.{en}", "need": False, "path": f"{rel}/{img}" if img else None,
                    "have": bool(img and (t.dir / rel / img).is_file()), "stale": False,
                    "prompt": str(spec.get("image_prompt") or f"{spec.get('title', en)}, ending illustration"),
                    **({"shows": str(spec["image_shows"])} if spec.get("image_shows") else {})}
            out.append(base)
            for sid, vp in _variant_rows(spec.get("assets")):  # the picture per companion (10-15)
                out.append({**base, "slot": f"{base['slot']}@{sid}", "label": f"{base['label']} · {sid}", "variant": sid,
                            "variant_of": base["slot"], "path": f"{rel}/{vp}", "have": (t.dir / rel / vp).is_file(), "shows": sid,
                            "prompt": str(((spec.get("variant_prompts") or {}) if isinstance(spec.get("variant_prompts"), dict) else {}).get(sid)
                                          or base["prompt"])})
    for r in t.data.get("rewards") if isinstance(t.data.get("rewards"), list) else []:  # a reward card's picture (10-18)
        if not isinstance(r, dict) or not r.get("id") or r.get("slot"):  # one that shows another slot's picture has none
            continue
        img, title = str(r.get("image") or ""), r.get("title")
        label = str((title.get(t.card.get("lang") or "zh") or next(iter(title.values()), "")) if isinstance(title, dict) else (title or r["id"]))
        out.append({"slot": f"reward:{r['id']}", "cls": "reward", "name": "card", "label": label, "kind": "image",
                    "owner": f"rewards.{r['id']}", "need": False, "path": img or None, "have": bool(img and (t.dir / img).is_file()),
                    "stale": False, "prompt": str(r.get("image_prompt") or f"{label}, collectible card illustration")})
    from neonrp.core import scene_cg
    from neonrp.template import v3

    for inst, cg in scene_cg.opening(t.data):  # the opening's fixed CG, in play order (10-14)
        out += _cg_rows(t, f"opening.cg:{inst}", "opening", inst, cg, "", label=scene_cg.caption(cg, t.card.get("lang") or "zh") or f"opening {inst}")
    try:
        slotted = {str(s.get("cls")) for s in v3.ui(t).get("slots") or []}
    except Exception:  # noqa: BLE001 — a pack that does not load: every plot entry is listed on its own
        slotted = set()
    for rel in t.plots:
        pj = _j(t.dir / rel / "plot.json", {}) or {}
        pid = str(pj.get("id") or Path(rel).name)
        for n, cg in scene_cg.stage(pj):  # a stage's cut-scene: plays when the plot's stage variable reaches it
            stages = pj.get("stages") if isinstance(pj.get("stages"), list) else []
            out += _cg_rows(t, f"stage.cg:{pid}.{n}", "stage", f"{pid}.{n}", cg, rel,
                            label=scene_cg.caption(cg, t.card.get("lang") or "zh") or (_stage_name(stages[n]) if 0 <= n < len(stages) else f"{pid} stage {n}"),
                            extra={"plot": pid, "stage": n})
        # a plot entry no class slot covers (归乡's illustrations, class `cg`): its own slot, so it can be filled and served
        for eid, es in (pj.get("entries") or {}).items():
            if not isinstance(es, dict) or str(es.get("class") or "") in slotted:
                continue
            img = str((es.get("assets") or {}).get("image") or "")
            props = es.get("props") if isinstance(es.get("props"), dict) else {}
            out.append({"slot": f"plot:{rel}:entry:{eid}", "cls": str(es.get("class") or ""), "name": "image", "inst": eid,
                        "label": str(es.get("name") or props.get("name") or eid), "kind": "image", "owner": f"{pid}.entries.{eid}",
                        "parent": es.get("parent"), "need": False, "path": f"{rel}/{img}" if img else None,
                        "have": bool(img and (t.dir / rel / img).is_file()), "stale": False,
                        "prompt": str(es.get("image_prompt") or props.get("image_prompt") or props.get("summary") or es.get("name") or eid)})

    if not classes:  # the template's own slots only (slot_file): no world build behind them
        return out
    try:
        for r in v3.cached_rows(t):
            if not r.get("empty"):
                out.append(r)
    except Exception:  # noqa: BLE001 — a template that does not build has no class slots (lint says why)
        pass
    return out


TEMPLATE_SLOTS = ("card:", "plot:", "opening.cg:", "stage.cg:", "reward:")  # slots of the template itself (not a class instance)


def _variant_rows(spec: Any) -> list[tuple[str, str]]:
    from neonrp.core import scene_cg

    return sorted(scene_cg.variants(spec).items())


def _cg_rows(t: Template, slot: str, cls: str, inst: str, cg: dict[str, Any], base: str, *, label: str,
             extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """A CG slot row + one row per companion variant (``<slot>@<sid>``, 10-15)."""
    row = _cg_row(t, slot, cls, inst, cg, base, label=label, extra=extra)
    out = [row]
    for sid, vp in _variant_rows(cg):
        p = f"{base}/{vp}" if base else vp
        out.append({**row, "slot": f"{slot}@{sid}", "label": f"{label} · {sid}", "variant": sid, "variant_of": slot,
                    "path": p, "have": (t.dir / p).is_file()})
    return out


def _cg_row(t: Template, slot: str, cls: str, inst: str, cg: dict[str, Any], base: str, *, label: str,
            extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """An opening / stage CG slot row: the picture (and its optional video), caption and camera note for the screen."""
    def rel(p: Any) -> str | None:
        return f"{base}/{p}" if p and base else (str(p) if p else None)

    img, vid = rel(cg.get("image")), rel(cg.get("video"))
    return {"slot": slot, "cls": cls, "name": "cg", "inst": inst, "label": label, "kind": "image", "need": False,
            "path": img, "have": bool(img and (t.dir / img).is_file()), "stale": False,
            "video": vid, "video_have": bool(vid and (t.dir / vid).is_file()),
            "caption": cg.get("caption"), "camera": cg.get("camera"),
            "prompt": str(cg.get("prompt") or scene_caption(cg) or label), **(extra or {})}


def scene_caption(cg: dict[str, Any]) -> str:
    from neonrp.core.scene_cg import caption

    return caption(cg)


def _slot_target(t: Template, slot: str, ext: str) -> tuple[Path, Any]:
    """Where a slot's file goes + a function that records it in the template's JSON."""
    if "@" in slot:  # a companion's picture (10-15): beside the generic one, recorded under variants
        return _variant_target(t, slot, ext)
    if slot.startswith(("opening.cg:", "stage.cg:")):
        return _cg_target(t, slot, ext)
    kind, _, rest = slot.partition(":")
    if kind == "reward":  # a reward card's own picture (core/rewards, 10-18)
        rows = t.data.get("rewards") if isinstance(t.data.get("rewards"), list) else []
        if not any(isinstance(r, dict) and str(r.get("id") or "") == rest for r in rows):
            raise TemplateError(f"unknown slot {slot!r}")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in rest)
        dest = t.dir / "assets" / f"reward-{safe}{ext}"

        def record() -> None:
            d = _j(t.dir / "template.json", {}) or {}
            for r in d.get("rewards") or []:
                if isinstance(r, dict) and str(r.get("id") or "") == rest:
                    r["image"] = f"assets/reward-{safe}{ext}"
            _w(t.dir / "template.json", d)
        return dest, record
    if kind == "card" and rest == "cover":
        dest = t.dir / "assets" / f"cover{ext}"

        def record() -> None:
            d = _j(t.dir / "template.json", {}) or {}
            d.setdefault("card", {})["cover"] = f"assets/cover{ext}"
            _w(t.dir / "template.json", d)
        return dest, record
    if kind == "plot":
        rel, _, tail = rest.partition(":")
        what, _, oid = tail.partition(":")
        if rel not in t.plots or what not in ("entry", "ending") or not oid:
            raise TemplateError(f"unknown slot {slot!r}")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in oid)
        dest = t.dir / rel / "assets" / f"{what}-{safe}{ext}"

        def record() -> None:
            pj = _j(t.dir / rel / "plot.json", {}) or {}
            table = pj.get("entries" if what == "entry" else "endings") or {}
            if oid not in table:
                raise TemplateError(f"{oid!r} not in {rel}")
            table[oid].setdefault("assets", {})["image"] = f"assets/{what}-{safe}{ext}"
            table[oid].pop("image_shows", None)  # a new generic picture: no longer one companion's (10-15)
            _w(t.dir / rel / "plot.json", pj)
        return dest, record
    if kind == "soul":
        path, _, part = rest.rpartition(":")
        if part != "portrait" or not any(r.get("path") == path for s in t.souls
                                         for r in ([{"sid": x} if isinstance(x, str) else x for x in s["pool"]] if isinstance(s.get("pool"), list) else [s])):
            raise TemplateError(f"unknown slot {slot!r}")
        return t.dir / path / "assets" / f"portrait{ext}", (lambda: None)
    raise TemplateError(f"unknown slot {slot!r}")


def _variant_target(t: Template, slot: str, ext: str) -> tuple[Path, Any]:
    """``<slot>@<sid>`` → the generic slot's file name + ``-<sid>``; recorded in that declaration's ``variants``."""
    base, _, sid = slot.rpartition("@")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)
    if not safe or base.startswith("card:"):
        raise TemplateError(f"unknown slot {slot!r}")
    dest0, _rec = _slot_target(t, base, ext)
    dest = dest0.with_name(f"{dest0.stem}-{safe}{ext}")
    kind, _, rest = base.partition(":")

    def put(d: dict[str, Any], rel_to: Path) -> None:
        d.setdefault("variants", {})[sid] = dest.relative_to(rel_to).as_posix()

    def record() -> None:
        from neonrp.core import scene_cg

        if kind == "plot":
            rel, _, tail = rest.partition(":")
            pj = _j(t.dir / rel / "plot.json", {}) or {}
            put(pj["endings"][tail.partition(":")[2]].setdefault("assets", {}), t.dir / rel)
            _w(t.dir / rel / "plot.json", pj)
        elif kind == "opening.cg":
            d = _j(t.dir / "template.json", {}) or {}
            idx = next(i for i, (k, _cg) in enumerate(scene_cg.opening(t.data)) if k == rest)
            items = d["opening"]["cg"]
            if isinstance(items[idx], str):
                items[idx] = {"image": items[idx]}
            put(items[idx], t.dir)
            _w(t.dir / "template.json", d)
        else:  # stage.cg:<pid>.<n>
            pid, _, n = rest.rpartition(".")
            for rel in t.plots:
                pj = _j(t.dir / rel / "plot.json", {}) or {}
                if str(pj.get("id") or Path(rel).name) != pid:
                    continue
                key = next(k for k in (pj.get("stage_cg") or {}) if scene_cg.stage_index(pj, k) == int(n))
                if isinstance(pj["stage_cg"][key], str):
                    pj["stage_cg"][key] = {"image": pj["stage_cg"][key]}
                put(pj["stage_cg"][key], t.dir / rel)
                _w(t.dir / rel / "plot.json", pj)
                break
    if kind == "plot" and rest.partition(":")[2].partition(":")[0] != "ending":
        raise TemplateError(f"unknown slot {slot!r}")  # entries have no companion variants
    return dest, record


def _cg_target(t: Template, slot: str, ext: str) -> tuple[Path, Any]:
    """opening.cg:<n> → assets/opening/cg-<n>.<ext> (template.json); stage.cg:<pid>.<n> → plots/<rel>/assets/stage-<n>.<ext>."""
    from neonrp.core import scene_cg

    kind, _, inst = slot.partition(":")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in inst)
    if kind == "opening.cg":
        idx = next((i for i, (k, _cg) in enumerate(scene_cg.opening(t.data)) if k == inst), None)
        if idx is None:
            raise TemplateError(f"unknown slot {slot!r}")

        def record() -> None:
            d = _j(t.dir / "template.json", {}) or {}
            items = d["opening"]["cg"]
            items[idx] = {**(items[idx] if isinstance(items[idx], dict) else {}), "image": f"assets/opening/cg-{safe}{ext}"}
            _w(t.dir / "template.json", d)
        return t.dir / "assets" / "opening" / f"cg-{safe}{ext}", record
    pid, _, n = inst.rpartition(".")
    for rel in t.plots:
        pj = _j(t.dir / rel / "plot.json", {}) or {}
        if str(pj.get("id") or Path(rel).name) != pid or not n.isdigit():
            continue
        key = next((k for k in (pj.get("stage_cg") or {}) if scene_cg.stage_index(pj, k) == int(n)), None)
        if key is None:
            break

        def record(rel: str = rel, key: str = key) -> None:
            p = _j(t.dir / rel / "plot.json", {}) or {}
            cur = p["stage_cg"][key]
            p["stage_cg"][key] = {**(cur if isinstance(cur, dict) else {}), "image": f"assets/stage-{n}{ext}"}
            _w(t.dir / rel / "plot.json", p)
        return t.dir / rel / "assets" / f"stage-{n}{ext}", record
    raise TemplateError(f"unknown slot {slot!r}")


def put_asset(t: Template | Path | str, slot: str, data: bytes, *, ext: str = ".png") -> dict[str, Any]:
    """Write an image into a slot (upload or generation) and record it. Only inside the template folder."""
    if not isinstance(t, Template):
        t = load(t)
    if not slot.startswith(TEMPLATE_SLOTS):  # a class slot instance (Template v3)
        from neonrp.template import v3

        return v3.fill_slot(t, slot, data, ext=ext)
    ext = ext.lower() if ext.lower() in IMAGE_EXTS else ".png"
    if not data or len(data) > MAX_UPLOAD:
        raise TemplateError("image is empty or larger than 8 MB")
    if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        raise TemplateError("not a PNG / JPEG / WebP image")
    dest, record = _slot_target(t, slot, ext)
    if not dest.resolve().is_relative_to(t.dir.resolve()):
        raise TemplateError("slot escapes the template")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    record()
    from neonrp.template import v3 as _v3

    _v3.forget(t)   # a plot entry's picture is also a class slot (item.icon:<entry>): slot_file must see it now
    # the template's own slots only: listing the class slots too builds the whole world (seconds, a minute in the browser engine)
    return next((s for s in asset_slots(load(t.dir), classes=False) if s["slot"] == slot), {"slot": slot, "have": True})


def generate_asset(t: Template | Path | str, slot: str, *, prompt: str | None = None) -> dict[str, Any]:
    """Fill a slot with the configured image backend (settings → image generation)."""
    if not isinstance(t, Template):
        t = load(t)
    if not slot.startswith(TEMPLATE_SLOTS):
        from neonrp.template import v3

        return v3.generate_slot(t, slot, prompt=prompt)
    s = next((x for x in asset_slots(t) if x["slot"] == slot), None)
    if s is None:
        raise TemplateError(f"unknown slot {slot!r}")
    from neonrp.core.imagegen import generate_image

    wide = slot == "card:cover" or ":ending:" in slot or slot.startswith(("opening.cg:", "stage.cg:"))
    with tempfile.TemporaryDirectory() as tmp:
        png = generate_image(prompt or s["prompt"], Path(tmp), width=1344 if wide else 1024, height=768 if wide else 1024)
        return put_asset(t, slot, png.read_bytes(), ext=png.suffix or ".png")


def slot_file(t: Template, slot: str, *, part: str = "image", variant: str | None = None) -> Path | None:
    """The file behind a filled slot, wherever it lives: the template (cover, plot dirs, opening / stage CG, brought-in
    souls, world-overlay) or the bound world (builtin world assets). ``part="video"`` = a CG slot's video.
    ``variant`` = the run's companion: an ending / CG slot with a filled picture for them gives that one (10-15)."""
    if slot.startswith(TEMPLATE_SLOTS):
        rows = asset_slots(t, classes=False)
        if "@" in slot:  # asked for a companion's picture directly
            slot, _, variant = slot.rpartition("@")
        if variant and part != "video":
            v = next((x for x in rows if x["slot"] == f"{slot}@{variant}" and x.get("have")), None)
            if v is not None:  # not filled yet → the generic picture
                slot = v["slot"]
        s = next((x for x in rows if x["slot"] == slot), None)
        key = "video" if part == "video" else "path"
        if not s or not s.get(key):
            return None
        p = (t.dir / s[key]).resolve()
        return p if p.is_file() and p.is_relative_to(t.dir.resolve()) else None
    from neonrp.template import v3

    cls, _, rest = slot.partition(".")
    name, _, inst = rest.partition(":")
    if cls == "soul" and name and inst and part != "video":  # a portrait / sprite: straight from the soul folders (10-15)
        p = v3.soul_file_fast(t, name, inst)
        if p is not None:
            return p
    return v3.source_file(t, slot)
