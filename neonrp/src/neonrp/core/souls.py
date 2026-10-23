"""WorldLines soul library — local soul-folder registry & migration.

A *soul* is a self-contained character bundle (player avatar or NPC) that
lives at ``~/.worldlines/souls/<sid>-<YYYYMMDD-HHMMSS>/``. This module is
the soul-side mirror of ``neonrp.worlds``: it discovers soul folders on
disk, reads/writes their ``soul.json`` identity envelope, mints new soul
folders with the design-locked 9-subfolder skeleton, and performs the
one-time ``players/`` → ``souls/`` migration.

It is a pure data/library layer: authoring (filling the subfolders with
real persona/agent content via the LLM) and runtime integration are
deliberately *not* its concern. See ``docs/WORLD_SOUL_FOLDERS.md`` §2 and
``docs/M16_SOULHUB_DESIGN.md`` §2 for the on-disk contract this enforces.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOUL_HOME = Path.home() / ".worldlines" / "souls"

# Legacy single-player-state model (pre-M16). `migrate_players_to_souls`
# folds each of these into a soul folder; see §2.4.
PLAYER_HOME = Path.home() / ".worldlines" / "players"

SOUL_JSON_SCHEMA_VERSION = 1
SOUL_CHARTER_FILENAME = "soul.md"

# The 9 subfolders every soul bundle ships with (M16 option B — the
# heroine skeleton adapted to NeonRP's apply/permission model). Order is
# stable so `create_soul_dir` is deterministic.
SOUL_SUBFOLDERS: tuple[str, ...] = (
    "agents",
    "persona",
    "background",
    "character",
    "rules",
    "short-term-memo",
    "long-term-memo",
    "trajectory",
    # `meta` is not in the heroine 9; the 9th here is the soul library's
    # own commit/version store, parallel to the world bundle. Keeping the
    # count at the documented 9 by treating `agents` ... `trajectory` as 8
    # and adding `.commits` (the disk-map §4 store) as the 9th.
    ".commits",
)


@dataclass
class SoulSource:
    """Where this soul folder came from (``soul.json.source``).

    ``kind`` is one of ``soulhub`` / ``builtin`` / ``local-create``.
    ``hash``/``version`` freeze which published creator-version this
    folder forked from (null for locally-created souls).
    """

    kind: str = "local-create"
    hash: str | None = None
    version: str | None = None


@dataclass
class SoulMeta:
    """In-memory mirror of ``soul.json`` (schema_version 1).

    Field order/names track ``docs/WORLD_SOUL_FOLDERS.md`` §2.1 exactly so
    ``write_soul_json`` round-trips byte-stably.
    """

    sid: str
    name: str
    name_local: str = ""
    version: str = "1.0"
    created_at: str = ""
    source: SoulSource = field(default_factory=SoulSource)
    agent_template: str = "heroine-classic"
    tags: list[str] = field(default_factory=list)
    schema_version: int = SOUL_JSON_SCHEMA_VERSION
    # v0.2.2: card i18n — multilingual fields for locale-aware display.
    # Each is either a plain string (back-compat) or {en, zh, ja, ko} map.
    source_lang: str = "en"
    name_i18n: dict[str, str] | None = None
    summary_i18n: dict[str, str] | None = None
    voice_i18n: dict[str, str] | None = None
    # 10-15: the author lets this character leave its world — talked to on its own, published on its own, gained by players
    standalone: bool = False
    # 10-15 (PLATFORM-PLAY-RULES §5): can a player take this character home, and when (companion_at_ending | ending:<id>)
    takeable: bool = True
    take_when: str = "companion_at_ending"

    def to_json(self) -> dict[str, Any]:
        """Serialise to the on-disk envelope (schema_version first)."""
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "sid": self.sid,
            "name": self.name,
            "name_local": self.name_local,
            "version": self.version,
            "created_at": self.created_at,
            "source": asdict(self.source),
            "agent_template": self.agent_template,
            "tags": list(self.tags),
        }
        if self.source_lang and self.source_lang != "en":
            d["source_lang"] = self.source_lang
        if self.name_i18n:
            d["name_i18n"] = self.name_i18n
        if self.summary_i18n:
            d["summary_i18n"] = self.summary_i18n
        if self.voice_i18n:
            d["voice_i18n"] = self.voice_i18n
        if self.standalone:
            d["standalone"] = True
        if not self.takeable:
            d["takeable"] = False
        if self.take_when and self.take_when != "companion_at_ending":
            d["take_when"] = self.take_when
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SoulMeta:
        """Parse a ``soul.json`` dict; tolerant of missing optional keys."""
        raw_source = data.get("source") or {}
        source = SoulSource(
            kind=raw_source.get("kind", "local-create"),
            hash=raw_source.get("hash"),
            version=raw_source.get("version"),
        )
        return cls(
            sid=data["sid"],
            name=data["name"],
            name_local=data.get("name_local", ""),
            version=data.get("version", "1.0"),
            created_at=data.get("created_at", ""),
            source=source,
            agent_template=data.get("agent_template", "heroine-classic"),
            tags=list(data.get("tags", [])),
            schema_version=data.get("schema_version", SOUL_JSON_SCHEMA_VERSION),
            source_lang=data.get("source_lang", "en"),
            name_i18n=data.get("name_i18n"),
            summary_i18n=data.get("summary_i18n"),
            voice_i18n=data.get("voice_i18n"),
            standalone=data.get("standalone") is True,
            takeable=data.get("takeable") is not False,
            take_when=str(data.get("take_when") or "companion_at_ending"),
        )


def read_soul_json(soul_dir: Path) -> SoulMeta | None:
    """Read ``<soul_dir>/soul.json`` → :class:`SoulMeta`.

    Returns ``None`` (never raises) if the file is missing, unreadable,
    not valid JSON, or lacks the mandatory ``sid``/``name`` keys — so
    callers can treat "not a soul folder" uniformly.
    """
    soul_json = soul_dir / "soul.json"
    try:
        data = json.loads(soul_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or "sid" not in data or "name" not in data:
        return None
    try:
        return SoulMeta.from_json(data)
    except (KeyError, TypeError):
        return None


def write_soul_json(soul_dir: Path, meta: SoulMeta) -> None:
    """Write ``meta`` to ``<soul_dir>/soul.json`` (pretty, UTF-8, trailing \\n)."""
    soul_dir.mkdir(parents=True, exist_ok=True)
    soul_json = soul_dir / "soul.json"
    soul_json.write_text(
        json.dumps(meta.to_json(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _seed_soul_md(sid: str, *, name: str, name_local: str = "") -> str:
    """Return the root ``soul.md`` charter stub for a newly-minted soul.

    The library owns the presence of this file (M16 root contract), while
    the authoring flow later replaces the stub with a real charter.
    """
    display = f"{name} ({name_local})" if name_local else name
    return (
        f"# Soul Charter — {display}\n\n"
        f"## Core Presence\n\n"
        f"{name} is a newly created soul (`sid={sid}`). Replace this stub with the "
        "character's voice, values, pressure pattern, and blind spots during soul authoring.\n"
    )


def _display_name(meta: SoulMeta, locale: str = "en") -> str:
    """Human label for pickers, locale-aware.

    In a non-source locale, prefers the latin ``name`` over ``name_local``
    (Chinese glyphs in a JP/KR UI are jarring). Back-compat: no i18n
    block → same label as before.
    """
    from neonrp.core.i18n_card import card_name_for_locale

    return card_name_for_locale(
        meta.name,
        meta.name_local,
        locale,
        source_lang=meta.source_lang,
        name_i18n=meta.name_i18n,
    )


def list_souls(locale: str = "en") -> list[dict[str, Any]]:
    """List soul folders with display info, newest-first by mtime.

    Mirrors :func:`neonrp.worlds.list_worlds` / ``list_saved_games``:
    each entry carries ``{sid, name, name_local, version, source,
    display_name}`` plus ``path``/``mtime``.

    ``locale`` controls how ``display_name`` is rendered: in a non-source
    locale the latin ``name`` is preferred over CJK ``name_local`` to
    avoid jarring mismatches (Chinese glyphs in a JP UI, etc.).

    Tolerant of soul.json-less bundles: hub-published / downloaded souls
    (bundle_factory output) ship persona/ + character/ but no M16 soul.json.
    Such a folder still counts as a soul if it has ``persona/`` or
    ``character/profile.json``; its identity is derived from
    ``character/profile.json`` / ``.worldhub.json`` / the directory name.
    """
    from neonrp.core.i18n_card import card_name_for_locale

    if not SOUL_HOME.exists():
        return []

    souls: list[dict[str, Any]] = []
    for soul_dir in SOUL_HOME.iterdir():
        if not soul_dir.is_dir() or soul_dir.name.startswith("."):
            continue
        meta = read_soul_json(soul_dir)
        if meta is not None:
            sid = meta.sid
            name = meta.name
            name_local = meta.name_local
            version = meta.version
            source = asdict(meta.source)
            display_name = _display_name(meta, locale)
            standalone = meta.standalone
            take = meta.take_when if meta.takeable else None
        else:
            # soul.json-less bundle — accept only if it is soul-shaped.
            profile_path = soul_dir / "character" / "profile.json"
            if not (soul_dir / "persona").is_dir() and not profile_path.is_file():
                continue
            prof: dict[str, Any] = {}
            try:
                prof = json.loads(profile_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                prof = {}
            wh: dict[str, Any] = {}
            try:
                wh = json.loads((soul_dir / ".worldhub.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                wh = {}
            sid = str(prof.get("sid") or wh.get("slug") or soul_dir.name.split("-")[0] or soul_dir.name)
            name_local = str(prof.get("name_local") or "")
            name = str(prof.get("display_name") or prof.get("name") or wh.get("name") or sid)
            version = str(wh.get("version") or "1.0")
            source = {"kind": "soulhub" if wh else "local-create", "hash": wh.get("hash"), "version": version}
            display_name = card_name_for_locale(name, name_local, locale)
            standalone, take = False, "companion_at_ending"
        mtime = soul_dir.stat().st_mtime
        souls.append({
            "sid": sid,
            "name": name,
            "name_local": name_local,
            "version": version,
            "source": source,
            "display_name": display_name,
            "path": soul_dir,
            "mtime": mtime,
            "mtime_display": datetime.fromtimestamp(mtime).strftime("%m/%d %H:%M"),
            "dir_name": soul_dir.name,
            "standalone": standalone,
            "takeable": take is not None,
            "take_when": take,
        })

    souls.sort(key=lambda s: s["mtime"], reverse=True)
    return souls


def soul_slug(name: str) -> str:
    """Folder/sid token for a character name — keeps CJK (罗文 stays 罗文)."""
    import re

    text = str(name or "").strip().lower()
    text = re.sub(r"[\s/\\:*?\"<>|]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-.")
    return text or "soul"


def is_soul_workshop(root: Path | str | None) -> bool:
    """True when ``root`` IS one character's folder (soul.json at the root,
    no `game/`): the build session authors the character in place."""
    if not root:
        return False
    r = Path(root)
    return (r / "soul.json").is_file() and not (r / "game").is_dir()


def ensure_soul_workshop_project(soul_dir: Path) -> Path:
    """Make a character folder runnable by the engine: `.neonrp/manifest.json`
    (the「NeonRP project not initialized」check) without the world-shaped
    `game/` / `rules/` that `ensure_dirs` would add. Idempotent."""
    from neonrp.core.manifest import Manifest
    from neonrp.core.paths import get_manifest_path, get_neonrp_dir
    from neonrp.core.storage import atomic_write_json

    soul_dir = Path(soul_dir)
    nd = get_neonrp_dir(soul_dir)
    nd.mkdir(parents=True, exist_ok=True)
    for sub in ("events", "logs", "sessions"):
        (nd / sub).mkdir(exist_ok=True)
    mp = get_manifest_path(soul_dir)
    if not mp.exists():
        atomic_write_json(mp, Manifest().model_dump())
    return mp


def create_soul_workshop(name: str, *, model_ref: str | None = None) -> Path:
    """Start a character in the library and make its folder a build-able
    project (「角色构建应该是新建一个 souls/<npc name> 的文档,
    然后在里面进行操作」— not a throw-away world).

    ``~/.worldlines/souls/<sid>/`` gets the 9-folder skeleton, a seeded
    ``soul.json``, an ``assets/`` for the portrait, and ``.neonrp/config.json``
    pointing at ``model_ref`` so the workshop has a model to talk to. Name
    collisions get ``-2``, ``-3``… like blank worlds do.
    """
    name = str(name or "").strip()
    if not name:
        raise ValueError("a character needs a name")
    base = soul_slug(name)
    sid, n = base, 1
    while (SOUL_HOME / sid).exists():
        n += 1
        sid = f"{base}-{n}"
    soul_dir = SOUL_HOME / sid
    soul_dir.mkdir(parents=True)
    for sub in SOUL_SUBFOLDERS:
        (soul_dir / sub).mkdir(parents=True, exist_ok=True)
    (soul_dir / "assets").mkdir(exist_ok=True)
    write_soul_json(soul_dir, SoulMeta(sid=sid, name=name, name_local=name, created_at=datetime.now().isoformat(timespec="seconds")))
    (soul_dir / "persona" / "core.md").write_text(f"# {name}\n\n(待写:一句话是谁、想要什么、怕什么。)\n", encoding="utf-8")
    ensure_soul_workshop_project(soul_dir)
    try:
        from neonrp.worlds import seed_run_model

        seed_run_model(soul_dir, model_ref)
    except Exception:  # noqa: BLE001 — a missing model is reported by the TUI, not here
        pass
    return soul_dir


def archive_soul(soul_dir: Path, sid: str | None = None, *, overwrite: bool = False) -> Path:
    """Put an authored soul folder into the library (``~/.worldlines/souls/<sid>/``).

    (任务 B1):「/create 是在 .worldlines 里存放 souls 的文件夹
    建立 character … cast 是初始化 souls 里面的文档进入世界」。The build agent
    authors a draft inside the project; the moment it is cast, a copy lands
    here so the character exists independently of that one world and shows
    up in the launcher's 角色库. Run-state is left behind (it belongs to the
    world instance, not the character).

    Returns the library path. A second cast of the same sid is a no-op unless
    ``overwrite`` is set.
    """
    import shutil

    soul_dir = Path(soul_dir)
    if not soul_dir.is_dir():
        raise FileNotFoundError(soul_dir)
    meta = read_soul_json(soul_dir)
    sid = str(sid or (meta.sid if meta else "") or soul_dir.name).strip()
    dest = SOUL_HOME / sid
    try:
        if soul_dir.resolve() == dest.resolve():
            return dest
    except OSError:
        pass
    if dest.exists():
        if not overwrite:
            return dest
        shutil.rmtree(dest)
    SOUL_HOME.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        soul_dir,
        dest,
        ignore=shutil.ignore_patterns("run_state.json", "__pycache__", ".DS_Store"),
    )
    return dest


def delete_soul(soul_dir_name: str) -> bool:
    """Delete a soul folder from the SOUL_HOME library. Best-effort.

    ``soul_dir_name`` is the folder name under :data:`SOUL_HOME` — the
    ``dir_name`` field :func:`list_souls` returns for each entry. Removes
    ``SOUL_HOME/<dir>`` with ``shutil.rmtree``. Refuses (returns False) for a
    blank/dotted/path-traversing name, or when the dir doesn't exist. Only the
    library copy is touched — souls baked into a world's run are untouched.
    Never raises; returns True only when the dir was actually removed.
    """
    import logging
    import shutil

    # Guard against empty / hidden / path-escaping names (the library only
    # lists plain, non-dotted child dirs — mirror that here).
    if not soul_dir_name or soul_dir_name.startswith(".") or "/" in soul_dir_name:
        return False
    soul_dir = SOUL_HOME / soul_dir_name
    if not soul_dir.is_dir():
        return False
    try:
        shutil.rmtree(soul_dir)
    except OSError:
        logging.getLogger("neonrp").warning(
            "delete_soul: failed to remove %s", soul_dir, exc_info=True,
        )
        return False
    return True


def create_soul_dir(
    sid: str,
    *,
    name: str,
    name_local: str = "",
    agent_template: str = "heroine-classic",
    source: SoulSource | None = None,
    tags: list[str] | None = None,
) -> Path:
    """Create a new soul directory and seed its ``soul.json``.

    Mirrors :func:`neonrp.worlds.create_game_dir`: the folder is
    ``~/.worldlines/souls/<sid>-<YYYYMMDD-HHMMSS>/`` and is created with
    the full :data:`SOUL_SUBFOLDERS` skeleton. The subfolders are left
    empty on purpose — populating persona/agents/etc. is the authoring
    step's job, not this library's.

    Returns the path to the new soul directory.
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    soul_dir = SOUL_HOME / f"{sid}-{timestamp}"
    soul_dir.mkdir(parents=True, exist_ok=True)
    for sub in SOUL_SUBFOLDERS:
        (soul_dir / sub).mkdir(parents=True, exist_ok=True)

    meta = SoulMeta(
        sid=sid,
        name=name,
        name_local=name_local,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source=source or SoulSource(kind="local-create"),
        agent_template=agent_template,
        tags=tags or [],
    )
    write_soul_json(soul_dir, meta)
    (soul_dir / SOUL_CHARTER_FILENAME).write_text(
        _seed_soul_md(sid, name=name, name_local=name_local),
        encoding="utf-8",
    )
    return soul_dir


