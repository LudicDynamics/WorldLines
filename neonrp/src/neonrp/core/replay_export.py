"""Replay bundles (TODO #2: 存档上传 + Hub 回放馆).

Format SoT: ``rp-infra/docs/REPLAY-BUNDLE.md`` v1.1, revised 10-18 — a zip with one top directory
``<slug>-replay/`` holding ``replay.json`` (card meta), ``timeline.json`` (the replay itself, ``worldlines.replay/1``,
core/replay_pack), ``story.md`` (the narrative as markdown, for v1.1 readers; rendered from the timeline when the run
has none), ``feed.jsonl`` (per-turn index, when the run has one) and ``cover.png``.

**Privacy red line, enforced by whitelist copy**: sessions, logs, playthrough.json, game/, souls/, agents/, rules/,
any config, and — since 10-18 — the raw turn trace (``orchestration.jsonl``: plan, soul drafts, proposals, timing,
usage) never enter the bundle; ``timeline.json`` takes from it only what the player saw. New files in a run directory
stay out by default.

This is the engine-side port of ``rp-infra/tools/export_replay.py`` so the
launcher (存档 → 上传回放) and ``neonrp replay export/upload`` share it.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The run directory name ends in one or more stamps: -YYYYMMDD-HHMMSS / -migXXXXXXXX.
_STAMP_RE = re.compile(r"(-\d{8}-\d{6}|-mig[0-9a-f]{8})+$")
_TURN_HEADING = re.compile(r"^## +T\d+", re.MULTILINE)

REPLAY_MEMBERS: tuple[tuple[str, str], ...] = (
    ("story.md", "story.md"),
    ("feed.jsonl", "feed.jsonl"),
    ("cover.png", "cover.png"),
)


class ReplayExportError(ValueError):
    pass


def derive_world_slug(run_dir: Path) -> str:
    base = _STAMP_RE.sub("", Path(run_dir).name).strip("-") or Path(run_dir).name
    return re.sub(r"[^a-z0-9._-]+", "-", base.lower()).strip("-.") or "world"


def count_turns(run_dir: Path) -> int:
    run_dir = Path(run_dir)
    feed = run_dir / "feed.jsonl"
    if feed.is_file():
        try:
            n = sum(1 for line in feed.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            n = 0
        if n:
            return n
    story = run_dir / "story.md"
    if story.is_file():
        try:
            return len(_TURN_HEADING.findall(story.read_text(encoding="utf-8")))
        except OSError:
            return 0
    return 0


def world_of_run(run_dir: Path) -> tuple[str, str]:
    """(world slug, world display name) for a saved run — the manifest /
    start card when present, the folder name otherwise."""
    run_dir = Path(run_dir)
    slug = ""
    name = ""
    try:
        manifest = json.loads((run_dir / ".neonrp" / "manifest.json").read_text(encoding="utf-8"))
        if isinstance(manifest, dict):
            wid = manifest.get("wid") or manifest.get("id") or manifest.get("slug") or manifest.get("world_id")
            if isinstance(wid, str) and wid.strip():
                slug = wid.strip().removeprefix("hub:")
            if isinstance(manifest.get("name"), str):
                name = manifest["name"].strip()
    except (OSError, ValueError):
        pass
    if not slug:
        slug = derive_world_slug(run_dir)
    if not name:
        try:
            from neonrp.worlds import read_local_world_name

            name = read_local_world_name(run_dir) or ""
        except Exception:
            name = ""
    return slug, name or slug


def world_ref_of_run(run_dir: Path) -> str | None:
    """The platform address of the world a run was played in — ``hub/template/<template id>`` (the same id as the
    catalog on neonrp.worldlines.gg; official worlds too, never ``builtin:<id>``). SNS reads it from a published
    replay's meta to know the world's zone (curated → may show on iOS). None = not built from a template."""
    from neonrp.core.player_data import world_of

    run_dir = Path(run_dir)
    tid = world_of(run_dir)
    return f"hub/template/{tid}" if tid and tid != run_dir.name else None


@dataclass
class ReplayCheck:
    source: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    turns: int = 0
    world_slug: str = ""
    world_name: str = ""
    cover: Path | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_replay_source(run_dir: Path) -> ReplayCheck:
    """Can this run become a replay? story.md with at least one turn is the
    only hard requirement; the rest degrades gracefully in the player."""
    run_dir = Path(run_dir)
    check = ReplayCheck(source=run_dir)
    if not run_dir.is_dir():
        check.errors.append("check.missing_dir")
        return check
    story = run_dir / "story.md"
    try:
        text = story.read_text(encoding="utf-8") if story.is_file() else ""
    except OSError:
        text = ""
    from neonrp.core import replay_pack

    has_story = len(text.strip()) >= 10 and bool(_TURN_HEADING.search(text))
    if not has_story and not replay_pack.has_content(run_dir):   # the turn trace alone is enough (v3 runs write no story.md)
        check.errors.append("check.replay_no_story")
    check.turns = count_turns(run_dir) if has_story else replay_pack.turn_count(replay_pack.build_replay_doc(run_dir))
    if not (run_dir / "feed.jsonl").is_file():
        check.warnings.append("check.replay_no_feed")
    if not (run_dir / ".neonrp" / "orchestration" / "main.jsonl").is_file():
        check.warnings.append("check.replay_no_backstage")
    cover = run_dir / "cover.png"
    if not cover.is_file():
        try:
            from neonrp.core.image_render import discover_world_images

            pics = discover_world_images(run_dir)
            cover = pics[0] if pics else None
        except Exception:
            cover = None
    check.cover = cover if cover and Path(cover).is_file() else None
    if check.cover is None:
        check.warnings.append("check.replay_no_cover")
    check.world_slug, check.world_name = world_of_run(run_dir)
    return check


def pack_replay(
    run_dir: Path,
    *,
    world_slug: str | None = None,
    world_name: str | None = None,
    uploader: str = "",
    lang: str = "zh",
    source: str = "local-play",
    cover: Path | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """(replay.json, {member: bytes}) for a run — the whole bundle in memory, nothing written: the browser build shares
    with this straight from its own run (replay_share.share_files), the zip and the local library write it out."""
    run_dir = Path(run_dir)
    check = validate_replay_source(run_dir)
    if not check.ok:
        raise ReplayExportError("nothing to replay yet — the run has no turn past its opening: " + str(run_dir))
    slug = (world_slug or check.world_slug).strip()
    name = (world_name or check.world_name).strip() or slug
    from neonrp.core import replay_pack
    from neonrp.core.player_data import world_of

    ref = world_ref_of_run(run_dir)
    cover_src = Path(cover) if cover else (run_dir / "cover.png" if (run_dir / "cover.png").is_file() else check.cover)
    has_cover = bool(cover_src and Path(cover_src).is_file())
    tid = world_of(run_dir)
    doc = replay_pack.build_replay_doc(run_dir, world_id=tid if ref else slug, world_name=name, world_ref=ref, lang=lang,
                                       has_cover=has_cover)
    assets = replay_pack.collect_assets(run_dir, doc, cover=has_cover)
    meta: dict[str, Any] = {
        "schema_version": 3,
        "kind": "replay",
        "format": replay_pack.FORMAT,
        "world": {"slug": slug, "name": name},
        **({"world_ref": ref} if ref else {}),
        "turns": replay_pack.turn_count(doc) or check.turns,
        **({"ending": doc["ending"]} if doc.get("ending") else {}),
        "uploader": uploader,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "lang": lang,
    }
    files: dict[str, bytes] = {"replay.json": json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"),
                               replay_pack.TIMELINE_MEMBER: json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8")}
    for member, rel in REPLAY_MEMBERS:
        src = Path(cover_src) if member == "cover.png" and has_cover else run_dir / rel
        if src.is_file():
            files[member] = src.read_bytes()
        elif member == "story.md":
            files[member] = replay_pack.render_story(doc).encode("utf-8")
    for member, src in assets.items():
        try:
            files[member] = src.read_bytes()
        except OSError:
            pass
    return meta, files


def build_replay_bundle(run_dir: Path, out: Path, **kw: Any) -> dict[str, Any]:
    """Whitelist-copy a run into ``out`` (zip, one top directory ``<slug>-replay/``). Returns ``replay.json``."""
    meta, files = pack_replay(run_dir, **kw)
    top = f"{meta['world']['slug']}-replay"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for member, data in files.items():
            zf.writestr(f"{top}/{member}", data)
    return meta


def default_replay_out(run_dir: Path) -> Path:
    from neonrp.core.world_export import default_export_path

    try:
        base = default_export_path(Path(run_dir)).parent
    except Exception:
        base = Path.home() / "Downloads"
    slug, _ = world_of_run(Path(run_dir))
    return base / f"{slug}-replay-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.zip"
