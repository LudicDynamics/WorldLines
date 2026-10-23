"""Packages — what was authored in the engine, taken out and brought back in (「我们在引擎里面修改好的文档
可以有地方可以 extract,或者 import」).

One format for every kind: a zip with ``pack.json`` at its root::

    {"schema": "worldlines.package/1", "kind": "template" | "soul", "id": "<id>", "title": "…", "exported": "<iso>",
     "links": ["<library soul>", …]}            # template only: the library souls it links, carried along

    template   <id>.template/…                   the template folder as on disk (plots · prompts · overlay · assets · world)
               souls-lib/<name>/…                every library soul the template links ({"lib": name}) — 「世界里只放 link」
                                                 stays true: on import they go into the character library, the rows keep
                                                 pointing at them
    soul       soul/…                            one character-library soul folder

Import never runs anything: the archive is unpacked into a scratch dir and checked first (no absolute / ``..`` paths,
no links, no code files, size caps), then moved into place. A taken id gets the next free ``-2``, ``-3`` …; a linked
soul already in the library with the same content is reused, a different one is installed under a new name and the
template's rows are repointed.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from neonrp.template import TemplateError, discover, library_dir, load

SCHEMA = "worldlines.package/1"
KINDS = ("template", "soul")
MAX_FILES = 5000
MAX_BYTES = 300 * 1024 * 1024
CODE_EXT = {".py", ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".sh", ".bat", ".cmd", ".js", ".mjs"}
SKIP = {"__pycache__", ".DS_Store"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _add_dir(z: zipfile.ZipFile, src: Path, arc: str, *, skip_top: tuple[str, ...] = ()) -> None:
    for f in sorted(src.rglob("*")):
        if any(p in SKIP for p in f.parts) or f.is_symlink() or not f.is_file():
            continue
        if f.relative_to(src).parts[0] in skip_top:
            continue
        z.write(f, f"{arc}/{f.relative_to(src).as_posix()}")


def _linked(t: Any) -> list[str]:
    out: list[str] = []
    for r in t.souls or []:
        for x in (r.get("pool") if isinstance(r.get("pool"), list) else [r]):
            if isinstance(x, dict) and x.get("lib") and str(x["lib"]) not in out:
                out.append(str(x["lib"]))
    return out


# ── export ───────────────────────────────────────────────────────────────────

class ExportRefused(TemplateError):
    """A default-zone work (``zone: reviewed`` — the official worlds among them) is played, not taken out: only free-zone
    works export (niko 10-16). ``code`` = default_zone."""

    code = "default_zone"


def export_template(ref: Any, *, any_zone: bool = False) -> bytes:
    """``any_zone``: the engine's own uses (publishing a work to the free zone, core/template_publish) — never a download."""
    t = ref if hasattr(ref, "dir") else load(discover().get(str(ref)) or ref)
    if not any_zone and (t.zone == "reviewed" or t.data.get("official") is True):   # 10-17: a fetched official world too
        raise ExportRefused(f"{t.id} is a default-zone work: only free-zone works can be exported")
    links = _linked(t)
    missing = [n for n in links if not (library_dir(n) / "soul.json").is_file()]
    if missing:
        raise TemplateError(f"linked souls not in the character library: {', '.join(missing)}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.json", json.dumps({"schema": SCHEMA, "kind": "template", "id": t.id,
                                            "title": str((t.data.get("card") or {}).get("title") or t.id),
                                            "exported": _now(), "links": links}, ensure_ascii=False, indent=2))
        _add_dir(z, t.dir, f"{t.id}.template", skip_top=("frontends",))   # a world's own front ends stay local (10-17; code files would not import anyway)
        for n in links:
            _add_dir(z, library_dir(n), f"souls-lib/{n}")
    return buf.getvalue()


def export_soul(name: str) -> bytes:
    src = library_dir(name)
    if "/" in name or name.startswith(".") or not (src / "soul.json").is_file():
        raise TemplateError(f"no soul {name!r} in the character library")
    sj = json.loads((src / "soul.json").read_text(encoding="utf-8"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.json", json.dumps({"schema": SCHEMA, "kind": "soul", "id": name,
                                            "title": str(sj.get("name") or sj.get("sid") or name), "exported": _now()},
                                           ensure_ascii=False, indent=2))
        _add_dir(z, src, "soul")
    return buf.getvalue()


# ── import ───────────────────────────────────────────────────────────────────

def _unpack(data: bytes, into: Path) -> dict[str, Any]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise TemplateError("not a zip package") from e
    infos = z.infolist()
    if len(infos) > MAX_FILES:
        raise TemplateError(f"too many files ({len(infos)} > {MAX_FILES})")
    if sum(i.file_size for i in infos) > MAX_BYTES:
        raise TemplateError("package too large")
    for i in infos:
        p = PurePosixPath(i.filename)
        if p.is_absolute() or ".." in p.parts or "\\" in i.filename:
            raise TemplateError(f"unsafe path in package: {i.filename}")
        if (i.external_attr >> 16) & 0o170000 == 0o120000:
            raise TemplateError(f"links are not allowed: {i.filename}")
        if not i.is_dir() and p.suffix.lower() in CODE_EXT:
            raise TemplateError(f"code files are not imported: {i.filename}")
    try:
        meta = json.loads(z.read("pack.json"))
    except KeyError as e:
        raise TemplateError("no pack.json — not a WorldLines package") from e
    except ValueError as e:
        raise TemplateError("pack.json is not valid JSON") from e
    if meta.get("schema") != SCHEMA or meta.get("kind") not in KINDS:
        raise TemplateError(f"unknown package ({meta.get('schema')} / {meta.get('kind')})")
    z.extractall(into)
    return meta


