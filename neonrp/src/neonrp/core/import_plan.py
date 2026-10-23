"""Plan-driven batched world-card conversion (计划-分批导入).

Large tavern cards / lorebooks can't convert in one agent turn (the build
session caps tool rounds), and an interrupted one-shot conversion leaves no
record of what landed. This module is the deterministic half of the protocol:

- the SOURCE CARD is persisted inside the world folder (``game/import/``) as a
  first-class step, so conversion never depends on an external path again;
- the PLAN lives next to it (``game/import/plan.json``) as machine-checkable
  JSON: an ordered batch list with per-batch status the agent checks off;
- batches execute sequentially, one per agent turn, each ending with a plan
  update — interruption at any point resumes from the first pending batch.

The LLM side of the protocol (how batches are decomposed and executed) lives
in ``builtin_skills/tavern-game-import/SKILL.md`` §计划-分批协议. Everything
here is engine-side and deterministic: persistence, validation, resume
detection, and the instruction strings that a UI/TUI hands to the build
session as opening messages. There are no LLM calls in this module.

Entry surface for frontends (创作门/工坊 route here explicitly — plan mode is
an OPTION the user picks, never an import-time hijack):

- ``persist_source_card(root, src)``   — land the card in the folder
- ``estimate_source(path)``            — size signal so UIs can *recommend* ①
- ``start_planned_conversion(root)``   — opening instruction for path ①
- ``resume_startup_command(root)``     — opening instruction when re-entering
- ``has_pending_plan(root)``           — "① in progress" folder state
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name

PLAN_VERSION = 1

# Recommendation thresholds (§scope: a *signal*, not a trigger). A tavern
# card under ~60KB of text converts comfortably in one turn; past that — or
# past ~40 lorebook entries — a one-shot conversion tends to die mid-way.
RECOMMEND_BYTES = 60_000
RECOMMEND_ENTRIES = 40

_ALLOWED_STATUS = {"pending", "done"}


def _import_dir(root: Path) -> Path:
    return Path(root) / get_data_dir_name(Path(root)) / "import"


def plan_path(root: Path) -> Path:
    """Stable plan location: ``<data_dir>/import/plan.json``."""
    return _import_dir(root) / "plan.json"


def persist_source_card(root: Path, source: Path | str) -> Path:
    """Copy the source card into the world folder (first-class step).

    Lands at ``<data_dir>/import/source<ext>`` (overwrite-idempotent) so every
    conversion path — planned, one-shot, manual — references the same
    persisted copy and resume never depends on the original external path.
    Returns the destination path.
    """
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f"source card not found: {src}")
    dest_dir = _import_dir(Path(root))
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower() or ".bin"
    dest = dest_dir / f"source{ext}"
    shutil.copyfile(src, dest)
    return dest


SOURCE_FORMATS = ("png-card", "json-card", "zip", "lore-text", "unknown")


def detect_source_format(source: Path | str) -> str:
    """世界卡的三态 + lore 文本,按扩展名判定(不解析内容)。

    - ``png-card``  — tavern 式 PNG(JSON 藏在 PNG 元数据里)
    - ``json-card`` — 裸 JSON 卡 / lorebook
    - ``zip``       — 世界包
    - ``lore-text`` — 纯文本设定(.txt/.md)
    """
    ext = Path(source).suffix.lower()
    return {
        ".png": "png-card",
        ".json": "json-card",
        ".zip": "zip",
        ".txt": "lore-text",
        ".md": "lore-text",
    }.get(ext, "unknown")


def _count_entries(data: Any) -> int:
    """Best-effort lorebook entry count over the known card shapes."""
    entries = 0
    if not isinstance(data, dict):
        return 0
    for holder in (
        data,
        data.get("data") or {},
        data.get("character_book") or {},
        ((data.get("data") or {}).get("character_book")) or {},
    ):
        got = holder.get("entries") if isinstance(holder, dict) else None
        if isinstance(got, (list, dict)):
            entries = max(entries, len(got))
    return entries


def estimate_source(source: Path | str) -> dict[str, Any]:
    """Deterministic size signal for UIs: ``recommend_plan`` suggests ①.

    Format-aware, reusing the existing extractors (never new parsers):
    - json-card: raw bytes + lorebook entry count
    - png-card: bytes = EXTRACTED embedded-JSON text length (image bytes
      wildly overstate content; extraction reuses the sillytavern importer),
      falling back to file size when extraction fails
    - zip / lore-text / unknown: raw bytes only
    Never raises on unreadable input — a signal, not a gate.
    """
    src = Path(source)
    size = src.stat().st_size if src.is_file() else 0
    fmt = detect_source_format(src)
    entries = 0
    if fmt == "json-card" and size:
        try:
            data = json.loads(src.read_text(encoding="utf-8", errors="replace"))
            entries = _count_entries(data)
        except Exception:
            pass
    elif fmt == "png-card" and size:
        try:
            from neonrp.core.importers.png_extract import extract_chara_from_png

            data = extract_chara_from_png(src)  # dict(内嵌 JSON)
            size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            entries = _count_entries(data)
        except Exception:
            pass  # 提取失败 → 用文件字节数兜底
    return {
        "bytes": size,
        "entries": entries,
        "format": fmt,
        "recommend_plan": size >= RECOMMEND_BYTES or entries >= RECOMMEND_ENTRIES,
    }


@dataclass
class ImportPlan:
    """Parsed, validated plan. ``raw`` keeps unknown fields intact."""

    source: str
    batches: list[dict[str, Any]]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.batches)

    @property
    def done(self) -> int:
        return sum(1 for b in self.batches if b.get("status") == "done")

    def next_pending(self) -> dict[str, Any] | None:
        for b in self.batches:
            if b.get("status") != "done":
                return b
        return None

    def progress_line(self) -> str:
        nxt = self.next_pending()
        head = f"导入计划进度 {self.done}/{self.total}"
        if nxt is None:
            return f"{head} · 全部完成"
        return f"{head} · 下一批:{nxt.get('id')} {nxt.get('title', '')}".rstrip()


def validate_plan(data: Any) -> list[str]:
    """Return a list of human-readable schema errors (empty = valid)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["plan 必须是 JSON 对象"]
    if data.get("version") != PLAN_VERSION:
        errors.append(f"version 必须为 {PLAN_VERSION}")
    if not isinstance(data.get("source"), str) or not data.get("source"):
        errors.append("source 必须是指向已持久化源卡的相对路径字符串")
    fmt = data.get("source_format")
    if fmt is not None and fmt not in SOURCE_FORMATS:
        errors.append(f"source_format 必须是 {'|'.join(SOURCE_FORMATS)} 之一")
    batches = data.get("batches")
    if not isinstance(batches, list) or not batches:
        errors.append("batches 必须是非空数组")
        return errors
    seen_ids: set[str] = set()
    for i, b in enumerate(batches):
        where = f"batches[{i}]"
        if not isinstance(b, dict):
            errors.append(f"{where} 必须是对象")
            continue
        bid = b.get("id")
        if not isinstance(bid, str) or not bid:
            errors.append(f"{where}.id 必须是非空字符串")
        elif bid in seen_ids:
            errors.append(f"{where}.id 重复:{bid}")
        else:
            seen_ids.add(bid)
        if not isinstance(b.get("title"), str) or not b.get("title"):
            errors.append(f"{where}.title 必须是非空字符串")
        if b.get("status") not in _ALLOWED_STATUS:
            errors.append(f"{where}.status 必须是 pending|done")
        if not isinstance(b.get("items"), list):
            errors.append(f"{where}.items 必须是数组")
        fw = b.get("files_written", [])
        if not isinstance(fw, list):
            errors.append(f"{where}.files_written 必须是数组")
    return errors


