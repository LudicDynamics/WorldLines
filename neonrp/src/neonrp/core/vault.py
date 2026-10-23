"""Obsidian vault projection — the world as something you can *watch* (M31).

We are file-first, but our files are engine records: 82 JSON to 28 markdown
in a starter world. Obsidian renders JSON as dead text — no title, no links,
no graph. So "the run folder is a vault" is false, and the missing piece is
a **projection**: engine state → a folder of linked notes.

The good news is that the data is already link-shaped. A location record
carries `id` / `kind` / `name` / `tags` / `summary` / `connections`, which is
exactly a note's frontmatter, title, body and outgoing links. The graph has
been sitting in the JSON all along.

**Deterministic on purpose.** This runs after every landed turn, so it has to
be reproducible and free. Handing the job to an LLM would make the vault a
second, drifting narrative instead of a view of the truth — the precise
failure file-first exists to avoid. Every word in a generated note comes from
a source file.

**Audience: the observer**. Not the player inside the
fiction — someone watching the world evolve from above: who is where, what
changed, how it moved. So the vault does not hide unrevealed secrets, and it
updates as turns land rather than only on request.

**Ownership.** `vault/` is generated and disposable: regenerated from source,
never hand-edited. `vault/我的笔记/` is yours and is never touched — link
into the generated notes from there and Obsidian's backlinks panel shows your
thinking on the world's pages, without the projector and you ever fighting
over a file.

**Zero plugins.** Frontmatter, wikilinks, tags, folders, graph, backlinks and
canvas are all core Obsidian. A generated vault that needs Dataview to be
readable is a broken vault.

**Pictures and hierarchy**. Portraits and the cover are
copied into `素材/` and embedded in their notes; `世界.canvas` draws the
world as nested groups — world ⊃ place ⊃ people — because the graph view
flattens everything onto one plane and a world is not flat. See
`vault_canvas.py`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from neonrp.core.vault_canvas import CANVAS_FILENAME, PlaceBox, SoulCard, build_canvas

logger = logging.getLogger(__name__)

VAULT_DIRNAME = "vault"
# The user's half. The projector reads it never and writes it once (a README).
USER_NOTES_DIRNAME = "我的笔记"
ASSETS_DIRNAME = "素材"
_INDEX_FILENAME = ".projection.json"
_GENERATED_DIRS = ("角色", "地点", "世界设定", ASSETS_DIRNAME)
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

# Filenames come from world data, which is author-written and may contain
# anything. Keep them openable on every OS Obsidian runs on.
_UNSAFE = set('\\/:*?"<>|#^[]')


def _safe_name(text: str, fallback: str) -> str:
    cleaned = "".join(ch for ch in (text or "") if ch not in _UNSAFE).strip()
    cleaned = cleaned.replace("\n", " ").strip(". ")
    return cleaned[:80] or fallback


def _link(name: str) -> str:
    return f"[[{name}]]"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(v) for v in value)
            lines.append(f"{key}: [{rendered}]")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


CONFIG_RELPATH = ".neonrp/vault.json"

# What every note gets when the world says nothing. Deliberately thin: these
# are the keys the projector itself relies on (identity + link resolution),
# not an opinion about what a world is made of.
_DEFAULT_FRONTMATTER: dict[str, Any] = {
    "soul": {"所在": "@location", "心情": "@mood", "记忆": "status.memory"},
    "location": {"tags": "tags"},
    "entity": {"tags": "tags"},
    "world": {"世界": "@world", "时刻": "@clock", "回合": "@turn"},
}


def _load_vault_config(root: Path) -> dict[str, Any]:
    """Per-world frontmatter rules, or the defaults.

    Frontmatter is the only part of a note Obsidian can query, sort and
    filter on, so *which* fields surface there is a property of the world's
    ontology — a BRP world wants 理智值 where a heist wants 警戒度. The
    engine ships defaults and gets out of the way.

    Read fresh every projection: editing the rules should show up on the next
    turn, not the next process.
    """
    data = _read_json(root / CONFIG_RELPATH)
    rules = data.get("frontmatter")
    if not isinstance(rules, dict):
        return dict(_DEFAULT_FRONTMATTER)
    merged = dict(_DEFAULT_FRONTMATTER)
    for kind, spec in rules.items():
        if kind.startswith("_"):
            continue
        merged[kind] = spec
    return merged


def _dig(source: Any, path: str) -> Any:
    """Follow a dotted path (`status.mood`) into a record, or None."""
    cursor = source
    for part in path.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def _resolve_field(spec: Any, record: dict[str, Any], computed: dict[str, Any]) -> Any:
    """One frontmatter value.

    `@name` reads something the projector worked out (a resolved place label,
    the world clock); anything else is a dotted path into the source record.
    A missing field yields None and the key is simply left out — a world that
    names a property it does not have should get a thinner note, not a broken
    one.
    """
    if not isinstance(spec, str) or not spec:
        return spec
    if spec.startswith("@"):
        return computed.get(spec[1:])
    return _dig(record, spec)


def _build_frontmatter(
    kind: str,
    base: dict[str, Any],
    record: dict[str, Any],
    computed: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Engine-owned identity keys, then whatever the world asked for."""
    fields = dict(base)
    spec = config.get(kind)
    if isinstance(spec, dict):
        pairs = spec.items()
    elif isinstance(spec, list):
        # Bare list form: lift these source keys under their own names.
        pairs = [(str(item).split(".")[-1], item) for item in spec]
    else:
        return fields
    for key, source in pairs:
        if str(key).startswith("_"):
            continue
        value = _resolve_field(source, record, computed)
        if value not in (None, "", [], {}):
            fields[str(key)] = value
    return fields


