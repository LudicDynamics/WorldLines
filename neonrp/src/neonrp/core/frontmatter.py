"""Frontmatter Markdown — the world's native document format.

A world's substance is prose with a few queryable facts attached: who this
character is, where they stand, what they are tagged with. Frontmatter holds
the facts, the body holds the prose, and the same file serves both the reader
and the index. See `docs/DATA-FORMAT.md` for why this replaces JSON for
anything a person would actually read.

**No YAML dependency, on purpose.** We parse a constrained subset instead —
the shape Obsidian itself writes for properties, and the shape we want a
model to emit. A full YAML parser would accept far more than we can validate
or repair, and the engine stays thin.

**There is a repair boundary, also on purpose.** `core/json_repair.py` exists
because models write broken JSON; they write broken frontmatter for the same
reasons. What can be fixed deterministically is fixed (full-width colons, a
missing closing fence); what cannot is refused *with the offending line*,
never swallowed. A silently-dropped field would surface later as a character
who mysteriously has no name.

Supported subset:

    ---
    id: luowen                  # scalar
    kind: soul
    aliases: [luowen, 罗文]      # inline list
    tags:                       # block list
      - smith
      - taciturn
    所在: "石津镇·北门"          # quoted (keeps a colon safely)
    turn: 7                     # number
    active: true                # boolean
    ---

Not supported (and refused rather than half-parsed): nested mappings,
multi-line scalars (`|` / `>`), anchors, and anything else that would make
the file unrepairable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

FENCE = "---"

# Models reach for the full-width punctuation their prose uses. These are
# unambiguous in a key position, so fixing them beats refusing the file.
_FULLWIDTH_COLON = "："
_FULLWIDTH_COMMA = "，"
_SMART_QUOTES = {"“": '"', "”": '"', "‘": "'", "’": "'"}

_KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[^:\s][^:]*?)\s*:\s*(?P<value>.*)$")
_LIST_ITEM_RE = re.compile(r"^\s*-\s+(?P<value>.*)$")


class FrontmatterError(ValueError):
    """Malformed frontmatter that could not be repaired.

    Carries the line number so the author (or the agent that wrote it) is
    told *where*, not just that something is wrong.
    """

    def __init__(self, message: str, *, line: int | None = None) -> None:
        self.line = line
        super().__init__(f"{message} (第 {line} 行)" if line else message)


@dataclass
class Document:
    """One parsed document: the facts, the prose, and whether we healed it."""

    fields: dict[str, Any]
    body: str
    repaired: list[str]

    @property
    def is_entity(self) -> bool:
        """Whether this document claims to be a world entity."""
        return bool(self.fields.get("id") and self.fields.get("kind"))


def has_frontmatter(text: str) -> bool:
    return text.lstrip("﻿").startswith(FENCE)


def _heal_line(line: str) -> tuple[str, str | None]:
    """Fix what is unambiguous. Returns (line, what-was-fixed)."""
    original = line
    # Only the *first* colon decides the key, so a full-width one there is a
    # typo we can fix; inside a value it is legitimate punctuation.
    if _FULLWIDTH_COLON in line and ":" not in line.split(_FULLWIDTH_COLON, 1)[0]:
        head, _, tail = line.partition(_FULLWIDTH_COLON)
        line = f"{head}:{tail}"
    for smart, plain in _SMART_QUOTES.items():
        line = line.replace(smart, plain)
    return line, ("全角标点" if line != original else None)


def _coerce(raw: str) -> Any:
    """A scalar, as the author most likely meant it."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    lowered = value.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    if lowered in ("null", "none", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d*\.\d+", value):
        return float(value)
    return value


def _split_inline_list(raw: str) -> list[Any]:
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    inner = inner.replace(_FULLWIDTH_COMMA, ",")
    return [_coerce(part) for part in inner.split(",") if part.strip()]


def parse(text: str) -> Document:
    """Parse a frontmatter document. Raises FrontmatterError when unrepairable."""
    text = text.lstrip("﻿")
    if not has_frontmatter(text):
        return Document(fields={}, body=text, repaired=[])

    lines = text.splitlines()
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == FENCE:
            end = index
            break

    repaired: list[str] = []
    if end is None:
        # A model that forgot the closing fence is the single most common
        # breakage. If a blank line separates the block from the prose we can
        # infer where it ended; otherwise the file is genuinely ambiguous.
        for index in range(1, len(lines)):
            if not lines[index].strip():
                end = index
                repaired.append("补上缺失的结束 ---")
                break
        if end is None:
            raise FrontmatterError("frontmatter 没有结束的 ---", line=len(lines))

    fields: dict[str, Any] = {}
    pending_key: str | None = None
    pending_list: list[Any] = []

    def _flush() -> None:
        nonlocal pending_key, pending_list
        if pending_key is not None:
            fields[pending_key] = pending_list
            pending_key, pending_list = None, []

    for offset in range(1, end):
        lineno = offset + 1
        raw_line = lines[offset]
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        line, fixed = _heal_line(raw_line)
        if fixed:
            repaired.append(f"第 {lineno} 行:{fixed}")

        item = _LIST_ITEM_RE.match(line)
        if item is not None:
            if pending_key is None:
                raise FrontmatterError("列表项没有对应的键", line=lineno)
            pending_list.append(_coerce(item.group("value")))
            continue

        match = _KEY_RE.match(line)
        if match is None:
            raise FrontmatterError(f"看不懂这一行:{raw_line.strip()!r}", line=lineno)

        _flush()
        key = match.group("key").strip()
        value = match.group("value").strip()
        if not key:
            raise FrontmatterError("空的键名", line=lineno)

        if not value:
            # Either a block list follows, or the field is simply empty.
            pending_key, pending_list = key, []
            continue
        if value.startswith("[") and value.endswith("]"):
            fields[key] = _split_inline_list(value)
            continue
        if value.startswith("{"):
            raise FrontmatterError(
                "不支持嵌套结构:纯结构的数据请留在 JSON 里(见 docs/DATA-FORMAT.md)",
                line=lineno,
            )
        fields[key] = _coerce(value)

    _flush()
    body = "\n".join(lines[end + 1 :]).strip("\n")
    return Document(fields=fields, body=body, repaired=repaired)


def _render_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(str(v) for v in value) + "]"
    text = str(value)
    # Quote anything whose colon would otherwise look like a key boundary.
    return f'"{text}"' if ": " in text else text


def render(fields: dict[str, Any], body: str = "") -> str:
    """The inverse of :func:`parse`, for whoever writes these files next."""
    lines = [FENCE]
    for key, value in fields.items():
        if value is None or value == [] or value == "":
            continue
        lines.append(f"{key}: {_render_value(value)}")
    lines.append(FENCE)
    text = "\n".join(lines)
    return f"{text}\n\n{body.strip()}\n" if body.strip() else f"{text}\n"
