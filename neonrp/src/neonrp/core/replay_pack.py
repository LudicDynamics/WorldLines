"""The replay document — ``worldlines.replay/1`` (niko 10-15/10-18: a finished run the player chooses to share).

One JSON file, display-only, built from a saved run. It carries what a reader sees and nothing else:

    {
      "format": "worldlines.replay/1",
      "world":  {"id": <template id | run slug>, "name": str, "ref"?: "hub/template/<id>"},
      "lang": str, "created_at": iso, "engine": <neonrp version>,
      "cover": "cover.png" | null,                       # a member of the bundle, never a path on the player's disk
      "cast":   [{"id": "player" | <soul id>, "name": str, "role": "player" | "soul"}],
      "places": [{"id": "<area>/<node>" | <node>, "name": str, "area"?: str}],
      "turns":  [{"n": int, "place"?: str, "time"?: {"day"?: int, "clock"?: str},
                  "beats": [{"kind": str, "input"?: str,
                             "lines": [{"who": str, "role": "host" | "player" | "soul" | "handoff" | "narrator" | ..., "text": str, "cast"?: id}],
                             "dice":  [{"who"?: str, "text": str}]}]}],
      "ending": {"id": str, "title": str, "kind"?: str, "turn"?: int, "image"?: member} | null   # kind from the world's plot
    }

For the player (10-18, niko: a replay is the run played back on the standard front end's stage — speeds, seek, the
ending's art), each beat also carries ``events`` — the contract beat events (core/beat_events, the names and shapes
GET /api/v1/play/engine/beats gives the live screen) that show something: plan.beat / resolve.beat (without the planning
board, its checks and who was asked), dice, state.changed (gained / lost only), party.join / party.leave, stage.changed,
show, place.discovered, achievement.unlocked, reward.granted, milestone, audio.cue, run.settled — and ``present``, the
characters on the scene. ``assets`` maps the template slot names the stage asks for (``place.scene:<addr>``,
``soul.portrait:<sid>``, ``soul.sprite:<sid>``, ``ending:<id>``) to the bundle members that carry the run's own pictures;
a reader without a member falls back to the template's slot, then to the silhouettes.

Open schema: readers ignore keys they do not know; writers may add keys (an ``x-`` prefix for experiments). A new
``format`` major is the only breaking change.

**Whitelist, not blacklist.** Each beat copies the four display fields of the turn trace — the narration a player saw,
the scripted lines, the dice lines, the ending — and nothing from plan / souls reasoning / proposals / tool calls /
timing / usage / bus messages (the private orchestration and the model's working). Text passes the publish key scan
(core/hub_publish) and a key-shaped string is replaced. The source of truth is the run's own turn trace
(``.neonrp/orchestration/<branch>.jsonl``); a run from before the trace carried beats falls back to ``story.md``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

FORMAT = "worldlines.replay/1"
TIMELINE_MEMBER = "timeline.json"

_TURN_HEADING = re.compile(r"^## +T(\d+)(.*)$")
_SPEAKER_LINE = re.compile(r"^\*\*(?P<who>[^*]{1,60})\*\*\s*[:：]\s*(?P<text>.*)$")
_REDACTED = "[redacted]"
# A character's line in a planning beat ends with her private draft, ``\n(<label>: <draft>)`` — table scaffolding the
# player sees only with the debug display on; the replay keeps what she said.
_INTENDS_TAIL = re.compile(r"\n\([^\n():：]{1,16}[:：][^\n]*\)\s*$")
# Scaffolding roles (the host handing the mic over) are not part of what was said at the table.
_BACKSTAGE_ROLES = frozenset({"handoff"})


def _redact(text: str) -> str:
    from neonrp.core.hub_publish import _KEY_PATTERNS

    for _kind, pat in _KEY_PATTERNS:
        text = pat.sub(_REDACTED, text)
    return text


def _text(v: Any, limit: int = 20000) -> str:
    return _redact(str(v).strip())[:limit] if isinstance(v, str) else ""


def _trace_path(run_dir: Path) -> Path | None:
    d = run_dir / ".neonrp" / "orchestration"
    branch = "main"
    try:
        m = json.loads((run_dir / ".neonrp" / "manifest.json").read_text(encoding="utf-8"))
        if isinstance(m, dict) and isinstance(m.get("current_branch"), str) and m["current_branch"].strip():
            branch = m["current_branch"].strip()
    except (OSError, ValueError):
        pass
    for p in (d / f"{branch}.jsonl", d / "main.jsonl"):
        if p.is_file():
            return p
    return None


def _records(path: Path) -> Iterable[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            yield rec


def _strip_roll_header(narration: str, dice: list[dict[str, Any]]) -> str:
    """A resolved check prints its own result as the narration's first paragraph (``[who skill: n > m] → …``); the
    replay keeps that in ``dice`` and the prose without it."""
    if not dice or not narration.startswith("["):
        return narration
    head, sep, rest = narration.partition("\n\n")
    return rest.strip() if sep and "]" in head and "\n" not in head else narration


# beat events a replay keeps (what the screen shows), and the keys of each that stay backstage
_EVENT_KEEP = ("plan.beat", "resolve.beat", "dice", "state.changed", "party.join", "party.leave", "stage.changed", "show",
               "place.discovered", "achievement.unlocked", "reward.granted", "milestone", "audio.cue", "run.settled")
_EVENT_DROP = {"plan.beat": ("board", "checks", "mic", "ended_by"), "resolve.beat": ("panels", "advanced_by"),
               "state.changed": ("applied", "created", "refused")}


def _clean(v: Any) -> Any:
    if isinstance(v, str):
        return _redact(v)
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    return v


def _events_of(rec: dict[str, Any], run_dir: Path | None) -> list[list[Any]]:
    """[[name, data]] — this beat's contract events, the backstage keys taken out."""
    try:
        from neonrp.core import beat_events

        evs, _ = beat_events.from_traces([rec], None, root=run_dir)
    except Exception:  # noqa: BLE001 — a replay without events still reads
        return []
    out: list[list[Any]] = []
    for name, data in evs:
        if name not in _EVENT_KEEP or not isinstance(data, dict):
            continue
        data = {k: v for k, v in data.items() if k not in _EVENT_DROP.get(name, ())}
        if name == "plan.beat":
            data["script"] = [{**x, "text": _INTENDS_TAIL.sub("", str(x.get("text") or "")).strip()} for x in data.get("script") or []
                              if isinstance(x, dict) and x.get("role") not in _BACKSTAGE_ROLES]
        if name == "state.changed" and not (data.get("gained") or data.get("lost")):
            continue
        out.append([name, _clean(data)])
    return out


