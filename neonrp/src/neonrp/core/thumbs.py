"""Small pictures for cards and avatars (10-15, chat-fe · PLATFORM-PLAY-RULES §5b「卡片用小图」): a template picture
asked with ``&w=<px>`` comes back scaled down to that width (one of :data:`WIDTHS`), as webp, made once and kept in
``~/.worldlines/cache/thumbs/`` keyed by the source file's path · mtime · size — a changed picture gets a new one.
Anything that cannot be scaled (no Pillow, not an image) is served as it is."""
from __future__ import annotations

import hashlib
from pathlib import Path

WIDTHS = (64, 128, 256, 512, 1024)
HOME = Path.home() / ".worldlines" / "cache" / "thumbs"


def width(v: str | int | None) -> int | None:
    """The asked width rounded up to one of WIDTHS (few sizes = few cache files); None = the original."""
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        return None
    return next((w for w in WIDTHS if n <= w), WIDTHS[-1]) if n > 0 else None


def thumb(src: Path | None, w: int | None) -> Path | None:
    if src is None or not w or not src.is_file():
        return src
    st = src.stat()
    key = hashlib.sha1(f"{src.resolve()}|{st.st_mtime_ns}|{st.st_size}|{w}".encode()).hexdigest()[:24]
    out = HOME / f"{key}.webp"
    if out.is_file():
        return out
    try:
        from PIL import Image

        with Image.open(src) as im:
            if im.width <= w:
                return src
            im = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA") else im.convert("RGB")
            im.thumbnail((w, w * 4))
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            im.save(tmp, "WEBP", quality=82)
            tmp.replace(out)
        return out
    except Exception:  # noqa: BLE001 — a picture that does not scale is served whole
        return src
