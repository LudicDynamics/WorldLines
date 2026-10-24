"""Heavy front ends of a world (10-17: the studio's front-end desk made real).

Two sources:
  builtin    the product's own — the Godot client (worldlines/examples/clients/godot), the standard web front end
             (worldlines/ui/player → /player.html), the protocol example (worldlines/examples/clients/ts), the phone
             (worldlines/ui/player/chat → /chat.html). Read-only here; only a source checkout has their files.
  template   ``<template>/frontends/<name>/frontend.json`` — a creator's own front end for this world:

      {"schema": "worldlines.frontend/1", "kind": "web-ts" | "godot" | "chat", "title": "…",
       "entry": "index.html" | "project.godot", "events": ["node.enter", …], "from": "builtin.godot", "targets": ["local"]}

Front ends live next to the world, never in a run (a run is built from the template's world folder) and not in an
exported package (local only for now — Hub / iOS pick them up later from ``targets``).

The front-end agent edits one front-end folder and nothing else: it sees the folder's files and this world's contract,
answers in prose and writes whole files as ``<file path="…">…</file>`` blocks (asks for more with ``<read path="…"/>``).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Iterator

SCHEMA = "worldlines.frontend/1"
KINDS = ("web-ts", "godot", "chat")
TARGETS = ("local", "hub", "ios")
MANIFEST = "frontend.json"
DIR = "frontends"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_SKIP = {"node_modules", ".godot", "__pycache__", ".DS_Store", "test-results", "dist", ".vite"}
_MAX_TREE = 2000
_MAX_READ = 1_000_000
_MAX_WRITE = 512 * 1024

# dev repo: worldlines/ beside src/ · public repo: worldlines/ beside neonrp/ (same as template.product_dirs)
_ROOT = Path(__file__).resolve().parents[3]
_REPO = next((d for d in (_ROOT / "worldlines", _ROOT.parent / "worldlines") if d.is_dir()), _ROOT / "worldlines")
# id → what it is; dir is relative to worldlines/ (only a source checkout has it)
# (title = a key of the prompts table "frontends": the words live in src/neonrp/prompts/frontends.<lang>.json)
BUILTIN: dict[str, dict[str, Any]] = {
    "builtin.godot": {"kind": "godot", "title": "title_godot", "dir": "examples/clients/godot", "entry": "project.godot",
                      "events": ["node.enter", "node.leave", "plan.beat", "resolve.beat", "dice", "state.changed", "run.settled"]},
    "builtin.player": {"kind": "web-ts", "title": "title_player", "dir": "ui/player", "entry": "src/index.html", "page": "/player.html",
                       "events": ["node.enter", "plan.beat", "resolve.beat", "dice", "state.changed", "stage.changed", "party.join", "run.settled"]},
    "builtin.ts": {"kind": "web-ts", "title": "title_ts", "dir": "examples/clients/ts", "entry": "index.html", "site": "dist",
                   "build": "npm install && npx vite build --base ./",
                   "events": ["node.enter", "plan.beat", "resolve.beat", "dice", "state.changed", "run.settled"]},
    "builtin.chat": {"kind": "chat", "title": "title_chat", "dir": "ui/player/chat", "entry": "index.html", "page": "/chat.html",
                     "events": ["chat.message", "chat.typing"]},
}


class FrontendError(ValueError):
    pass


# ── where a front end lives ──────────────────────────────────────────────────

def builtin_dir(fid: str) -> Path | None:
    b = BUILTIN.get(fid)
    d = (_REPO / b["dir"]) if b else None
    return d if d is not None and d.is_dir() else None


_RESERVED = ("new", "import", "_")   # route words: …/frontends/<tpl>/new · …/import


def template_dir(t: Any, name: str) -> Path:
    if not NAME_RE.match(name or "") or name in _RESERVED:
        raise FrontendError("name: 1–40 chars, lowercase letters / digits / '-'")
    return Path(t.dir) / DIR / name


def manifest(d: Path) -> dict[str, Any] | None:
    try:
        m = json.loads((d / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m if isinstance(m, dict) else None


def _writable(t: Any) -> bool:
    from neonrp.template import author

    return author.writable(t)


def words(lang: str | None) -> dict[str, Any]:
    from neonrp import prompts

    return prompts.strings("frontends", lang or "zh")


def listing(t: Any | None, lang: str | None = None) -> list[dict[str, Any]]:
    """The builtin ones (with or without their source here) + this template's own."""
    out, w = [], words(lang)
    for fid, b in BUILTIN.items():
        d = builtin_dir(fid)
        out.append({"id": fid, "source": "builtin", "kind": b["kind"], "title": w[b["title"]], "entry": b["entry"],
                    "events": list(b["events"]), "dir": f"worldlines/{b['dir']}", "have_source": d is not None, "writable": False,
                    **{k: b[k] for k in ("page", "site", "build") if k in b},
                    **({"site_built": (d / b["site"] / "index.html").is_file()} if d is not None and "site" in b else {})})
    if t is not None:
        root = Path(t.dir) / DIR
        for sub in sorted(root.iterdir()) if root.is_dir() else []:
            if not sub.is_dir() or not NAME_RE.match(sub.name):
                continue
            m = manifest(sub) or {}
            out.append({"id": sub.name, "source": "template", "kind": m.get("kind"), "title": str(m.get("title") or sub.name),
                        "entry": m.get("entry"), "events": list(m.get("events") or []), "from": m.get("from"),
                        "targets": list(m.get("targets") or ["local"]), "dir": f"{DIR}/{sub.name}", "have_source": True,
                        "writable": _writable(t), "problems": check(t, sub.name, lang or "zh")})
    return out


