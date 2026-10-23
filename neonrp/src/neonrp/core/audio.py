"""What a world sounds like right now (10-15, niko: 「neonrp 接上音乐库」): one music channel and one ambient bed.

The engine decides; a front end only plays (效果归引擎,定制只管控制). An author may write nothing — the world still has
a theme, a mood track when things turn tense and a bed that fits the place — or steer any part of it:

    template.json  "audio": {"theme": <music>, "ambient": <bed when nothing fits the place>, "moods": {"tense": <music>, "crisis": <music>},
                             "places": {<addr>: {"ambient": …, "bgm": …}}, "credits": "assets/audio/CREDITS.md"}
    location.json  "audio": {"ambient": …, "bgm": …}               a place; places inside it inherit
    plot.json      "stages": [{"name", "goal", "audio": {"mood", "bgm", "ambient"}}]   while that stage is current
    triggers       {"to": "audio", "mood": "crisis", "bgm"?: …, "ambient"?: …}         from that beat on

A value is a pool id (``worldlines/audio/catalog.json``: ``tense``, ``guixiang``, ``harbor-waves`` …), a file inside the
template (``assets/audio/x.mp3``), ``silence`` (no music: the theme rests too) / ``none`` (no bed), or ``default``
(as if not written).

Mood: ``calm`` plays the theme (or the place's / stage's own track); ``tense`` / ``crisis`` play the mood tracks. The
engine reads it off what landed — a crisis mode layer (combat), the player's hp low → crisis; hp / sanity lost this beat,
the plot's last stage → tense — and holds a raised mood a couple of beats before it comes down. An author's mood (a
stage's, a trigger's) is the floor the events raise from.

Out: ``after_apply`` → the ``audio.cue`` beat event when what plays changed; ``current`` → the same shape for a page that
opens mid-run (``GET /api/v1/play/engine/audio``). URLs carry the file's content hash, so they cache for a year.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

MOODS = ("calm", "tense", "crisis")
SILENCE, NONE, DEFAULT = "silence", "none", "default"
HOLD_BEATS = 2  # a mood an event raised stays this many beats before it comes down
FADE_MS = {"calm": 2500, "tense": 1800, "crisis": 800}
CRISIS_MODES = ("combat", "battle", "fight", "chase")
LOW_HP = 0.3
STATE_FILE = "audio.json"
AUDIO_EXTS = (".mp3", ".ogg", ".m4a", ".wav")
MAX_BYTES = 4 * 1024 * 1024  # lint warns above this (a phone downloads it)

_CAT: dict[str, Any] = {}
_HASH: dict[tuple[str, int, int], str] = {}


# ── the pool ─────────────────────────────────────────────────────────────────

def pool_dir() -> Path | None:
    """``NEONRP_AUDIO_DIR``; the repo's ``worldlines/audio`` (dev · the public layout); an installed WorldLines shell's."""
    env = os.environ.get("NEONRP_AUDIO_DIR", "").strip()
    if env:
        p = Path(env).expanduser()
        return p if (p / "catalog.json").is_file() else None
    repo = Path(__file__).resolve().parents[3]
    for d in (repo / "worldlines" / "audio", repo.parent / "worldlines" / "audio"):
        if (d / "catalog.json").is_file():
            return d
    from neonrp.core.paths import shell_dir

    d = shell_dir("audio")
    return d if d is not None and (d / "catalog.json").is_file() else None


def catalog() -> dict[str, Any]:
    """The pool's catalog (``{tracks: [...], defaults: {...}}``); empty when no pool is installed."""
    d = pool_dir()
    if d is None:
        return {"tracks": [], "defaults": {}}
    p = d / "catalog.json"
    key = f"{p}|{p.stat().st_mtime_ns}"
    if _CAT.get("key") != key:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _CAT.clear()
        _CAT.update(key=key, data=data if isinstance(data, dict) else {})
    return _CAT["data"]


