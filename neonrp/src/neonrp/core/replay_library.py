"""The replays kept on this machine (Hub world page → this world's replays → a read-only replay page).

    ~/.worldlines/replays/<id>/
        replay.json     card meta (core/replay_export)
        timeline.json   the replay (worldlines.replay/1, core/replay_pack)
        story.md · feed.jsonl · cover.png   — the rest of the bundle whitelist, as exported
        local.json      {session_id, template, turns, ending_id, exported_at, shared?: {ref, replay_id, moment_url?, at}}

A replay is a copy taken when the run is exported (by hand, or when an ending lands): it stays readable after the run
is deleted or played on, and sharing uploads exactly these files. Exporting the same run at the same point again
returns the copy already made.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home() / ".worldlines" / "replays"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MEMBERS = ("replay.json", "timeline.json", "story.md", "feed.jsonl", "cover.png")
_EXPORT = threading.Lock()   # the ending's own export (a thread) and the ending screen's POST may race on one run


class ReplayLibraryError(Exception):
    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__(message or code)
        self.status, self.code = status, code

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": str(self)}


def _read(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _dir(rid: str) -> Path:
    if not _ID.match(rid or ""):
        raise ReplayLibraryError(400, "bad_replay_id")
    d = HOME / rid
    if not (d / "timeline.json").is_file():
        raise ReplayLibraryError(404, "no_such_replay", rid)
    return d


def _entry(d: Path, lang: str = "", names: dict[str, str | None] | None = None) -> dict[str, Any]:
    """One row of the list. ``tpl`` / ``title`` / ``updated`` are what the Hub cards read; ``title`` is the world's card
    title in ``lang`` when its template is on this machine, else the name taken at export."""
    meta, loc, doc = _read(d / "replay.json"), _read(d / "local.json"), _read(d / "timeline.json")
    world = doc.get("world") or {}
    tpl = loc.get("template") or world.get("id") or ""
    when = loc.get("exported_at") or meta.get("created_at") or ""
    names = {} if names is None else names
    if lang and world.get("ref") and tpl not in names:
        names[tpl] = _world_name(None, tpl, lang)
    title = names.get(tpl) or world.get("name") or tpl
    return {"id": d.name, "tpl": tpl, "title": title, "updated": when,
            "world": {"id": world.get("id") or tpl, "name": world.get("name") or ""},
            **({"world_ref": world["ref"]} if world.get("ref") else {}),
            "turns": meta.get("turns", 0), "ending": doc.get("ending"), "lang": doc.get("lang") or meta.get("lang") or "",
            "created_at": loc.get("exported_at") or meta.get("created_at") or "", "session_id": loc.get("session_id") or "",
            "has_cover": _cover_of(d) is not None, "shared": loc.get("shared")}


def list_replays(world: str | None = None, lang: str = "", *, home: Path | None = None) -> list[dict[str, Any]]:
    """Newest first; ``world`` = a template id (a replay matches by its world id or the run it came from)."""
    home = home or HOME
    if not home.is_dir():
        return []
    out, names = [], {}
    for d in home.iterdir():
        if not (d / "timeline.json").is_file():
            continue
        e = _entry(d, lang, names)
        if world and world not in (e["world"]["id"], e["tpl"]):
            continue
        out.append(e)
    return sorted(out, key=lambda e: str(e["created_at"]), reverse=True)


def get(rid: str) -> dict[str, Any]:
    d = _dir(rid)
    return {**_read(d / "timeline.json"), "id": rid, "local": _entry(d)}


def _cover_of(d: Path) -> Path | None:
    """cover.png, or the template's cover the replay carries as ``doc["cover"]`` (assets/card/…)."""
    if (d / "cover.png").is_file():
        return d / "cover.png"
    m = _read(d / "timeline.json").get("cover")
    p = d / str(m) if isinstance(m, str) and m.startswith("assets/") and ".." not in m.split("/") else None
    return p if p is not None and p.is_file() else None


def cover(rid: str) -> Path | None:
    return _cover_of(_dir(rid))