def resolve(t: Any | None, fid: str) -> tuple[Path, bool, dict[str, Any]]:
    """→ (folder, writable, info)."""
    if fid in BUILTIN:
        d = builtin_dir(fid)
        if d is None:
            raise FrontendError("this install has no source for the builtin front ends")
        return d, False, {"id": fid, **BUILTIN[fid], "title": words(None)[BUILTIN[fid]["title"]]}
    if t is None:
        raise FrontendError("no world")
    d = template_dir(t, fid)
    if not d.is_dir():
        raise FrontendError(f"no front end {fid!r} in {t.id}")
    m = manifest(d) or {}
    return d, _writable(t), {"id": fid, **m}


# ── files ────────────────────────────────────────────────────────────────────

def _skip(rel: Path) -> bool:
    return any(p in _SKIP or (p.startswith(".") and p not in (".gitignore",)) for p in rel.parts)


def tree(d: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in sorted(d.rglob("*")):
        rel = f.relative_to(d)
        if _skip(rel) or not f.is_file():
            continue
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        out.append({"path": rel.as_posix(), "size": size})
        if len(out) >= _MAX_TREE:
            break
    return out


def _inside(d: Path, rel: str) -> Path:
    rel = str(rel or "").strip().lstrip("/")
    if not rel or "\\" in rel or any(p in ("..", "") for p in rel.split("/")):
        raise FrontendError("bad path")
    p = (d / rel).resolve()
    if not p.is_relative_to(d.resolve()) or _skip(Path(rel)):
        raise FrontendError("bad path")
    return p


def read(d: Path, rel: str) -> str:
    p = _inside(d, rel)
    if not p.is_file():
        raise FileNotFoundError(rel)
    if p.stat().st_size > _MAX_READ:
        raise FrontendError("too large")
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise FrontendError("binary file") from e


def write(d: Path, rel: str, content: str) -> None:
    p = _inside(d, rel)
    if len(content.encode("utf-8")) > _MAX_WRITE:
        raise FrontendError("too large")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def delete(d: Path, rel: str) -> bool:
    p = _inside(d, rel)
    if p.is_file() and p.name != MANIFEST:
        p.unlink()
        return True
    return False


# ── manifest checks (template lint: frontend.*) ──────────────────────────────

def known_events() -> set[str]:
    from neonrp.core.beat_events import EVENTS

    return set(EVENTS) | {"var.changed", "entity.created", "entry.entered", "flag.set", "trigger.fired", "ending.reached", "pending", "commit"}


def check(t: Any, name: str, lang: str | None = "en") -> list[dict[str, str]]:
    """Problems of one front end: [{level, code, where, message}] (message in ``lang``: prompts table "frontends")."""
    return check_dir(Path(t.dir) / DIR / name, f"{DIR}/{name}", lang)


def check_dir(d: Path, where: str, lang: str | None = "en") -> list[dict[str, str]]:
    """The manifest checks on any folder (a front end in place, or one being imported before it lands)."""
    w = words(lang)
    say = lambda key, **kv: str(w[key]).format(**kv)  # noqa: E731
    m = manifest(d)
    if m is None:
        return [{"level": "block", "code": "frontend.manifest", "where": where, "message": say("chk_no_manifest", file=MANIFEST)}]
    out = []
    if m.get("schema") != SCHEMA:
        out.append({"level": "warn", "code": "frontend.manifest", "where": where, "message": say("chk_schema", schema=SCHEMA)})
    if m.get("kind") not in KINDS:
        out.append({"level": "block", "code": "frontend.manifest", "where": where, "message": say("chk_kind", kind=repr(m.get("kind")), known=", ".join(KINDS))})
    entry = str(m.get("entry") or "")
    if not entry:
        out.append({"level": "block", "code": "frontend.entry", "where": where, "message": say("chk_no_entry")})
    else:
        try:
            ok = _inside(d, entry).is_file()
        except FrontendError:
            ok = False
        if not ok:
            out.append({"level": "block", "code": "frontend.entry", "where": where, "message": say("chk_entry_missing", entry=entry)})
    ev = m.get("events") or []
    if not isinstance(ev, list):
        out.append({"level": "warn", "code": "frontend.events", "where": where, "message": say("chk_events_list")})
    else:
        known = known_events()
        bad = [str(e) for e in ev if not (str(e) in known or re.match(r"^[a-z_]+\.beat$", str(e)) or (m.get("kind") == "chat" and str(e).startswith("chat.")))]
        if bad:
            out.append({"level": "warn", "code": "frontend.events", "where": where, "message": say("chk_events_bad", events=", ".join(bad))})
    tg = m.get("targets") or ["local"]
    if not isinstance(tg, list) or any(x not in TARGETS for x in tg):
        out.append({"level": "warn", "code": "frontend.target", "where": where, "message": say("chk_targets", known=", ".join(TARGETS))})
    elif any(x in ("hub", "ios") for x in tg):
        out.append({"level": "warn", "code": "frontend.target", "where": where, "message": say("chk_hosted")})
    return out


def lint(t: Any) -> list[dict[str, str]]:
    root = Path(t.dir) / DIR
    out: list[dict[str, str]] = []
    for sub in sorted(root.iterdir()) if root.is_dir() else []:
        if sub.is_dir():
            if not NAME_RE.match(sub.name):
                out.append({"level": "warn", "code": "frontend.manifest", "where": f"{DIR}/{sub.name}", "message": str(words("en")["chk_folder_name"])})
                continue
            out += check(t, sub.name)
    return out


# ── a new front end ──────────────────────────────────────────────────────────

_WEB_HTML = """<!doctype html>
<html lang="%%html_lang%%">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<main id="app">
  <header><b id="world">…</b><span id="status">%%connecting%%</span></header>
  <section id="feed"></section>
  <form id="say"><input id="line" autocomplete="off" placeholder="%%say%%"><button>➤</button></form>
</main>
<script type="module" src="main.js"></script>
</body>
</html>
"""
_WEB_CSS = """body{margin:0;background:#0b0d14;color:#f2efe8;font:15px/1.6 system-ui,sans-serif}
#app{display:flex;flex-direction:column;height:100vh;max-width:760px;margin:0 auto;padding:0 16px}
header{display:flex;justify-content:space-between;padding:14px 0;border-bottom:1px solid #ffffff22}
#status{opacity:.6;font-size:13px}
#feed{flex:1;overflow:auto;padding:12px 0}
#feed p{margin:0 0 10px;white-space:pre-wrap}
#feed .you{color:#c9f27a}
#feed .ev{font:12px ui-monospace,monospace;opacity:.55}
form{display:flex;gap:8px;padding:12px 0}
input{flex:1;padding:10px 12px;border-radius:10px;border:1px solid #ffffff33;background:#ffffff10;color:inherit}
button{padding:0 16px;border-radius:10px;border:0;background:#c9f27a;color:#111}
"""
_WEB_JS = """// A world's own web front end (worldlines.frontend/1 · web-ts). Plain ES module: the local engine serves this folder,
// so the page is on the engine's origin and talks to it directly.
//   POST /rpc         JSON-RPC 2.0: session.hello · turn.send   (Authorization: Bearer <token>)
//   GET  /rpc/events  SSE: bus.message {topic, seq, payload} — engine/stream chunks · engine/beat events
// The token: GET /api/v1/local/frontends/_/connect (the local engine only). Types: contract.ts (this world's contract).
const $ = s => document.querySelector(s)
const feed = $('#feed')
let token = '', id = 1, cur = null
const client = Math.random().toString(16).slice(2, 10)

const rpc = async (method, params = {}) => {
  const r = await fetch('/rpc', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ jsonrpc: '2.0', id: id++, method, params }) })
  const m = await r.json()
  if (m.error) throw new Error(m.error.message)
  return m.result
}
const line = (text, cls) => { const p = document.createElement('p'); if (cls) p.className = cls; p.textContent = text; feed.appendChild(p); feed.scrollTop = feed.scrollHeight; return p }

function onBus({ topic, payload: pl = {} }) {
  if (topic === 'engine/stream' && pl.kind === 'chunk') { cur = cur || line(''); cur.textContent += String(pl.text || '').replace(/\\[\\[subagent:[^\\]]+\\]\\]/g, '') }
  else if (topic === 'engine/beat') { cur = null; line(`· ${pl.kind}`, 'ev') }
  else if (topic === 'engine/event' && pl.kind === 'turn_finished') cur = null
}
async function listen() {
  for (;;) {
    try {
      const r = await fetch(`/rpc/events?client=${client}`, { headers: { Authorization: `Bearer ${token}` } })
      const rd = r.body.pipeThrough(new TextDecoderStream()).getReader()
      let buf = ''
      for (;;) {
        const { value, done } = await rd.read(); if (done) break
        buf += value
        let i
        while ((i = buf.indexOf('\\n\\n')) >= 0) {
          const frame = buf.slice(0, i); buf = buf.slice(i + 2)
          for (const l of frame.split('\\n')) if (l.startsWith('data: ')) { const m = JSON.parse(l.slice(6)); if (m.method === 'bus.message') onBus(m.params || {}) }
        }
      }
    } catch { /* reconnect */ }
    await new Promise(res => setTimeout(res, 1000))
  }
}

async function main() {
  try {
    token = (await (await fetch('/api/v1/local/frontends/_/connect')).json()).token
    const hello = await rpc('session.hello', { protocol: 'worldlines.net/1' })
    $('#world').textContent = hello.world || '(no run)'
    $('#status').textContent = '%%connected%%'
    listen()
  } catch (e) { $('#status').textContent = '%%no_conn%%' + e.message }
}
$('#say').addEventListener('submit', async e => {
  e.preventDefault()
  const v = $('#line').value.trim(); if (!v) return
  $('#line').value = ''; line(v, 'you'); cur = null
  try { await rpc('turn.send', { text: v, client }) } catch (err) { line('%%error%%' + err.message, 'ev') }
})
main()
"""
_CHAT_JS = """// A world's own phone (worldlines.frontend/1 · chat): talk to one character of this world, alone.
//   GET  /api/v1/chat/souls            → {souls: [{tpl, sid, name, avatar_url, standalone, obtained}]}
//   GET  /api/v1/chat/thread?tpl=&sid= → {soul, access, messages: [{from: me|soul, text}]}
//   POST /api/v1/chat/send {tpl, sid, kind: 'text', text}
const $ = s => document.querySelector(s)
const q = new URLSearchParams(location.search)
const tpl = q.get('tpl') || '{tpl}'
let sid = q.get('sid') || ''
const feed = $('#feed')
const line = (text, cls) => { const p = document.createElement('p'); if (cls) p.className = cls; p.textContent = text; feed.appendChild(p); feed.scrollTop = feed.scrollHeight }

async function main() {
  const souls = ((await (await fetch('/api/v1/chat/souls')).json()).souls || []).filter(s => s.tpl === tpl)
  if (!sid && souls.length) sid = souls[0].sid
  const s = souls.find(x => x.sid === sid)
  $('#world').textContent = s ? s.name : '%%chat_none%%'
  if (!s) return
  const th = await (await fetch(`/api/v1/chat/thread?tpl=${encodeURIComponent(tpl)}&sid=${encodeURIComponent(sid)}`)).json()
  $('#status').textContent = th.access || ''
  for (const m of th.messages || []) line(m.text || '', m.from === 'me' ? 'you' : '')
}
$('#say').addEventListener('submit', async e => {
  e.preventDefault()
  const v = $('#line').value.trim(); if (!v || !sid) return
  $('#line').value = ''; line(v, 'you')
  const r = await fetch('/api/v1/chat/send', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tpl, sid, kind: 'text', text: v }) })
  const b = await r.json().catch(() => ({}))
  for (const m of (b.messages || (b.message ? [b.message] : []))) if (m.from !== 'me') line(m.text || '')
  if (!r.ok) line('%%error%%' + (b.error || r.status), 'ev')
})
main()
"""


def _contract_ts(t: Any) -> str:
    from neonrp.template import v3

    try:
        with v3._scratch(t, None) as root:
            return v3.gen_ts(v3.contract(t, root))
    except Exception:  # noqa: BLE001 — a template that does not build: the front end still starts (lint says why)
        return "// this world's contract could not be built — see the template lint\n"


def _starter(text: str, lang: str | None) -> str:
    """A starter file with its page words (``%%key%%``) in ``lang``."""
    for k, v in words(lang).items():
        text = text.replace(f"%%{k}%%", str(v).replace("'", "\\'"))
    return text


def create(t: Any, name: str, kind: str, title: str = "", lang: str | None = None) -> dict[str, Any]:
    """A new front end in ``frontends/<name>/`` from a starter (godot = a copy of the Godot client); the starter page
    speaks ``lang`` (default zh)."""
    if not _writable(t):
        raise FrontendError(f"{t.id} is not writable here — make your own copy first")
    if kind not in KINDS:
        raise FrontendError(f"kind: {', '.join(KINDS)}")
    d = template_dir(t, name)
    if d.exists():
        raise FrontendError(f"{DIR}/{name} already exists")
    title = (title or name).strip()[:60]
    events = list(BUILTIN["builtin.godot" if kind == "godot" else "builtin.chat" if kind == "chat" else "builtin.ts"]["events"])
    if kind == "godot":
        src = builtin_dir("builtin.godot")
        if src is None:
            raise FrontendError("this install has no Godot client to start from")
        shutil.copytree(src, d, ignore=shutil.ignore_patterns(*_SKIP, "*.uid", "town_*.gd", "scene_*.gd"))
        entry, frm = "project.godot", "builtin.godot"
        pg = d / "project.godot"
        pg.write_text(re.sub(r'config/name="[^"]*"', f'config/name="{title}"', pg.read_text(encoding="utf-8")), encoding="utf-8")
    else:
        d.mkdir(parents=True)
        html = _starter(_WEB_HTML, lang).replace("{title}", title)
        (d / "index.html").write_text(html, encoding="utf-8")
        (d / "style.css").write_text(_WEB_CSS, encoding="utf-8")
        (d / "main.js").write_text(_starter(_CHAT_JS.replace("{tpl}", t.id) if kind == "chat" else _WEB_JS, lang), encoding="utf-8")
        (d / "contract.ts").write_text(_contract_ts(t), encoding="utf-8")
        entry, frm = "index.html", "builtin.chat" if kind == "chat" else "builtin.ts"
    m = {"schema": SCHEMA, "kind": kind, "title": title, "entry": entry, "events": events, "from": frm, "targets": ["local"]}
    (d / MANIFEST).write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"id": name, **m}