_CONFIG_TEMPLATE: dict[str, Any] = {
    "_comment": (
        "这个世界投影成 Obsidian vault 时,每种页的 frontmatter 写什么。"
        "frontmatter 是 Obsidian 唯一能查询/排序/过滤的部分,所以按你这个"
        "世界的本体论来定。删掉本文件即回到引擎默认。"
    ),
    "frontmatter": {
        "_comment": (
            "键=frontmatter 里的字段名;值=取哪儿的数据。"
            "'status.mood' 这样的点路径从源记录里取;'@开头' 取引擎算出来的值。"
            "soul 可用 @location @mood @sid @name;location 可用 @present;"
            "world 可用 @world @clock @turn。取不到就整条省略,不会写坏。"
        ),
        "soul": {"所在": "@location", "心情": "@mood", "记忆": "status.memory"},
        "location": {"tags": "tags"},
        "entity": {"tags": "tags"},
        "world": {"世界": "@world", "时刻": "@clock", "回合": "@turn"},
    },
}


def write_config_template(root: Path) -> Path:
    """Drop a starter rules file next to the world. Never clobbers."""
    path = Path(root) / CONFIG_RELPATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_CONFIG_TEMPLATE, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return path


def _demote_headings(text: str) -> str:
    """Push embedded prose one level down.

    Soul charters and background files are authored as standalone documents
    and start at `#`. Dropped verbatim into a note that already has a title,
    they produce two H1s and a broken outline — so every heading shifts one
    level, and the page keeps a single title.
    """
    out = []
    fenced = False
    for line in (text or "").splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("#"):
            line = "#" + line
        out.append(line)
    return "\n".join(out)


def _generated_footer(source: str) -> str:
    return (
        "\n---\n"
        f"*由引擎投影自 `{source}`。这一页会被重新生成——"
        f"要改内容请改源文件,要写自己的想法请写进 `{USER_NOTES_DIRNAME}/`"
        "(在那里 `[[链接]]` 到本页,反向链接会把你的笔记显示在下面)。*\n"
    )


@dataclass
class VaultReport:
    """What one projection did."""

    written: list[str] = field(default_factory=list)
    unchanged: int = 0
    removed: list[str] = field(default_factory=list)
    vault_dir: Path | None = None

    @property
    def changed(self) -> bool:
        return bool(self.written or self.removed)

    def headline(self) -> str:
        bits = []
        if self.written:
            bits.append(f"{len(self.written)} 更新")
        if self.removed:
            bits.append(f"{len(self.removed)} 移除")
        if not bits:
            bits.append("无变化")
        return " · ".join(bits)


# ---------------------------------------------------------------------------
# Source readers — everything the observer wants to know


def _world_name(root: Path) -> str:
    world_map = _read_json(root / "game" / "world" / "world_map.json")
    return str(world_map.get("name") or root.name)