def track(tid: str, kind: str | None = None) -> dict[str, Any] | None:
    for t in catalog().get("tracks") or []:
        if t.get("id") == tid and (kind is None or t.get("kind") == kind):
            return t
    return None


def file_hash(p: Path) -> str:
    st = p.stat()
    k = (str(p), st.st_mtime_ns, st.st_size)
    if k not in _HASH:
        _HASH[k] = hashlib.sha256(p.read_bytes()).hexdigest()[:10]
    return _HASH[k]


def hashed_name(rel: str, h: str) -> str:
    """``music/guixiang.mp3`` + hash → ``music/guixiang.<h>.mp3`` (the browser build names its static copies the same)."""
    stem, dot, ext = rel.rpartition(".")
    return f"{stem}.{h}.{ext}" if dot else f"{rel}.{h}"


def pool_url(t: dict[str, Any]) -> str:
    return "/api/v1/audio/" + hashed_name(str(t["file"]), str(t.get("sha") or "0"))


def pool_file(name: str) -> tuple[Path | None, bool]:
    """A pool request path (hashed or not) → (file, whether the hash in the name is the file's). Never leaves the pool."""
    d = pool_dir()
    if d is None or ".." in name.split("/"):
        return None, False
    parts = name.rsplit(".", 2)
    rel, h = (f"{parts[0]}.{parts[2]}", parts[1]) if len(parts) == 3 else (name, "")
    t = next((x for x in catalog().get("tracks") or [] if x.get("file") == rel), None)
    if t is None:
        return None, False
    p = (d / rel).resolve()
    if not p.is_file() or not p.is_relative_to(d.resolve()):
        return None, False
    return p, bool(h) and h == t.get("sha")


def credits() -> list[dict[str, Any]]:
    """Every pool track with its attribution, CC-BY first (those must be shown) — 菜单 → 声音 → 音乐鸣谢."""
    rows = [{k: t.get(k) for k in ("id", "kind", "title", "artist", "license", "source")} for t in catalog().get("tracks") or []
            if t.get("kind") in ("music", "ambient")]
    return sorted(rows, key=lambda r: (not str(r.get("license") or "").startswith("CC-BY"), r.get("kind") != "music"))


# ── the run's template ───────────────────────────────────────────────────────