# ── copy · export · import (10-19: the desk reads, saves, exports, imports) ──────────────────────────────────

_ZIP_MAX = 20 * 1024 * 1024  # unpacked bytes
_ZIP_FILES = 2000


def _free_dest(t: Any, name: str) -> Path:
    if not _writable(t):
        raise FrontendError(str(words(None)["err_readonly_world"]).format(world=t.id))
    d = template_dir(t, name)
    if d.exists():
        raise FrontendError(str(words(None)["err_exists"]).format(where=f"{DIR}/{name}"))
    return d


def fork(t: Any, fid: str, name: str, title: str = "") -> dict[str, Any]:
    """A copy of a front end (builtin or this world's) into ``frontends/<name>/`` — then it can be changed. Leaves out
    node_modules / .godot / dist; a builtin gets a frontend.json (from = its id)."""
    src, _, info = resolve(t, fid)
    d = _free_dest(t, name)
    shutil.copytree(src, d, ignore=shutil.ignore_patterns(*_SKIP), symlinks=False)
    base = {"schema": SCHEMA, "kind": info.get("kind"), "title": f"{info.get('title') or fid} · {name}", "entry": info.get("entry"),
            "events": list(info.get("events") or []), "targets": ["local"],
            **{k: info[k] for k in ("site", "build") if k in info}}
    m = {**base, **{k: v for k, v in (manifest(d) or {}).items() if k != "title"}, "from": fid}   # the copy's own name on its tab
    if title.strip():
        m["title"] = title.strip()[:60]
    (d / MANIFEST).write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"id": name, **m}


