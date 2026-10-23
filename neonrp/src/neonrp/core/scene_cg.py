"""Opening CG and stage cut-scenes — two optional slot kinds a template declares (10-14, the standard front end §5.1).

``template.json``::

    "opening": {"cg": [{"image": "assets/opening/cg-1.webp", "caption": {"zh": "…", "en": "…"},
                        "camera": "slow push-in", "video": "assets/opening/cg-1.mp4", "prompt": "…"}, …]}

``plots/<id>/plot.json`` (keys = a stage's index in ``stages`` or its name; paths relative to the plot folder)::

    "stage_cg": {"1": {"image": "assets/stage-1.webp", "caption": "…", "camera": "…", "video": "…", "prompt": "…"}}

Slot ids: ``opening.cg:<n>`` (n = the entry's ``id``, else its 1-based place in the list — the order they play in) and
``stage.cg:<plot id>.<n>`` (n = the stage index the plot's stage variable takes). Every field but one picture or one video
is optional; a slot nobody filled is an optional slot (lint: ``asset.optional``), the screen falls back (the cover).

Per companion (10-15): ``"variants": {"<sid>": "assets/stage-1-isse.webp"}`` beside ``image`` — a picture that shows the
companion the player picked; a run whose companion has no variant gets ``image``. Slot id ``<slot>@<sid>``. The same
``variants`` sits in an ending's ``assets`` (template/__init__.py).
"""
from __future__ import annotations

from typing import Any

FIELDS = ("image", "video", "caption", "camera", "prompt", "variants")
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v")


def norm(spec: Any) -> dict[str, Any] | None:
    """One CG declaration → {image, video, caption, camera, prompt} (a bare string = the image path)."""
    if isinstance(spec, str):
        spec = {"image": spec}
    if not isinstance(spec, dict):
        return None
    return {k: spec.get(k) for k in FIELDS if spec.get(k) not in (None, "")}


def variants(spec: Any) -> dict[str, str]:
    """{sid: image path} of a CG declaration / an ending's ``assets`` — the pictures per companion."""
    v = spec.get("variants") if isinstance(spec, dict) else None
    return {str(k): str(p) for k, p in v.items() if isinstance(p, str) and p.strip()} if isinstance(v, dict) else {}


def for_companion(cg: dict[str, Any], slot: str, sid: str | None) -> dict[str, Any]:
    """A CG as this run plays it: with a picture for ``sid`` → ``slot@sid`` and that ``image``; else the generic one.
    ``variant`` says which (None = generic); the per-companion table itself stays out of what the screen gets."""
    own = variants(cg).get(sid or "")
    out = {k: v for k, v in cg.items() if k != "variants"}
    out.update({"slot": f"{slot}@{sid}" if own else slot, "variant": sid if own else None})
    if own:
        out["image"] = own
    return out


def opening(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """[(inst, cg)] in play order, from a template.json."""
    op = data.get("opening") if isinstance(data, dict) else None
    items = op.get("cg") if isinstance(op, dict) else None
    out: list[tuple[str, dict[str, Any]]] = []
    for i, raw in enumerate(items if isinstance(items, list) else [], 1):
        cg = norm(raw)
        if cg is not None:
            inst = str((raw.get("id") if isinstance(raw, dict) else None) or i)
            out.append((inst, cg))
    return out


def stage_index(plot: dict[str, Any], key: Any) -> int | None:
    stages = plot.get("stages") if isinstance(plot.get("stages"), list) else []
    s = str(key).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    from neonrp.core.objective import stage_name

    return next((i for i, name in enumerate(stages) if stage_name(name) == s), None)


def stage(plot: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """[(stage index, cg)] from a plot.json, by stage."""
    raw = plot.get("stage_cg") if isinstance(plot, dict) else None
    out: list[tuple[int, dict[str, Any]]] = []
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        n, cg = stage_index(plot, k), norm(v)
        if n is not None and cg is not None:
            out.append((n, cg))
    return sorted(out, key=lambda x: x[0])


def caption(cg: dict[str, Any], lang: str = "zh") -> str:
    c = cg.get("caption")
    if isinstance(c, dict):
        return str(c.get(lang) or c.get("en") or c.get("zh") or next(iter(c.values()), "") or "")
    return str(c or "")
