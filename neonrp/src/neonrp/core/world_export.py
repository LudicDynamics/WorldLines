"""Zip a worldlines game folder for sharing / backup.

The archive contains the whole game directory (including `.neonrp/` history
and event log). The sibling Claude Code workspace (`<name>-cc/`) is NOT
included — it's derivable from the templates and contains symlinks back into
the main game dir. On import, re-running `worldlines` in MCP mode regenerates it.
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path


def default_download_dir() -> Path:
    """Return a sensible default output directory for exports."""
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        return downloads
    return Path.home()


def default_export_path(world_path: Path) -> Path:
    """Build a default zip file path from the world folder's name."""
    stem = world_path.name
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return default_download_dir() / f"worldlines-{stem}-{ts}.zip"


# Directories we always skip inside a game folder — noise that would
# bloat the archive and isn't useful for restoring the world.
_EXCLUDE_DIR_NAMES = {
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
}

# 安全边界(B3/W1):export deny-by-default —— `.neonrp/` 是
# 引擎运行时(config.json 含明文 API key、sessions/events 是存档态)。分享用的
# 导出只放引擎必需的 canonical playthrough.json,其余 .neonrp/** 一律不出包。
# 新增运行时文件也默认不泄露(allowlist,非 denylist)。
# manifest.json is the project index (branches / entity table, no secrets):
# without it an export is not a worldlines project on the other side, and
# `load_world_zip` used to refuse every export. Kept on the allowlist since
# 2026-09-11; config.json / sessions / events / logs stay out.
_NEONRP_EXPORT_ALLOW = {".neonrp/playthrough.json", ".neonrp/manifest.json"}