def export_zip(d: Path, arc: str) -> bytes:
    """The folder as a zip (``<arc>/…``), without installs / builds / links — builtin ones too."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(d.rglob("*")):
            rel = f.relative_to(d)
            if _skip(rel) or f.is_symlink() or not f.is_file():
                continue
            z.write(f, f"{arc}/{rel.as_posix()}")
    return buf.getvalue()


def import_zip(t: Any, name: str, data: bytes, lang: str | None = None) -> dict[str, Any]:
    """An exported front end back in as ``frontends/<name>/``. Nothing lands unless every entry is a plain relative
    path, it is small enough, and its frontend.json passes the checks (blocks); otherwise FrontendImportRefused(problems)."""
    import io
    import tempfile
    import zipfile
    from pathlib import PurePosixPath

    w = words(lang)
    d = _free_dest(t, name)
    bad = lambda key, **kv: FrontendImportRefused([{"level": "block", "code": "frontend.import", "where": f"{DIR}/{name}", "message": str(w[key]).format(**kv)}])  # noqa: E731
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise bad("imp_not_zip") from None
    infos = [i for i in z.infolist() if not i.is_dir()]
    if len(infos) > _ZIP_FILES or sum(i.file_size for i in infos) > _ZIP_MAX:
        raise bad("imp_too_big", files=_ZIP_FILES, mb=_ZIP_MAX // (1024 * 1024))
    for i in z.infolist():
        p = PurePosixPath(i.filename)
        if p.is_absolute() or ".." in p.parts or "\\" in i.filename or (i.external_attr >> 16) & 0o170000 == 0o120000:
            raise bad("imp_unsafe", path=i.filename)
    tops = {PurePosixPath(i.filename).parts[0] for i in infos}
    strip = len(tops) == 1 and all(len(PurePosixPath(i.filename).parts) > 1 for i in infos)   # one top folder: its content
    with tempfile.TemporaryDirectory(prefix="wl-fe-import-") as td:
        tmp = Path(td) / name
        tmp.mkdir()
        for i in infos:
            parts = PurePosixPath(i.filename).parts[1 if strip else 0:]
            rel = Path(*parts)
            if _skip(rel):
                continue
            out = (tmp / rel).resolve()
            if not out.is_relative_to(tmp.resolve()):
                raise bad("imp_unsafe", path=i.filename)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(i))
        probs = check_dir(tmp, f"{DIR}/{name}", lang)
        if any(p["level"] == "block" for p in probs):
            raise FrontendImportRefused(probs)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(tmp, d)
    return {"id": name, **(manifest(d) or {}), "problems": probs}


class FrontendImportRefused(FrontendError):
    def __init__(self, problems: list[dict[str, str]]):
        super().__init__("; ".join(p["message"] for p in problems))
        self.problems = problems


# ── building a web front end that needs it (builtin.ts: Vite) ────────────────

_BUILD_LOCK = threading.Lock()


def build(fid: str, timeout: float = 300, *, d: Path | None = None, info: dict[str, Any] | None = None) -> dict[str, Any]:
    """``npm install`` (once) + ``vite build --base ./`` → its ``site`` folder, served by the desk's preview. The builtin
    protocol example has a build step, and so does a world's copy of it (``site`` in its frontend.json + a Vite
    package.json); a world's own starter is plain modules served as they are."""
    b = info if info is not None else BUILTIN.get(fid) or {}
    d = d if d is not None else builtin_dir(fid)
    vite = d is not None and "vite" in ((d / "package.json").read_text(encoding="utf-8") if (d / "package.json").is_file() else "")
    if d is None or "site" not in b or not vite:
        raise FrontendError("this front end has no build step")
    npm = shutil.which("npm")
    if npm is None:
        raise FrontendError("npm not found (install Node.js)")
    steps = ([] if (d / "node_modules").is_dir() else [[npm, "install", "--no-audit", "--no-fund"]]) + \
        [[shutil.which("npx") or "npx", "vite", "build", "--base", "./"]]
    out, code = [], 0
    if not _BUILD_LOCK.acquire(blocking=False):
        raise FrontendError("a build is already running")
    try:
        for cmd in steps:
            try:
                r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=timeout)
                out.append(f"$ {' '.join(Path(cmd[0]).name if i == 0 else c for i, c in enumerate(cmd))}\n{(r.stdout or '') + (r.stderr or '')}")
                code = r.returncode
            except (OSError, subprocess.TimeoutExpired) as e:
                out.append(f"$ {' '.join(cmd[1:])}\n{e}")
                code = -1
            if code != 0:
                break
    finally:
        _BUILD_LOCK.release()
    return {"ok": code == 0 and (d / b["site"] / "index.html").is_file(), "code": code, "output": "\n".join(out)[-6000:]}