def _j(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _meta(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(Path(root)) / "meta"


def _template(root: Path) -> tuple[str, Path | None, dict[str, Any], str]:
    """(template id, its folder, its ``audio``, its play contract) for this run; the folder may be gone (then pool ids only)."""
    rec = _j(_meta(root) / "template.json", {}) or {}
    tid = str(rec.get("id") or "")
    tdir: Path | None = None
    src = rec.get("source")
    if isinstance(src, str) and (Path(src) / "template.json").is_file():
        tdir = Path(src)
    elif tid:
        try:
            from neonrp.template import discover

            tdir = discover().get(tid)
        except Exception:  # noqa: BLE001
            tdir = None
    cfg = rec.get("audio") if isinstance(rec.get("audio"), dict) else None
    if cfg is None and tdir is not None:
        cfg = (_j(tdir / "template.json", {}) or {}).get("audio")
    contract = str(rec.get("play_contract") or "").split("@", 1)[0]
    return tid, tdir, cfg if isinstance(cfg, dict) else {}, contract


def resolve(ref: Any, kind: str, tid: str = "", tdir: Path | None = None) -> dict[str, Any] | None:
    """One written value → ``{id, url, title?}``, ``{"quiet": True}`` (silence / none), or None (not written / unknown /
    missing: the next default applies). ``kind`` = music | ambient."""
    if not isinstance(ref, str) or not ref.strip() or ref.strip() == DEFAULT:
        return None
    v = ref.strip()
    if v in (SILENCE, NONE):
        return {"quiet": True}
    if v.startswith("assets/"):
        if tdir is None or ".." in v.split("/") or not v.lower().endswith(AUDIO_EXTS):
            return None
        p = tdir / v
        if not p.is_file():
            return None
        return {"id": v, "url": f"/api/v1/local/templates/{quote(tid)}/audio?path={quote(v)}&h={file_hash(p)}"}
    t = track(v, kind)
    if t is None:
        return None
    return {"id": v, "url": pool_url(t), "title": t.get("title")}


def check_ref(ref: Any, kind: str, tdir: Path | None) -> str | None:
    """Lint: what is wrong with one written value (None = fine). ``tdir`` None = a template file cannot be looked at here."""
    if ref is None:
        return None
    if not isinstance(ref, str) or not ref.strip():
        return "must be a pool id, assets/… or silence / none / default"
    v = ref.strip()
    if v in (SILENCE, NONE, DEFAULT):
        return None
    if v.startswith("assets/"):
        if ".." in v.split("/"):
            return f"{v}: must stay inside the template"
        if not v.lower().endswith(AUDIO_EXTS):
            return f"{v}: audio must be one of {', '.join(AUDIO_EXTS)}"
        if tdir is not None and not (tdir / v).is_file():
            return f"{v}: file not found"
        return None
    if "/" in v:
        return f"{v}: a pool id has no '/'; a template file starts with assets/"
    if not catalog().get("tracks"):
        return None  # no pool installed here: ids cannot be checked
    if track(v, kind) is None:
        ids = sorted(str(t["id"]) for t in catalog().get("tracks") or [] if t.get("kind") == kind)
        return f"{v}: no {kind} track of that id (pool: {', '.join(ids)})"
    return None


# ── places ───────────────────────────────────────────────────────────────────

def _chain(root: Path, addr: str | None) -> list[dict[str, Any]]:
    """The player's place and every place above it (nearest first), each ``{addr, name, kind, audio}``."""
    if not addr:
        return []
    from neonrp.core import worldmap as M
    from neonrp.core.paths import get_data_dir_name

    try:
        nodes = M.build_map_tree(Path(root))["nodes"]
    except Exception:  # noqa: BLE001 — a world without a map still has folders
        nodes = {}
    locs = Path(root) / get_data_dir_name(Path(root)) / "locations"
    out: list[dict[str, Any]] = []
    a: str | None = addr
    while a and a != M.ROOT and a not in {n["addr"] for n in out}:
        n = nodes.get(a) or {}
        lj = _j(locs / a / "location.json", {}) or {}
        au = lj.get("audio") if isinstance(lj, dict) and isinstance(lj.get("audio"), dict) else {}
        out.append({"addr": a, "name": str(n.get("name") or lj.get("name") or ""), "kind": str(n.get("kind") or lj.get("type") or ""),
                    "audio": au})
        a = n.get("parent") if n else (a.rsplit("/", 1)[0] if "/" in a else None)
    return out


def _guess_ambient(chain: list[dict[str, Any]]) -> str | None:
    """A bed for a place nobody gave one: the longest pool keyword in its name, else its id, else its kind — else the
    same for the place it is in. The keywords are the catalog's (data), never the engine's."""
    import re

    beds = [t for t in catalog().get("tracks") or [] if t.get("kind") == "ambient" and t.get("keywords")]

    def hit(k: str, text: str) -> bool:  # a latin keyword is a whole word (「seated」 is not 「sea」); CJK is a substring
        return bool(re.search(rf"\b{re.escape(k)}\b", text)) if k.isascii() else k in text

    for n in chain:
        for text in (n["name"], n["addr"].rsplit("/", 1)[-1].replace("_", " "), n["kind"]):
            text = text.lower()
            best = max(((len(str(k)), str(t["id"])) for t in beds for k in t["keywords"] if text and hit(str(k).lower(), text)), default=None)
            if best:
                return best[1]
    return None


# ── state ────────────────────────────────────────────────────────────────────

def _state(root: Path) -> dict[str, Any]:
    s = _j(_meta(root) / STATE_FILE, {}) or {}
    return s if isinstance(s, dict) else {}


def _save(root: Path, s: dict[str, Any]) -> None:
    p = _meta(root) / STATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def set_author(root: Path, e: dict[str, Any], *, turn: int, by: str) -> dict[str, Any]:
    """A trigger's ``{"to": "audio", …}``: what it says holds from this beat on (``default`` clears that part)."""
    s = _state(root)
    a = dict(s.get("author") or {})
    for k in ("mood", "bgm", "ambient"):
        if k in e:
            v = e[k]
            if v in (None, DEFAULT):
                a.pop(k, None)
            elif k != "mood" or v in MOODS:
                a[k] = v
    a.update(turn=turn, by=by)
    s["author"] = a
    _save(root, s)
    return {"to": "audio", **{k: a[k] for k in ("mood", "bgm", "ambient") if k in a}}


def _stage_audio(root: Path, variables: dict[str, Any]) -> dict[str, Any]:
    """The current stage's ``audio`` of every staged plot (the last plot that says something wins)."""
    out: dict[str, Any] = {}
    meta = _meta(root)
    for _pid, info in (_j(meta / "plots.json", {}) or {}).items():
        var = (info or {}).get("stage_var")
        if not var:
            continue
        pj = _j(Path(root) / str((info or {}).get("dir") or "") / "plot.json", {}) or {}
        stages = pj.get("stages") or []
        n = variables.get(var)
        if isinstance(n, int) and not isinstance(n, bool) and 0 <= n < len(stages):
            st = stages[n]
            if isinstance(st, dict) and isinstance(st.get("audio"), dict):
                out.update({k: v for k, v in st["audio"].items() if k in ("mood", "bgm", "ambient")})
            if n == len(stages) - 1 and len(stages) > 1:
                out.setdefault("_last", True)
    return out


def _hp_low(reg: Any) -> bool:
    v = reg.variables.get("player.hp") if reg is not None else None
    if v is None or not isinstance(v.value, (int, float)):
        return False
    mx = v.max
    if mx is None:
        pl = reg.entries.get("player")
        mx = pl.props.get("max_hp") if pl is not None else None
    if not mx and v.max_key:
        cur: Any = _j(Path(reg.root) / v.path, {})
        for k in v.max_key.split("."):
            cur = cur.get(k) if isinstance(cur, dict) else None
        mx = cur
    return isinstance(mx, (int, float)) and mx > 0 and v.value <= LOW_HP * mx


def _event_mood(root: Path, reg: Any, res: Any) -> str | None:
    """What this beat says about the mood, from what landed (None = nothing)."""
    from neonrp.core.modes import read_mode

    m = read_mode(Path(root)) or {}
    if str(m.get("name") or "") in CRISIS_MODES or _hp_low(reg):
        return "crisis"
    for a in getattr(res, "applied", None) or []:
        if not isinstance(a, dict) or a.get("var") not in ("player.hp", "player.san"):
            continue
        f, t = a.get("from"), a.get("to")
        if isinstance(f, (int, float)) and isinstance(t, (int, float)) and t < f:
            return "tense"
    return None


def _rank(m: str | None) -> int:
    return MOODS.index(m) if m in MOODS else 0


def compute(root: Path, reg: Any = None, res: Any = None, *, turn: int | None = None, save: bool = False) -> dict[str, Any]:
    """The cue for now. With ``res`` (an apply) the beat's events raise the mood and the hold is advanced."""
    root = Path(root)
    if reg is None:
        from neonrp.core.registry import load_registry

        reg = load_registry(root)
    tid, tdir, cfg, contract = _template(root)
    defaults = catalog().get("defaults") or {}
    s = _state(root)
    author = s.get("author") or {}
    variables = {k: v.value for k, v in reg.variables.items()}
    stage = _stage_audio(root, variables)
    chain = _chain(root, reg.player_location)
    places = cfg.get("places") if isinstance(cfg.get("places"), dict) else {}
    for n in chain:  # the template's per-place lines fill what location.json left out
        over = places.get(n["addr"])
        if isinstance(over, dict):
            n["audio"] = {**over, **n["audio"]}

    # mood: the author's floor (trigger > stage), raised by this beat's events, held a little
    floor = author.get("mood") or stage.get("mood") or ("tense" if stage.get("_last") else "calm")
    hold = s.get("hold") or {}
    now = turn if turn is not None else int(getattr(res, "turn", 0) or 0)
    ev = _event_mood(root, reg, res) if res is not None else None
    if ev and _rank(ev) >= _rank(hold.get("mood")):
        hold = {"mood": ev, "until": now + HOLD_BEATS}
    elif res is not None and hold and now > int(hold.get("until") or 0):
        hold = {}
    held = hold.get("mood") if hold else None
    raised = _rank(held) > _rank(floor)
    mood = held if raised else floor
    by = "mood" if raised else "trigger" if author.get("mood") else "stage" if stage.get("mood") or stage.get("_last") else "default"

    # music: calm = the trigger's / stage's / place's own track, else the theme (the template's, else its contract's);
    # tense / crisis = the mood tracks. `silence` from any of them rests the music altogether.
    place_bgm = next((n["audio"]["bgm"] for n in chain if n["audio"].get("bgm") not in (None, DEFAULT)), None)
    own = [(author.get("bgm"), "trigger"), (stage.get("bgm"), "stage"), (place_bgm, "place")]
    pick: dict[str, Any] | None = None
    if any(r == SILENCE for r, _ in own):
        pick = {"quiet": True}
    elif mood == "calm":
        for ref, src in [*own, (cfg.get("theme"), "")]:
            pick = resolve(ref, "music", tid, tdir)
            if pick is not None:
                by = src if src and by == "default" else by
                break
        if pick is None:
            theme_map = defaults.get("theme_by_contract") or {}
            pick = resolve(theme_map.get(contract) or theme_map.get("*") or "calm", "music", tid, tdir)
    else:
        moods = cfg.get("moods") if isinstance(cfg.get("moods"), dict) else {}
        pick = resolve(moods.get(mood), "music", tid, tdir) or resolve((defaults.get("moods") or {}).get(mood) or mood, "music", tid, tdir)
    music = None if pick is None or pick.get("quiet") else {**pick, "mood": mood}

    # ambient: trigger > stage > the place (and above) > a guess from the place's name > the world's
    amb = None
    for ref in (author.get("ambient"), stage.get("ambient"), *(n["audio"].get("ambient") for n in chain), _guess_ambient(chain), cfg.get("ambient")):
        amb = resolve(ref, "ambient", tid, tdir)
        if amb is not None:
            break
    ambient = None if amb is None or amb.get("quiet") else amb

    cue = {"music": music, "ambient": ambient, "mood": mood, "by": by, "fade_ms": FADE_MS.get(mood, 2000),
           "place": chain[0]["addr"] if chain else None}
    if save:
        s["hold"] = hold
        s["last"] = _key(cue)
        _save(root, s)
    return cue


def _key(cue: dict[str, Any]) -> list[Any]:
    return [(cue.get("music") or {}).get("url"), (cue.get("ambient") or {}).get("url")]


def after_apply(root: Path, reg: Any, res: Any) -> dict[str, Any] | None:
    """After a beat landed: the cue when what plays changed (→ the ``audio.cue`` event), else None."""
    if pool_dir() is None and not (_template(Path(root))[2]):
        return None
    before = _state(Path(root)).get("last")
    cue = compute(root, reg, res, save=True)
    return {"turn": getattr(res, "turn", None), **cue} if _key(cue) != before else None


def current(root: Path) -> dict[str, Any]:
    """The cue as it stands (a page opening mid-run) + the credits the screen shows."""
    tid, tdir, cfg, _c = _template(Path(root))
    out = compute(root)
    out["credits"] = credits()
    cr = cfg.get("credits")
    if isinstance(cr, str) and tdir is not None and cr.startswith("assets/") and (tdir / cr).is_file():
        out["template_credits"] = (tdir / cr).read_text(encoding="utf-8")[:4000]
    return out