def _world_clock(run_state: dict[str, Any]) -> str:
    time = run_state.get("time") or {}
    day, clock = time.get("day"), time.get("clock")
    if day and clock:
        return f"第 {day} 天 {clock}"
    return str(clock or "")


def _world_place(run_state: dict[str, Any]) -> str:
    loc = run_state.get("location")
    if isinstance(loc, dict):
        return str(loc.get("display") or loc.get("node") or "")
    return str(loc or "")


def _soul_dirs(root: Path) -> list[Path]:
    souls = root / "souls"
    if not souls.is_dir():
        return []
    return sorted(d for d in souls.iterdir() if d.is_dir() and not d.name.startswith("."))


def _soul_view(soul_dir: Path) -> dict[str, Any]:
    """Everything a soul note needs, pulled from its own folder."""
    identity = _read_json(soul_dir / "soul.json")
    run_state = _read_json(soul_dir / "run_state.json")
    profile = _read_json(soul_dir / "character" / "profile.json")
    status = _read_json(soul_dir / "character" / "status.json") or run_state.get("status") or {}
    sid = str(identity.get("sid") or run_state.get("sid") or soul_dir.name.split("-")[0])
    name = str(
        identity.get("name_local")
        or identity.get("name")
        or profile.get("name")
        or sid
    )
    return {
        "sid": sid,
        "name": name,
        "dir": soul_dir,
        "identity": identity,
        "run_state": run_state,
        "profile": profile,
        "status": status if isinstance(status, dict) else {},
        "location": str(run_state.get("location") or ""),
        "charter": _read_text(soul_dir / "soul.md"),
        "origin": _read_text(soul_dir / "background" / "origin.md"),
        "history": _read_text(soul_dir / "background" / "history.md"),
        "secrets": _read_text(soul_dir / "background" / "secrets.md"),
        "events": _read_text(soul_dir / "long-term-memo" / "important_events.md"),
        "traits": _read_json(soul_dir / "persona" / "core_traits.json"),
        "motivations": _read_json(soul_dir / "persona" / "motivations.json"),
        "relationships": _read_json(soul_dir / "persona" / "relationships.json"),
    }


def _find_image(folder: Path, stem: str) -> Path | None:
    """`<folder>/<stem>.<any image suffix>`, or None."""
    for suffix in _IMAGE_SUFFIXES:
        candidate = folder / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _soul_portrait(soul_dir: Path) -> Path | None:
    return _find_image(soul_dir / "assets", "portrait")


def _world_cover(root: Path) -> Path | None:
    return _find_image(root / "assets", "cover")


def _place_index(root: Path) -> dict[str, str]:
    """Canonical node id → friendly place name.

    A soul's `run_state.location` is a *navigation* node (`gate_north`,
    `T004`), not a location-entity id (`north-gate`) — different id spaces
    for the same place. Without collapsing them, every "who is where" link
    in the vault points at a note that does not exist. `canonical_node`
    is what makes `gate_north` and `north-gate` the same key.

    Mirrors the resolution the web runtime does for its map labels; that one
    lives in the shell, so the engine builds its own rather than importing
    upward.
    """
    from neonrp.core.place_nav import canonical_node

    index: dict[str, str] = {}
    game = root / "game"

    def _add(node_id: Any, name: Any) -> None:
        if node_id and name:
            key = canonical_node(str(node_id)) or str(node_id)
            index.setdefault(key, str(name))

    def _name_of(data: dict[str, Any]) -> Any:
        return data.get("name_local") or data.get("name") or data.get("display_name")

    # The authoritative town/region table.
    from neonrp.core.place_tree import WORLD, level_doc, town_docs

    for node in ((level_doc(root, WORLD) or {}).get("nodes") or []):
        if isinstance(node, dict):
            _add(node.get("id"), _name_of(node))

    for sub, nested in (("locations", False), ("towns", True)):
        droot = game / sub
        if not droot.is_dir():
            continue
        for child in sorted(droot.iterdir()):
            if nested:
                f = child / "town.json"
            elif child.is_dir():
                f = child / "location.json"  # 任务 B2 folder form
            else:
                f = child
            if f.suffix != ".json" or not f.is_file():
                continue
            data = _read_json(f)
            if data:
                _add(data.get("id") or child.stem, _name_of(data))

    # Precise spot names (公会大厅, 北门…) live only in each town's map.
    # (old town_map.json files and folder trees alike — place_tree)
    for tid, tm in town_docs(root).items():
        town_name = index.get(canonical_node(tid) or tid, tid)
        for spot in (tm.get("nodes") or []):
            if not isinstance(spot, dict):
                continue
            sid = canonical_node(str(spot.get("id") or "")) or ""
            if sid:
                for key in (sid, *(str(a) for a in spot.get("aliases") or [])):
                    index.setdefault(key, str(spot.get("name") or sid))
                index.setdefault(f"{tid}/{sid}", f"{town_name}·{spot.get('name') or sid}")
    return index