# ── Godot on this machine ────────────────────────────────────────────────────

_PROCS: dict[int, dict[str, Any]] = {}  # pid → what we started (only these are ever stopped)
_LOCK = threading.Lock()
_VERSION: dict[str, str] = {}


def godot_bin() -> str | None:
    for c in (os.environ.get("GODOT", "").strip(), shutil.which("godot") or "", shutil.which("godot4") or "",
              "/Applications/Godot.app/Contents/MacOS/Godot"):
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


def godot_status() -> dict[str, Any]:
    b = godot_bin()
    if b and b not in _VERSION:
        try:
            _VERSION[b] = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=20).stdout.strip().splitlines()[-1]
        except (OSError, subprocess.SubprocessError, IndexError):
            _VERSION[b] = ""
    with _LOCK:
        for pid in [p for p, x in _PROCS.items() if x["proc"].poll() is not None]:
            _PROCS[pid]["exit"] = _PROCS[pid]["proc"].returncode
        running = [{"pid": p, "dir": x["dir"], "started": x["started"]} for p, x in _PROCS.items() if x["proc"].poll() is None]
    return {"bin": b, "version": _VERSION.get(b or "", ""), "running": running}


def _env(host: str, token: str, world: str, line: str | None = None) -> dict[str, str]:
    env = {**os.environ, "WL_HOST": host, "WL_TOKEN": token, "WL_WORLD": world}
    if line:
        env["WL_LINE"] = line
    return env