# Sentinel dropped into PLAYER_HOME after a successful migration so the
# one-time import is idempotent across launches. Presence == done; we
# never re-scan players/ once it exists.
_MIGRATION_MARKER = ".migrated_to_souls"


def migrate_players_to_souls() -> list[Path]:
    """One-time import of legacy ``~/.worldlines/players/`` → souls.

    For each ``players/<p>/`` profile, synthesise a minimal soul folder:
    a stub ``soul.json`` (``source.kind="builtin"``, marking it as a
    migrated legacy profile) plus the soul skeleton, with the legacy
    ``profile/stats/inventory/...`` JSON files copied verbatim into the
    soul's ``character/`` folder (the §2.4 mapping).

    Idempotent: a marker file is written under ``players/`` on success;
    if it already exists the function is a no-op and returns ``[]``.
    Returns the list of newly-created soul directories.
    """
    if not PLAYER_HOME.exists():
        return []

    marker = PLAYER_HOME / _MIGRATION_MARKER
    if marker.exists():
        return []

    created: list[Path] = []
    for player_dir in sorted(PLAYER_HOME.iterdir()):
        if not player_dir.is_dir():
            continue

        sid = player_dir.name
        soul_dir = create_soul_dir(
            sid,
            name=sid,
            agent_template="minimal",
            source=SoulSource(kind="builtin"),
            tags=["migrated"],
        )

        # §2.4: legacy player state (profile/stats/inventory/equipment/
        # wallet/flags/journal) maps into the soul's character/ folder.
        character_dir = soul_dir / "character"
        for legacy_file in player_dir.iterdir():
            if legacy_file.is_file():
                (character_dir / legacy_file.name).write_bytes(
                    legacy_file.read_bytes()
                )

        created.append(soul_dir)

    marker.write_text(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n",
        encoding="utf-8",
    )
    return created