def _place_label(index: dict[str, str], node: str) -> str:
    """Friendly name for a node id, or the raw id when nothing names it."""
    from neonrp.core.place_nav import canonical_node, split_location

    node = (node or "").strip()
    if not node:
        return ""
    if node in index:
        return index[node]
    town, sub = split_location(node)
    if town and sub:
        scoped = index.get(f"{town}/{sub}")
        if scoped:
            return scoped
        return f"{index.get(town, town)}·{index.get(sub, sub)}"
    key = canonical_node(node) or node
    return index.get(key, node)


def _location_records(root: Path) -> list[dict[str, Any]]:
    """Location entities, read straight from game/ rather than the index so a
    world that was never indexed still projects."""
    out: list[dict[str, Any]] = []
    loc_dir = root / "game" / "locations"
    if loc_dir.is_dir():
        for path in sorted(loc_dir.rglob("*.json")):
            # Folder-form places keep scene_state.json / map.json next to the
            # record; only the record is a location.
            if path.parent != loc_dir and path.name != "location.json":
                continue
            data = _read_json(path)
            if data.get("id"):
                data["_path"] = path.relative_to(root).as_posix()
                # Folder-form ids are local to their town (T001/shop_general and T004/shop_general are two places):
                # the folder path is the address; a flat record keeps its own id.
                data["_addr"] = (path.parent.relative_to(loc_dir).as_posix() if path.name == "location.json"
                                 else str(data.get("id")))
                out.append(data)
    return out


def _scoped(place_names: dict[str, str], addr: str, other: str) -> str:
    """The address a connection points at: a sibling in the same folder first, then a top-level id."""
    parent = addr.rsplit("/", 1)[0] if "/" in addr else ""
    if parent and f"{parent}/{other}" in place_names:
        return f"{parent}/{other}"
    return other


def _other_entities(root: Path, skip_kinds: set[str]) -> list[dict[str, Any]]:
    """Named game entities that are not locations and not machine plumbing."""
    out: list[dict[str, Any]] = []
    game = root / "game"
    if not game.is_dir():
        return out
    # meta/, agents/ and player/ are runtime plumbing — no reader value, and
    # they would only clutter the graph.
    skip_dirs = {"meta", "agents", "player", "locations", "secrets"}
    for path in sorted(game.rglob("*.json")):
        rel = path.relative_to(game)
        if rel.parts and rel.parts[0] in skip_dirs:
            continue
        data = _read_json(path)
        kind = str(data.get("kind") or "")
        if not data.get("id") or not data.get("name") or kind in skip_kinds:
            continue
        data["_path"] = path.relative_to(root).as_posix()
        out.append(data)
    return out


# ---------------------------------------------------------------------------
# Note builders