def _present_of(rec: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(str(s.get("sid")) for s in rec.get("souls") or []
                              if isinstance(s, dict) and s.get("sid") and s.get("activated") not in (False, "False")))


def _beat_of(rec: dict[str, Any], run_dir: Path | None = None) -> dict[str, Any] | None:
    apply = rec.get("apply") if isinstance(rec.get("apply"), dict) else {}
    beat = apply.get("beat") if isinstance(apply.get("beat"), dict) else {}
    kind = str(beat.get("kind") or "turn")
    dice = [{**({"who": _text(c.get("who"), 80)} if isinstance(c, dict) and c.get("who") else {}),
             "text": _text(c.get("text") if isinstance(c, dict) else c, 400)}
            for c in (beat.get("rolled") or []) if (isinstance(c, str) and c.strip()) or (isinstance(c, dict) and c.get("text"))]
    lines: list[dict[str, Any]] = []
    for s in beat.get("script") or []:
        if not isinstance(s, dict) or not _text(s.get("text")):
            continue
        role = _text(s.get("role"), 24) or "host"
        if role in _BACKSTAGE_ROLES:
            continue
        said_line = _INTENDS_TAIL.sub("", _text(s.get("text"))).strip()
        if said_line:
            lines.append({"who": _text(s.get("who"), 80), "role": role, "text": said_line})
    player = rec.get("player") if isinstance(rec.get("player"), dict) else {}
    said = "" if kind == "opening" else _text(player.get("input"), 4000)   # the opening's input is the engine's start line
    if said:
        lines = [ln for ln in lines if not (ln["role"] == "player" and ln["text"] == said)]
    if not lines:
        prose = _strip_roll_header(_text(apply.get("narration_plain")), dice)
        if prose:
            lines.append({"who": "", "role": "narrator", "text": prose})
    events = _events_of(rec, run_dir) if run_dir is not None else []
    if not lines and not dice and not said and not any(e[0] not in ("plan.beat", "resolve.beat") for e in events):
        return None   # nothing shown: a beat's own event without any text is not a beat of the replay
    present = _present_of(rec)
    return {"kind": kind, **({"input": said} if said else {}), "lines": lines, "dice": dice,
            **({"events": events} if events else {}), **({"present": present} if present else {})}