def godot_launch(d: Path, *, host: str, token: str, world: str) -> dict[str, Any]:
    import time

    b = godot_bin()
    if b is None:
        raise FrontendError("Godot not found (set GODOT=/path/to/godot)")
    p = subprocess.Popen([b, "--path", str(d)], env=_env(host, token, world), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    with _LOCK:
        _PROCS[p.pid] = {"proc": p, "dir": str(d), "started": time.time()}
    return {"pid": p.pid}


def godot_stop(pid: int) -> bool:
    with _LOCK:
        x = _PROCS.get(int(pid))
    if x is None:
        return False  # not ours: never touched
    if x["proc"].poll() is None:
        x["proc"].terminate()
        try:
            x["proc"].wait(5)
        except subprocess.TimeoutExpired:
            x["proc"].kill()
    with _LOCK:
        _PROCS.pop(int(pid), None)
    return True


def godot_smoke(d: Path, *, host: str, token: str, world: str, line: str, timeout: float = 180) -> dict[str, Any]:
    """``godot --headless -s tests/smoke.gd``: one real line through the client node into the bound run."""
    b = godot_bin()
    if b is None:
        raise FrontendError("Godot not found (set GODOT=/path/to/godot)")
    script = d / "tests" / "smoke.gd"
    if not script.is_file():
        raise FrontendError("this front end has no tests/smoke.gd")
    try:
        r = subprocess.run([b, "--headless", "--path", str(d), "-s", "tests/smoke.gd"], env=_env(host, token, world, line),
                           capture_output=True, text=True, timeout=timeout)
        out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
    except subprocess.TimeoutExpired as e:
        out, code = str(e.stdout or "") + f"\n(timed out after {timeout:.0f} s)", -1
    out = out.replace(token, "<token>") if token else out
    keep = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith(("Godot Engine v", "WARNING: ")) ]
    return {"ok": code == 0, "code": code, "output": "\n".join(keep)[-6000:],
            "connected": next((ln for ln in keep if ln.startswith("connected")), ""),
            "turn": next((ln for ln in keep if ln.startswith("turn ")), ""),
            "events": next((ln for ln in keep if ln.startswith("beat events")), ""),
            "streamed": next((ln for ln in keep if ln.startswith("streamed")), "")}