def _soul_note(view: dict[str, Any], config: dict[str, Any]) -> str:
    status = view["status"]
    where = view.get("where_label") or ""
    where_link = view.get("where_link") or ""
    record = {k: v for k, v in view.items() if k != "dir"}
    computed = {
        "location": where,
        "mood": status.get("mood", ""),
        "sid": view["sid"],
        "name": view["name"],
    }
    body = [
        _frontmatter(
            _build_frontmatter(
                "soul",
                {"id": view["sid"], "kind": "soul", "aliases": [view["sid"]]},
                record,
                computed,
                config,
            )
        ),
        "",
        f"# {view['name']}",
        "",
    ]
    if view.get("portrait"):
        body += [f"![[{view['portrait']}|240]]", ""]
    facts = []
    if where:
        facts.append(
            f"**此刻在** {_link(where_link)}" if where_link else f"**此刻在** {where}"
        )
    if status.get("mood"):
        facts.append(f"**心情** {status['mood']}")
    hp, max_hp = status.get("hp"), status.get("max_hp")
    if hp is not None:
        facts.append(f"**状态** {hp}/{max_hp}" if max_hp else f"**状态** {hp}")
    if facts:
        body += [" · ".join(facts), ""]

    if view["charter"]:
        body += [_demote_headings(view["charter"]), ""]

    traits = (view["traits"] or {}).get("traits")
    if isinstance(traits, dict) and traits:
        salient = sorted(traits.items(), key=lambda kv: -float(kv[1] or 0))[:6]
        body += ["## 性格", "", " · ".join(f"{k} ({v})" for k, v in salient), ""]

    rel = (view["relationships"] or {}).get("relationships")
    if isinstance(rel, dict) and rel:
        body += ["## 关系", ""]
        for other, info in rel.items():
            if not isinstance(info, dict):
                continue
            disposition = str(info.get("disposition", "") or "")
            truth = str(info.get("truth", "") or "")
            line = f"- {_link(other)}"
            if disposition:
                line += f" — {disposition}"
            if truth:
                line += f"\n  > {truth}"
            body.append(line)
        body.append("")

    for heading, text in (
        ("出身", view["origin"]),
        ("经历", view["history"]),
        ("秘密", view["secrets"]),
        ("重要事件", view["events"]),
    ):
        if text:
            body += [f"## {heading}", "", _demote_headings(_demote_headings(text)), ""]

    body.append(_generated_footer(f"souls/{view['dir'].name}/"))
    return "\n".join(body)


def _location_note(
    data: dict[str, Any],
    place_names: dict[str, str],
    present: list[str],
    config: dict[str, Any],
) -> str:
    name = str(data.get("name") or data.get("id"))
    body = [
        _frontmatter(
            _build_frontmatter(
                "location",
                {"id": data.get("id"), "kind": "location", "aliases": [data.get("id")]},
                data,
                {"present": present},
                config,
            )
        ),
        "",
        f"# {name}",
        "",
    ]
    if data.get("summary"):
        body += [str(data["summary"]), ""]
    if present:
        body += ["## 此刻在这里", "", " · ".join(_link(p) for p in present), ""]
    connections = data.get("connections")
    if isinstance(connections, list) and connections:
        addr = str(data.get("_addr") or data.get("id") or "")
        linked = [_link(place_names.get(_scoped(place_names, addr, str(c)), str(c))) for c in connections]
        body += ["## 通向", "", " · ".join(linked), ""]
    if data.get("notes"):
        body += ["## 备注", "", str(data["notes"]), ""]
    body.append(_generated_footer(str(data.get("_path", "game/locations/"))))
    return "\n".join(body)


def _entity_note(data: dict[str, Any], config: dict[str, Any]) -> str:
    name = str(data.get("name") or data.get("id"))
    kind = str(data.get("kind") or "entity")
    # A world may govern a specific kind (`npc`, `item`) or fall back to the
    # generic `entity` rules.
    spec_kind = kind if kind in config else "entity"
    body = [
        _frontmatter(
            _build_frontmatter(
                spec_kind,
                {"id": data.get("id"), "kind": kind, "aliases": [data.get("id")]},
                data,
                {},
                config,
            )
        ),
        "",
        f"# {name}",
        "",
    ]
    if data.get("summary"):
        body += [str(data["summary"]), ""]
    if data.get("description"):
        body += [str(data["description"]), ""]
    # Anything else the author wrote, rendered as plain facts rather than
    # dropped — this is an observation surface, not a curated wiki.
    skip = {"id", "kind", "name", "tags", "summary", "description", "_path", "schema_version"}
    extras = [
        (k, v) for k, v in data.items()
        if k not in skip and isinstance(v, (str, int, float, bool)) and str(v).strip()
    ]
    if extras:
        body += ["## 属性", ""]
        body += [f"- **{k}** {v}" for k, v in extras]
        body.append("")
    body.append(_generated_footer(str(data.get("_path", "game/"))))
    return "\n".join(body)


