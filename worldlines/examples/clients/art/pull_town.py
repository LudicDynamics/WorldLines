#!/usr/bin/env python3
"""Copy the 石津镇 · 雾退之夜 pixel art from the asset workshop into stoneford-town/ (Pillow).

    python3 pull_town.py            # $WORLDLINES_ASSETS_DIR, default ~/Workspaces/worldlines/worldlines-assets

Scenes and sprites are taken at their native pixel size (480x270 scenes, 64 px frames) and drawn with nearest-neighbour
scaling by the games. The grey behind the turnaround sheets is cut away (flood fill from the edges, so a white dress
stays white); the icon sheets are cut into one picture per icon. Pictures not drawn yet are reported, and the games
draw a stand-in.
"""
from __future__ import annotations

import json
import os
import sys
from collections import deque
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "stoneford-town"
ASSETS = Path(os.environ.get("WORLDLINES_ASSETS_DIR") or Path.home() / "Workspaces/worldlines/worldlines-assets")
SRC = ASSETS / "worlds/stoneford-town"
TPL = HERE.parents[3] / "src/neonrp/templates/stoneford-elena"

SCENES = {"gate_north": "gate_north", "market-square": "market_square", "guild": "guild", "inn": "inn", "shop_general": "shop",
          "townhall": "townhall", "dock": "dock", "main_street": "main_street", "road_camp": "battle/road_camp",
          "tomb_gate": "battle/tomb_gate", "tomb_chamber": "battle/tomb_chamber"}
SPRITES = ["player", "elena", "rowan", "heron", "kas", "laowei", "laoyu", "mira", "tiger", "vera", "bandit", "wraith"]
PORTRAITS = {"heron": "characters/heron/base.png", "kas": "characters/kas/base.png", "laowei": "characters/laowei/base.png",
             "laoyu": "characters/laoyu/base.png", "mira": "characters/mira/base.png", "tiger": "characters/tiger/base.png",
             "vera": "characters/vera/base.png"}
TPL_PORTRAITS = {"player": "game/player/assets/portrait.png", "elena": "souls/elena-si-elena0001/assets/portrait.png",
                 "rowan": "souls/rowan-si-rowan0001/assets/portrait.png"}
ACTIONS = ["talk", "ask", "persuade", "trade", "steal", "recruit", "fight", "rest", "quest"]
ITEMS = ["fog_map", "amulet", "commission", "pass", "duel_permit", "gate_key", "ledger", "bandit_badge"]

missing: list[str] = []


def cut_background(im: Image.Image, tol: int = 18) -> Image.Image:
    """Make the flat backdrop transparent: flood from every edge pixel through colours close to the corner's."""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    bg = px[0, 0][:3]
    near = lambda c: all(abs(c[i] - bg[i]) <= tol for i in range(3))  # noqa: E731
    seen = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        q.extend(((x, 0), (x, h - 1)))
    for y in range(h):
        q.extend(((0, y), (w - 1, y)))
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        c = px[x, y]
        if not near(c):
            continue
        px[x, y] = (c[0], c[1], c[2], 0)
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                q.append((nx, ny))
    return im


def runs(mask: list[bool], min_gap: int = 6) -> list[tuple[int, int]]:
    out, start, gap = [], None, 0
    for i, on in enumerate(mask + [False] * min_gap):
        if on:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                out.append((start, i - gap + 1))
                start, gap = None, 0
    return out