def _time_of(apply: dict[str, Any]) -> dict[str, Any] | None:
    v = apply.get("variables") if isinstance(apply.get("variables"), dict) else {}
    out: dict[str, Any] = {}
    try:
        if v.get("time.day") is not None:
            out["day"] = int(v["time.day"])
    except (TypeError, ValueError):
        pass
    if isinstance(v.get("time.clock"), str) and v["time.clock"].strip():
        out["clock"] = v["time.clock"].strip()
    return out or None


def _ending_of(apply: dict[str, Any], turn: int) -> dict[str, Any] | None:
    e = apply.get("ended")
    if isinstance(e, dict) and e.get("id"):
        return {"id": _text(str(e["id"]), 120), "title": _text(str(e.get("title") or ""), 200), "turn": int(e.get("turn", turn) or turn)}
    return None


def _from_trace(path: Path, run_dir: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[str]]:
    turns: dict[int, dict[str, Any]] = {}
    ending: dict[str, Any] | None = None
    places: list[str] = []
    for rec in _records(path):
        try:
            n = int(rec.get("turn_seq") or 0)
        except (TypeError, ValueError):
            n = 0
        apply = rec.get("apply") if isinstance(rec.get("apply"), dict) else {}
        t = turns.setdefault(n, {"n": n, "beats": []})
        v = apply.get("variables") if isinstance(apply.get("variables"), dict) else {}
        place = v.get("location") if isinstance(v.get("location"), str) and v["location"].strip() else rec.get("world_location")
        if isinstance(place, str) and place.strip():
            t["place"] = place.strip()
            if place.strip() not in places:
                places.append(place.strip())
        if (tm := _time_of(apply)) is not None:
            t["time"] = tm
        if (b := _beat_of(rec, run_dir)) is not None:
            if t["beats"] and b.get("input") and b["input"] == t["beats"][-1].get("input"):
                del b["input"]   # the beat that settles what was just talked over: the player said it once
            t["beats"].append(b)
        ending = _ending_of(apply, n) or ending
    # the trace names a place by its node (``hall``) before the first commit and by ``<area>/<node>`` after: one id each
    full = {p.rsplit("/", 1)[-1]: p for p in places if "/" in p}
    for t in turns.values():
        if t.get("place") in full:
            t["place"] = full[t["place"]]
    places = list(dict.fromkeys(full.get(p, p) for p in places))
    return [turns[k] for k in sorted(turns) if turns[k]["beats"]], ending, places