def _world_note(
    root: Path,
    run_state: dict[str, Any],
    soul_views: list[dict[str, Any]],
    place_names: dict[str, str],
    location_names: list[str],
    config: dict[str, Any],
    cover: str | None = None,
) -> str:
    world_name = _world_name(root)
    clock = _world_clock(run_state)
    place = _world_place(run_state)

    body = [
        _frontmatter(
            _build_frontmatter(
                "world",
                {"kind": "world"},
                run_state,
                {
                    "world": world_name,
                    "clock": clock,
                    "turn": run_state.get("turn_count"),
                    "place": place,
                },
                config,
            )
        ),
        "",
        f"# {world_name}",
        "",
        "> 这是从上方看这个世界的入口。每落一个回合,引擎重新投影一次。",
        f"> 俯瞰全貌(谁在哪个地方、地方之间怎么通)看 {_link(CANVAS_FILENAME)}。",
        "",
    ]
    if cover:
        body += [f"![[{cover}|480]]", ""]
    facts = []
    if clock:
        facts.append(f"**{clock}**")
    if place:
        facts.append(f"视点在 {_link(place)}")
    if facts:
        body += [" · ".join(facts), ""]

    if soul_views:
        body += ["## 此刻的人", "", "| 谁 | 在哪 | 心情 |", "| --- | --- | --- |"]
        for view in soul_views:
            label = view.get("where_label") or "—"
            link = view.get("where_link") or ""
            mood = view["status"].get("mood") or "—"
            where_cell = _link(link) if link else label
            body.append(f"| {_link(view['name'])} | {where_cell} | {mood} |")
        body.append("")

    if location_names:
        body += ["## 地方", "", " · ".join(_link(n) for n in sorted(location_names)), ""]

    story = _read_text(root / "story.md")
    if story:
        tail = story.splitlines()[-24:]
        body += ["## 最近发生", "", "\n".join(tail), ""]

    body += [
        "## 你的笔记",
        "",
        f"写在 `{USER_NOTES_DIRNAME}/` 里。那里的东西投影器永远不碰——"
        f"在笔记里 `[[链接]]` 到任何一页,反向链接会把你的想法带到那一页下面。",
        "",
    ]
    body.append(_generated_footer("game/meta/run_state.json · souls/*/run_state.json"))
    return "\n".join(body)


_README = f"""# 这是一个被投影出来的世界

左边每一页都由引擎从世界的源文件生成,**每落一个回合重新投影一次**。
你可以把它当成从上方观察这个世界:谁在哪、心情如何、彼此什么关系、
最近发生了什么。

**先打开 `{CANVAS_FILENAME}`。** 它把世界画成层级:世界 ⊃ 地点 ⊃ 人,
立绘就在卡片上;地点之间的路、人与人的关系都是连线。图谱视图是平的,
画布不是。

## 两条规矩

**生成区不要手改。** `角色/` `地点/` `世界设定/` `{ASSETS_DIRNAME}/`、
`世界.md` 和 `{CANVAS_FILENAME}` 会被重写,改了会丢(在画布上挪卡片也会
被摆回去)。要改内容,改世界的源文件(每页底部写了它来自哪里)。

**`{USER_NOTES_DIRNAME}/` 是你的。** 投影器永远不碰它。在笔记里
`[[链接]]` 到任何一页,Obsidian 的反向链接会把你的想法显示在那一页下面
——这样你的思考和世界的真相能共存,谁也不覆盖谁。

## 想干预世界?

写进 run 目录的 `inbox/pending/`(不在本 vault 内),引擎会在下一回合读它。
"""


# ---------------------------------------------------------------------------
# Projection


def _write_if_changed(path: Path, content: str, report: VaultReport, rel: str) -> None:
    """Only touch a file whose bytes actually differ.

    Obsidian watches the folder: rewriting an unchanged note makes it reload
    and flicker for no reason, and makes the report lie about what moved.
    """
    try:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            report.unchanged += 1
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        report.written.append(rel)
    except OSError:
        logger.debug("vault write skipped: %s", rel, exc_info=True)


def _copy_if_changed(src: Path, dst: Path, report: VaultReport, rel: str) -> None:
    """Same contract as `_write_if_changed`, for binary assets."""
    try:
        data = src.read_bytes()
        if dst.exists() and dst.read_bytes() == data:
            report.unchanged += 1
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        report.written.append(rel)
    except OSError:
        logger.debug("vault asset copy skipped: %s", rel, exc_info=True)