def file(rid: str, path: str) -> Path | None:
    """A picture of the replay (``assets/…``, the cover) — never outside its folder."""
    d = _dir(rid)
    if not path or ".." in path.split("/") or not (path == "cover.png" or path.startswith("assets/")):
        return None
    p = (d / path).resolve()
    return p if p.is_file() and p.is_relative_to(d.resolve()) else None


def delete(rid: str) -> None:
    shutil.rmtree(_dir(rid), ignore_errors=True)


def export(run_dir: Path, *, lang: str = "", source: str = "local-play", home: Path | None = None) -> dict[str, Any]:
    """Export a run into the library (or return the copy already made at this point of the run)."""
    with _EXPORT:
        return _export(Path(run_dir), lang=lang, source=source, home=home or HOME)


def _export(run_dir: Path, *, lang: str, source: str, home: Path) -> dict[str, Any]:
    from neonrp.core.player_data import world_of
    from neonrp.core.replay_export import ReplayExportError, pack_replay, world_of_run

    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise ReplayLibraryError(404, "no_such_run", run_dir.name)
    tid = world_of(run_dir)
    try:
        meta, files = pack_replay(run_dir, lang=lang or "zh", source=source, world_name=_world_name(run_dir, tid, lang))
    except ReplayExportError as exc:
        raise ReplayLibraryError(422, "nothing_to_replay", str(exc)) from exc
    ending_id = (meta.get("ending") or {}).get("id") or ""
    for e in list_replays(home=home):
        if e["session_id"] == run_dir.name and e["turns"] == meta.get("turns") and ((e.get("ending") or {}).get("id") or "") == ending_id:
            return e
    slug = world_of_run(run_dir)[0]
    rid = f"{slug[:80]}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    while (home / rid).exists():
        rid += "x"
    d = home / rid
    for name, data in files.items():
        if name in MEMBERS or (name.startswith("assets/") and ".." not in name.split("/")):
            (d / name).parent.mkdir(parents=True, exist_ok=True)
            (d / name).write_bytes(data)
    (d / "local.json").write_text(json.dumps({"session_id": run_dir.name, "template": tid, "turns": meta.get("turns", 0),
                                              "ending_id": ending_id, "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                                             ensure_ascii=False, indent=1), encoding="utf-8")
    return _entry(d)


def _world_name(run_dir: Path | None, tid: str, lang: str) -> str | None:
    """The world's card title in the player's language, when the run was built from a template."""
    try:
        from neonrp import template as TP
        from neonrp.template import i18n

        found = TP.discover()
        if tid in found:
            t = TP.load(found[tid])
            return str(i18n.card(t, lang or "zh").get("title") or t.card.get("title") or "") or None
    except Exception:  # noqa: BLE001 — the name falls back to the run's own
        return None
    return None


def share(rid: str, *, text: str = "", lang: str | None = None) -> dict[str, Any]:
    """Upload this replay to the platform (core/replay_share) and remember the link."""
    from neonrp.core import replay_share

    d = _dir(rid)
    files = {n: (d / n).read_bytes() for n in MEMBERS if (d / n).is_file()}
    files.update({f.relative_to(d).as_posix(): f.read_bytes() for f in sorted((d / "assets").rglob("*")) if f.is_file()})
    out = replay_share.share_files(_read(d / "replay.json"), files, text=text, lang=lang)
    loc = _read(d / "local.json")
    loc["shared"] = {"ref": out.get("ref"), "replay_id": out.get("replay_id"), **({"moment_url": out["moment_url"]} if out.get("moment_url") else {}),
                     "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (d / "local.json").write_text(json.dumps(loc, ensure_ascii=False, indent=1), encoding="utf-8")
    return {**out, "id": rid}


def on_ending(root: Path, ended: dict[str, Any], home: Path | None = None) -> None:
    """An ending landed: keep this run as a replay (best-effort, never raises into the turn). ``home`` is fixed by the
    caller when it runs this on another thread."""
    try:
        from neonrp.core.output_lang import normalize_prompt_lang, resolve_output_lang

        lang = normalize_prompt_lang(resolve_output_lang(Path(root)))
    except Exception:  # noqa: BLE001
        lang = ""
    try:
        export(Path(root), lang=lang, home=home)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).debug("replay on ending not kept", exc_info=True)
