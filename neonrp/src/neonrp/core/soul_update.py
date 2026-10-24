"""A taken character when its author ships a new version (10-20): the
player sees a diff and chooses, item by item, 「keep mine」 or 「use the author's」. Nothing follows the author on its
own — not the settings, not the memory; until the player decides, the character stays as it is (the Hub only says
「the author updated」).

    GET  /api/v1/local/player-data/souls/<world>/<sid>/update[?lang=]   → the diff (worldlines.soul-update/1)
    POST /api/v1/local/player-data/souls/<world>/<sid>/update {token, choices: {<item id>: mine | theirs}} | {token, all}
    GET  /api/v1/local/player-data/souls/<world>/<sid>/updates           → the saved decisions
    GET  /api/v1/local/player-data/souls/<world>/<sid>/file?f=&side=mine|theirs   a file of either side (previews)

Only the character's own folder takes part: what the run keeps in the world (``game/states``, where she stands, the
party, the world's things she holds, plot flags) never travels with her and is never in a diff.

The snapshot (core/soul_chat.snapshot_dir) is the player's character — read and written by everything; the author's
version is only compared with. Beside it, ``.wl/``::

    snapshot.json     {schema, world, sid, lang, source, accepted_at, accepted_version, author_version, author_files
                       {rel: sha256} | null (not known), globs, updates: [...], migrated}
    accepted/         the whole folder as it was right after the last decision (or the take) — the player's base
    author/           the author's version at that moment (text files; binary ones only by hash) — the author's base
    updates/NNNN-<from>-to-<to>.json   each diff with the player's choices
    orchestration.json   the character's effective graph at the last decision (used when the author's is gone)

An item appears only where the author changed something (author's now vs ``author/``). Its default: the player did
not change it since the last decision (snapshot vs ``accepted/``) → the author's; both changed, or the player kept
theirs there last time → mine; already the same → not shown. A portrait (``assets/**``) defaults to the author's.
JSON splits into fields (lists of objects with an id — ``id`` · ``item_id`` · ``sid`` · ``qid`` — into one item per
id, other lists whole); ``.md`` / ``.txt`` into entries (top-level list items, and each ``## `` section's other text
as one entry); anything else is one item per file.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

SCHEMA = "worldlines.soul-snapshot/1"
DIFF_SCHEMA = "worldlines.soul-update/1"
WL = ".wl"
DEFAULT_GLOBS = ("run_state.json", "trajectory/**", "short-term-memo/**", "long-term-memo/**", "character/**")
ID_KEYS = ("id", "item_id", "sid", "qid")
BINARY = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".wav", ".ogg", ".mp4", ".webm")
TEXT = (".md", ".txt")
PAIR_RATIO = 0.6
# read from where it comes from, never part of a diff: the character's graph (core/soul_chat.graph_of) and the
# engine's own bookkeeping
SKIP = ("agents/orchestration.json",)
_AUTHOR: dict[tuple[str, str, str], tuple[str, Path | None]] = {}


class UpdateError(Exception):
    def __init__(self, status: int, code: str, msg: str = ""):
        super().__init__(msg or code)
        self.status, self.code = status, code


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Missing)

    def __hash__(self) -> int:
        return 0


MISSING = _Missing()


# ── files ────────────────────────────────────────────────────────────────────

def _sha(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _files(d: Path | None) -> dict[str, bytes]:
    """rel → bytes of a character folder (the engine's own dotted folders and SKIP left out)."""
    out: dict[str, bytes] = {}
    if d is None or not d.is_dir():
        return out
    for f in sorted(d.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(d).as_posix()
        if any(p.startswith(".") for p in rel.split("/")) or rel in SKIP:
            continue
        try:
            out[rel] = f.read_bytes()
        except OSError:
            continue
    return out


def _binary(rel: str, b: bytes | None = None) -> bool:
    if rel.lower().endswith(BINARY):
        return True
    if b is None:
        return False
    try:
        b.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _globs(folder: Path) -> tuple[str, ...]:
    try:
        man = json.loads((folder / "agents" / "manifest.json").read_text(encoding="utf-8"))
        g = next((a.get("write_globs") for a in man.get("agents") or [] if isinstance(a, dict) and a.get("role") == "soul"), None)
        if isinstance(g, list) and g:
            return tuple(str(x) for x in g)
    except (OSError, ValueError, AttributeError):
        pass
    return DEFAULT_GLOBS


def _matches(rel: str, globs: tuple[str, ...]) -> bool:
    from fnmatch import fnmatch

    return any(rel == g or (g.endswith("/**") and rel.startswith(g[:-2])) or fnmatch(rel, g) for g in globs)


def category(rel: str, globs: tuple[str, ...]) -> str:
    """settings (the author's: not in the soul's write_globs) · memory (memos, trajectory) · state (the rest it writes)."""
    if not _matches(rel, globs):
        return "settings"
    top = rel.split("/", 1)[0]
    return "memory" if top.endswith("-memo") or top == "trajectory" else "state"


# ── where things are ─────────────────────────────────────────────────────────

def snap_dir(world: str, sid: str) -> Path:
    from neonrp.core import soul_chat

    return soul_chat.snapshot_dir(world, sid)


def _wl(world: str, sid: str) -> Path:
    return snap_dir(world, sid) / WL


def _meta(world: str, sid: str) -> dict[str, Any]:
    try:
        d = json.loads((_wl(world, sid) / "snapshot.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_meta(world: str, sid: str, m: dict[str, Any]) -> None:
    p = _wl(world, sid) / "snapshot.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fingerprint(d: Path) -> str:
    h = hashlib.sha1()
    for f in sorted(d.rglob("*")):
        if f.is_file():
            try:
                st = f.stat()
            except OSError:
                continue
            h.update(f"{f.relative_to(d).as_posix()}|{st.st_mtime_ns}|{st.st_size}\n".encode())
    return h.hexdigest()[:16]


def _template(world: str) -> Any:
    from neonrp.core import rewards

    return rewards.store_template(world)


def author_dir(world: str, sid: str, lang: str) -> Path | None:
    """The author's version of this character as a run built today in ``lang`` would have it (the template store's,
    every layer the build lays — the world's souls, a builtin world's overlay, the language layer, the prompt layer);
    a plot NPC = what its plot entry says. None when the template or the character is gone. Cached on the template's
    files."""
    t = _template(world)
    if t is None:
        return None
    from neonrp import template as TP

    dirs = [Path(t.dir)] + ([TP.world_dir(t)] if TP.world_dir(t) is not None else [])
    fp = "-".join(_fingerprint(d) for d in dirs if d is not None and d.is_dir())
    key = (world, sid, lang)
    hit = _AUTHOR.get(key)
    if hit is not None and hit[0] == fp and (hit[1] is None or hit[1].is_dir()):
        return hit[1]
    out: Path | None = None
    if hit is not None and hit[1] is not None:  # the author's version moved on: the old build goes
        shutil.rmtree(_build_root(hit[1]), ignore_errors=True)
    root = Path(tempfile.mkdtemp(prefix="wl-soul-author-"))
    try:
        TP.build(t, root / "run", lang=lang)
        from neonrp.core import player_data

        souls = player_data.run_souls(root / "run")
        s = next((x for x in souls.values() if x["sid"] == sid), None)
        if s is not None and s.get("dir"):
            out = Path(s["dir"])
        elif s is not None:  # a plot NPC: what the phone's folder for it is made from (core/soul_chat.npc_dir)
            out = root / "npc" / sid
            out.mkdir(parents=True)
            body = "\n\n".join(x for x in (f"# {s['name']}", s.get("persona") or "", s.get("appearance") or "") if x).strip() + "\n"
            (out / "soul.md").write_text(body, encoding="utf-8")
            (out / "soul.json").write_text(json.dumps({"sid": sid, "name": s["name"], "name_local": s["name"], "source_lang": lang},
                                                      ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001 — a template that does not build has no comparable version
        out = None
    if out is None:
        shutil.rmtree(root, ignore_errors=True)
    if out is not None:
        _portrait_into(out, t, sid)
    _AUTHOR[key] = (fp, out)
    return out


def _build_root(p: Path) -> Path:
    """The scratch folder an author's version was built in (``wl-soul-author-*``)."""
    for q in [p, *p.parents]:
        if q.name.startswith("wl-soul-author-"):
            return q
    return p


def clear_cache() -> None:
    """Drop every author's version built in this process (and their scratch folders)."""
    for _, (_, d) in list(_AUTHOR.items()):
        if d is not None:
            shutil.rmtree(_build_root(d), ignore_errors=True)
    _AUTHOR.clear()


import atexit  # noqa: E402

atexit.register(lambda: clear_cache())


def portrait(folder: Path) -> Path | None:
    """The character's own portrait in a folder (``assets/portrait.<ext>``), or None."""
    d = folder / "assets"
    return next((d / f"portrait{e}" for e in (".webp", ".png", ".jpg", ".jpeg") if (d / f"portrait{e}").is_file()), None)


def _portrait_into(folder: Path, t: Any, sid: str) -> None:
    """Most templates keep a character's portrait as a template slot (``soul.portrait:<sid>``), not in its folder: a
    copy goes into ``assets/portrait.<ext>`` so the character carries its picture (and an author's new picture shows in
    the diff). A folder that has its own keeps it."""
    if portrait(folder) is not None or t is None:
        return
    try:
        from neonrp import template as TP

        f = TP.slot_file(t, f"soul.portrait:{sid}")
    except Exception:  # noqa: BLE001
        f = None
    if f is not None and Path(f).is_file():
        (folder / "assets").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, folder / "assets" / f"portrait{Path(f).suffix.lower()}")


# ── the snapshot's side ──────────────────────────────────────────────────────

def _copy_tree(src: Path, dst: Path, *, skip_wl: bool = True) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if skip_wl and rel.parts and rel.parts[0] == WL:
            continue
        if f.is_dir():
            (dst / rel).mkdir(parents=True, exist_ok=True)
        elif f.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / rel)


def _write_author(world: str, sid: str, files: dict[str, bytes]) -> dict[str, str]:
    """``.wl/author/``: the author's text files as they are; binary ones only by their hash (in snapshot.json)."""
    d = _wl(world, sid) / "author"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for rel, b in files.items():
        if not _binary(rel, b):
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_bytes(b)
    return {rel: _sha(b) for rel, b in files.items()}


def _save_graph(world: str, sid: str, folder: Path | None) -> None:
    """The character's effective graph (its folder's · the template's override), kept for when the author's is gone."""
    t = _template(world)
    if folder is None or t is None:
        return
    try:
        from neonrp.core import soul_orchestration as SO

        g = SO.graph(folder, Path(t.dir), sid)
        (_wl(world, sid) / "orchestration.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def on_take(root: Path, world: str, sid: str, *, source: str = "template") -> None:
    """A character was just taken home (core/player_data._snapshot): the snapshot is the player's base, the author's
    version of today the author's base (one build of the template per language, cached)."""
    from neonrp.core import player_data

    snap = snap_dir(world, sid)
    if not (snap / "soul.json").is_file():
        return
    try:
        rec = json.loads((Path(root) / _data_dir(root) / "meta" / "template.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = {}
    lang = str(((rec.get("i18n") or {}) if isinstance(rec, dict) else {}).get("lang") or (rec.get("card") or {}).get("lang") or "zh")
    _portrait_into(snap, _template(world), sid)
    _copy_tree(snap, _wl(world, sid) / "accepted")
    _save_meta(world, sid, {"schema": SCHEMA, "world": world, "sid": sid, "lang": lang, "source": source, "accepted_at": _now(),
                            "accepted_version": player_data.version_of(root), "author_version": player_data.version_of(root),
                            "author_files": None, "pending_base": True, "globs": list(_globs(snap)), "updates": [], "migrated": None})
    ensure(world, sid)  # the author's base now (what the author has today), so a later change of the author's shows


def _data_dir(root: Path) -> str:
    from neonrp.core.paths import get_data_dir_name

    return get_data_dir_name(root)


def _record(world: str, sid: str) -> dict[str, Any] | None:
    from neonrp.core import player_data

    return next((c for c in player_data.read()["characters"] if c.get("world") == world and c.get("sid") == sid), None)


def _guess_lang(world: str, sid: str, snap: Path) -> str:
    """An old snapshot does not say which language it was taken in: the language whose author version matches it best."""
    t = _template(world)
    if t is None:
        return "zh"
    from neonrp.template import i18n

    langs = sorted({str(t.card.get("lang") or "zh"), *i18n.layers(t)})
    mine = _files(snap)
    best, score = langs[0], -1
    for lg in langs:
        a = _files(author_dir(world, sid, lg))
        n = sum(1 for rel, b in a.items() if mine.get(rel) == b)
        if n > score:
            best, score = lg, n
    return best


def ensure(world: str, sid: str) -> dict[str, Any] | None:
    """The snapshot's ``.wl/`` in shape: an old snapshot (no ``.wl/``) is migrated; a fresh take gets its author's base.
    None when there is no snapshot. Idempotent; the player's files are never changed here."""
    snap = snap_dir(world, sid)
    if not (snap / "soul.json").is_file():
        return None
    m = _meta(world, sid)
    rec = _record(world, sid) or {}
    t = _template(world)
    if not m:  # 9ce2d8a3 … 69722ada snapshots: the folder only
        lang = _guess_lang(world, sid, snap)
        _copy_tree(snap, _wl(world, sid) / "accepted")
        m = {"schema": SCHEMA, "world": world, "sid": sid, "lang": lang, "source": "npc" if rec.get("npc") else "template",
             "accepted_at": _now(), "accepted_version": str(rec.get("version") or ""), "author_version": str(rec.get("version") or ""),
             "author_files": None, "pending_base": True, "globs": list(_globs(snap)), "updates": [], "migrated": "pending"}
        if not (snap / "assets").is_dir() or not any((snap / "assets").iterdir()):  # never had the pictures: take the author's
            a = author_dir(world, sid, lang)
            if a is not None and (a / "assets").is_dir():
                _copy_tree(a / "assets", snap / "assets", skip_wl=False)
                _copy_tree(snap, _wl(world, sid) / "accepted")
    if m.get("pending_base") and t is not None:
        a = author_dir(world, sid, m.get("lang") or "zh")
        if a is not None:
            exact = str(m.get("accepted_version") or "") == str(t.version or "")
            if exact:
                m["author_files"] = _write_author(world, sid, _files(a))
                m["author_version"] = str(t.version or "")
            m["pending_base"] = False
            if m.get("migrated") == "pending":
                m["migrated"] = "exact" if exact else "no_base"
            _save_graph(world, sid, a)
    _save_meta(world, sid, m)
    return m


# ── entries of a text file ───────────────────────────────────────────────────

_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s")
_H2 = re.compile(r"^##\s")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = "\n".join(_ITEM.sub("", ln.strip(), count=1) for ln in t.splitlines())
    t = "".join(ch for ch in t if not unicodedata.category(ch).startswith("P"))  # punctuation does not make another entry
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower()


def _blocks(text: str) -> list[dict[str, Any]]:
    """The file as blocks in order: {kind: heading | item | body, section, raw}."""
    out: list[dict[str, Any]] = []
    section = ""
    cur: dict[str, Any] | None = None
    for ln in text.splitlines(keepends=True):
        if _H2.match(ln):
            section = ln[3:].strip()
            out.append({"kind": "heading", "section": section, "raw": ln})
            cur = None
            continue
        if _ITEM.match(ln):
            cur = {"kind": "item", "section": section, "raw": ln}
            out.append(cur)
            continue
        if cur is not None and cur["kind"] == "item" and ln.strip() and (ln[:1] in (" ", "\t") or not _ITEM.match(ln)):
            cur["raw"] += ln
            continue
        if cur is None or cur["kind"] != "body":
            cur = {"kind": "body", "section": section, "raw": ""}
            out.append(cur)
        cur["raw"] += ln
        if not ln.strip():
            pass
    return out


def entries(text: str) -> list[dict[str, Any]]:
    """The entries of a text file (10-20): each top-level list item; each ``## `` section's other text as one."""
    blocks = _blocks(text)
    out: list[dict[str, Any]] = []
    bodies: dict[str, list[str]] = {}
    for b in blocks:
        if b["kind"] == "item":
            out.append({"section": b["section"], "kind": "item", "text": b["raw"].strip()})
        elif b["kind"] == "body" and b["raw"].strip():
            bodies.setdefault(b["section"], []).append(b["raw"].strip())
    for sec, parts in bodies.items():
        out.append({"section": sec, "kind": "body", "text": "\n\n".join(parts)})
    for e in out:
        e["key"] = hashlib.sha1(f"{e['section']}\n{_norm(e['text'])}".encode()).hexdigest()[:16]
    return out


def _by_key(es: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in es:
        out.setdefault(e["key"], e)
    return out


# ── the diff ─────────────────────────────────────────────────────────────────

def _jload(b: bytes | None) -> Any:
    if b is None:
        return MISSING
    try:
        return json.loads(b.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise


def _sub(v: Any, k: Any) -> Any:
    if isinstance(k, dict):
        (name, val), = k.items()
        if isinstance(v, list):
            return next((x for x in v if isinstance(x, dict) and x.get(name) == val), MISSING)
        return MISSING
    return v.get(k, MISSING) if isinstance(v, dict) else MISSING


def _id_key(*lists: Any) -> str | None:
    """The id field all elements of these lists (the present ones) share, or None."""
    vals = [x for lst in lists if isinstance(lst, list) for x in lst]
    if not vals or not all(isinstance(x, dict) for x in vals):
        return None
    return next((k for k in ID_KEYS if all(x.get(k) not in (None, "") for x in vals)), None)


def _jpaths(a0: Any, a1: Any, path: list[Any]) -> list[tuple[list[Any], str, Any]]:
    """Where the author's version changed: [(path, unit, after-anchor)]. unit: field | list_item | list."""
    if a0 == a1:
        return []
    if isinstance(a0, dict) and isinstance(a1, dict):
        out = []
        for k in list(a0) + [k for k in a1 if k not in a0]:
            out += _jpaths(a0.get(k, MISSING), a1.get(k, MISSING), path + [k])
        return out
    if isinstance(a0, list) and isinstance(a1, list):
        key = _id_key(a0, a1)
        if key is not None:
            out = []
            ids1 = [x[key] for x in a1]
            for v in [x[key] for x in a0] + [i for i in ids1 if i not in [x[key] for x in a0]]:
                e0, e1 = _sub(a0, {key: v}), _sub(a1, {key: v})
                if e0 != e1:
                    after = None
                    if v in ids1 and ids1.index(v) > 0:
                        after = {key: ids1[ids1.index(v) - 1]}
                    out.append((path + [{key: v}], "list_item", after))
            return out
        return [(path, "list", None)]
    return [(path, "field", None)]


def _get(v: Any, path: list[Any]) -> Any:
    for k in path:
        v = _sub(v, k)
        if v is MISSING or isinstance(v, _Missing):
            return MISSING
    return v


def _jsonable(v: Any) -> Any:
    return None if isinstance(v, _Missing) else v


def _iid(*parts: Any) -> str:
    return "i_" + hashlib.sha1(json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _labels(lang: str) -> dict[str, Any]:
    from neonrp import prompts

    try:
        return prompts.strings("soul_update", lang) or {}
    except Exception:  # noqa: BLE001
        return {}


def human_key(k: str) -> str:
    """A field key no label table names, made readable: ``personality_type`` → ``Personality type``."""
    t = re.sub(r"[_\-]+", " ", str(k)).strip()
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)
    return t[:1].upper() + t[1:].lower() if t else str(k)


def _label(rel: str, path: list[Any] | None, where: str | None, L: dict[str, Any]) -> str:
    """The item's name for the player: the file's (four languages), then each field's (the table's general keys, else
    the key made readable); a file's own name only when no field follows (``人设 · 性格类型``, not the raw keys)."""
    names, fields = L.get("files") or {}, L.get("fields") or {}
    top = rel.split("/", 1)[0]
    head = names.get(rel) or names.get(top) or human_key(top)
    bits = [head]
    stem = Path(rel).stem
    if "/" in rel and rel not in names and not path:
        lab = fields.get(stem) or human_key(stem)
        if lab != head:
            bits.append(lab)
    for k in path or []:
        bits.append(str(next(iter(k.values()))) if isinstance(k, dict) else fields.get(str(k)) or (str(k) if str(k).isdigit() else human_key(str(k))))
    if where:
        bits.append(where)
    return " · ".join(bits)


def _kept(world: str, sid: str) -> dict[str, Any]:
    """key → the author's value the player said 「keep mine」 to, in the saved decisions (latest wins)."""
    out: dict[str, Any] = {}
    d = _wl(world, sid) / "updates"
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            u = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ch = u.get("choices") or {}
        for it in u.get("items") or []:
            k = it.get("key")
            if not k:
                continue
            if ch.get(it.get("id"), it.get("default")) == "mine":
                out[k] = it.get("theirs")
            else:
                out.pop(k, None)
    return out


def _sides(world: str, sid: str, m: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, str], dict[str, bytes], dict[str, bytes], dict[str, bytes], bool]:
    """(author's base files — text only, the author's base hashes, the author's now, mine, the player's base, unknown)."""
    snap = snap_dir(world, sid)
    a = author_dir(world, sid, m.get("lang") or "zh")
    a1 = _files(a)
    mine = _files(snap)
    unknown = m.get("author_files") is None
    if unknown:  # no author's base (an old snapshot whose world moved on): take mine as it, every difference = both changed
        return dict(mine), {r: _sha(b) for r, b in mine.items()}, a1, mine, dict(mine), True
    a0 = _files(_wl(world, sid) / "author")
    acc = _files(_wl(world, sid) / "accepted")
    return a0, dict(m.get("author_files") or {}), a1, mine, acc, False


def _token(a1: dict[str, bytes], mine: dict[str, bytes]) -> str:
    h = hashlib.sha1()
    for side in (a1, mine):
        for rel in sorted(side):
            h.update(f"{rel}={_sha(side[rel])}\n".encode())
        h.update(b"|")
    return "u_" + h.hexdigest()[:12]


def diff(world: str, sid: str, lang: str = "zh") -> dict[str, Any]:
    """The diff for the player (worldlines.soul-update/1); ``items`` empty = nothing to decide."""
    m = ensure(world, sid)
    if m is None:
        raise UpdateError(404, "not_collected")
    if _template(world) is None or author_dir(world, sid, m.get("lang") or "zh") is None:
        return {"schema": DIFF_SCHEMA, "world": world, "sid": sid, "gone": True, "items": [], "token": None}
    a0, h0, a1, mine, acc, unknown = _sides(world, sid, m)
    globs = tuple(m.get("globs") or DEFAULT_GLOBS)
    kept = {} if unknown else _kept(world, sid)
    L = _labels(lang)
    snap = snap_dir(world, sid)
    items: list[dict[str, Any]] = []

    def emit(rel: str, unit: str, op: str, key: str, before: Any, m_v: Any, p_v: Any, t_v: Any, **extra: Any) -> None:
        if m_v == t_v:
            return
        player = m_v != p_v
        was_kept = key in kept and kept[key] == _jsonable(before)
        both = unknown or player or was_kept
        cat = category(rel, globs)
        default = "theirs" if rel.startswith("assets/") else ("mine" if both else "theirs")
        items.append({"id": _iid(rel, key, _jsonable(before), _jsonable(t_v)), "key": key, "category": cat, "file": rel, "unit": unit,
                      "op": op, "label": _label(rel, extra.get("path"), extra.get("where"), L),
                      **({"author_before": _jsonable(before)} if op != "add" else {}),
                      "mine": _jsonable(m_v), "theirs": _jsonable(t_v), "both_changed": both,
                      **({"kept_before": True} if was_kept else {}), "default": default, **extra})

    for rel in sorted(set(h0) | set(a1)):
        b1 = a1.get(rel)
        if h0.get(rel) == (_sha(b1) if b1 is not None else None):
            continue  # the author did not change it
        b0, bm, bp = a0.get(rel), mine.get(rel), acc.get(rel)
        whole = rel not in h0 or b1 is None or _binary(rel, b1) or _binary(rel, bm)
        if not whole and rel.endswith(".json"):
            try:
                j0, j1, jm, jp = _jload(b0), _jload(b1), _jload(bm), _jload(bp)
            except (UnicodeDecodeError, ValueError):
                whole = True
            else:
                for path, unit, after in _jpaths(j0, j1, []):
                    v0, v1 = _get(j0, path), _get(j1, path)
                    op = "add" if v0 is MISSING else "remove" if v1 is MISSING else "change"
                    emit(rel, unit, op, f"{rel}#{json.dumps(path, ensure_ascii=False)}", v0, _get(jm, path), _get(jp, path), v1,
                         path=path, **({"after": after} if after else {}))
                continue
        if not whole and rel.endswith(TEXT):
            t0, t1 = (b0 or b"").decode("utf-8", "replace"), b1.decode("utf-8", "replace")
            tm, tp = (bm or b"").decode("utf-8", "replace"), (bp or b"").decode("utf-8", "replace")
            e0, e1, em, ep = _by_key(entries(t0)), _by_key(entries(t1)), _by_key(entries(tm)), _by_key(entries(tp))
            gone = [e for k, e in e0.items() if k not in e1]
            new = [e for k, e in e1.items() if k not in e0]
            order1 = [e["key"] for e in entries(t1)]
            pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for sec in sorted({e["section"] for e in gone + new}):
                g = [e for e in gone if e["section"] == sec]
                n = [e for e in new if e["section"] == sec]
                for r in list(g):
                    cands = sorted(((difflib.SequenceMatcher(None, _norm(r["text"]), _norm(a["text"])).ratio(), a) for a in n
                                    if a["kind"] == r["kind"]), key=lambda x: -x[0])
                    if cands and (cands[0][0] >= PAIR_RATIO or (len(g) == 1 and len(n) == 1) or r["kind"] == "body"):
                        pairs.append((r, cands[0][1]))
                        g.remove(r)
                        n.remove(cands[0][1])
            paired_r = {r["key"] for r, _ in pairs}
            paired_a = {a["key"] for _, a in pairs}

            def anchor(a: dict[str, Any]) -> str | None:
                i = order1.index(a["key"]) if a["key"] in order1 else -1
                for k in reversed(order1[:max(i, 0)]):
                    e = e1.get(k)
                    if e is not None and e["section"] == a["section"] and e["kind"] == "item":
                        return e["text"]
                return None

            for r, a in pairs:
                if a["key"] in em:
                    continue
                mv = r["text"] if r["key"] in em else None
                pv = r["text"] if r["key"] in ep else None
                emit(rel, "entry", "change", f"{rel}§{a['section']}§{a['key']}", r["text"], mv if mv is not None else MISSING,
                     r["text"] if pv is not None else MISSING, a["text"], where=a["section"], entry=a["kind"],
                     **({"after": anchor(a)} if anchor(a) else {}))
            for r in (e for e in gone if e["key"] not in paired_r):
                if r["key"] not in em:
                    continue
                emit(rel, "entry", "remove", f"{rel}§{r['section']}§{r['key']}§rm", r["text"], r["text"],
                     r["text"] if r["key"] in ep else MISSING, MISSING, where=r["section"], entry=r["kind"])
            for a in (e for e in new if e["key"] not in paired_a):
                if a["key"] in em:
                    continue
                emit(rel, "entry", "add", f"{rel}§{a['section']}§{a['key']}", MISSING, MISSING, MISSING, a["text"],
                     where=a["section"], entry=a["kind"], **({"after": anchor(a)} if anchor(a) else {}))
            continue
        # a whole file: binary, unparsable, or added / removed by the author
        op = "add" if rel not in h0 else "remove" if b1 is None else "change"
        hm = _sha(bm) if bm is not None else None
        hp = _sha(bp) if bp is not None else None
        emit(rel, "file", op, f"{rel}#file", h0.get(rel) or MISSING, hm or MISSING, hp or MISSING, _sha(b1) if b1 is not None else MISSING)
        if items and items[-1]["file"] == rel and items[-1]["unit"] == "file":
            it = items[-1]
            for side, b in (("mine", bm), ("theirs", b1)):
                if b is None:
                    it[side] = None
                elif _binary(rel, b):
                    it[side] = {"url": f"/api/v1/local/player-data/souls/{world}/{sid}/file?side={side}&f={rel}", "sha256": _sha(b)}
                else:
                    it[side] = {"text": b.decode("utf-8", "replace")[:20000], "sha256": _sha(b)}
            it.pop("author_before", None)
    counts: dict[str, int] = {"settings": 0, "memory": 0, "state": 0, "both_changed": 0}
    for it in items:
        counts[it["category"]] += 1
        counts["both_changed"] += int(it["both_changed"])
    t = _template(world)
    return {"schema": DIFF_SCHEMA, "world": world, "sid": sid, "name": _name(snap), "lang": lang,
            "from_version": str(m.get("author_version") or ""), "to_version": str(getattr(t, "version", "") or ""),
            "token": _token(a1, mine), "base": {"accepted_at": m.get("accepted_at"), "author_version": m.get("author_version"),
                                               "unknown": unknown, **({"migrated": m["migrated"]} if m.get("migrated") else {})},
            "counts": counts, "items": items, "choices": None}


def _name(snap: Path) -> str:
    try:
        sj = json.loads((snap / "soul.json").read_text(encoding="utf-8"))
        return str(sj.get("name_local") or sj.get("name") or "")
    except (OSError, ValueError):
        return ""


def has_update(world: str, sid: str) -> bool:
    """The author's files differ from the author's base (or there is no base yet and they differ from the snapshot)."""
    m = ensure(world, sid)
    if not m or _template(world) is None:
        return False
    a = author_dir(world, sid, m.get("lang") or "zh")
    if a is None:
        return False
    a1 = {r: _sha(b) for r, b in _files(a).items()}
    if m.get("author_files") is None:
        mine = {r: _sha(b) for r, b in _files(snap_dir(world, sid)).items()}
        return any(mine.get(r) != h for r, h in a1.items())
    return a1 != m["author_files"]


# ── choosing ─────────────────────────────────────────────────────────────────

def _set(doc: Any, path: list[Any], value: Any, *, after: Any = None) -> Any:
    """``doc`` with ``value`` at ``path`` (MISSING = remove); containers made as needed."""
    if not path:
        return value
    k, rest = path[0], path[1:]
    if isinstance(k, dict):
        (name, val), = k.items()
        lst = doc if isinstance(doc, list) else []
        i = next((n for n, x in enumerate(lst) if isinstance(x, dict) and x.get(name) == val), None)
        if rest:
            cur = lst[i] if i is not None else {}
            new = _set(cur, rest, value)
            if i is None:
                lst.append(new)
            else:
                lst[i] = new
            return lst
        if value is MISSING:
            if i is not None:
                lst.pop(i)
            return lst
        if i is not None:
            lst[i] = value
            return lst
        j = None
        if isinstance(after, dict):
            (an, av), = after.items()
            j = next((n for n, x in enumerate(lst) if isinstance(x, dict) and x.get(an) == av), None)
        lst.insert(j + 1 if j is not None else len(lst), value)
        return lst
    d = doc if isinstance(doc, dict) else {}
    if rest:
        d[k] = _set(d.get(k, MISSING), rest, value, after=after)
    elif value is MISSING:
        d.pop(k, None)
    else:
        d[k] = value
    return d


def _apply_entries(text: str, its: list[dict[str, Any]]) -> str:
    blocks = _blocks(text)

    def find(t: str, section: str, kind: str) -> int | None:
        n = _norm(t)
        for i, b in enumerate(blocks):
            if b["section"] == section and b["kind"] == kind and _norm(b["raw"]) == n:
                return i
        if kind == "body":  # the section's body entry is all its body blocks together
            idx = [i for i, b in enumerate(blocks) if b["section"] == section and b["kind"] == "body" and b["raw"].strip()]
            if idx and _norm("\n\n".join(blocks[i]["raw"].strip() for i in idx)) == n:
                return idx[0]
        return None

    def raw_of(t: str) -> str:
        return t.rstrip("\n") + "\n"

    def insert(it: dict[str, Any]) -> None:
        sec, kind = it.get("where") or "", it.get("entry") or "item"
        new = {"kind": kind, "section": sec, "raw": raw_of(it["theirs"]) + ("\n" if kind == "body" else "")}
        if it.get("after"):
            j = find(it["after"], sec, "item")
            if j is not None:
                blocks.insert(j + 1, new)
                return
        idx = [i for i, b in enumerate(blocks) if b["section"] == sec and (sec or b["kind"] != "heading")]
        if idx:
            last = idx[-1]
            while last > idx[0] and blocks[last]["kind"] == "body" and not blocks[last]["raw"].strip():
                last -= 1
            blocks.insert(last + 1, new)
            return
        if sec:
            tail = "" if not blocks or blocks[-1]["raw"].endswith("\n\n") else "\n"
            blocks.append({"kind": "body", "section": sec, "raw": tail + f"## {sec}\n\n"})
        blocks.append(new)

    def body_idx(sec: str) -> list[int]:
        return [i for i, b in enumerate(blocks) if b["section"] == sec and b["kind"] == "body" and b["raw"].strip()]

    for it in its:
        sec, kind = it.get("where") or "", it.get("entry") or "item"
        if it["op"] == "add":
            insert(it)
        elif it["op"] == "remove":
            if kind == "body":
                for i in reversed(body_idx(sec)):
                    blocks.pop(i)
            else:
                i = find(it["author_before"], sec, kind)
                if i is not None:
                    blocks.pop(i)
        else:  # change
            if kind == "body":
                idx = body_idx(sec)
                if idx and it.get("mine") is not None:
                    for i in reversed(idx[1:]):
                        blocks.pop(i)
                    blocks[idx[0]]["raw"] = raw_of(it["theirs"]) + "\n"
                else:
                    insert(it)
                continue
            i = find(it["author_before"], sec, kind) if it.get("mine") is not None else None
            if i is not None:
                blocks[i]["raw"] = raw_of(it["theirs"])
            else:
                insert(it)
    return "".join(b["raw"] for b in blocks)


def _land(snap: Path, out: dict[str, bytes | None]) -> None:
    """Every changed file or none: the new ones are written beside the snapshot first, the old ones kept aside; a
    failure halfway puts every old one back."""
    tmp = Path(tempfile.mkdtemp(prefix=".wl-apply-", dir=str(snap.parent)))
    new, old = tmp / "new", tmp / "old"
    done: list[str] = []
    try:
        for rel, b in out.items():
            if b is not None:
                (new / rel).parent.mkdir(parents=True, exist_ok=True)
                (new / rel).write_bytes(b)
            if (snap / rel).is_file():
                (old / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snap / rel, old / rel)
        try:
            for rel, b in out.items():
                dst = snap / rel
                done.append(rel)
                if b is None:
                    if dst.is_file():
                        dst.unlink()
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(new / rel, dst)
        except Exception:
            for rel in done:
                dst = snap / rel
                if (old / rel).is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old / rel, dst)
                elif dst.is_file():
                    dst.unlink()
            raise UpdateError(500, "write_failed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def apply(world: str, sid: str, *, token: str | None = None, choices: dict[str, str] | None = None, all_: str | None = None,
          lang: str = "zh") -> dict[str, Any]:
    """The player's decision: the items chosen 「theirs」 land in the snapshot (atomically), the diff and the choices are
    saved, both bases move to this moment."""
    d = diff(world, sid, lang)
    if d.get("gone"):
        raise UpdateError(404, "author_gone")
    if token is not None and token != d["token"]:
        raise UpdateError(409, "stale")
    if all_ not in (None, "defaults", "mine", "theirs"):
        raise UpdateError(400, "bad_all")
    pick: dict[str, str] = {}
    for it in d["items"]:
        c = (choices or {}).get(it["id"])
        if c not in ("mine", "theirs"):
            c = it["default"] if all_ in (None, "defaults") else all_
        pick[it["id"]] = c
    snap = snap_dir(world, sid)
    m = _meta(world, sid)
    a = author_dir(world, sid, m.get("lang") or "zh")
    a1 = _files(a)
    mine = _files(snap)
    by_file: dict[str, list[dict[str, Any]]] = {}
    for it in d["items"]:
        if pick[it["id"]] == "theirs":
            by_file.setdefault(it["file"], []).append(it)
    out: dict[str, bytes | None] = {}
    for rel, its in by_file.items():
        if any(it["unit"] == "file" for it in its):
            out[rel] = a1.get(rel)
        elif rel.endswith(".json"):
            doc: Any = copy.deepcopy(_jload(mine.get(rel))) if rel in mine else {}
            for it in its:
                doc = _set(doc, list(it["path"]), MISSING if it["op"] == "remove" else copy.deepcopy(it["theirs"]), after=it.get("after"))
            out[rel] = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        else:
            out[rel] = _apply_entries((mine.get(rel) or b"").decode("utf-8", "replace"), its).encode("utf-8")
    _land(snap, out)
    # save the decision, move both bases
    t = _template(world)
    ups = _wl(world, sid) / "updates"
    ups.mkdir(parents=True, exist_ok=True)
    n = len(list(ups.glob("*.json"))) + 1
    name = f"{n:04d}-{d['from_version'] or 'x'}-to-{d['to_version'] or 'x'}.json"
    (ups / name).write_text(json.dumps({**d, "choices": pick, "decided_at": _now()}, ensure_ascii=False, indent=1), encoding="utf-8")
    _copy_tree(snap, _wl(world, sid) / "accepted")
    m.update({"author_files": _write_author(world, sid, a1), "author_version": str(getattr(t, "version", "") or ""),
              "accepted_at": _now(), "accepted_version": str(getattr(t, "version", "") or ""), "pending_base": False,
              "updates": [*(m.get("updates") or []), name]})
    _save_meta(world, sid, m)
    _save_graph(world, sid, a)
    from neonrp.core import player_data

    player_data.update("characters", {"sid": sid, "world": world},
                       {"version": str(getattr(t, "version", "") or ""), "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    took = [k for k, v in pick.items() if v == "theirs"]
    return {"ok": True, "update": name, "took": len(took), "kept": len(pick) - len(took), "version": m["author_version"]}


def updates(world: str, sid: str) -> list[dict[str, Any]]:
    d = _wl(world, sid) / "updates"
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            u = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"file": f.name, "from_version": u.get("from_version"), "to_version": u.get("to_version"),
                    "decided_at": u.get("decided_at"), "items": u.get("items") or [], "choices": u.get("choices") or {}})
    return out


def side_file(world: str, sid: str, side: str, rel: str) -> Path | None:
    """A file of the player's version (``mine``) or the author's (``theirs``), for previews; inside that folder only."""
    if side == "theirs":
        m = ensure(world, sid) or {}
        base = author_dir(world, sid, m.get("lang") or "zh")
    else:
        base = snap_dir(world, sid)
    if base is None or ".." in Path(rel).parts:
        return None
    p = (base / rel).resolve()
    return p if p.is_file() and p.is_relative_to(base.resolve()) else None
