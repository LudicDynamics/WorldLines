"""Talking with a character outside its world (10-15, niko · PLATFORM-PLAY-RULES §3; the chat-fe phone screen).

    GET  /api/v1/chat/souls[?lang=]                 → {souls: [{tpl, sid, name, avatar_url, standalone, obtained, talked,
                                                        memory: full|trial, last: {from, kind, text, at} | null}]}
    GET  /api/v1/chat/thread?tpl=&sid=[&lang=]      → {soul: {tpl, sid, name, avatar_url, tagline, lang},
                                                        access: standalone|obtained|locked, memory, messages, stickers: {soul: […]}}
    POST /api/v1/chat/send {tpl, sid, lang?, kind: text|sticker, text?|sticker?}
                                                    → 200 {messages: [the character's bubbles: text / sticker]}
                                                      403 locked · 404 no such character · 409 still answering · 502 model error
    GET  /api/v1/chat/sticker?tpl=&sid=&id=         a character's own sticker image (``stickers/<id>.png`` in its folder)
    POST /api/v1/chat/greet {tpl, sid, lang?}       → {messages: [her opening line(s), the last with ``suggest``: [3 replies]]}
                                                      — only on an empty thread, written once (:func:`greet`, 10-17)
    POST /api/v1/chat/presence {tpl, sid, lang?, typing?} → {messages, online} — the phone's heartbeat while this thread is
                                                      open and visible; a plugin may answer with her messages (:func:`presence`, 10-19)
    GET  /api/v1/chat/world_card?run=&id=         a world result a message carries (:func:`world_card`, 10-21)
    GET/POST /api/v1/chat/subscription {tpl, sid, on?, cadence?} · POST /api/v1/chat/catchup {tpl, sid}
                                                    → a plugin's answer (the phone orchestration: following a character,
                                                      her owed turns, catching up in order; 404 without one, 10-21)
    POST /api/v1/chat/answer {tpl, sid, id, answer: yes|no}
                                                    → {message, messages} — the player answers a message that waits for
                                                      one (``status: open``, a plugin's; :func:`answer`, 10-18)

Who can be talked to: a character whose author let it go on its own (``standalone``), or one the player has taken home
(core/player_data ``characters``). What it knows: its own folder — soul.md, persona, background, profile, its memos —
from the run it was taken from (a snapshot made when it was taken: ``memory: full``) or, not taken yet, the template's
(``memory: trial``); and the thread itself. The thread lives with the player (``~/.worldlines/player-data/<player>/chats``),
never in a template. One model call per message on the player's provider (metered like a turn). The first time the
player talks with a standalone character it is noted in ``talked`` — not gained.

Stickers: the built-in set ``wl:<id>`` (:data:`STICKERS`, drawn by the front end) and a character's own ``soul:<id>``.

Three kinds of character (niko 10-16, hybrid): one in the character library that no world links (``tpl = "lib:<folder>"``:
the player's own, always open, its memory is that folder) · one a world lets talk on its own (``standalone``) · one a world
lets the player take home (``takeable``, open once gained). :func:`catalog` lists all three for the bench and the phone.
How a character answers is its orchestration graph's chat node (core/soul_orchestration: history · docs · tools), read
from where it comes from (its folder · the template's override), never from the player's snapshot — memory stays put.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STICKERS = ("hello", "happy", "laugh", "shy", "love", "thanks", "ok", "think", "surprised", "sad", "cry", "angry", "sleepy",
            "sorry", "cheer", "bye")
DOC_FILES = ("soul.md", "persona", "background", "character/profile.json", "long-term-memo", "short-term-memo")
DOC_CAP = 9000
HISTORY = 24
_BUSY: dict[str, threading.Lock] = {}
_BUSY_LOCK = threading.Lock()


class ChatError(Exception):
    def __init__(self, status: int, msg: str, extra: dict[str, Any] | None = None):
        super().__init__(msg)
        self.status, self.extra = status, extra or {}


def _T(lang: str) -> dict[str, Any]:
    from neonrp.prompts import strings

    return strings("soul_chat", lang)


def _lang(lang: str | None, fallback: str = "zh") -> str:
    from neonrp.core.output_lang import normalize_prompt_lang

    return normalize_prompt_lang(lang) if lang else fallback


def _pick(v: Any, lang: str) -> str:
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("en") or v.get("zh") or next(iter(v.values()), "") or "")
    return str(v or "")


# ── who ──────────────────────────────────────────────────────────────────────

LIB = "lib:"


def library_souls() -> dict[str, dict[str, Any]]:
    """folder name → {dir, sj} for every soul in the character library (``~/.worldlines/souls``)."""
    from neonrp.core import souls as _souls

    out: dict[str, dict[str, Any]] = {}
    home = _souls.SOUL_HOME
    if not home.is_dir():
        return out
    for d in sorted(home.iterdir()):
        sj: Any = None
        try:
            sj = json.loads((d / "soul.json").read_text(encoding="utf-8")) if d.is_dir() and not d.name.startswith(".") else None
        except (OSError, ValueError):
            sj = None
        if isinstance(sj, dict) and sj.get("sid"):
            out[d.name] = {"dir": d, "sj": sj}
    return out


def template_souls() -> dict[tuple[str, str], dict[str, Any]]:
    """(tpl, sid) → {dir, sj, standalone, lang} for every soul every template in the store carries."""
    from neonrp import template as TP

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for tid, d in TP.discover().items():
        try:
            t = TP.load(d)
        except TP.TemplateError:
            continue
        for p in t.soul_files():
            try:
                sj = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(sj, dict) and sj.get("sid") and (tid, str(sj["sid"])) not in out:
                out[(tid, str(sj["sid"]))] = {"dir": p.parent, "sj": sj, "standalone": sj.get("standalone") is True,
                                              "lang": str(t.card.get("lang") or t.lang or "zh"), "t": t}
        for eid, e in plot_npcs(t).items():  # a plot's character without a soul folder (the creation desk's mine_N01, 10-18)
            if (tid, eid) not in out:
                lang = str(t.card.get("lang") or t.lang or "zh")
                out[(tid, eid)] = {"dir": npc_dir(tid, eid, e, lang), "sj": {"sid": eid, "name": e["name"], "name_local": e["name"], "source_lang": lang},
                                   "standalone": False, "lang": lang, "t": t, "npc": True}
    return out


def plot_npcs(t: Any) -> dict[str, dict[str, str]]:
    """entry id → {name, persona, appearance} of the template's plot entries of class ``npc`` (``plots/<id>/plot.json``)."""
    out: dict[str, dict[str, str]] = {}
    for rel in getattr(t, "plots", None) or []:
        try:
            d = json.loads((Path(t.dir) / str(rel) / "plot.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for eid, e in ((d.get("entries") or {}) if isinstance(d, dict) else {}).items():
            if isinstance(e, dict) and e.get("class") == "npc" and str(e.get("name") or "").strip():
                props = e.get("props") if isinstance(e.get("props"), dict) else {}
                out[str(eid)] = {"name": str(e["name"]).strip(), **{k: str(props[k]) for k in ("persona", "appearance") if props.get(k)}}
    return out


def npc_dir(tpl: str, eid: str, e: dict[str, str], lang: str) -> Path:
    """A plot character's folder, kept with the player (``npcs/<template>/<entry id>``): its ``soul.md`` is what the plot
    says of it (rewritten when that changes); its memory (a tick's doings, a world's news) grows there."""
    d = _player_dir() / "npcs" / _safe(tpl) / _safe(eid)
    body = "\n\n".join(x for x in (f"# {e['name']}", e.get("persona") or "", e.get("appearance") or "") if x).strip() + "\n"
    try:
        p = d / "soul.md"
        if not p.is_file() or p.read_text(encoding="utf-8") != body:
            d.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
            (d / "soul.json").write_text(json.dumps({"sid": eid, "name": e["name"], "name_local": e["name"], "source_lang": lang},
                                                    ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass
    return d


def _player_dir() -> Path:
    from neonrp.core import player_data

    return player_data.HOME / player_data.player_id()


def snapshot_dir(tpl: str, sid: str) -> Path:
    """Where a taken character's folder (its memory from that run) is kept for the player."""
    return _player_dir() / "souls" / _safe(tpl) / _safe(sid)


def _safe(s: str) -> str:
    return "".join(c for c in str(s) if c.isalnum() or c in "-_.") or "_"


def _obtained(tpl: str, sid: str) -> dict[str, Any] | None:
    from neonrp.core import player_data

    return next((c for c in player_data.read()["characters"] if c.get("world") == tpl and c.get("sid") == sid), None)


def _talked(tpl: str, sid: str) -> bool:
    from neonrp.core import player_data

    return any(c.get("world") == tpl and c.get("sid") == sid for c in player_data.read()["talked"])


def resolve(tpl: str, sid: str) -> dict[str, Any]:
    """The character and what the player may do with it; ChatError(404) when no template carries it.
    ``tpl = "lib:<folder>"`` = a character in the library: the player's own, open, its memory is its folder."""
    if tpl.startswith(LIB):
        lib = library_souls().get(tpl[len(LIB):])
        if lib is None or (sid and str(lib["sj"].get("sid")) != sid):
            raise ChatError(404, "no such character")
        return {**lib, "standalone": False, "lang": str(lib["sj"].get("source_lang") or "zh"), "t": None, "tpl": tpl,
                "sid": str(lib["sj"]["sid"]), "access": "library", "memory": "full", "folder": lib["dir"]}
    src = template_souls().get((tpl, sid))
    got = _obtained(tpl, sid)
    snap = snapshot_dir(tpl, sid)
    if src is None and got and (snap / "soul.json").is_file():  # its template is gone: the snapshot carries it (10-20)
        try:
            sj = json.loads((snap / "soul.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sj = {"sid": sid}
        lang = str(sj.get("source_lang") or "zh")
        try:
            lang = str(json.loads((snap / ".wl" / "snapshot.json").read_text(encoding="utf-8")).get("lang") or lang)
        except (OSError, ValueError):
            pass
        return {"dir": snap, "sj": sj, "standalone": sj.get("standalone") is True, "lang": lang, "t": None, "tpl": tpl, "sid": sid,
                "access": "obtained", "memory": "full", "folder": snap, "orphan": True}
    if src is None:
        raise ChatError(404, "no such character")
    access = "obtained" if got else ("standalone" if src["standalone"] else "locked")
    return {**src, "tpl": tpl, "sid": sid, "access": access, "memory": "full" if got else "trial",
            "folder": snap if got and (snap / "soul.json").is_file() else src["dir"]}


def _name(sj: dict[str, Any], lang: str) -> str:
    """Her name in ``lang``: ``name_i18n``, else the local name in the world's own language, else the latin ``name``."""
    own = _pick(sj.get("name_i18n"), lang) if isinstance(sj.get("name_i18n"), dict) and sj["name_i18n"].get(lang) else ""
    src = str(sj.get("source_lang") or "zh")
    local, latin = str(sj.get("name_local") or ""), str(sj.get("name") or "")
    return own or (local if lang == src or lang in ("zh", "ja") and not latin else latin) or local or latin or str(sj.get("sid") or "")


def _cname(c: dict[str, Any], lang: str) -> str:
    """Her name in ``lang`` for a template's character: the template's own translations first (template.i18n.soul_names —
    glossary · name_i18n · the foreign layer's soul.json; the Hub's Souls page uses the same, web-create 10-23: ja / ko got
    the English name although the layer has its own), then :func:`_name` (a missing language falls back to English)."""
    sj, t = c["sj"], c.get("t")
    if t is not None:
        try:
            from neonrp.template import i18n

            n = i18n.soul_names(t, {str(c["sid"]): str(sj.get("name_local") or sj.get("name") or "")}).get(str(c["sid"])) or {}
            if n.get(lang):
                return n[lang]
            if lang != str(sj.get("source_lang") or "zh") and n.get("en") and not (isinstance(sj.get("name_i18n"), dict) and sj["name_i18n"].get(lang)):
                return n["en"]
        except Exception:  # noqa: BLE001 — a name is a label: the soul.json's own still answers
            pass
    return _name(sj, lang)


def _avatar(tpl: str, sid: str) -> str:
    if tpl.startswith(LIB):
        return f"/api/v1/local/souls/{tpl[len(LIB):]}/portrait"
    if _obtained(tpl, sid):  # 10-20: a taken character shows its own picture (it changes only with the author's update)
        from neonrp.core import soul_update

        pic = soul_update.portrait(snapshot_dir(tpl, sid))
        if pic is not None:
            return f"/api/v1/local/player-data/souls/{tpl}/{sid}/file?side=mine&f=assets/{pic.name}"
    return f"/api/v1/local/templates/{tpl}/assets/file?slot=soul.portrait:{sid}"


def world_title(c: dict[str, Any], lang: str) -> str:
    """The world it comes from, as the player's language titles it (template i18n card)."""
    from neonrp.template import i18n

    if c.get("t") is None:
        return ""
    try:
        return str(i18n.card(c["t"], lang).get("title") or c["t"].card.get("title") or c["tpl"])
    except Exception:  # noqa: BLE001 — a title is a label, never a failure
        return str(c["tpl"])


def soul_card(c: dict[str, Any], lang: str) -> dict[str, Any]:
    from neonrp.core import fallback_art

    sj = c["sj"]
    tagline = _pick(sj.get("intro_i18n") or sj.get("summary_i18n"), lang)
    av = _avatar(c["tpl"], c["sid"])
    return {"tpl": c["tpl"], "sid": c["sid"], "name": _cname(c, lang), "avatar_url": av,
            "avatar_thumb_url": av + ("&w=256" if "?" in av else ""), "tagline": tagline,
            "portrait_fallback": fallback_art.soul_dir(c.get("dir"), sj),  # the picture does not load: which silhouette (10-17)
            "world": world_title(c, lang), "lang": lang}


# ── the thread ───────────────────────────────────────────────────────────────

def _thread_path(tpl: str, sid: str) -> Path:
    if tpl.startswith(LIB):
        return _player_dir() / "chats" / f"lib__{_safe(tpl[len(LIB):])}__{_safe(sid)}.jsonl"
    return _player_dir() / "chats" / f"{_safe(tpl)}__{_safe(sid)}.jsonl"


def read_thread(tpl: str, sid: str) -> list[dict[str, Any]]:
    p = _thread_path(tpl, sid)
    try:
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def _append(tpl: str, sid: str, msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    p = _thread_path(tpl, sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = len(read_thread(tpl, sid))
    out = []
    with p.open("a", encoding="utf-8") as fh:
        for k, m in enumerate(msgs):
            rec = {"id": f"m{n + k + 1}", **m, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.append(rec)
    return out


def sticker_dir(c: dict[str, Any]) -> Path:
    """A character's own stickers are pictures its author made, not memory: read from where it comes from (its folder in
    the template / the library), the player's snapshot only when the source has none (10-16)."""
    # 10-20: a taken character's stickers are the player's (they change only when the player takes the author's update)
    order = (c["folder"], c["dir"]) if c.get("access") == "obtained" else (c["dir"], c["folder"])
    for d in (Path(order[0]) / "stickers", Path(order[1]) / "stickers"):
        if d.is_dir():
            return d
    return Path(c["dir"]) / "stickers"


def sticker_meta(d: Path) -> dict[str, Any]:
    """``stickers/stickers.json`` — ``{<id>: {label: {zh, en, ja, ko} | str, when: "<when to send it>"}}``: what each one
    means, for the picker (label in the chat's language) and for the model (label + when)."""
    try:
        m = json.loads((d / "stickers.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        m = {}
    return {str(k): v for k, v in m.items() if isinstance(v, dict)} if isinstance(m, dict) else {}


def soul_stickers(c: dict[str, Any], lang: str | None = None) -> list[dict[str, str]]:
    from urllib.parse import quote

    d = sticker_dir(c)
    if not d.is_dir():
        return []
    meta, lg = sticker_meta(d), _lang(lang, c["lang"])
    out = []
    for p in sorted(d.glob("*.png")):
        m = meta.get(p.stem) or {}
        when = str(m.get("when") or "").strip()[:120]
        out.append({"id": f"soul:{p.stem}", "label": _pick(m.get("label"), lg) or p.stem,
                    "url": f"/api/v1/chat/sticker?tpl={quote(c['tpl'])}&sid={quote(c['sid'])}&id={p.stem}", **({"when": when} if when else {})})
    return out


def sticker_file(tpl: str, sid: str, sid_sticker: str) -> Path | None:
    c = resolve(tpl, sid)
    d = sticker_dir(c).resolve()
    p = (d / f"{_safe(sid_sticker)}.png").resolve()
    return p if p.is_file() and p.is_relative_to(d) else None


def thread(tpl: str, sid: str, lang: str | None = None) -> dict[str, Any]:
    c = resolve(tpl, sid)
    lg = _lang(lang, c["lang"])
    return {"soul": soul_card(c, lg), "access": c["access"], "memory": c["memory"], "messages": read_thread(tpl, c["sid"]),
            "stickers": {"soul": soul_stickers(c, lg) if "sticker" in (chat_node(c).get("tools") or []) else []}}


def graph_of(c: dict[str, Any]) -> dict[str, Any]:
    """This character's orchestration graph: from where it comes from (its own folder · the template's override for this
    world), never the player's snapshot — an edited graph reaches a character already taken home, its memory untouched."""
    from neonrp.core import soul_orchestration as SO

    t = c.get("t")
    g = SO.graph(Path(c["dir"]), Path(t.dir) if t is not None else None, c["sid"])
    kept = Path(c["folder"]) / ".wl" / "orchestration.json"
    if t is None and c.get("orphan") and kept.is_file():  # the template is gone: the graph the snapshot kept (core/soul_update)
        try:
            g = {**json.loads(kept.read_text(encoding="utf-8")), "schema": g.get("schema"), "subject": g.get("subject")}
        except (OSError, ValueError):
            pass
    return g


def chat_node(c: dict[str, Any]) -> dict[str, Any]:
    """The node that answers the phone (core/soul_orchestration.chat_node); the default chat when the graph has none."""
    from neonrp.core import soul_orchestration as SO

    return SO.chat_node(graph_of(c)) or SO.chat_node(SO.default_graph())


def souls(lang: str | None = None) -> dict[str, Any]:
    """The characters the player can talk to, or has: standalone · taken home · talked with."""
    from neonrp.core import player_data

    pd = player_data.read()
    got = {(c.get("world"), c.get("sid")) for c in pd["characters"]}
    talked = {(c.get("world"), c.get("sid")) for c in pd["talked"]}
    out: list[dict[str, Any]] = []
    for (tpl, sid), src in sorted(template_souls().items()):
        if not (src["standalone"] or (tpl, sid) in got or (tpl, sid) in talked):
            continue
        c = resolve(tpl, sid)
        lg = _lang(lang, src["lang"])
        msgs = read_thread(tpl, sid)
        last = msgs[-1] if msgs else None
        out.append({**{k: v for k, v in soul_card(c, lg).items() if k in ("tpl", "sid", "name", "avatar_url", "avatar_thumb_url", "portrait_fallback", "world")},
                    "standalone": src["standalone"], "obtained": (tpl, sid) in got, "talked": (tpl, sid) in talked,
                    "memory": c["memory"], "_official": src["t"].zone == "reviewed",
                    "last": {k: last.get(k) for k in ("from", "kind", "text", "sticker", "at") if last.get(k) is not None} if last else None})
    srcs = template_souls()
    for tpl, sid in sorted(k for k in got if k not in srcs and (snapshot_dir(*k) / "soul.json").is_file()):
        c = resolve(str(tpl), str(sid))  # taken from a template that is gone: still the player's (10-20)
        lg = _lang(lang, c["lang"])
        msgs = read_thread(str(tpl), str(sid))
        last = msgs[-1] if msgs else None
        out.append({**{k: v for k, v in soul_card(c, lg).items() if k in ("tpl", "sid", "name", "avatar_url", "avatar_thumb_url", "portrait_fallback", "world")},
                    "standalone": c["standalone"], "obtained": True, "talked": (tpl, sid) in talked, "memory": c["memory"], "_official": False,
                    "last": {k: last.get(k) for k in ("from", "kind", "text", "sticker", "at") if last.get(k) is not None} if last else None})
    rows = _one_each(out) + _library_rows(lang)
    from neonrp.core import node_kinds

    if node_kinds.hooks("phone_row"):  # a plugin's word on each row (the phone orchestration: followed? turns owed?)
        for r in rows:
            try:
                c = resolve(r["tpl"], "" if str(r["tpl"]).startswith(LIB) else r["sid"])
            except ChatError:
                continue
            got = next((x for x in node_kinds.call_all("phone_row", c) if isinstance(x, dict)), None)
            if got:
                r["phone"] = got
    return {"souls": rows}


def _library_rows(lang: str | None) -> list[dict[str, Any]]:
    """The character library's own (the player's, open): listed after the worlds' characters, one row each."""
    rows = []
    for name in library_souls():
        c = resolve(LIB + name, "")
        lg = _lang(lang, c["lang"])
        msgs = read_thread(c["tpl"], c["sid"])
        last = msgs[-1] if msgs else None
        rows.append({**{k: v for k, v in soul_card(c, lg).items() if k in ("tpl", "sid", "name", "avatar_url", "avatar_thumb_url", "portrait_fallback", "world")},
                     "standalone": False, "obtained": False, "talked": False, "library": True, "memory": "full",
                     "last": {k: last.get(k) for k in ("from", "kind", "text", "sticker", "at") if last.get(k) is not None} if last else None})
    return rows


def _one_each(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One character carried by several templates (the same sid and name — the four Stoneford templates' Elena) is
    listed once (lead 10-15): every copy the player has touched (gained — the world it was gained in —, talked with, or
    has a thread with); none touched → the officially listed world's copy (template ``zone: reviewed``), else the
    first template's. Other variants are not listed."""
    def touched(r: dict[str, Any]) -> bool:
        return bool(r["obtained"] or r["talked"] or r["last"])

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["sid"], r["name"]), []).append(r)
    keep = set()
    for g in groups.values():
        hit = [r for r in g if touched(r)] or [next((r for r in g if r["_official"]), g[0])]
        keep |= {id(r) for r in hit}
    return [{k: v for k, v in r.items() if k != "_official"} for r in rows if id(r) in keep]


# ── one message ──────────────────────────────────────────────────────────────

def _docs(folder: Path, docs: Any = DOC_FILES, cap: int = DOC_CAP) -> str:
    parts: list[str] = []
    for rel in [str(x) for x in (docs if isinstance(docs, (list, tuple)) else DOC_FILES)]:
        if ".." in Path(rel).parts:
            continue
        p = folder / rel
        files = sorted(x for x in p.rglob("*") if x.is_file() and x.suffix in (".md", ".json", ".txt")) if p.is_dir() else ([p] if p.is_file() else [])
        for f in files:
            try:
                t = f.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if t:
                parts.append(f"## {f.relative_to(folder)}\n{t}")
    return "\n\n".join(parts)[:max(0, int(cap or DOC_CAP))]


def _adapter(rt: Any = None) -> Any:
    """The player's model: the bound run's provider when there is one (what its turns use), else the user's default."""
    if rt is not None:
        from neonrp.core.more_choices import _adapter as run_adapter

        return run_adapter(rt.root)
    from neonrp.core.hub_publish import adapter_for_preset

    return adapter_for_preset(None)


def _parse(raw: str, own: set[str], *, stickers: bool = True, most: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln in str(raw or "").splitlines():
        t = ln.strip()
        if not t:
            continue
        m = re.fullmatch(r"\[\s*sticker\s+((?:wl|soul):[\w-]+)\s*\]", t, re.IGNORECASE)
        if m:
            sid = m.group(1).lower()
            if stickers and ((sid.startswith("wl:") and sid[3:] in STICKERS) or sid in own):
                out.append({"from": "soul", "kind": "sticker", "sticker": sid})
            continue
        if re.fullmatch(r"\[\s*~?\s*image\b[^\]]*\]", t, re.IGNORECASE):  # image.generate is an interface only (10-16): never shown as text
            continue
        t = re.sub(r"\[\s*sticker[^\]]*\]", "", t).strip()
        if t:
            out.append({"from": "soul", "kind": "text", "text": t[:600]})
        if len(out) >= max(1, most):
            break
    return out


def send(tpl: str, sid: str, *, kind: str = "text", text: str = "", sticker: str = "", lang: str | None = None, rt: Any = None,
         adapter: Any = None) -> dict[str, Any]:
    c = resolve(tpl, sid)
    if c["access"] == "locked":
        raise ChatError(403, "this character has not left its world for you yet")
    sid = c["sid"]
    lg = _lang(lang, c["lang"])
    T = _T(lg)
    node = chat_node(c)   # how it answers: its orchestration graph's chat node (history · docs · tools · bubbles)
    can_sticker = "sticker" in (node.get("tools") or [])
    if kind == "sticker":
        if not sticker:
            raise ChatError(400, "sticker required")
        mine = {"from": "me", "kind": "sticker", "sticker": str(sticker)}
        said = str(T["player_sticker"]).format(label=(T.get("stickers") or {}).get(str(sticker)[3:], str(sticker)))
    else:
        if not str(text or "").strip():
            raise ChatError(400, "text required")
        mine = {"from": "me", "kind": "text", "text": str(text).strip()[:2000]}
        said = mine["text"]
    key = f"{tpl}/{sid}"
    with _BUSY_LOCK:
        lock = _BUSY.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        raise ChatError(409, "still answering")
    try:
        name = _cname(c, lg)
        mine_st = soul_stickers(c, lg) if can_sticker else []
        own = {s["id"] for s in mine_st}
        labels = T.get("stickers") or {}
        sticker_list = ("、".join(f"wl:{s}({labels.get(s, s)})" for s in STICKERS)
                        + "".join(f"、{s['id']}({s['label']}{' · ' + s['when'] if s.get('when') else ''})" for s in mine_st)) if can_sticker else "—"
        system = str(T["system"]).format(name=name, docs=_docs(Path(c["folder"]), node.get("docs"), int(node.get("doc_cap") or DOC_CAP)), stickers=sticker_list)
        from neonrp.core import node_kinds

        system += "".join(str(x) for x in node_kinds.call_all("chat_system", c, node, lg))  # a plugin's own rule (10-18)
        keep = max(0, int(node.get("history") if node.get("history") is not None else HISTORY))
        hist = [m for m in read_thread(tpl, sid) if m.get("kind") != "answer"][-keep:] if keep else []
        lines = [str(T["line_me"] if m.get("from") == "me" else T["line_soul"]).format(
            name=name, text=m.get("text") or (T["sticker_said"].format(id=m.get("sticker")))) for m in hist]
        user = str(T["user"]).format(history="\n".join(lines) or T["none"], text=said, name=name)
        t0 = time.monotonic()
        try:
            from neonrp.core.llm import Message

            ad = adapter or _adapter(rt)
            out = ad.chat([Message(role="system", content=system), Message(role="user", content=user)])
        except ChatError:
            raise
        except Exception as exc:  # noqa: BLE001 — no model set up / transport failure: an answer, never a crash
            raise ChatError(502, str(exc)[:300]) from exc
        err = getattr(out, "error", None)
        if err:
            from neonrp.core import billing_stop

            stop = billing_stop.remember(billing_stop.from_text(err))
            raise ChatError(502, str(err)[:300], {"billing": stop.to_dict()} if stop else {})
        from neonrp.core.soul_result import clean_line

        raw = clean_line(str(getattr(getattr(out, "message", None), "content", None) or ""))
        extra: list[dict[str, Any]] = []
        for _kind, fn in node_kinds.hooks("chat_reply"):  # each plugin takes its own lines out of what the one before left
            try:
                r = fn(c, node, raw, lg)
            except Exception:  # noqa: BLE001 — a plugin never breaks the reply
                logger.warning("chat_reply of %s failed", _kind, exc_info=True)
                continue
            if isinstance(r, tuple) and len(r) == 2:
                raw, extra = str(r[0]), extra + [{"from": "soul", **m} for m in r[1] if isinstance(m, dict)]
        msgs = _parse(raw, own, stickers=can_sticker, most=int(node.get("max_bubbles") or 5)) + extra
        if not msgs:
            raise ChatError(502, "empty reply")
        _append(tpl, sid, [mine])
        saved = _append(tpl, sid, msgs)
        if c["access"] == "standalone" and not _talked(tpl, sid):
            from neonrp.core import player_data

            player_data._add("talked", {"sid": sid, "name": name, "world": tpl}, ("sid", "world"))
        node_kinds.call_all("chat_sent", c, node, saved, adapter=ad, lang=lg)
        return {"messages": saved, "usage": dict(getattr(out, "usage", None) or {}), "ms": round((time.monotonic() - t0) * 1000)}
    finally:
        lock.release()


# ── the player is on the phone with her (10-19 niko: 连线的时候对方知道玩家在线) ───────────────────────────────

def presence(tpl: str, sid: str, *, typing: bool = False, lang: str | None = None, rt: Any = None, now: float | None = None) -> dict[str, Any]:
    """A heartbeat from the phone while this thread is open and visible (``POST /api/v1/chat/presence``): the player is
    online with her now (``typing`` = writing at this moment). Kept with the player (``presence.json``: when last seen,
    when last typing); a plugin's ``chat_online`` may answer with her messages (an online message is not a tick: it
    writes only the thread). Hidden / closed = no heartbeat = offline. Busy answering = nothing this time."""
    from neonrp.core import node_kinds

    c = resolve(tpl, sid)
    if c["access"] == "locked":
        raise ChatError(403, "this character has not left its world for you yet")
    sid = c["sid"]
    now = time.time() if now is None else float(now)
    p = _player_dir() / "presence.json"
    try:
        db = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        db = {}
    db = db if isinstance(db, dict) else {}
    key = f"{tpl}/{sid}"
    was = db.get(key) if isinstance(db.get(key), dict) else {}
    db[key] = {"at": now, **({"typing_at": now} if typing else ({"typing_at": was["typing_at"]} if was.get("typing_at") else {}))}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(db, ensure_ascii=False) + "\n", encoding="utf-8")
    with _BUSY_LOCK:
        lock = _BUSY.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        return {"messages": [], "online": True}
    try:
        lg = _lang(lang, c["lang"])
        st = {"now": now, "typing": bool(typing), "seen_before": was.get("at"), "typing_at": db[key].get("typing_at")}
        out: list[dict[str, Any]] = []
        for r in node_kinds.call_all("chat_online", c, st, rt=rt, lang=lg):
            out += [{"kind": "text", **m, "from": "soul", "origin": "online"} for m in (r if isinstance(r, list) else []) if isinstance(m, dict) and m.get("text")]
        return {"messages": _append(tpl, sid, out) if out else [], "online": True}
    finally:
        lock.release()


# ── subscribing to a character · catching up on her ticks (10-21: the phone orchestration's, a plugin answers) ──

def _plugin_answer(hook: str, tpl: str, sid: str, *args: Any, **kw: Any) -> dict[str, Any]:
    from neonrp.core import node_kinds

    c = resolve(tpl, sid)
    for r in node_kinds.call_all(hook, c, *args, **kw):
        if isinstance(r, dict):
            return r
    raise ChatError(404, "no phone orchestration on this engine")


def subscription(tpl: str, sid: str, body: dict[str, Any] | None = None, *, lang: str | None = None) -> dict[str, Any]:
    """``GET`` (body None) / ``POST`` /api/v1/chat/subscription — whether the player follows this character (her own
    life between chats), how often, how many of her turns are owed; a plugin's (``phone_subscription``). 404 without."""
    return _plugin_answer("phone_subscription", tpl, sid, body, lang=lang)


def catchup(tpl: str, sid: str, *, lang: str | None = None, rt: Any = None) -> dict[str, Any]:
    """``POST`` /api/v1/chat/catchup — run what is owed, in order (a plugin's: ``phone_catchup``). 404 without."""
    return _plugin_answer("phone_catchup", tpl, sid, lang=lang, rt=rt)


def world_card(run: str, rid: str) -> dict[str, Any]:
    """One world result of a run in the player's plays folder (core/world_exec), for a message that carries it. 404
    when there is no such run or result."""
    from neonrp import worlds
    from neonrp.core import world_exec

    home = Path(worlds.PLAYS_HOME)
    d = (home / _safe(run)).resolve()
    if not d.is_dir() or not d.is_relative_to(home.resolve()):
        raise ChatError(404, "no such run")
    hit = next((x for x in reversed(world_exec.results(d, last=0)) if x.get("id") == rid), None)
    if hit is None:
        raise ChatError(404, "no such world card")
    return hit


# ── a message the player answers (10-18) ─────────────────────────────────────────────────────────────────────────

def answer(tpl: str, sid: str, mid: str, answer: str) -> dict[str, Any]:
    """The player answers a message that waits for one (``status: open`` — a plugin's message, e.g. a small invitation):
    its status becomes accepted / declined and the answer is kept in the thread (``kind: answer``, ``ref``). Nothing else
    happens here; what an answer means is the plugin's."""
    c = resolve(tpl, sid)
    if c["access"] == "locked":
        raise ChatError(403, "this character has not left its world for you yet")
    sid = c["sid"]
    if answer not in ("yes", "no"):
        raise ChatError(400, "answer is yes or no")
    with _BUSY_LOCK:
        lock = _BUSY.setdefault(f"{tpl}/{sid}", threading.Lock())
    if not lock.acquire(blocking=False):
        raise ChatError(409, "still answering")
    try:
        msgs = read_thread(tpl, sid)
        hit = next((m for m in msgs if m.get("id") == mid and m.get("from") == "soul" and "status" in m), None)
        if hit is None:
            raise ChatError(404, "no such message to answer")
        if hit.get("status") != "open":
            raise ChatError(409, "already answered")
        hit["status"] = "accepted" if answer == "yes" else "declined"
        _thread_path(tpl, sid).write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in msgs), encoding="utf-8")
        rec = _append(tpl, sid, [{"from": "me", "kind": "answer", "ref": mid, "answer": answer, "of": hit.get("kind"), "text": hit.get("text") or ""}])
        return {"message": hit, "messages": rec}
    finally:
        lock.release()


# ── the first time (10-17, niko: 头几条要有引导) ─────────────────────────────

def _own_greeting(sj: dict[str, Any], lang: str) -> str:
    """Her opening line as her author wrote it: ``greeting_i18n`` (per language) or ``greeting`` in soul.json."""
    g = sj.get("greeting_i18n") or sj.get("greeting")
    return _pick(g, lang).strip()[:600] if g else ""


def _parse_greet(raw: str) -> tuple[list[str], list[str]]:
    """``<greeting>…</greeting><suggest>…</suggest>`` → (her lines, up to three things the player could say back)."""
    from neonrp.core.soul_result import clean_line

    s = str(raw or "")
    m = re.search(r"<greeting>(.*?)(?:</greeting>|<suggest>|$)", s, re.S | re.I)
    body = m.group(1) if m else re.sub(r"<suggest>.*", "", s, flags=re.S | re.I)
    lines = [x.strip() for x in clean_line(body).splitlines() if x.strip() and not re.fullmatch(r"\[[^\]]*\]", x.strip())][:2]
    k = re.search(r"<suggest>(.*?)(?:</suggest>|$)", s, re.S | re.I)
    sug = [re.sub(r"^\s*(?:[-*•·]|\d+[.、)])\s*", "", x).strip().strip("「」\"") for x in (k.group(1).splitlines() if k else [])]
    return [x[:600] for x in lines], [x[:60] for x in sug if x][:3]


def greet(tpl: str, sid: str, *, lang: str | None = None, rt: Any = None, adapter: Any = None) -> dict[str, Any]:
    """The first time the player opens a character's chat (an empty thread): her opening line — her author's
    (``greeting_i18n``), else one the model writes in her voice from her own documents — kept in the thread, written once.
    The model also suggests three things to say back (on the message's ``suggest``; the phone falls back on its own
    generic three). Not empty any more → nothing new. 403 locked · 409 already greeting · 502 no model / model error."""
    c = resolve(tpl, sid)
    if c["access"] == "locked":
        raise ChatError(403, "this character has not left its world for you yet")
    sid = c["sid"]
    if read_thread(tpl, sid):
        return {"messages": []}
    lg = _lang(lang, c["lang"])
    key = f"{tpl}/{sid}"
    with _BUSY_LOCK:
        lock = _BUSY.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        raise ChatError(409, "still answering")
    try:
        if read_thread(tpl, sid):
            return {"messages": []}
        own = _own_greeting(c["sj"], lg)
        if own:
            return {"messages": _append(tpl, sid, [{"from": "soul", "kind": "text", "text": own, "greeting": True}])}
        T = _T(lg)
        name = _cname(c, lg)
        node = chat_node(c)
        system = str(T["system"]).format(name=name, docs=_docs(Path(c["folder"]), node.get("docs"), int(node.get("doc_cap") or DOC_CAP)), stickers="—")
        from neonrp.core import node_kinds

        system += "".join(str(x) for x in node_kinds.call_all("greet_system", c, lg))  # a plugin's own rule for the first line (10-19)
        try:
            from neonrp.core.llm import Message

            out = (adapter or _adapter(rt)).chat([Message(role="system", content=system), Message(role="user", content=str(T["greet"]).format(name=name))])
        except Exception as exc:  # noqa: BLE001 — no model set up / transport failure: an answer, never a crash
            raise ChatError(502, str(exc)[:300]) from exc
        err = getattr(out, "error", None)
        if err:
            from neonrp.core import billing_stop

            stop = billing_stop.remember(billing_stop.from_text(err))
            raise ChatError(502, str(err)[:300], {"billing": stop.to_dict()} if stop else {})
        lines, sug = _parse_greet(str(getattr(getattr(out, "message", None), "content", None) or ""))
        if not lines:
            raise ChatError(502, "empty reply")
        recs = [{"from": "soul", "kind": "text", "text": x, "greeting": True} for x in lines]
        if sug:
            recs[-1]["suggest"] = sug
        return {"messages": _append(tpl, sid, recs), "usage": dict(getattr(out, "usage", None) or {})}
    finally:
        lock.release()