def _digest(d: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(d.rglob("*")):
        if f.is_file() and not any(p in SKIP for p in f.parts):
            h.update(f.relative_to(d).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _free(base: str, taken) -> str:
    if not taken(base):
        return base
    for n in range(2, 1000):
        cand = f"{base[:44]}-{n}"
        if not taken(cand):
            return cand
    raise TemplateError(f"no free id for {base}")


def _install_soul(src: Path, name: str) -> tuple[str, str]:
    """→ (name in the library, "new" | "same" | "renamed")."""
    dst = library_dir(name)
    if (dst / "soul.json").is_file():
        if _digest(dst) == _digest(src):
            return name, "same"
        name = _free(name, lambda n: library_dir(n).exists())
        dst = library_dir(name)
        how = "renamed"
    else:
        how = "new"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    return name, how


def import_package(data: bytes, *, new_id: str | None = None, into: Path | None = None, replace: bool = False,
                   patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Unpack a package into its home. → {kind, id, title, souls: [{name, how}], renamed_from?}.
    ``into`` / ``replace`` / ``patch`` (10-17, core/template_publish.fetch_official): a template lands in ``into`` instead
    of the write store under its own id, an older copy there swapped out whole, ``patch`` laid over its template.json."""
    from neonrp.template.author import ID_RE, write_root

    with tempfile.TemporaryDirectory(prefix="wl-import-") as td:
        tmp = Path(td)
        meta = _unpack(data, tmp)
        if meta["kind"] == "soul":
            if not (tmp / "soul" / "soul.json").is_file():
                raise TemplateError("soul package without soul/soul.json")
            base = str(new_id or meta.get("id") or "soul")
            if "/" in base or base.startswith("."):
                raise TemplateError("bad soul name")
            name, how = _install_soul(tmp / "soul", base)
            try:
                from neonrp.template import agentdocs

                agentdocs.write_library(library_dir(name).parent)
            except Exception:  # noqa: BLE001
                pass
            return {"kind": "soul", "id": name, "title": meta.get("title") or name, "souls": [{"name": name, "how": how}]}

        root = into or write_root()
        if root is None:
            raise TemplateError("no writable template store (NEONRP_TEMPLATE_WRITE_DIR)")
        src_id = str(meta.get("id") or "")
        tsrc = tmp / f"{src_id}.template"
        if not (tsrc / "template.json").is_file():
            raise TemplateError(f"template package without {src_id}.template/template.json")
        tid = str(new_id or src_id)
        if not ID_RE.match(tid):
            raise TemplateError("id: 2–48 chars, lowercase letters / digits / '-'")
        if replace:
            pass   # its own id, in its own folder: a newer copy of the same world
        elif new_id is None:
            tid = _free(tid, lambda n: n in discover() or (root / f"{n}.template").exists())
        elif tid in discover() or (root / f"{tid}.template").exists():
            raise TemplateError(f"template {tid!r} already exists")
        # the linked souls first: the rows must point at what is really in the library
        souls, rename = [], {}
        for n in meta.get("links") or []:
            s = tmp / "souls-lib" / str(n)
            if not (s / "soul.json").is_file():
                raise TemplateError(f"package lists linked soul {n} but does not carry it")
            got, how = _install_soul(s, str(n))
            souls.append({"name": got, "how": how})
            if got != n:
                rename[str(n)] = got
        d = json.loads((tsrc / "template.json").read_text(encoding="utf-8"))
        d["id"] = tid
        d.update(patch or {})
        for r in d.get("souls") or []:
            for x in (r.get("pool") if isinstance(r, dict) and isinstance(r.get("pool"), list) else [r]):
                if isinstance(x, dict) and str(x.get("lib") or "") in rename:
                    x["lib"] = rename[str(x["lib"])]
        (tsrc / "template.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        root.mkdir(parents=True, exist_ok=True)
        dest = root / f"{tid}.template"
        if replace and dest.exists():   # swap whole: the new copy is complete before the old one goes
            new, old = root / f".{tid}.template.new", root / f".{tid}.template.old"
            for x in (new, old):
                shutil.rmtree(x, ignore_errors=True)
            shutil.copytree(tsrc, new)
            dest.rename(old)
            new.rename(dest)
            shutil.rmtree(old, ignore_errors=True)
        else:
            shutil.copytree(tsrc, dest)
        t_new = load(dest)  # it must load where it landed
        try:  # this engine's specs, not the exporter's (template/agentdocs.py)
            from neonrp.template import agentdocs
            from neonrp.template.author import _agent_files

            _agent_files(t_new)
            if souls:
                agentdocs.write_library(library_dir("_").parent)
        except Exception:  # noqa: BLE001
            pass
        out = {"kind": "template", "id": tid, "title": meta.get("title") or tid, "souls": souls}
        if tid != src_id:
            out["renamed_from"] = src_id
        return out
