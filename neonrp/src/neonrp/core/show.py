"""「此刻展示这张图」 — the host shows one of the template's own slots, and the world shows a plot's picture on its own
the first time the player walks into where it hangs (10-14, the standard front end §5.2).

    run_slots(root)               every slot of the run's template, read off the run (game/meta/template.json + the
                                  installed plots + the registry): card · opening CG · plot entries / endings · stage
                                  CG · class slot instances. Only these can be shown.
    resolve(root, reg, token)     a slot id, or an entry's id / name → its slot (a plot picture first, then a class slot)
    show_tool                     the ``[~show <slot>]`` op (async: fired, shown, never awaited) — refused when the
                                  template has no such slot
    arrivals(root, reg, before)   plot pictures hung on a place the player just walked into for the first time

The op is registered only in a run built from a template that has pictures a host would show at a moment (plot
pictures no class slot covers · stage CG · opening CG), so other worlds' prompts are unchanged. Front ends fetch the file
with ``GET /api/v1/local/templates/<template>/assets/file?slot=<slot>[&part=video]``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEEN = "shown.json"  # <data>/meta: the plot pictures already shown on arrival (once each)


def _j(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _meta(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return root / get_data_dir_name(root) / "meta"


def _plots(root: Path) -> list[tuple[str, str, Path, dict[str, Any]]]:
    """[(plot id, the template's folder for it, the installed folder, plot.json)]."""
    rec = _j(_meta(root) / "template.json", {}) or {}
    dirs = ((rec.get("built") or {}).get("plot_dirs") or {}) if isinstance(rec, dict) else {}
    rels = [str(r) for r in rec.get("plots") or []] if isinstance(rec, dict) else []
    out = []
    for pid, info in (_j(_meta(root) / "plots.json", {}) or {}).items():
        d = root / str((info or {}).get("dir") or "")
        rel = dirs.get(pid) or next((r for r in rels if Path(r).name == pid), None) or (rels[0] if len(rels) == 1 else f"plots/{pid}")
        out.append((str(pid), rel, d, _j(d / "plot.json", {}) or {}))
    return out


def run_slots(root: Path, reg: Any = None) -> dict[str, dict[str, Any]]:
    from neonrp.core import scene_cg

    rec = _j(_meta(root) / "template.json", {}) or {}
    if not isinstance(rec, dict) or not rec.get("id"):
        return {}
    tid = str(rec["id"])
    lang = str((rec.get("card") or {}).get("lang") or "zh")
    out: dict[str, dict[str, Any]] = {}

    def add(slot: str, **kw: Any) -> None:
        out[slot] = {"slot": slot, "template": tid, **kw}

    if (rec.get("card") or {}).get("cover"):
        add("card:cover", cls="card", inst="cover", label=str((rec.get("card") or {}).get("title") or tid))
    for i, cg in enumerate(((rec.get("opening") or {}).get("cg") or []) if isinstance(rec.get("opening"), dict) else [], 1):
        if isinstance(cg, dict) and cg.get("slot"):
            add(str(cg["slot"]), cls="opening", inst=str(cg["slot"]).partition(":")[2], order=i,
                label=scene_cg.caption(cg, lang), **{k: cg.get(k) for k in ("caption", "camera", "video") if cg.get(k)})
    slotted = {str(s.get("cls")) for s in ((rec.get("ui") or {}).get("slots") or []) if isinstance(s, dict)}
    for pid, rel, d, pj in _plots(root):
        for eid, es in (pj.get("endings") or {}).items():
            if isinstance(es, dict):
                add(f"plot:{rel}:ending:{eid}", cls="ending", inst=str(eid), label=str(es.get("title") or eid))
        for eid, es in (pj.get("entries") or {}).items():
            if not isinstance(es, dict) or str(es.get("class") or "") in slotted:
                continue
            img = str((es.get("assets") or {}).get("image") or "")
            add(f"plot:{rel}:entry:{eid}", cls=str(es.get("class") or ""), inst=str(eid), parent=es.get("parent"),
                label=str(es.get("name") or (es.get("props") or {}).get("name") or eid), have=bool(img and (d / img).is_file()))
        for n, cg in scene_cg.stage(pj):
            add(f"stage.cg:{pid}.{n}", cls="stage", inst=f"{pid}.{n}", plot=pid, stage=n, label=scene_cg.caption(cg, lang),
                **{k: cg.get(k) for k in ("caption", "camera", "video") if cg.get(k)})
    if reg is not None:
        from neonrp.core.holdings import _souls

        cast = {iid: v["sid"] for iid, v in _souls(root).items() if v.get("sid")}
        for sl in (rec.get("ui") or {}).get("slots") or []:
            cls, name = str(sl.get("cls") or ""), str(sl.get("slot") or "")
            if not cls or not name or cls == "level" or sl.get("scope") == "class":
                continue
            for e in reg.of_class(cls):
                inst = cast.get(e.id, e.id) if cls == "soul" else e.id
                add(f"{cls}.{name}:{inst}", cls=cls, inst=inst, entry=e.id, label=e.name)
    return out


def showable(root: Path) -> list[dict[str, Any]]:
    """The slots a host would show at a moment: plot pictures (no class slot covers them), stage CG, opening CG."""
    return [s for s in run_slots(root).values() if s["slot"].startswith(("plot:", "stage.cg:", "opening.cg:")) and ":ending:" not in s["slot"]]


def resolve(root: Path, reg: Any, token: str) -> dict[str, Any] | None:
    tok = str(token or "").strip().strip("<>[]「」\"'")
    if not tok:
        return None
    slots = run_slots(root, reg)
    if tok in slots:
        return slots[tok]
    eid = reg.resolve(tok) if reg is not None else None
    eid = eid or (tok if any(s.get("inst") == tok for s in slots.values()) else None)
    if not eid:
        return None
    hits = [s for s in slots.values() if s.get("inst") == eid or s.get("entry") == eid]
    hits.sort(key=lambda s: (not s["slot"].startswith("plot:"), not s.get("have", True)))
    return hits[0] if hits else None


def show_tool(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    """``[~show <slot | entry>]`` — only a slot the template has; the front end draws it full screen."""
    want = str(op.get("slot") or op.get("what") or "")
    hit = resolve(root, reg, want)
    if hit is None:
        return {"ok": False, "why": f"no slot {want!r} in this template", "text": ""}
    return {"ok": True, "text": str(hit.get("label") or hit["slot"]), "show": {**hit, "by": "host"}}


def queue(root: Path, hit: dict[str, Any]) -> None:
    """A trigger's ``{"to": "show"}`` (10-16): the picture goes out with this beat's shows (``arrivals`` hands it on)."""
    p = _meta(root) / SEEN
    seen = _j(p, {}) or {}
    seen["queued"] = [*(seen.get("queued") or []), hit]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")


def arrivals(root: Path, reg: Any, before_player: str | None) -> list[dict[str, Any]]:
    """What the world shows on its own this beat: pictures a trigger queued, then plot pictures hung on the place the
    player just arrived at, the first time (each shown once per run)."""
    p = _meta(root) / SEEN
    seen = _j(p, {}) or {}
    out = [s for s in seen.pop("queued", None) or [] if isinstance(s, dict)]
    here = reg.player_location
    hung = [s for s in run_slots(root).values() if s["slot"].startswith("plot:") and ":entry:" in s["slot"]
            and s.get("parent") == here and s.get("have")] if here and here != before_player else []
    done = set(seen.get("arrive") or [])
    fresh = [{**s, "by": "arrive"} for s in hung if s["slot"] not in done]
    if fresh:
        seen["arrive"] = sorted(done | {s["slot"] for s in fresh})
    if out or fresh:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")
    return out + fresh


_ACTION: dict[str, tuple[tuple[float, ...], Any]] = {}


def action(root: Path) -> Any:
    """The ``show`` op for this run, or None (nothing a host would show). Cached on the files it reads (the registry is
    loaded many times a turn)."""
    from neonrp.core.registry import ActionSpec

    meta = _meta(root)
    if not (meta / "template.json").is_file():
        return None
    sig = tuple((meta / n).stat().st_mtime if (meta / n).is_file() else 0.0 for n in ("template.json", "plots.json"))
    hit = _ACTION.get(str(root))
    if hit is not None and hit[0] == sig:
        return hit[1]
    items = showable(root)
    if not items:
        _ACTION[str(root)] = (sig, None)
        return None

    from neonrp.prompts import strings

    def line(lg: str) -> str:
        names = " · ".join(f"{s.get('inst') if s['slot'].startswith('plot:') else s['slot']} {s.get('label') or ''}".strip() for s in items[:16])
        return str(strings("player_action", lg)["show_doc"]).format(items=names)

    spec = ActionSpec("show", "tool", "neonrp.core.show:show_tool", ["slot"], wait=False, doc=line("zh"),
                      doc_i18n={lg: line(lg) for lg in ("en", "ja", "ko")})
    _ACTION[str(root)] = (sig, spec)
    return spec