def project_vault(root: Path) -> VaultReport:
    """Rebuild the Obsidian face of this world. Never raises into a turn.

    Full projection every time, but only files whose content actually changed
    are written — simpler than tracking deltas and idempotent by construction.
    A starter world is ~100 small notes, so the whole pass is milliseconds.
    """
    report = VaultReport()
    try:
        root = Path(root)
        vault = root / VAULT_DIRNAME
        report.vault_dir = vault

        config = _load_vault_config(root)
        run_state = _read_json(root / "game" / "meta" / "run_state.json")
        soul_views = [_soul_view(d) for d in _soul_dirs(root)]
        locations = _location_records(root)

        # id → display name, so every link reads like a place and not a slug.
        place_names: dict[str, str] = {}
        for loc in locations:
            addr, lid = str(loc.get("_addr") or loc.get("id")), str(loc.get("id"))
            label = _safe_name(str(loc.get("name") or lid), lid)
            if label in place_names.values():  # two places, one name → say which town
                parent = addr.rsplit("/", 1)[0] if "/" in addr else ""
                label = _safe_name(f"{label}·{place_names.get(parent, parent)}", addr.replace("/", "-")) if parent else label
            place_names[addr] = label
        # Souls stand on navigation nodes, which are a different id space from
        # location entities — resolve through the shared place index so a soul
        # in `gate_north` lands on the 石津镇·北门 page rather than a dead link.
        nav_index = _place_index(root)
        entities = _other_entities(root, skip_kinds={"location", "meta"})
        # Any generated page can be a link target — a soul standing in 碧石镇
        # should reach its note whether that note came from a location record
        # or from the world's own entity set.
        note_by_label = {label: label for label in place_names.values()}
        for data in entities:
            eid = str(data.get("id"))
            note_by_label.setdefault(
                _safe_name(str(data.get("name") or eid), eid), eid
            )

        def _where(node: str) -> str:
            label = _place_label(nav_index, node)
            safe = _safe_name(label, node)
            # Only link when a location page actually exists for it.
            return safe if safe in note_by_label else ""

        for view in soul_views:
            view["where_label"] = _place_label(nav_index, view["location"])
            view["where_link"] = _where(view["location"])

        # Who is standing where, keyed by the location note that will show it.
        present: dict[str, list[str]] = {}
        for view in soul_views:
            if view["where_link"]:
                present.setdefault(view["where_link"], []).append(
                    _safe_name(view["name"], view["sid"])
                )

        expected: dict[str, str] = {}

        # Pictures first: notes embed them by vault-relative path, so the
        # path has to be decided before the note is rendered.
        cover_rel: str | None = None
        cover_src = _world_cover(root)
        if cover_src is not None:
            cover_rel = f"{ASSETS_DIRNAME}/世界{cover_src.suffix.lower()}"
            _copy_if_changed(cover_src, vault / cover_rel, report, cover_rel)
            expected["img:world"] = cover_rel
        for view in soul_views:
            portrait = _soul_portrait(view["dir"])
            view["portrait"] = None
            if portrait is not None:
                rel = f"{ASSETS_DIRNAME}/{_safe_name(view['name'], view['sid'])}{portrait.suffix.lower()}"
                _copy_if_changed(portrait, vault / rel, report, rel)
                expected[f"img:{view['sid']}"] = rel
                view["portrait"] = rel

        world_md = _world_note(
            root, run_state, soul_views, place_names, list(place_names.values()), config,
            cover=cover_rel,
        )
        _write_if_changed(vault / "世界.md", world_md, report, "世界.md")
        expected["世界"] = "世界.md"

        for view in soul_views:
            fname = f"角色/{_safe_name(view['name'], view['sid'])}.md"
            _write_if_changed(vault / fname, _soul_note(view, config), report, fname)
            expected[f"soul:{view['sid']}"] = fname

        for loc in locations:
            lid = str(loc.get("_addr") or loc.get("id"))
            label = place_names.get(lid, lid)
            fname = f"地点/{label}.md"
            _write_if_changed(
                vault / fname,
                _location_note(loc, place_names, present.get(label, []), config),
                report,
                fname,
            )
            expected[f"loc:{lid}"] = fname

        for data in entities:
            eid = str(data.get("id"))
            safe = _safe_name(str(data.get("name") or eid), eid)
            fname = f"世界设定/{safe}.md"
            _write_if_changed(vault / fname, _entity_note(data, config), report, fname)
            expected[f"ent:{eid}"] = fname

        canvas = _canvas_document(root, soul_views, locations, place_names, cover_rel)
        _write_if_changed(
            vault / CANVAS_FILENAME,
            json.dumps(canvas, ensure_ascii=False, indent=1) + "\n",
            report,
            CANVAS_FILENAME,
        )
        expected["canvas"] = CANVAS_FILENAME

        _write_if_changed(vault / "README.md", _README, report, "README.md")

        notes_dir = vault / USER_NOTES_DIRNAME
        if not notes_dir.exists():
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / "读我.md").write_text(
                "# 你的地盘\n\n"
                "这个文件夹投影器永远不碰。写什么都行。\n\n"
                "在这里 `[[链接]]` 到任何一页(比如某个角色),"
                "那一页底部的反向链接就会把这条笔记显示出来。\n",
                encoding="utf-8",
            )

        _prune_stale(vault, expected, report)
        _write_index(vault, expected)
    except Exception:  # noqa: BLE001 — the vault must never break a turn
        logger.debug("vault projection skipped", exc_info=True)
    return report


