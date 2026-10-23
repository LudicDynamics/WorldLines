"""World localization layer — a template played in one language (niko 10-14:「本地化,不只是翻译」).

A template is authored in one language (``card.lang``, the main language). ``i18n/<lang>/`` holds a localized
version of it as an overlay: files at the same paths as the template's own (``world/…``, ``prompts/…``,
``plots/…``, ``template.json``)::

    <id>.template/
      i18n/
        glossary.json              the proper nouns: one row per thing, its name in each language (lint's residue check)
        ja/world/game/towns/T001/npcs.json
        ja/plots/P01/plot.json
        ja/prompts/world.md
        en/…

When a run is started in ``lang`` the overlay is laid over a copy of the template before the build, so the engine and
the prompts only ever see one language:

- ``.json`` files merge into the template's (objects merge key by key; lists of the same length merge item by item;
  anything else — a list of another length, a string, a ``{zh,en,ja,ko}`` object — is replaced). A localized file may
  therefore be a whole translated copy or only the strings it changes.
- any other file (``.md``, ``.txt``, images) replaces the template's.
- ids never change: ``id`` / ``sid`` / place ids / item ids / flag / var keys stay as authored, so triggers and rules
  keep working; names (places, items, characters, NPCs) are free to change entirely — a Japanese run can take place
  on a Japanese line with Japanese names.
- after the build every ``{zh,en,ja,ko}`` text object in the run is narrowed to the run's language (``{lang: text}``,
  lang → en → zh → any), so the other languages' text is not in the run either.
- a language without an overlay plays the template as authored (its main language); lint warns. The main language
  may have a layer of its own too (``i18n/zh/``: what a zh run changes, e.g. romanized display names).

Nothing in here knows a world: the overlay is data, the glossary is data.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from neonrp.template import Template

LANGS: tuple[str, ...] = ("zh", "en", "ja", "ko")
DIR = "i18n"
GLOSSARY = "glossary.json"
TEXT_EXTS = (".json", ".md", ".txt")
# keys whose string values are references, not text: an overlay that changes an id under one breaks the triggers / rules
ID_KEYS = frozenset({"id", "sid", "instance_id", "pid", "key", "var", "flag", "at", "parent", "class", "kind", "to", "who",
                     "location", "entry", "ending", "town_id", "world_id", "start_location", "entry_agent", "type", "role",
                     "template", "schema", "schema_version", "state_path", "dir", "image", "cover", "ratio", "widget"})
# files in a template that are about the template (for an agent), not part of any run
_NOT_RUN = ("AGENTS.md", "CLAUDE.md", "ORC-NOTICE.md")
# an id is ASCII (``T001/cab``, ``got_key``, ``si-xiacheng01``); a value with other letters under a reference key is a name
# a world refers by (``"who": "<a name>"``), which a localization may rename along with the thing. ``key`` (a path into a
# file, ``skills.<skill>``) never changes: keys are ids
_ID = re.compile(r"^[A-Za-z0-9_.:/@+-]+$")
_SCRIPT = {"zh": r"[一-鿿]", "ja": r"[぀-ヿ]", "ko": r"[가-힯]", "en": r"[A-Za-z]{3,}"}
# an image slot's generation prompt (``opening.cg[i].prompt``, ``stage_cg.<n>.prompt``: a picture's description for the
# image model, written in English whatever the run's language) is not text of the run — no player reads it, no model
# prompt carries it — so the residue check skips it. Only under a slot: a key named here, in an object that also has one
# of ART_SLOT_KEYS (``prompt`` elsewhere — a ui prompt, a plot's prompt entry — is text and stays checked)
ART_PROMPT_KEYS = frozenset({"prompt", "negative_prompt"})
ART_SLOT_KEYS = frozenset({"image", "video", "camera", "caption"})


def norm_lang(value: Any) -> str:
    s = str(value or "").strip().lower()[:2]
    return s if s in LANGS else ""


def source_lang(t: "Template") -> str:
    """The language the template is authored in (``card.lang``; zh when unset)."""
    return norm_lang(t.card.get("lang")) or "zh"


def layer_dir(t: "Template", lang: str) -> Path | None:
    d = Path(t.dir) / DIR / lang
    return d if lang and d.is_dir() else None


def layers(t: "Template") -> list[str]:
    """Languages the template has an overlay for (the main language never needs one)."""
    src = source_lang(t)
    return [lg for lg in LANGS if lg != src and layer_dir(t, lg) is not None]


def declared(t: "Template") -> list[str]:
    """Languages the template means to be played in: ``template.json["i18n"]["langs"]``, else its overlays."""
    d = t.data.get("i18n") if isinstance(t.data.get("i18n"), dict) else {}
    want = [norm_lang(x) for x in d.get("langs") or []]
    return [lg for lg in LANGS if lg in want and lg != source_lang(t)] or layers(t)


def langs(t: "Template") -> list[str]:
    """Every language a run of this template can be fully localized in (main language first)."""
    return [source_lang(t), *layers(t)]


# ── merge ────────────────────────────────────────────────────────────────────

def merge(base: Any, over: Any) -> Any:
    """The overlay rule: objects key by key, same-length lists item by item, anything else replaced. Keys are never
    localized (a key is an id — a skill table's keys too); the names shown are values, and values are what a layer changes."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = merge(base[k], v) if k in base else v
        return out
    if isinstance(base, list) and isinstance(over, list) and len(base) == len(over):
        return [merge(b, o) for b, o in zip(base, over)]
    return over


def minimize(base: Any, over: Any) -> Any:
    """The smallest overlay that merges to the same result: only what differs (an unchanged object in a list → ``{}``).
    Returns ``None`` when nothing differs. A whole translated copy becomes a text-only layer, so later edits to the
    template's logic (a trigger's conditions, a number) are not frozen in the localization."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = {}
        for k, v in over.items():
            if k not in base:
                out[k] = v
                continue
            m = minimize(base[k], v)
            if m is not None:
                out[k] = m
        return out or None
    if isinstance(base, list) and isinstance(over, list) and len(base) == len(over):
        items = [minimize(b, o) for b, o in zip(base, over)]
        if all(x is None for x in items):
            return None
        return [({} if isinstance(b, dict) else b) if x is None else x for b, x in zip(base, items)]
    return None if over == base else over


def tidy(t: "Template") -> dict[str, int]:
    """Rewrite every JSON file of every layer as its minimized form (a file that changes nothing is removed).
    Returns lang → files rewritten."""
    out: dict[str, int] = {}
    for lg in LANGS:
        layer = layer_dir(t, lg)
        if layer is None:
            continue
        for f in sorted(layer.rglob("*.json")):
            base_f = Path(t.dir) / f.relative_to(layer)
            if not base_f.is_file():
                continue
            try:
                base, over = json.loads(base_f.read_text(encoding="utf-8")), json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            m = minimize(base, over)
            if m is None:
                f.unlink()
            elif m != over:
                f.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            else:
                continue
            out[lg] = out.get(lg, 0) + 1
    return out


def _drop_art_prompts(d: Any) -> Any:
    """``d`` without image slots' generation prompts (:data:`ART_PROMPT_KEYS`), for the residue check."""
    if isinstance(d, list):
        return [_drop_art_prompts(x) for x in d]
    if not isinstance(d, dict):
        return d
    art = bool(ART_SLOT_KEYS & set(d))
    return {k: _drop_art_prompts(v) for k, v in d.items() if not (art and k in ART_PROMPT_KEYS)}


# notes an author keeps beside a text's languages (``{"zh": …, "en": …, "doc": "what this term means"}``): not a language,
# not a key a layer could be adding by mistake
NOTE_KEYS = frozenset({"doc", "note", "notes", "hint", "_doc"})


def _lang_keys_only(v: Any) -> bool:
    """An object whose keys are language codes (plus :data:`NOTE_KEYS`) — a text object even with one language written so
    far (``{"zh": …}``, ``{"zh": …, "en": …, "doc": …}``): a layer adds its own language there, not a new key."""
    return isinstance(v, dict) and bool(set(v) & set(LANGS)) and set(v) <= set(LANGS) | NOTE_KEYS


def is_lang_text(v: Any) -> bool:
    """A ``{zh,en,ja,ko}`` text object (≥2 languages, every value text or a list of text)."""
    if not isinstance(v, dict) or len(v) < 2 or not set(v) <= set(LANGS):
        return False
    return all(isinstance(x, str) or (isinstance(x, list) and all(isinstance(y, (str, dict)) for y in x)) for x in v.values())


def narrow(data: Any, lang: str) -> Any:
    """Every ``{zh,en,ja,ko}`` text object → ``{lang: text}`` (lang → en → zh → any): the run keeps one language and
    every reader that picks by the run's language still finds it."""
    if isinstance(data, list):
        return [narrow(x, lang) for x in data]
    if not isinstance(data, dict):
        return data
    if is_lang_text(data):
        for k in (lang, "en", "zh", *data):
            v = data.get(k)
            if v not in (None, "", []):
                return {lang: narrow(v, lang)}
        return data
    return {k: narrow(v, lang) for k, v in data.items()}


def narrow_run(root: Path, lang: str) -> int:
    """:func:`narrow` over every JSON file of a built run. Returns how many files changed."""
    n = 0
    for f in sorted(Path(root).rglob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        nd = narrow(d, lang)
        if nd != d:
            f.write_text(json.dumps(nd, ensure_ascii=False, indent=2), encoding="utf-8")
            n += 1
    return n


def _lay(root: Path, layer: Path) -> list[str]:
    """Lay ``layer`` over the template copy at ``root``. Returns the paths it touched."""
    done: list[str] = []
    for f in sorted(layer.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(layer)
        dst = root / rel
        if f.suffix == ".json" and dst.is_file():
            base = json.loads(dst.read_text(encoding="utf-8"))
            over = json.loads(f.read_text(encoding="utf-8"))
            dst.unlink()  # may be a link to the original file
            dst.write_text(json.dumps(merge(base, over), ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            shutil.copy2(f, dst)
        done.append(rel.as_posix())
    return done


def _copy_tree(src: Path, dst: Path) -> None:
    """The template, minus its own ``i18n/``: text files copied (the overlay rewrites them), the rest linked."""
    def ignore(d: str, names: list[str]) -> list[str]:
        return [DIR] if Path(d) == src else []

    def copy(s: str, d: str) -> None:
        if Path(s).suffix in TEXT_EXTS:
            shutil.copy2(s, d)
        else:
            try:
                os.symlink(os.path.abspath(s), d)
            except OSError:
                shutil.copy2(s, d)

    shutil.copytree(src, dst, ignore=ignore, copy_function=copy)


@contextmanager
def localized(t: "Template", lang: str | None) -> Iterator["Template"]:
    """The template as it is played in ``lang``: a scratch copy with ``i18n/<lang>/`` laid over it (removed on exit).
    No overlay for that language (or the main language) → the template itself, unchanged."""
    from neonrp.template import load

    lg = norm_lang(lang)
    if getattr(t, "lang", "") == lg and lg:
        yield t  # already the localized one
        return
    layer = layer_dir(t, lg)  # the main language may have one too (a zh run's own touch-ups: romanized names → 中文)
    if layer is None:
        yield t
        return
    tmp = Path(tempfile.mkdtemp(prefix=f"wl-i18n-{lg}-"))
    try:
        root = tmp / Path(t.dir).name
        _copy_tree(Path(t.dir), root)
        touched = _lay(root, layer)
        lt = load(root)
        lt.lang, lt.origin, lt.localized_files = lg, Path(t.dir), touched
        yield lt
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run_text(rel: str, raw: str) -> tuple[Any, str]:
    """(the parsed JSON — None when it is not JSON or not a .json file —, the raw text) of one run text file."""
    if not rel.endswith(".json"):
        return None, raw
    try:
        return json.loads(raw), raw
    except ValueError:
        return None, raw


def _localized_texts(t: "Template", lang: str | None, base: dict[str, tuple[Any, str]] | None = None,
                     read: Any = None) -> dict[str, tuple[Any, str]]:
    """rel path → (parsed JSON or None, raw text) of every run text file :func:`localized` would hold for ``lang``,
    without making the copy — in the order ``_template_texts`` lists the copy. Same layering as ``_lay``: a JSON file over
    one the template has is merged into it, anything else replaces / adds the file. ``base``: the template's own run
    texts (``_run_text`` of each), when the caller has read them already (the lint reads them once for every language);
    ``read``: how to read a file (the lint's once-per-file reader)."""
    from pathlib import PurePosixPath

    lg = norm_lang(lang)
    root = Path(t.dir)
    rd = read or (lambda p: p.read_text(encoding="utf-8"))
    if base is None:
        base = {rel: _run_text(rel, rd(f)) for rel, f in _template_texts(root).items()}
    out = dict(base)
    layer = None if (getattr(t, "lang", "") == lg and lg) else layer_dir(t, lg)
    if layer is None:
        return out
    for f in sorted(layer.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(layer)
        r = rel.as_posix()
        on_base = (root / rel).is_file() and rel.parts[0] != DIR  # the copy leaves out only the template's own top-level i18n/
        runs = f.suffix in TEXT_EXTS and f.name not in _NOT_RUN and rel.parts[0] not in (DIR, "spec")
        if f.suffix == ".json" and on_base:
            # _lay merges it into the copy (a base that is not JSON stops the copy there too)
            mine = base[r][0] if r in base and base[r][0] is not None else json.loads(rd(root / rel))
            merged = merge(mine, json.loads(rd(f)))
            if runs:
                out[r] = (merged, "null") if merged is None else (merged, "")
        elif runs:
            out[r] = _run_text(r, rd(f))
    return {r: out[r] for r in sorted(out, key=lambda r: PurePosixPath(r).parts)}


def card(t: "Template", lang: str) -> dict[str, Any]:
    """The card in ``lang``: the overlay's ``template.json`` card over the template's (a launcher shows this)."""
    layer = layer_dir(t, norm_lang(lang))
    if layer is None or not (layer / "template.json").is_file():
        return dict(t.card)
    try:
        over = json.loads((layer / "template.json").read_text(encoding="utf-8"))
    except ValueError:
        return dict(t.card)
    return merge(dict(t.card), over.get("card") or {}) if isinstance(over, dict) else dict(t.card)


# ── glossary · residue ───────────────────────────────────────────────────────

def glossary(t: "Template") -> list[dict[str, Any]]:
    """``i18n/glossary.json`` rows: ``{"id": "soul:xiacheng", "zh": "夏澄", "ja": "…", "ko": "…", "en": "…",
    "also": ["Xia Cheng"]}`` — ``also`` = spellings of the main-language name that must not survive either
    (an old transliteration in a translated text)."""
    p = Path(t.dir) / DIR / GLOSSARY
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = d.get("terms") if isinstance(d, dict) else d
    return [r for r in rows or [] if isinstance(r, dict)]


def foreign_terms(t: "Template", lang: str) -> dict[str, str]:
    """Spelling → term id for every name that must not appear in a ``lang`` run (other languages' names and the
    main language's old transliterations), minus what ``lang`` itself spells the same way."""
    own: set[str] = set()
    out: dict[str, str] = {}
    rows = glossary(t)
    for r in rows:
        v = r.get(lang)
        own |= {x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str) and x.strip()}
    for r in rows:
        tid = str(r.get("id") or r.get(source_lang(t)) or "?")
        forms: list[str] = []
        for k in (*LANGS, "also"):
            if k == lang:
                continue
            v = r.get(k)
            forms += [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str) and len(x.strip()) >= 2]
        for f in forms:
            if not any(f in o for o in own):
                out.setdefault(f.strip(), tid)
    return out


def residue(texts: dict[str, str], terms: dict[str, str]) -> dict[str, list[str]]:
    """term spelling → the files (of ``texts``: path → text) it is still found in."""
    hits: dict[str, list[str]] = {}
    for name, body in texts.items():
        for term in terms:
            if term in body:
                hits.setdefault(term, []).append(name)
    return hits


def run_texts(root: Path) -> dict[str, str]:
    """path → text for every text file of a run (what the engine and its prompts read)."""
    out: dict[str, str] = {}
    for f in sorted(Path(root).rglob("*")):
        if f.is_file() and f.suffix in TEXT_EXTS and f.name not in _NOT_RUN:
            try:
                out[f.relative_to(root).as_posix()] = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
    return out


# ── lint ─────────────────────────────────────────────────────────────────────

def _template_texts(tdir: Path) -> dict[str, Path]:
    """rel path → file for the template's text files that go into a run (``i18n/`` and ``spec/`` and agent docs aside)."""
    out: dict[str, Path] = {}
    for f in sorted(tdir.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_EXTS or f.name in _NOT_RUN:
            continue
        rel = f.relative_to(tdir)
        if rel.parts[0] in (DIR, "spec"):
            continue
        out[rel.as_posix()] = f
    return out


def _leaves(d: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(d, dict):
        if is_lang_text(d):
            yield path, json.dumps(d, ensure_ascii=False)
            return
        for k, v in d.items():
            if k not in ID_KEYS:
                yield from _leaves(v, f"{path}.{k}" if path else str(k))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from _leaves(v, f"{path}[{i}]")
    elif isinstance(d, str):
        yield path, d


def _lists(d: Any, path: str = "") -> Iterator[str]:
    """Paths of the lists in ``d`` that carry anything (an overlay that gives a list localizes all of it)."""
    if isinstance(d, dict):
        for k, v in d.items():
            yield from _lists(v, f"{path}.{k}" if path else str(k))
    elif isinstance(d, list):
        if any(x not in ({}, None) for x in d):
            yield path
        for i, v in enumerate(d):
            yield from _lists(v, f"{path}[{i}]")


def _in_given_list(p: str, lists: set[str]) -> bool:
    cut = p.rfind("[")
    return cut > 0 and p[:cut] in lists


def _units(f: Path, script: re.Pattern[str], src: str = "zh", read: Any = None) -> dict[str, Any]:
    """What a file asks a localization for: a text file is one unit; a JSON file one unit per string in the main language.
    ``read``: how to read the file (the lint's own once-per-file reader)."""
    text = read(f) if read is not None else f.read_text(encoding="utf-8")
    if f.suffix != ".json":
        return {"": text} if script.search(text) else {}
    try:
        d = json.loads(text)
    except ValueError:
        return {}
    return {p: v for p, v in _leaves(d) if script.search(v) and p.rsplit(".", 1)[-1] not in set(LANGS) - {src}}


def _lang_has(d: Any, path: str, lang: str) -> bool:
    """Whether the ``{zh,en,…}`` object at ``path`` already carries ``lang`` (narrowing then picks it, no overlay needed)."""
    return bool(re.search(rf'"{lang}"\s*:', d)) if isinstance(d, str) else False


def _check_ids(base: Any, over: Any, where: str, out: list[tuple[str, str, str, str]]) -> None:
    if isinstance(base, dict) and isinstance(over, dict):
        for k, v in over.items():
            if k not in base:
                if not (is_lang_text(base) or (_lang_keys_only(base) and k in LANGS)):
                    out.append(("warn", "i18n.key", f"{where}.{k}", 'a key the template does not have (a typo? it is added as is; keys are '
                            'ids and stay as authored — localize the names shown, not the keys)'))
                continue
            if k in ID_KEYS and isinstance(base[k], (str, int)) and (_ID.match(str(base[k])) or k == "key") and v != base[k]:
                out.append(("block", "i18n.id", f"{where}.{k}", f"changes a reference ({base[k]!r} → {v!r}); ids stay as authored"))
                continue
            _check_ids(base[k], v, f"{where}.{k}", out)
    elif isinstance(base, list) and isinstance(over, list):
        if len(base) == len(over):
            for i, (b, o) in enumerate(zip(base, over)):
                _check_ids(b, o, f"{where}[{i}]", out)
        elif any(isinstance(x, dict) for x in base):
            out.append(("warn", "i18n.list", where, f"{len(over)} items for {len(base)}: the whole list is replaced (its structure is not checked)"))


def _on_world(t: "Template", rel: str) -> bool:
    """A layer path under the template's overlay folder (``world-overlay/`` by default) that is a file of the bound world:
    it localizes the world's own file (a builtin world has no copy in the template), so it is not an orphan."""
    from neonrp import template as _t

    head, _, sub = rel.partition("/")
    wd = _t.world_dir(t)
    return bool(sub) and head == str(t.world.get("overlay") or "world-overlay").strip("/") and wd is not None and (wd / sub).is_file()


def _check_whole(t: "Template", rel: str, over: Any, where: str, probs: list) -> None:
    """A layer file over the bound world's own file (a builtin world through ``world-overlay/``) is not merged: it
    replaces that file whole (10-15, 石津镇: agent.json lost id / defaults, flag_aliases lost aliases). Warn when it
    drops keys the world's file has."""
    from neonrp import template as _t

    od, wd = _t.overlay_dir(t), _t.world_dir(t)
    if od is None or wd is None or not isinstance(over, dict):
        return
    try:
        sub = (Path(t.dir) / rel).resolve().relative_to(od.resolve())
    except ValueError:
        return
    if (od / sub).is_file() or not (wd / sub).is_file():
        return
    try:
        orig = json.loads((wd / sub).read_text(encoding="utf-8"))
    except ValueError:
        return
    gone = sorted(k for k in orig if k not in over) if isinstance(orig, dict) else []
    if gone:
        probs.append(("warn", "i18n.replaces", where,
                      f"replaces the world's {sub.as_posix()} whole (not merged) and drops {', '.join(gone[:6])}"
                      f"{' …' if len(gone) > 6 else ''} — write the whole file"))


def lint(t: "Template", *, deep: bool = False) -> tuple[list[tuple[str, str, str, str]], dict[str, Any]]:
    """Overlay problems + a report ``{source, declared, langs: {lang: {units, covered, coverage, missing, residue}}}``.
    ``deep`` also lints each localized template (a full build per language) and reports its blocks."""
    from neonrp.template import lint as template_lint

    probs: list[tuple[str, str, str, str]] = []
    seen: dict[Path, str] = {}  # every file read once per lint (10-19: the loops below read the same files per language)

    def rd(p: Path) -> str:
        if p not in seen:
            seen[p] = p.read_text(encoding="utf-8")
        return seen[p]

    src = source_lang(t)
    script = re.compile(_SCRIPT[src])
    base_files = _template_texts(Path(t.dir))
    want = declared(t)
    report: dict[str, Any] = {"source": src, "declared": want, "langs": {}}
    if not want and not (Path(t.dir) / DIR).is_dir():
        return probs, report
    units = {rel: _units(f, script, src, read=rd) for rel, f in base_files.items()}
    units = {k: v for k, v in units.items() if v}
    base_leaves: dict[str, dict[str, str]] = {}
    for rel in units:
        if rel.endswith(".json"):
            try:
                base_leaves[rel] = dict(_leaves(json.loads(rd(base_files[rel]))))
            except ValueError:
                pass
    total = sum(len(v) for v in units.values())
    base_raw: dict[str, tuple[Any, str]] | None = None  # the template's run texts, read once for every language's residue check
    own = [src] if layer_dir(t, src) is not None or glossary(t) else []
    for lg in sorted(set(want) | set(layers(t)) | set(own), key=LANGS.index):
        layer = layer_dir(t, lg)
        if lg == src:  # the main language needs no coverage; its run is still checked for the other languages' names
            layer = layer or Path(t.dir) / DIR / src
        if layer is None:
            probs.append(("warn", "i18n.missing", f"i18n/{lg}", f"no {lg} layer: a {lg} run plays the {src} text"))
            report["langs"][lg] = {"units": total, "covered": 0, "coverage": 0.0, "missing": sorted(units)[:20], "residue": {}}
            continue
        if lg != src and (layer / "template.json").is_file():  # the card says which language it is in (a launcher sorts by it)
            try:
                lc = (json.loads(rd(layer / "template.json")) or {}).get("card")
            except ValueError:
                lc = None
            if isinstance(lc, dict) and lc.get("lang") != lg:
                probs.append(("warn", "i18n.card_lang", f"i18n/{lg}/template.json.card.lang",
                              f"the {lg} card's lang is {lc.get('lang')!r}, not {lg!r} (the card would claim the main language)"))
        covered, missing = 0, []
        sib = re.compile(rf"\.{src}$")
        for rel, us in units.items():
            # a {zh,en,…,base} row (a name table) that already has this language counts as localized
            us = {p: v for p, v in us.items() if not (sib.search(p) and sib.sub(f".{lg}", p) in base_leaves.get(rel, {}))}
            covered += len(units[rel]) - len(us)
            ov = layer / rel
            if lg == src:
                covered += len(us)
                continue
            if not ov.is_file():
                n = sum(1 for p, v in us.items() if _lang_has(v, p, lg))
                covered += n
                if n < len(us):
                    missing.append(rel)
                continue
            if ov.suffix != ".json":
                covered += 1
                continue
            try:
                merged = merge(json.loads(rd(base_files[rel])), json.loads(rd(ov)))
            except ValueError:
                continue
            over_d = json.loads(rd(ov))
            now, given, lists = dict(_leaves(merged)), dict(_leaves(over_d)), set(_lists(over_d))
            left = [p for p, v in us.items()
                    if now.get(p) == v and p not in given and not _in_given_list(p, lists) and not _lang_has(v, p, lg)]
            covered += len(us) - len(left)
            if left:
                missing.append(f"{rel} ({len(left)})")
        for f in sorted(layer.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(layer).as_posix()
            where = f"i18n/{lg}/{rel}"
            if rel not in base_files and not (Path(t.dir) / rel).exists() and not _on_world(t, rel):
                probs.append(("warn", "i18n.orphan", where, "the template has no file at this path (it is added as is)"))
            if f.suffix == ".json":
                try:
                    over = json.loads(rd(f))
                except ValueError as e:
                    probs.append(("block", "i18n.parse", where, f"not JSON ({e})"))
                    continue
                if (Path(t.dir) / rel).is_file():
                    try:
                        _check_ids(json.loads(rd(Path(t.dir) / rel)), over, where, probs)
                    except ValueError:
                        pass
                else:
                    _check_whole(t, rel, over, where, probs)
        if missing:
            probs.append(("warn", "i18n.partial", f"i18n/{lg}", f"{len(missing)} file(s) still in {src} (falls back): {', '.join(missing[:6])}"
                          + (" …" if len(missing) > 6 else "")))
        hits: dict[str, list[str]] = {}
        terms = foreign_terms(t, lg)
        if terms:
            # the run's texts in this language, read in place (10-19: a scratch copy per language made every template
            # write wait ~1 s for its lint; the copy is only built when ``deep`` lints the localized template too)
            texts = {}
            if base_raw is None:
                base_raw = {rel: _run_text(rel, rd(f)) for rel, f in base_files.items()}
            for rel, (d, raw) in _localized_texts(t, lg, base_raw, read=rd).items():
                texts[rel] = json.dumps(narrow(_drop_art_prompts(d), lg), ensure_ascii=False) if d is not None else raw
            hits = residue(texts, terms)
            for term, files in sorted(hits.items()):
                probs.append(("warn", "i18n.residue", f"i18n/{lg}", f"{term!r} ({terms[term]}) left in {', '.join(files[:4])}"
                              + (" …" if len(files) > 4 else "")))
        if deep:
            with localized(t, lg) as lt:
                rep = template_lint(lt, i18n=False)
            for p in rep["problems"]:
                if p["level"] == "block":
                    probs.append(("block", "i18n.build", f"[{lg}] {p['where']}", f"{p['code']}: {p['msg']}"))
        report["langs"][lg] = {"units": total, "covered": covered, "coverage": round(covered / total, 3) if total else 1.0,
                               "missing": missing[:20], "residue": {k: v[:4] for k, v in hits.items()}}
    return probs, report


def soul_names(t: "Template", labels: dict[str, str] | None = None) -> dict[str, dict[str, str]]:
    """Each character's name per language (ios4 10-23: the local Hub — iOS — showed the Chinese name in every language;
    the web catalog already had these, hub/build_static.py ``_names`` · ``_layer_souls``, same order of trust):
    the glossary's ``soul:<sid>`` / Chinese-name rows → the soul.json ``name_i18n`` → the foreign layer's own soul.json.
    ``labels`` = sid → the name the slots show (the source language). Only characters with a portrait slot are listed."""
    from neonrp import template as TP

    first = lambda v: (v[0] if isinstance(v, list) and v else v) if isinstance(v, (str, list)) else ""  # noqa: E731
    by_id: dict[str, dict[str, str]] = {}
    by_src: dict[str, dict[str, str]] = {}
    for r in glossary(t):
        rid = str(r.get("id") or "")
        if rid.split(":", 1)[0] not in ("soul", "npc"):
            continue
        row = {lg: first(r.get(lg)) for lg in LANGS if first(r.get(lg))}
        by_id[rid] = row
        for z in (r.get("zh") if isinstance(r.get("zh"), list) else [r.get("zh")]):
            if isinstance(z, str) and z:
                by_src.setdefault(z, row)
    wd = TP.world_dir(t)
    roots = [t.dir / "world" / "souls", t.dir / "world-overlay" / "souls", *([Path(wd) / "souls"] if wd is not None else [])]

    def soul_json(root_list: list[Path], sid: str) -> dict[str, Any]:
        for r in root_list:
            for c in (sorted(r.glob(f"{sid}-*/soul.json")) + sorted(r.glob(f"{sid}/soul.json"))) if r.is_dir() else []:
                try:
                    d = json.loads(c.read_text(encoding="utf-8"))
                    return d if isinstance(d, dict) else {}
                except (OSError, ValueError):
                    continue
        return {}

    out: dict[str, dict[str, str]] = {}
    src = t.lang or str((t.card or {}).get("lang") or "zh")
    for sid, label in (labels or {}).items():
        sj = soul_json(roots, sid)
        base = str(sj.get("name_local") or label or sid)
        ni = sj.get("name_i18n") if isinstance(sj.get("name_i18n"), dict) else {}
        name = {**(by_src.get(base) or {}), **(by_id.get(f"soul:{sid}") or {}), **{k: str(v) for k, v in ni.items() if v}, src: base}
        for lg in layers(t):
            d = layer_dir(t, lg)
            lj = soul_json([d / "world" / "souls"], sid) if d else {}
            li = lj.get("name_i18n")
            nm = (li if isinstance(li, str) else (li or {}).get(lg) if isinstance(li, dict) else "") or (lj.get("name_local") if lj.get("name_local") != base else "")
            if isinstance(nm, str) and nm:
                name[lg] = nm
        if sj.get("name") and "en" not in name:
            name["en"] = str(sj["name"])
        out[sid] = {k: v for k, v in name.items() if k in LANGS and v}
    return out
