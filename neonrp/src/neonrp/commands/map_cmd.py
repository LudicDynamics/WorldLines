"""`neonrp map` — the layered world map and its images (core/worldmap.py).

    neonrp map status                     levels, whether each has a current image, data issues
    neonrp map generate T001              draw the layout guide → image model → assets/maps/T001.webp
    neonrp map generate --all             every level that has no image or a stale one
    neonrp map scene T001/inn             scene picture for a place → assets/places/
    neonrp map portrait rowan             style-matched portrait (+ transparent sprite) for a soul

``--backend openai|codex`` overrides the configured image backend for this run
only (settings are not changed). ``codex`` uses the local Codex login.
"""

from __future__ import annotations

import time
from pathlib import Path

import click


def _world(into: str | None) -> Path:
    root = Path(into).expanduser() if into else Path.cwd()
    if not (root / "game").is_dir():
        raise click.ClickException(f"{root} is not a world folder (no game/).")
    return root


def _cfg(backend: str | None):
    from neonrp.core.imagegen import load_image_config

    cfg = load_image_config()
    if backend:
        cfg.backend = backend
    if not cfg.backend:
        raise click.ClickException("No image backend. Pass --backend openai|codex or set one in settings.")
    return cfg


_world_opt = click.option("--world", "into", default=None, help="World folder (default: cwd).")
_backend_opt = click.option("--backend", type=click.Choice(["openai", "codex", "comfyui"]), default=None)


@click.group("map")
def map_group() -> None:
    """Layered world map: status, and image generation that follows the map data."""


@map_group.command("status")
@_world_opt
def status(into: str | None) -> None:
    from neonrp.core import worldmap as M

    root = _world(into)
    tree = M.build_map_tree(root)
    for lv, st in M.map_status(root, tree).items():
        mark = "stale" if st["stale"] else ("ok" if st["has_image"] else "missing")
        n = tree["nodes"][lv]
        click.echo(f"{lv:10} {n['name']:12} {st['kind']:8} {len(n['children']):3} places  image: {mark}")
    for i in tree["issues"]:
        click.echo(f"  ! {i['kind']}: {i['msg']}")


@map_group.command("generate")
@click.argument("level", required=False)
@click.option("--all", "all_", is_flag=True, help="Every level whose image is missing or stale.")
@_world_opt
@_backend_opt
def generate(level: str | None, all_: bool, into: str | None, backend: str | None) -> None:
    from neonrp.core import worldmap as M

    root = _world(into)
    cfg = _cfg(backend)
    tree = M.build_map_tree(root)
    if all_:
        todo = [lv for lv, st in M.map_status(root, tree).items() if not st["has_image"] or st["stale"]]
    elif level:
        todo = [level]
    else:
        raise click.UsageError("give a LEVEL (e.g. world, T001) or --all")
    for lv in todo:
        t0 = time.time()
        click.echo(f"{lv}: drawing guide → {cfg.backend} …")
        try:
            M.generate_map(root, lv, cfg=cfg)
        except (RuntimeError, ValueError) as exc:
            raise click.ClickException(f"{lv}: {exc}") from exc
        click.echo(f"{lv}: {M.map_image_path(root, lv).relative_to(root)} ({time.time() - t0:.0f}s)")


@map_group.command("scene")
@click.argument("addr")
@_world_opt
@_backend_opt
def scene(addr: str, into: str | None, backend: str | None) -> None:
    from neonrp.core import worldmap as M

    root = _world(into)
    try:
        out = M.generate_scene(root, addr, cfg=_cfg(backend))
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(str(out.relative_to(root)))


@map_group.command("portrait")
@click.argument("sid")
@click.option("--no-sprite", is_flag=True)
@_world_opt
@_backend_opt
def portrait(sid: str, no_sprite: bool, into: str | None, backend: str | None) -> None:
    from neonrp.core import worldmap as M

    root = _world(into)
    try:
        out = M.generate_portrait(root, sid, cfg=_cfg(backend), sprite=not no_sprite)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(str(out.relative_to(root)))