# ── the front-end agent ──────────────────────────────────────────────────────

_FILE_RE = re.compile(r'<file path="([^"]+)">\n?(.*?)\n?</file>', re.S)
_DEL_RE = re.compile(r'<delete path="([^"]+)"\s*/>')
_READ_RE = re.compile(r'<read path="([^"]+)"\s*/>')
_BUDGET = 60_000


def _contract_summary(t: Any | None) -> str:
    if t is None:
        return "(no world)"
    from neonrp.template import v3

    try:
        with v3._scratch(t, None) as root:
            c = v3.contract(t, root)
    except Exception:  # noqa: BLE001
        return "(the contract does not build — see the template lint)"
    return json.dumps({"world": c.get("world"), "beat_events": c.get("beat_events"), "events": c.get("events"),
                       "vars": [v["name"] for v in c.get("vars") or []][:80], "views": [v.get("id") for v in c.get("views") or []],
                       "slots": [s["id"] for s in c.get("slots") or []][:80], "hash": c.get("hash")}, ensure_ascii=False)


def _files_block(d: Path) -> str:
    parts, used = [], 0
    rows = tree(d)
    for r in rows:
        try:
            txt = read(d, r["path"]) if r["size"] <= 40_000 else None
        except (FrontendError, FileNotFoundError):
            txt = None
        if txt is not None and used + len(txt) <= _BUDGET:
            parts.append(f'<file path="{r["path"]}">\n{txt}\n</file>')
            used += len(txt)
        else:
            parts.append(f'- {r["path"]} ({r["size"]} bytes, not shown — <read path="{r["path"]}"/> to see it)')
    return "\n".join(parts) or "(empty)"