def load_plan(root: Path) -> ImportPlan | None:
    """Load + validate the folder's plan. None when absent or invalid.

    Invalid plans are treated as absent on purpose (fail-open to a fresh
    plan rather than wedging the flow); callers that need the errors use
    ``validate_plan`` directly.
    """
    path = plan_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if validate_plan(data):
        return None
    return ImportPlan(source=data["source"], batches=data["batches"], raw=data)


def has_pending_plan(root: Path) -> bool:
    """Folder state "① in progress": a valid plan with pending batches."""
    plan = load_plan(root)
    return plan is not None and plan.next_pending() is not None


def start_planned_conversion(root: Path, *, source_rel: str | None = None) -> str:
    """Opening instruction for path ① (制定转换计划).

    The caller (创作门/工坊 UI or TUI flow) starts a build session with this
    as the first message. Deterministic string only — the agent does the
    planning per SKILL.md §计划-分批协议.
    """
    rel = source_rel
    if rel is None:
        imp = _import_dir(Path(root))
        found = sorted(imp.glob("source.*")) if imp.is_dir() else []
        rel = (
            # as_posix: Windows 上别把反斜杠路径写进给 agent 的指令
            found[0].relative_to(Path(root)).as_posix() if found else "game/import/source.*"
        )
    fmt = detect_source_format(rel)
    fmt_hint = {
        "png-card": "(PNG 卡:JSON 内嵌在图片元数据,用现有导入路径提取,如 `import_sillytavern_card`,不要当图片读)",
        "zip": "(ZIP 世界包:逐文件读包内内容再分类)",
        "lore-text": "(纯文本设定:按 lore 分类拆解)",
    }.get(fmt, "")
    return (
        "使用内置 skill `tavern-game-import` 的【计划-分批协议】。\n"
        f"源卡已持久化在:{rel} {fmt_hint}\n"
        "第一步:通读源卡,写出 game/import/plan.json(按协议 schema,含 source_format,"
        "批次按 骨架→地点→角色→lore→任务 分解,每批 ≤8 项,首批必须是最小可玩切片)。\n"
        "第二步:立即执行第 1 批,完成后更新 plan.json 并汇报进度,然后停下等待「继续」。"
    )


def resume_startup_command(root: Path) -> str | None:
    """Opening instruction when re-entering a folder with pending batches.

    None when there is nothing to resume. Injected by the TUI continue flow
    (and usable by the studio agent panel) — it *is* the message the user
    would have typed, so it adds no extra LLM calls.
    """
    plan = load_plan(root)
    if plan is None:
        return None
    nxt = plan.next_pending()
    if nxt is None:
        return None
    return (
        "检测到未完成的导入计划(game/import/plan.json,"
        f"{plan.done}/{plan.total} 批已完成)。"
        "使用 `tavern-game-import` 的【计划-分批协议】继续:不要重新规划,"
        f"从第一个 pending 批次(`{nxt.get('id')}` {nxt.get('title', '')})接着执行,"
        "完成后更新 plan.json 并汇报进度。"
    )