def _from_story(path: Path) -> list[dict[str, Any]]:
    """Legacy runs: ``## T<n> · place · time`` sections, ``> input``, ``**who**: text``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    turns: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    body: list[str] = []

    def flush() -> None:
        if cur is None:
            return
        said = [ln[1:].strip() for ln in body if ln.startswith(">")]
        rest = "\n".join(ln for ln in body if not ln.startswith(">")).strip()
        lines = []
        if rest:
            m = _SPEAKER_LINE.match(rest.split("\n", 1)[0])
            if m:
                tail = rest.split("\n", 1)[1] if "\n" in rest else ""
                lines.append({"who": _text(m["who"], 80), "role": "host", "text": _text((m["text"] + ("\n" + tail if tail else "")).strip())})
            else:
                lines.append({"who": "", "role": "narrator", "text": _text(rest)})
        if lines or said:
            cur["beats"] = [{"kind": "turn", **({"input": _text(" ".join(said), 4000)} if said else {}), "lines": lines, "dice": []}]
            turns.append(cur)

    for raw in text.splitlines():
        m = _TURN_HEADING.match(raw)
        if m:
            flush()
            bits = [b.strip() for b in m.group(2).split("·") if b.strip()]
            cur, body = {"n": int(m.group(1)), "beats": []}, []
            if bits:
                cur["place"] = bits[0]
            if len(bits) > 1:
                cur["time"] = {"clock": bits[1]}
            continue
        if cur is not None and not (raw.startswith("# ") and not body):
            body.append(raw)
    flush()
    return turns


def _game_dir(run_dir: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return run_dir / get_data_dir_name(run_dir)


def _place_names(run_dir: Path, ids: list[str]) -> list[dict[str, Any]]:
    """Names from the world's ``locations/<area>/<node>/location.json`` — only the ``name`` fields are read."""
    root = _game_dir(run_dir) / "locations"
    names: dict[str, tuple[str, str]] = {}
    if root.is_dir():
        for f in root.glob("*/*/location.json"):
            try:
                node = json.loads(f.read_text(encoding="utf-8"))
                area = json.loads((f.parent.parent / "location.json").read_text(encoding="utf-8")) if (f.parent.parent / "location.json").is_file() else {}
            except (OSError, ValueError):
                continue
            nm = str(node.get("name") or "") if isinstance(node, dict) else ""
            an = str(area.get("name") or "") if isinstance(area, dict) else ""
            names[f"{f.parent.parent.name}/{f.parent.name}"] = (nm, an)
            names.setdefault(f.parent.name, (nm, an))
    out = []
    for pid in ids:
        nm, an = names.get(pid, ("", ""))
        out.append({"id": pid, "name": _text(nm, 120) or pid, **({"area": _text(an, 120)} if an else {})})
    return out