def cut_icons(path: Path, names: list[str], cols: int, rows: int, dest: Path, size: int = 64) -> None:
    if not path.exists():
        missing.append(str(path.relative_to(SRC)))
        return
    im = Image.open(path).convert("RGBA")
    if im.getpixel((0, 0))[3] > 0:
        im = cut_background(im, 24)
    w, h = im.size
    for r in range(rows):
        for c in range(cols):
            k = r * cols + c
            if k >= len(names):
                continue
            box = (c * w // cols, r * h // rows, (c + 1) * w // cols, (r + 1) * h // rows)
            cell = im.crop(box)
            bb = cell.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
            if not bb:
                continue
            cell = cell.crop(bb)
            side = max(cell.size)
            sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            sq.paste(cell, ((side - cell.size[0]) // 2, (side - cell.size[1]) // 2))
            sq.resize((size, size), Image.Resampling.BOX).save(dest / f"{names[k]}.png")


def main() -> int:
    if not SRC.exists():
        print(f"no asset workshop at {SRC} (set WORLDLINES_ASSETS_DIR)")
        return 1
    for d in ("scenes", "sprites", "portraits", "icons", "items", "map"):
        (OUT / d).mkdir(parents=True, exist_ok=True)
    layers: dict[str, list[dict]] = {}
    for zone, name in SCENES.items():
        # the scene at full size (1920×1080, the painted HD-2D picture): the games draw it under a 480×270 stage, so the
        # people (64 px frames, nearest-neighbour ×4) stay crisp pixels while the scene keeps its detail
        p = SRC / "scenes" / f"{name}.png"
        if not p.exists():
            p = SRC / "scenes" / f"{name}-native.png"
        if p.exists():
            Image.open(p).convert("RGB").save(OUT / "scenes" / f"{zone}.jpg", quality=90)
            (OUT / "scenes" / f"{zone}.png").unlink(missing_ok=True)
        else:
            missing.append(f"scenes/{name}.png")
        # collision mask (white = ground) and foreground cut-outs with their base line — see the workshop's LAYERS.md
        m = SRC / "scenes" / f"{name}-walk.png"
        if m.exists():
            Image.open(m).convert("L").resize((480, 270), Image.Resampling.NEAREST).save(OUT / "scenes" / f"{zone}-walk.png")
        else:
            missing.append(f"scenes/{name}-walk.png")
        for fg in sorted((SRC / "scenes").glob(f"{name}-fg-*.png")):
            im = Image.open(fg).convert("RGBA").resize((480, 270), Image.Resampling.NEAREST)
            out = f"scenes/{zone}-{fg.stem.split('-fg-')[1]}.fg.png"
            im.save(OUT / out)
            bb = im.getchannel("A").point(lambda v: 255 if v > 32 else 0).getbbox()
            layers.setdefault(zone, []).append({"img": out, "base": bb[3] if bb else 270})
    (OUT / "scenes" / "layers.json").write_text(json.dumps(layers, indent=1) + "\n", encoding="utf-8")
    meta = {}
    for s in SPRITES:
        p = SRC / "sprites" / s / "turnaround-native.png"
        if not p.exists():
            missing.append(f"sprites/{s}/turnaround-native.png")
            continue
        im = cut_background(Image.open(p))
        im.save(OUT / "sprites" / f"{s}.png", optimize=True)
        fh = im.size[1]
        foot = max((y for y in range(fh) for x in range(im.size[0]) if im.getpixel((x, y))[3] > 0), default=fh - 1)
        top = min((y for y in range(fh) for x in range(im.size[0]) if im.getpixel((x, y))[3] > 0), default=0)
        meta[s] = {"frame": fh, "frames": im.size[0] // fh, "foot": foot, "top": top}
    for s in ("coffin",):
        for v in ("object", "object-open"):
            p = SRC / "sprites" / s / f"{v}-native.png"
            if p.exists():
                cut_background(Image.open(p)).save(OUT / "sprites" / f"{s}-{v}.png")
    (OUT / "sprites" / "index.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    for pid, rel in [*PORTRAITS.items(), *((k, None) for k in TPL_PORTRAITS)]:
        p = (SRC / rel) if rel else (TPL / TPL_PORTRAITS[pid])
        if not p.exists():
            missing.append(str(rel or TPL_PORTRAITS[pid]))
            continue
        im = Image.open(p).convert("RGB")
        im.thumbnail((480, 720), Image.Resampling.LANCZOS)
        im.save(OUT / "portraits" / f"{pid}.jpg", quality=86)
    cut_icons(SRC / "ui/actions.png", ACTIONS, 3, 3, OUT / "icons")
    cut_icons(SRC / "ui/items.png", ITEMS, 4, 2, OUT / "items")
    p = SRC / "map/town.png"
    if p.exists():
        im = Image.open(p).convert("RGB")
        im.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        im.save(OUT / "map/town.jpg", quality=85)
    else:
        missing.append("map/town.png")
    print(f"stoneford-town: {sum(1 for _ in OUT.rglob('*.png')) + sum(1 for _ in OUT.rglob('*.jpg'))} pictures")
    if missing:
        print("not drawn yet (the games use stand-ins):\n  " + "\n  ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