def export_world(
    world_path: Path,
    output_path: Path | None = None,
    *,
    include_logs: bool = True,
) -> Path:
    """Zip a worldlines game folder. Returns the final archive path.

    Args:
        world_path: path to the game directory (must contain `.neonrp/`).
        output_path: destination .zip path; default = ~/Downloads/<auto>.zip.
        include_logs: retained for API compat. The security boundary now
            excludes ALL of `.neonrp/` except playthrough.json (deny-by-default),
            so logs/sessions/config never ship regardless of this flag.

    Raises:
        FileNotFoundError: if world_path doesn't exist.
        ValueError: if world_path has no `.neonrp/` directory.
    """
    world_path = Path(world_path).expanduser().resolve()
    if not world_path.is_dir():
        raise FileNotFoundError(f"World directory not found: {world_path}")
    if not (world_path / ".neonrp").is_dir():
        raise ValueError(f"Not a worldlines game (missing .neonrp/): {world_path}")

    output_path = Path(output_path).expanduser().resolve() if output_path else default_export_path(world_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    arc_root = world_path.name

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in world_path.rglob("*"):
            rel = entry.relative_to(world_path)
            rel_posix = rel.as_posix()
            if any(part in _EXCLUDE_DIR_NAMES for part in rel.parts):
                continue
            # deny-by-default:.neonrp/ 运行时只放 playthrough.json(见上),
            # 其余(config.json 明文 key / sessions / events / logs)不出包。
            if (rel_posix == ".neonrp" or rel_posix.startswith(".neonrp/")) \
                    and rel_posix not in _NEONRP_EXPORT_ALLOW:
                continue
            if entry.is_symlink() or not entry.is_file():
                continue
            zf.write(entry, arcname=str(Path(arc_root) / rel))

        # A′ 画布边车(issue #14):STUDIO_HOME 的创作画布随包出行,打进
        # zip 的 <root>/.studio/ 侧目录 —— 不混入 game/**,世界源保持纯内容
        # (对 2026-07-13「never exported」决定的修正案:随行但隔离,
        # 导入侧恢复回 STUDIO_HOME,世界目录里不留 .studio)。best-effort。
        try:
            from neonrp.worlds import get_studio_dir

            sdir = get_studio_dir(world_path.name)
            for name in ("flow.json", "relationships.json"):
                f = sdir / name
                if f.is_file():
                    zf.write(f, arcname=str(Path(arc_root) / ".studio" / name))
        except Exception:  # noqa: BLE001 — 画布缺席不阻塞导出
            pass

    return output_path


def summarize_archive(archive_path: Path) -> dict:
    """Return a small summary of an exported archive (for display)."""
    archive_path = Path(archive_path)
    size_bytes = archive_path.stat().st_size
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            count = len(zf.namelist())
    except Exception:
        count = -1
    return {
        "path": str(archive_path),
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "file_count": count,
    }


def load_world_zip(
    zip_path: Path,
    games_dir: Path | None = None,
    *,
    overwrite: bool = False,
) -> Path:
    """Extract an exported world zip into the world library.

    The archive produced by `export_world` has a single top-level folder
    (the original world dir name). We preserve that name unless the target
    already exists — then we append a timestamp suffix to avoid clobbering.

    Args:
        zip_path: path to the .zip produced by export_world.
        games_dir: destination root (default: ~/.worldlines/worlds — the
            library SOURCE home; a downloaded world is a reusable source).
        overwrite: if True and target exists, replace it; otherwise suffix.

    Returns:
        Path to the extracted game folder.

    Raises:
        FileNotFoundError: if zip_path doesn't exist.
        ValueError: if the archive isn't a valid worldlines export.
    """
    import shutil

    zip_path = Path(zip_path).expanduser().resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(f"Zip not found: {zip_path}")

    if games_dir is None:
        from neonrp.worlds import WORLDS_HOME

        games_dir = WORLDS_HOME
    games_dir = Path(games_dir).expanduser()
    games_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()
            if not members:
                raise ValueError("Zip is empty")
            # Detect the single top-level dir from the archive.
            top_levels = {m.split("/", 1)[0] for m in members if m.strip("/")}
            if len(top_levels) != 1:
                raise ValueError(
                    f"Expected exactly one top-level folder in the archive, got {len(top_levels)}"
                )
            arc_root = next(iter(top_levels))

            # Pre-flight: a worldlines export carries `<arc_root>/.neonrp/manifest.json`.
            # Template-style worlds (hub downloads, hand-made folders) ship
            # without `.neonrp/` but are still worlds — recognise them by
            # their `game/` payload and bootstrap the manifest after
            # extraction. Anything with neither is refused (2026-09-11: the
            # strict check broke every hub download of a template world).
            expected = f"{arc_root}/.neonrp/manifest.json"
            has_manifest = any(m == expected or m.startswith(expected) for m in members)
            looks_like_world = any(
                m.startswith(f"{arc_root}/game/")
                or m.endswith(("/game-start.json", "/playthrough.json", "/world_map.json"))
                for m in members
            )
            if not has_manifest and not looks_like_world:
                raise ValueError(
                    "Archive does not look like a worldlines export "
                    "(missing .neonrp/manifest.json and no game/ payload)."
                )

            target = games_dir / arc_root
            if target.exists():
                if overwrite:
                    shutil.rmtree(target)
                else:
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    target = games_dir / f"{arc_root}-restored-{ts}"

            # Archive's entries are `<arc_root>/...`. If we just
            # `extractall(games_dir)`, the entries land at
            # `games_dir/<arc_root>/...` — which collides with (and
            # silently overwrites) any pre-existing game dir of that name,
            # even when we already picked a timestamped target above.
            # Extract to a fresh staging dir, then move into target.
            staging = games_dir / f".extract-tmp-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
            try:
                staging.mkdir(parents=True, exist_ok=False)
                zf.extractall(staging)
                extracted = staging / arc_root
                shutil.move(str(extracted), target)
            finally:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Not a valid zip: {exc}")

    # Template-style archive: give it the minimal `.neonrp/` so the engine
    # (and `load_world_zip`'s own callers) see an initialized world.
    if not has_manifest:
        try:
            from neonrp.core.manifest import Manifest
            from neonrp.core.paths import get_manifest_path
            from neonrp.core.storage import atomic_write_json, ensure_dirs

            ensure_dirs(target)
            mp = get_manifest_path(target)
            if not mp.exists():
                atomic_write_json(mp, Manifest().model_dump())
        except Exception:  # noqa: BLE001 — bootstrap is best-effort; the world still landed
            pass

    # A′ 边车恢复:包里带的 .studio/ 画布 → STUDIO_HOME/<目标名>/,然后从
    # 世界目录移除(源保持纯内容)。目标名=最终落地目录名(可能带时间戳后缀)。
    studio_src = target / ".studio"
    if studio_src.is_dir():
        try:
            from neonrp.worlds import get_studio_dir

            dest = get_studio_dir(target.name, create=True)
            for f in studio_src.iterdir():
                if f.is_file() and f.suffix == ".json":
                    shutil.copy2(f, dest / f.name)
        except Exception:  # noqa: BLE001 — 画布恢复失败不阻塞导入
            pass
        shutil.rmtree(studio_src, ignore_errors=True)

    return target