def _cast(run_dir: Path, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The player and the souls who appear — names from each soul's ``soul.json``. Lines spoken by a soul get its id."""
    souls: dict[str, str] = {}
    names: dict[str, str] = {}   # sid → the name the run's narration uses (name_local first)
    for f in sorted((run_dir / "souls").glob("*/soul.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(s, dict):
            sid = str(s.get("sid") or s.get("id") or f.parent.name.split("-si-")[0])
            for key in ("name_local", "name"):   # lines carry whichever name the narration used
                v = s.get(key)
                for name in (v.values() if isinstance(v, dict) else [v]):
                    if sid and isinstance(name, str) and name.strip():
                        souls.setdefault(name.strip(), sid)
                        names.setdefault(sid, name.strip())
    cast: list[dict[str, Any]] = []
    seen: set[str] = set()
    for t in turns:
        for b in t["beats"]:
            for sid in b.get("present") or []:
                if sid not in seen and sid in names:
                    seen.add(sid)
                    cast.append({"id": sid, "name": _text(names[sid], 80), "role": "soul"})
            for ln in b["lines"]:
                if ln["role"] == "player" and "player" not in seen and ln["who"]:
                    seen.add("player")
                    cast.append({"id": "player", "name": ln["who"], "role": "player"})
                sid = souls.get(ln["who"])
                if sid:
                    ln["cast"] = sid
                    if sid not in seen:
                        seen.add(sid)
                        cast.append({"id": sid, "name": _text(ln["who"], 80), "role": "soul"})
    return cast


def _ending_card(run_dir: Path, eid: str) -> dict[str, Any]:
    """``kind`` (and the title, when the trace had none) of an ending, from the world's ``plots/*/plot.json``."""
    for f in sorted((_game_dir(run_dir) / "plots").glob("*/plot.json")):
        try:
            e = (json.loads(f.read_text(encoding="utf-8")).get("endings") or {}).get(eid)
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(e, dict):
            return {k: _text(str(e[k]), 200) for k in ("title", "kind") if isinstance(e.get(k), str) and e[k].strip()}
    return {}


_IMG = (".webp", ".png", ".jpg", ".jpeg", ".gif")
ASSET_MAX_BYTES = 4 << 20      # one picture
ASSETS_MAX_BYTES = 24 << 20    # all of them


def _first_image(d: Path, stem: str) -> Path | None:
    for ext in _IMG:
        f = d / f"{stem}{ext}"
        if f.is_file():
            return f
    return None


def _ending_image(run_dir: Path, eid: str) -> Path | None:
    for f in sorted((_game_dir(run_dir) / "plots").glob("*/plot.json")):
        try:
            e = (json.loads(f.read_text(encoding="utf-8")).get("endings") or {}).get(eid)
        except (OSError, ValueError, AttributeError):
            continue
        rel = ((e or {}).get("assets") or {}).get("image") if isinstance(e, dict) else None
        if isinstance(rel, str) and rel and ".." not in rel:
            p = f.parent / rel
            if p.is_file() and p.suffix.lower() in _IMG:
                return p
    return None


def _member(slot: str, src: Path) -> str:
    cls, _, inst = slot.partition(":")
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in inst.replace("/", "__")) or "x"
    return f"assets/{cls}/{safe}{src.suffix.lower()}"


def _template_files(tid: str) -> dict[str, Path]:
    """slot → file of the template the run was built from (when it is on this machine / in the browser build's world
    package): a run that did not copy a picture into itself (the browser build keeps them in the template) still has it."""
    if not tid:
        return {}
    try:
        from neonrp import template as TP

        found = TP.discover()
        if tid not in found:
            return {}
        t = TP.load(found[tid])
        out: dict[str, Path] = {}
        for x in TP.asset_slots(t):
            if x.get("have") and not x.get("variant_of"):
                f = TP.slot_file(t, str(x["slot"]))   # the same file GET …/assets/file?slot= serves (bound world · soul library)
                if f is not None and Path(f).is_file() and Path(f).suffix.lower() in _IMG:
                    f = Path(f)
                    slot = str(x["slot"])
                    if x.get("cls") == "ending" and ":ending:" in slot:
                        slot = "ending:" + slot.rsplit(":ending:", 1)[1]
                    out.setdefault(slot, f)
        return out
    except Exception:  # noqa: BLE001 — no template = the run's own pictures only
        return {}


def collect_assets(run_dir: Path, doc: dict[str, Any], *, cover: bool = True) -> dict[str, Path]:
    """{member: source file} — the pictures for the places the replay visits, the characters in it and its ending: the
    run's own first, the template's slot file otherwise; ``doc["assets"]`` (slot → member) and ``doc["ending"]["image"]``
    are filled in, and without a cover of its own (``cover``) the template's card cover goes in as ``doc["cover"]``.
    Size-capped."""
    run_dir = Path(run_dir)

    want: list[tuple[str, Path | None]] = []
    for p in doc.get("places") or []:
        want.append((f"place.scene:{p['id']}", _first_image(run_dir / "assets" / "places", p["id"].replace("/", "__"))))
    for c in doc.get("cast") or []:
        if c.get("role") != "soul":
            continue
        dirs = sorted((run_dir / "souls").glob(f"{c['id']}-*/assets"))
        for name in ("portrait", "sprite"):
            want.append((f"soul.{name}:{c['id']}", next((f for d in dirs if (f := _first_image(d, name))), None)))
    e = doc.get("ending")
    if isinstance(e, dict) and e.get("id"):
        want.append((f"ending:{e['id']}", _ending_image(run_dir, str(e["id"]))))
    world = doc.get("world") or {}
    missing = not cover or any(src is None for _slot, src in want)
    tpl = _template_files(str(world.get("id") or "")) if missing and world.get("ref") else {}
    for p in doc.get("places") or []:   # a place named by its node alone (before the run's first commit): the template's <area>/<node>
        if "/" not in p["id"] and f"place.scene:{p['id']}" not in tpl:
            hit = next((k for k in tpl if k.startswith("place.scene:") and k.endswith("/" + p["id"])), None)
            if hit:
                tpl[f"place.scene:{p['id']}"] = tpl[hit]
    if not cover and "card:cover" in tpl:
        want.insert(0, ("card:cover", None))
    files: dict[str, Path] = {}
    slots: dict[str, str] = {}
    total = 0
    for slot, src in want:
        src = src or tpl.get(slot)
        if src is None:
            continue
        try:
            size = src.stat().st_size
        except OSError:
            continue
        if size > ASSET_MAX_BYTES or total + size > ASSETS_MAX_BYTES:
            continue
        m = _member(slot, src)
        files[m], slots[slot] = src, m
        total += size
    if "card:cover" in slots:
        doc["cover"] = slots["card:cover"]
    doc["assets"] = slots
    if isinstance(e, dict) and e.get("id") and f"ending:{e['id']}" in slots:
        e["image"] = slots[f"ending:{e['id']}"]
    return files


def _engine_version() -> str:
    try:
        from importlib.metadata import version

        return version("neonrp")
    except Exception:  # noqa: BLE001
        return ""


def has_content(run_dir: Path) -> bool:
    """A run is replayable when its trace or its story.md yields at least one turn past the opening."""
    run_dir = Path(run_dir)
    trace = _trace_path(run_dir)
    turns = _from_trace(trace)[0] if trace else []
    if not any(b["kind"] != "opening" for t in turns for b in t["beats"]):
        turns = _from_story(run_dir / "story.md")
    return bool(turns)


def build_replay_doc(run_dir: Path, *, world_id: str = "", world_name: str = "", world_ref: str | None = None,
                     lang: str = "", has_cover: bool = False) -> dict[str, Any]:
    run_dir = Path(run_dir)
    trace = _trace_path(run_dir)
    turns, ending, place_ids = _from_trace(trace, run_dir) if trace else ([], None, [])
    if not any(b["kind"] != "opening" for t in turns for b in t["beats"]):   # old runs: the trace has no beats
        story = _from_story(run_dir / "story.md")
        if story:
            turns, place_ids = story, []
            for t in story:
                if t.get("place") and t["place"] not in place_ids:
                    place_ids.append(t["place"])
    places = _place_names(run_dir, place_ids)
    if ending:
        ending = {**_ending_card(run_dir, ending["id"]), **{k: v for k, v in ending.items() if v not in ("", None)}}
    return {
        "format": FORMAT,
        "world": {"id": world_id, "name": world_name or world_id, **({"ref": world_ref} if world_ref else {})},
        "lang": lang,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": _engine_version(),
        "cover": "cover.png" if has_cover else None,
        "cast": _cast(run_dir, turns),
        "places": places,
        "turns": turns,
        "ending": ending,
    }


def render_story(doc: dict[str, Any]) -> str:
    """story.md for bundle readers that only know the v1.1 layout (the old Hub replay player)."""
    names = {p["id"]: p.get("name") or p["id"] for p in doc.get("places") or []}
    out = [f"# {doc.get('world', {}).get('name') or ''}".rstrip(), ""]
    for t in doc.get("turns") or []:
        bits = [f"T{t['n']}"]
        if t.get("place"):
            bits.append(names.get(t["place"], t["place"]))
        tm = t.get("time") or {}
        if tm:
            bits.append(" ".join(x for x in (f"Day{tm['day']}" if tm.get("day") is not None else "", tm.get("clock") or "") if x))
        out += [f"## {' · '.join(bits)}", ""]
        for b in t["beats"]:
            if b.get("input"):
                out += [f"> {b['input']}", ""]
            for d in b.get("dice") or []:
                out += [f"`{d['text']}`", ""]
            for ln in b["lines"]:
                out += [f"**{ln['who']}**: {ln['text']}" if ln.get("who") else ln["text"], ""]
    return "\n".join(out).rstrip() + "\n"


def turn_count(doc: dict[str, Any]) -> int:
    return sum(1 for t in doc.get("turns") or [] if any(b["kind"] != "opening" for b in t["beats"]))