def _canvas_document(
    root: Path,
    soul_views: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    place_names: dict[str, str],
    cover_rel: str | None,
) -> dict[str, Any]:
    """Feed the projector's resolved facts into the canvas layout.

    Everything here is already computed for the notes — which soul stands on
    which place page, what the places are called, who relates to whom — so
    the canvas cannot disagree with the notes it links to.
    """
    cards = {
        view["sid"]: SoulCard(
            key=view["sid"],
            note=f"角色/{_safe_name(view['name'], view['sid'])}.md",
            name=view["name"],
        )
        for view in soul_views
    }
    boxes: dict[str, PlaceBox] = {}
    for loc in locations:
        lid = str(loc.get("_addr") or loc.get("id"))
        label = place_names.get(lid, lid)
        connections = loc.get("connections")
        boxes[label] = PlaceBox(
            key=lid,
            label=label,
            note=f"地点/{label}.md",
            connections=[_scoped(place_names, lid, str(c)) for c in connections] if isinstance(connections, list) else [],
        )
    # A soul may stand somewhere that has a name but no location record (a
    # town that is only an entity page, a nav node nothing describes). Those
    # still get a box of their own, labelled with the place's name, so the
    # picture stays "who is where"; only the truly nameless go to 在路上.
    unplaced: list[SoulCard] = []
    for view in soul_views:
        box = boxes.get(view.get("where_link") or "")
        if box is None and view.get("where_label"):
            label = _safe_name(str(view["where_label"]), view["location"])
            box = boxes.setdefault(
                label, PlaceBox(key=f"~{label}", label=label, note=None)
            )
        if box is None:
            unplaced.append(cards[view["sid"]])
        else:
            box.souls.append(cards[view["sid"]])

    by_name = {view["name"]: view["sid"] for view in soul_views}
    relations: list[tuple[str, str, str]] = []
    for view in soul_views:
        rel = (view.get("relationships") or {}).get("relationships")
        if not isinstance(rel, dict):
            continue
        for other, info in rel.items():
            target = by_name.get(str(other)) or (str(other) if str(other) in cards else None)
            if target is None:
                continue
            label = str(info.get("disposition") or "") if isinstance(info, dict) else ""
            relations.append((view["sid"], target, label))

    return build_canvas(_world_name(root), cover_rel, list(boxes.values()), unplaced, relations)


def _prune_stale(vault: Path, expected: dict[str, str], report: VaultReport) -> None:
    """Drop generated notes whose source is gone (renames, deletions).

    Only ever inside the generated folders — the user's notes are untouchable.
    """
    previous = _read_json(vault / _INDEX_FILENAME).get("notes") or {}
    if not isinstance(previous, dict):
        return
    live = set(expected.values())
    for rel in previous.values():
        if not isinstance(rel, str) or rel in live:
            continue
        if not any(rel.startswith(f"{d}/") for d in _GENERATED_DIRS):
            continue
        target = vault / rel
        try:
            if target.is_file():
                target.unlink()
                report.removed.append(rel)
        except OSError:
            logger.debug("vault prune skipped: %s", rel, exc_info=True)


def _write_index(vault: Path, expected: dict[str, str]) -> None:
    try:
        vault.mkdir(parents=True, exist_ok=True)
        (vault / _INDEX_FILENAME).write_text(
            json.dumps(
                {
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "notes": expected,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.debug("vault index write skipped", exc_info=True)