def agent(d: Path, info: dict[str, Any], t: Any | None, text: str, *, history: list[dict[str, str]] | None = None,
          adapter: Any = None, root: Path | None = None, lang: str | None = None) -> Iterator[tuple[str, dict[str, Any]]]:
    """One turn: yields (event, data) — chunk {text} · tool_use {name, path} · done {assistant_message, wrote} · error {error}."""
    from neonrp.core.llm import Message

    if adapter is None:
        from neonrp.core.config import load_config, resolve_provider
        from neonrp.core.llm import get_adapter_from_config

        adapter = get_adapter_from_config(resolve_provider(load_config(root or d), None, None))
    from neonrp import prompts

    sysm = prompts.fill("frontend_agent", lang or "zh", kind=info.get("kind") or "?", title=info.get("title") or info.get("id"),
                        contract=_contract_summary(t), files=_files_block(d))
    msgs = [Message(role="system", content=sysm)]
    for h in (history or [])[-8:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append(Message(role=h["role"], content=str(h["content"])[:8000]))
    msgs.append(Message(role="user", content=text))
    reply = ""
    for _ in range(4):
        reply = ""
        for ch in adapter.chat_stream(msgs, tools=None):
            if getattr(ch, "error", None):
                yield "error", {"error": str(ch.error)}
                return
            if ch.delta:
                reply += ch.delta
                yield "chunk", {"text": ch.delta}
        reads = _READ_RE.findall(reply)
        if reads and not _FILE_RE.search(reply):
            got = []
            for rel in reads[:8]:
                yield "tool_use", {"name": "read_file", "path": rel}
                try:
                    got.append(f'<file path="{rel}">\n{read(d, rel)[:_BUDGET]}\n</file>')
                except (FrontendError, FileNotFoundError) as e:
                    got.append(f'<missing path="{rel}">{e}</missing>')
            msgs += [Message(role="assistant", content=reply), Message(role="user", content="\n".join(got))]
            continue
        break
    wrote: list[str] = []
    for rel, body in _FILE_RE.findall(reply):
        try:
            write(d, rel, body if body.endswith("\n") else body + "\n")
            wrote.append(rel)
            yield "tool_use", {"name": "write_file", "path": rel}
        except FrontendError as e:
            yield "tool_use", {"name": "write_file", "path": rel, "error": str(e)}
    for rel in _DEL_RE.findall(reply):
        try:
            if delete(d, rel):
                yield "tool_use", {"name": "delete_file", "path": rel}
        except FrontendError:
            pass
    wrote_w = str(words(lang)["wrote"])
    prose = _DEL_RE.sub("", _FILE_RE.sub(lambda m: wrote_w.replace("{path}", m.group(1)), reply)).strip()
    yield "done", {"assistant_message": prose, "wrote": wrote}
