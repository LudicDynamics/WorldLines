"""World-folder file ops (「新建文件、删除文件、更改文件、新建文件夹、删除文件夹 —— 没有它们就不具备 open schema 能力」).

The narrator does not read or write files itself (play mode has no file tools); it *proposes* file ops like any other
op, the engine checks them here and lands them. What exists is shown to it in the pack (the folder tree, and the
contents of what was created in play), so it never needs to read.

    write <path> + body   create or replace a .json / .md / .txt file (JSON must parse)
    edit  <path> k=v …    set keys (dotted) in a JSON file
    rm    <path>          delete a file
    mkdir <path>          create a folder
    rmdir <path>          delete a folder (and what is in it)

Sandbox: inside the world's data folder only; never its meta/ (the engine's own), never a file a registered variable or
list-backed class lives in (those change through their ops). rm / rmdir only touch what was created in play or lives
under the open-schema folder — an authored file is edited, not deleted.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name

FILE_OPS = ("write", "edit", "rm", "mkdir", "rmdir")
EXTS = (".json", ".md", ".txt")
LEDGER = "meta/play_files.json"  # what was created in play (relative to the data folder)
MAX_BYTES = 20000


def data_dir(root: Path) -> Path:
    return root / get_data_dir_name(root)


def _ledger(root: Path) -> dict[str, Any]:
    p = data_dir(root) / LEDGER
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"paths": []}


def _note_created(root: Path, rel: str, turn: int) -> None:
    led = _ledger(root)
    if rel not in led["paths"]:
        led["paths"].append(rel)
        led.setdefault("turns", {})[rel] = turn
    p = data_dir(root) / LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")


def _note_removed(root: Path, rel: str) -> None:
    led = _ledger(root)
    led["paths"] = [x for x in led["paths"] if x != rel and not x.startswith(rel.rstrip("/") + "/")]
    (data_dir(root) / LEDGER).write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize(root: Path, path: str) -> str | None:
    """A path relative to the data folder (``towns/T001/x.json``), or None if it leaves the sandbox."""
    p = str(path or "").strip().strip("`'\"").replace("\\", "/")
    dn = get_data_dir_name(root)
    if p.startswith(dn + "/"):
        p = p[len(dn) + 1:]
    p = p.strip("/")
    parts = [x for x in p.split("/") if x not in ("", ".")]
    if not parts or any(x == ".." for x in parts) or parts[0] == "meta":
        return None
    return "/".join(parts)


def protected(root: Path, reg: Any, rel: str) -> bool:
    """Files the engine owns through ops: variable sources and list-backed classes."""
    full = f"{get_data_dir_name(root)}/{rel}"
    if any(str(v.path) == full for v in reg.variables.values() if getattr(v, "path", None)):
        return True
    return any((c.list_store or ("",))[0] == full for c in reg.classes.values() if getattr(c, "list_store", None))


def protected_keys(root: Path, reg: Any, rel: str) -> set[str]:
    """Keys inside a file that belong to a registered variable or a list-backed class (edit may not touch them)."""
    full = f"{get_data_dir_name(root)}/{rel}"
    keys = {str(v.key) for v in reg.variables.values() if getattr(v, "path", None) and str(v.path) == full}
    keys |= {c.list_store[1] for c in reg.classes.values() if getattr(c, "list_store", None) and c.list_store[0] == full}
    return keys


def removable(root: Path, rel: str) -> bool:
    led = _ledger(root)
    return rel in led["paths"] or any(rel.startswith(x.rstrip("/") + "/") for x in led["paths"]) or rel.split("/")[0] == "open"


def check(root: Path, reg: Any, o: dict[str, Any]) -> str | None:
    """None = fine; otherwise the reason (fed back to the narrator)."""
    op, rel = o["op"], normalize(root, str(o.get("path") or ""))
    if rel is None:
        return f"路径 {o.get('path')!r} 不在世界文件夹里(也不能是 meta/)"
    base = data_dir(root)
    target = base / rel
    if op in ("write", "edit", "rm") and target.suffix not in EXTS:
        return f"只能操作 {', '.join(EXTS)} 文件"
    if op in ("write", "rm") and protected(root, reg, rel):
        return f"{rel} 里有引擎通过变量 / 类管理的数据,不能整份覆盖或删除(改别的键用 edit)"
    if op == "edit":
        guarded = protected_keys(root, reg, rel)
        hit = [k for k in dict(o.get("set") or {}) if any(k == g or k.startswith(g + ".") or g.startswith(k + ".") for g in guarded)]
        if hit:
            return f"{', '.join(hit)} 是变量 / 类的数据,用它们自己的 op 改"
    if op == "write":
        body = str(o.get("body") or "")
        if not body.strip():
            return "write 要带内容:[~write 路径]内容[/write]"
        if len(body.encode("utf-8")) > MAX_BYTES:
            return f"内容超过 {MAX_BYTES} 字节"
        if target.suffix == ".json":
            try:
                json.loads(body)
            except ValueError as exc:
                return f"JSON 写错了:{exc}"
        if target.is_dir():
            return f"{rel} 是文件夹"
    elif op == "edit":
        if not target.is_file() or target.suffix != ".json":
            return f"{rel} 不存在或不是 JSON 文件(新文件用 write)"
        if not o.get("set"):
            return "edit 要写 键=值"
    elif op == "rm":
        if not target.is_file():
            return f"{rel} 不存在"
        if not removable(root, rel):
            return f"{rel} 是作者写的文件,不能删(要改它用 edit)"
    elif op == "mkdir":
        if target.exists():
            return f"{rel} 已经存在"
    elif op == "rmdir":
        if not target.is_dir():
            return f"{rel} 不是文件夹"
        if not removable(root, rel):
            return f"{rel} 不是游玩中建的文件夹,不能删"
    return None


def _coerce(v: str) -> Any:
    s = str(v)
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s


def apply(root: Path, o: dict[str, Any], turn: int) -> dict[str, Any]:
    rel = normalize(root, str(o.get("path") or "")) or ""
    target = data_dir(root) / rel
    op = o["op"]
    if op == "write":
        new = not target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        body = str(o.get("body") or "")
        if target.suffix == ".json":
            body = json.dumps(json.loads(body), ensure_ascii=False, indent=2)
        target.write_text(body.strip() + "\n", encoding="utf-8")
        if new:
            _note_created(root, rel, turn)
        return {"op": "write", "path": rel, "new": new}
    if op == "edit":
        data = json.loads(target.read_text(encoding="utf-8"))
        changes = {}
        for k, v in dict(o.get("set") or {}).items():
            cur = data
            parts = str(k).split(".")
            for part in parts[:-1]:
                cur = cur.setdefault(part, {}) if isinstance(cur, dict) else {}
            if isinstance(cur, dict):
                changes[k] = {"from": cur.get(parts[-1]), "to": _coerce(v)}
                cur[parts[-1]] = _coerce(v)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"op": "edit", "path": rel, "set": changes}
    if op == "rm":
        target.unlink()
        _note_removed(root, rel)
        return {"op": "rm", "path": rel}
    if op == "mkdir":
        target.mkdir(parents=True, exist_ok=True)
        _note_created(root, rel, turn)
        return {"op": "mkdir", "path": rel}
    if op == "rmdir":
        shutil.rmtree(target)
        _note_removed(root, rel)
        return {"op": "rmdir", "path": rel}
    return {}


def tree(root: Path, max_entries: int = 160) -> str:
    """The world folder as the narrator sees it: one line per folder with its files (meta/ left out)."""
    base = data_dir(root)
    if not base.is_dir():
        return ""
    lines, n = [], 0
    for d in sorted([base, *[p for p in base.rglob("*") if p.is_dir()]]):
        rel = "" if d == base else str(d.relative_to(base))
        if rel.split("/")[0] == "meta":
            continue
        files = sorted(p.name for p in d.iterdir() if p.is_file() and p.suffix in EXTS)
        lines.append(f"{rel or '.'}/" + (": " + " ".join(files) if files else ""))
        n += 1 + len(files)
        if n > max_entries:
            lines.append("…")
            break
    return "\n".join(lines)


def created_contents(root: Path, budget: int = 1800) -> str:
    """What was written in play (so the narrator knows what it made without reading)."""
    out, used = [], 0
    for rel in _ledger(root)["paths"]:
        p = data_dir(root) / rel
        if not p.is_file():
            continue
        t = p.read_text(encoding="utf-8").strip()
        t = t if len(t) < 600 else t[:600] + " …"
        if used + len(t) > budget:
            break
        out.append(f"--- {rel}\n{t}")
        used += len(t)
    return "\n".join(out)
