"""``neonrp mcp serve-create --root <folder>``: a stdio MCP server that lets a local agent (Claude Code / Codex CLI) author
ONE folder — a template (``<id>.template/``), a world (the workbench's edit copy) or a soul — read / write its text files,
lint it, and for a template list its asset slots and build a scratch run. It only creates; it never hosts play
(docs/planning/CREATE-MULTIMODEL-MCP-STUDY-1026.md).

Boundary: every path is resolved under ``--root``; ``..``, absolute escapes, symlinks and dot-folders (``.neonrp/`` holds the
run's model config, ``.git/``) are refused, paths are ASCII; write_file refuses text that looks like a key (the publish
scan's rules, core/hub_publish.secrets_in_text). The server never calls a model, never reads the user's
``~/.neonrp/config.json`` and holds no key. The agent's own built-in tools (Bash / Write) are NOT bound by this — whoever
launches the agent passes its tool / sandbox flags (webui/agent_cli_backend.py does for the workbench)."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

MAX_READ = 256 * 1024
MAX_WRITE = 512 * 1024
MAX_LIST = 3000
TEXT = {".json", ".md", ".txt", ".yml", ".yaml", ".toml"}
KINDS = ("template", "world", "soul")


class PathRefused(ValueError):
    pass


def kind_of(root: Path) -> str | None:
    """What the folder is: template.json → template · soul.json → soul · game/ → world."""
    if (root / "template.json").is_file():
        return "template"
    if (root / "soul.json").is_file():
        return "soul"
    if (root / "game").is_dir():
        return "world"
    return None


def resolve(root: Path, rel: str) -> Path:
    """``rel`` inside ``root`` or PathRefused. ``root`` is already resolved."""
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not rel.isascii():
        raise PathRefused("paths are ASCII (ids, field names, file names)")
    parts = [x for x in rel.split("/") if x not in ("", ".")]
    if ".." in parts:
        raise PathRefused(f"{rel}: outside the folder")
    if any(x.startswith(".") for x in parts):
        raise PathRefused(f"{rel}: dot-folders (.neonrp/, .git/ …) are engine internals, not editable")
    p = root
    for x in parts:
        p = p / x
        if p.is_symlink():
            raise PathRefused(f"{rel}: symlinks are not followed")
    r = p.resolve()
    if r != root and root not in r.parents:
        raise PathRefused(f"{rel}: outside the folder")
    return r


def _visible(rel: Path) -> bool:
    return not any(x.startswith(".") for x in rel.parts)


def list_files(root: Path, sub: str = "") -> dict[str, Any]:
    base = resolve(root, sub)
    out: list[dict[str, Any]] = []
    more = False
    if base.is_dir():
        for p in sorted(base.rglob("*")):
            r = p.relative_to(root)
            if not _visible(r) or p.is_symlink() or not p.is_file():
                continue
            if len(out) >= MAX_LIST:
                more = True
                break
            out.append({"path": r.as_posix(), "bytes": p.stat().st_size})
    return {"files": out, "truncated": more}


def read_file(root: Path, rel: str) -> str:
    p = resolve(root, rel)
    if not p.is_file():
        raise PathRefused(f"{rel}: no such file")
    if p.suffix.lower() not in TEXT:
        return f"(binary {p.suffix} · {p.stat().st_size} bytes — not shown)"
    if p.stat().st_size > MAX_READ:
        raise PathRefused(f"{rel}: larger than {MAX_READ} bytes")
    return p.read_text(encoding="utf-8")


def write_file(root: Path, rel: str, content: str) -> dict[str, Any]:
    p = resolve(root, rel)
    if p == root or p.is_dir():
        raise PathRefused(f"{rel}: is a folder")
    if p.suffix.lower() not in TEXT:
        raise PathRefused(f"{rel}: only text files ({', '.join(sorted(TEXT))}); images go through the asset slots")
    data = content.encode("utf-8")
    if len(data) > MAX_WRITE:
        raise PathRefused(f"{rel}: larger than {MAX_WRITE} bytes")
    from neonrp.core.hub_publish import is_credential_file, secrets_in_text

    rel_s = p.relative_to(root).as_posix()
    if is_credential_file(rel_s):
        raise PathRefused(f"{rel}: a credentials file name — keys never go into this folder; nothing written")
    found = secrets_in_text(content)
    if found:  # the publish scan's rules: a prompt injected through some text must not carry a key into the folder
        where = ", ".join(f"{k} line {n}" for k, n in found[:3])
        raise PathRefused(f"{rel}: looks like a key or token ({where}) — keys never go into this folder; nothing written")
    if p.suffix.lower() == ".json":
        try:
            json.loads(content)  # a JSON file that does not parse is refused, not written
        except ValueError as e:
            raise PathRefused(f"{rel}: not valid JSON ({e}) — nothing written") from e
    existed = p.is_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(p)
    return {"ok": True, "path": p.relative_to(root).as_posix(), "bytes": len(data), "created": not existed}


def _problem(level: str, code: str, where: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "where": where, "message": message}


def lint(root: Path) -> dict[str, Any]:
    """Same shape for every kind: ``{kind, ok, counts: {block, warn}, problems: [{level, code, where, message}]}``.
    template → template lint (ok = publishable) · world → the playability check (ok = playable) · soul → its files parse."""
    kind = kind_of(root)
    probs: list[dict[str, str]] = []
    if kind == "template":
        from neonrp import template as TP

        r = TP.lint(root)
        probs = [_problem(str(p.get("level")), str(p.get("code")), str(p.get("where")), str(p.get("message"))) for p in r["problems"]]
    elif kind == "world":
        from neonrp.core.validation import check_world

        h = check_world(root)
        for lv, items in (("block", h.blockers), ("warn", h.warnings)):
            for i in items:
                msg = i.message + (f" — fix: {i.suggestion}" if i.suggestion else "")
                probs.append(_problem(lv, i.code, f"{i.file} {i.path}".strip(), msg))
    elif kind == "soul":
        from neonrp.core.souls import read_soul_json

        for p in sorted(root.rglob("*.json")):
            rel = p.relative_to(root)
            if not _visible(rel) or p.is_symlink():
                continue
            try:
                json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                probs.append(_problem("block", "json", rel.as_posix(), f"does not parse: {e}"))
        if read_soul_json(root) is None:
            probs.append(_problem("block", "soul.json", "soul.json", "soul.json does not load (id / name missing or wrong shape)"))
        if not (root / "soul.md").is_file():
            probs.append(_problem("warn", "soul.md", "soul.md", "no soul.md: the soul plays without its charter voice"))
    else:
        probs.append(_problem("block", "kind", ".", "not a template, world or soul folder"))
    counts = {"block": sum(p["level"] == "block" for p in probs), "warn": sum(p["level"] == "warn" for p in probs)}
    return {"kind": kind, "ok": counts["block"] == 0, "counts": counts, "problems": probs}


def slots(root: Path) -> list[dict[str, Any]]:
    from neonrp import template as TP

    return [{k: s.get(k) for k in ("slot", "label", "need", "have", "stale")} for s in TP.asset_slots(TP.load(root))]


def build_preview(root: Path) -> dict[str, Any]:
    """Build into a throwaway folder (no model, no play) → what the run would contain (a summary, never prompt text)."""
    from neonrp import template as TP

    tmp = Path(tempfile.mkdtemp(prefix="neonrp-mcp-build-"))
    try:
        rec = TP.build(root, tmp / "run")
        return {"ok": True, "id": rec.get("id"), "pack": rec.get("pack"), "built": rec.get("built")}
    except TP.TemplateError as e:
        return {"ok": False, "error": str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def spec_list(root: Path) -> list[dict[str, Any]]:
    from neonrp import spec

    return spec.names()


def spec_read(root: Path, name: str, lang: str = "zh") -> str:
    from neonrp import spec

    try:
        return spec.read(name, lang=lang if lang in ("zh", "en") else "zh")
    except KeyError as e:
        raise PathRefused(str(e).strip("'\"")) from e


def instructions(root: Path, kind: str) -> str:
    what = {"template": "a NeonRP template folder", "world": "a NeonRP world folder", "soul": "a NeonRP soul (character) folder"}[kind]
    return (f"You author {what} ({root.name}) through these tools only. Read before you write. Write content natively in the "
            "target language; ids, field names and file names are ASCII. Never invent fields: read the spec first "
            f"(spec_read('{kind}'), spec_list for the rest). After every change run lint and fix every block.")


def server(root: Path) -> Any:
    from mcp.server.fastmcp import FastMCP

    kind = kind_of(root) or "world"
    mcp = FastMCP("neonrp-create", log_level="WARNING", instructions=instructions(root, kind))

    def safe(fn: Any, *a: Any) -> str:
        try:
            v = fn(root, *a)
        except (PathRefused, ValueError, OSError) as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)

    @mcp.tool(name="list_files")
    def _list_files(subdir: str = "") -> str:
        """Every file in the folder (or under subdir), with sizes."""
        return safe(list_files, subdir)

    @mcp.tool(name="read_file")
    def _read_file(path: str) -> str:
        """One text file, relative to the folder."""
        return safe(read_file, path)

    @mcp.tool(name="write_file")
    def _write_file(path: str, content: str) -> str:
        """Write (create / replace) one text file, relative to the folder. JSON must parse; only text files."""
        return safe(write_file, path, content)

    @mcp.tool(name="lint")
    def _lint() -> str:
        """Every problem the folder has: block = must fix (stops play / publishing), warn = a reminder."""
        return safe(lint)

    @mcp.tool(name="spec_list")
    def _spec_list() -> str:
        """The specs (world · soul · template · contract · ops …) that say what each file must hold."""
        return safe(spec_list)

    @mcp.tool(name="spec_read")
    def _spec_read(name: str, lang: str = "zh") -> str:
        """One spec as markdown (lang zh or en)."""
        return safe(spec_read, name, lang)

    if kind == "template":

        @mcp.tool(name="slots")
        def _slots() -> str:
            """The asset slots (map / portraits / scenes / icons) and which are still missing."""
            return safe(slots)

        @mcp.tool(name="build_preview")
        def _build_preview() -> str:
            """Build the template into a throwaway run (no model call) and report what it contains."""
            return safe(build_preview)

    return mcp


def open_root(raw: str) -> Path:
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"{root}: no such folder")
    if kind_of(root) is None:
        raise SystemExit(f"{root}: not a template (template.json), soul (soul.json) or world (game/) folder")
    return root


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m neonrp.create_mcp")
    ap.add_argument("--root", required=True, help="the template / world / soul folder the agent may edit")
    a = ap.parse_args(argv)
    server(open_root(a.root)).run()  # stdio


if __name__ == "__main__":
    main()
