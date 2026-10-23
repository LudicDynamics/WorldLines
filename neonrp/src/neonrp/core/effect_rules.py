"""Effect rules as one free line each (「状态处理写成一行,不要把所有属性和词条都定义成死的字段」).

A world (``game/rules/status.md``) or its pack (``packs/<pack>/data/status.<lang>.md``) lists effects one per line,
written however the author likes::

    <name>: 持续 3 次结算 · 检定 -2,只作用于 DEX/STR · <what it feels like> · <how it goes away>

The engine reads only the mechanisms it can recognise in that line and leaves the rest as text for the narrator and
the host (「暧昧的话,察觉到能转译成状态的时候才当成机制,否则一带而过」):

- a countdown in resolves (``持续 3 次结算`` / ``3 turns`` / ``3ターン`` / ``3턴``) → ``turns`` (core/effects.py counts it);
- a countdown in game time (``持续 12 小时`` / ``2 days``) → ``hours`` (the clock belongs to the rpg layer, which
  turns it into an ``until`` on the world clock — packs/rpg/effects_clock.py);
- a per-resolve change (``每次结算 player.hp -1`` / ``each resolve player.hp -1``) → ``each`` (``var:delta``).

- a check modifier (``检定 -20`` / ``checks -2`` / ``判定 -10`` / ``판정 -10``) → ``check`` (the number is the
  rule's, added by the engine; whether it applies to this roll — 「只作用于用到伤处的动作」 — is still the host's call,
  made by naming the effect when it agrees the check, 10-05 decision 1). Nothing in this module knows any particular effect.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_NUM = r"(\d+(?:\.\d+)?)"
_VAR_DELTA = re.compile(r"([A-Za-z_]\w*(?:\.\w+)+)\s*:?\s*([+-]\s*\d+)")
_CLAUSE = re.compile(r"[·;;,,。、|]|\s-\s")
_RX: dict[str, Any] = {}


def _vocab() -> dict[str, Any]:
    """The unit / marker words of all four languages (src/neonrp/prompts/effect_rules.<lang>.json) → regexes, built once.
    A line in any language reads the same."""
    if _RX:
        return _RX
    from neonrp import prompts

    words: dict[str, list[str]] = {}
    for lang in prompts.LANGS:
        for k, v in (prompts.strings("effect_rules", lang) or {}).items():
            words.setdefault(k, [])
            words[k] += [w for w in (v if isinstance(v, list) else [v]) if w not in words[k]]

    def alt(k: str) -> str:
        return "|".join(re.escape(w) for w in sorted(words.get(k, []), key=len, reverse=True))

    edge = r"(?![A-Za-z])"
    _RX.update({
        "lasts": re.compile(rf"(?:{alt('lasts')}){edge}", re.IGNORECASE),
        "turns": re.compile(rf"{_NUM}\s*(?:{alt('turns')}){edge}", re.IGNORECASE),
        "strong": re.compile(rf"\d\s*(?:{alt('turns')}){edge}", re.IGNORECASE),
        "hours": re.compile(rf"{_NUM}\s*(?:{alt('hours')}){edge}", re.IGNORECASE),
        "days": re.compile(rf"{_NUM}\s*(?:{alt('days')}){edge}", re.IGNORECASE),
        "each": re.compile(rf"(?:{alt('each')})", re.IGNORECASE),
        "check": re.compile(rf"(?:{alt('check')})\s*[::]?\s*([+-]\s*\d+)", re.IGNORECASE),
        "none": {w.lower() for w in words.get("none", [])} | {"", "0", "-", "—"},
    })
    return _RX


def parse_rule(line: str) -> dict[str, Any]:
    """The mechanisms a free rule line states: {turns?, hours?, each?}. Unrecognised wording → nothing (stays text).
    A duration needs a 「持续 / lasts」 word or an unmistakable unit (次结算 / turns / ターン / 턴); a per-resolve change
    needs an 「每次结算 / each resolve」 word in the same clause."""
    rx = _vocab()
    out: dict[str, Any] = {}
    each: list[str] = []
    for clause in _CLAUSE.split(str(line or "")):
        c = clause.strip()
        if not c:
            continue
        if rx["each"].search(c):
            each += [f"{var}:{int(d.replace(' ', '')):+d}" for var, d in _VAR_DELTA.findall(c)]
            continue
        m = rx["check"].search(c)
        if m and "check" not in out:
            out["check"] = int(m.group(1).replace(" ", ""))
        lasts = bool(rx["lasts"].search(c))
        if lasts and "hours" not in out:
            m = rx["hours"].search(c) or rx["days"].search(c)
            if m:
                out["hours"] = float(m.group(1)) * (24.0 if rx["days"].search(c) and not rx["hours"].search(c) else 1.0)
                continue
        if (lasts or rx["strong"].search(c)) and "turns" not in out:
            m = rx["turns"].search(c)
            if m:
                out["turns"] = int(float(m.group(1)))
    if each:
        out["each"] = ",".join(dict.fromkeys(each))
    return out


def check_of(root: Path, e: Any) -> int:
    """An effect instance's check modifier, read off its rule line (the table's for its name, else its own ``rule``) —
    0 when the line states none. Read at roll time, so a corrected table line counts from the next roll on."""
    hit = lookup(table(root), str(getattr(e, "name", "") or ""))
    line = hit[1] if hit else str((getattr(e, "props", None) or {}).get("rule") or "")
    return int(parse_rule(line).get("check") or 0)


def normalize_each(value: Any) -> str:
    """Whatever a model wrote for a per-resolve change → ``var:+n,var:-n`` or ''. ``无`` / ``none`` / ``0`` → '';
    ``player.hp+2`` / ``player.hp -1`` / ``player.hp: -1`` → ``player.hp:+2`` / ``player.hp:-1``; anything else → ''."""
    s = str(value or "").strip()
    if s.lower() in _vocab()["none"]:
        return ""
    parts = [f"{v}:{int(d.replace(' ', '')):+d}" for v, d in _VAR_DELTA.findall(s)]
    return ",".join(dict.fromkeys(parts))


def split_line(line: str) -> tuple[str, str]:
    """``名字: 规则`` → (name, rule). Both colons (half / full width)."""
    m = re.match(r"^\s*[-*]?\s*([^::#]{1,40}?)\s*[::]\s*(.+?)\s*$", str(line or ""))
    return (m.group(1).strip(), m.group(2).strip()) if m else ("", "")


def _read_lines(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for ln in text.splitlines():
        if ln.lstrip().startswith("#"):
            continue
        n, r = split_line(ln)
        if n and r:
            out[n] = r
    return out


def world_table_path(root: Path) -> Path:
    from neonrp.core.paths import get_game_dir

    return get_game_dir(root) / "rules" / "status.md"


_TABLES: dict[tuple[str, str, float], dict[str, str]] = {}


def table(root: Path, lang: str | None = None) -> dict[str, str]:
    """{name: rule line} — the pack's lines (in the run's language), then the world's own (override / add). Cached
    until the world's table file changes (every pack reads it)."""
    from neonrp.core.output_lang import prompt_lang

    lang = lang or prompt_lang(root)
    wp = world_table_path(root)
    try:
        mt = wp.stat().st_mtime
    except OSError:
        mt = 0.0
    key = (str(Path(root).resolve()), lang, mt)
    if key not in _TABLES:
        _TABLES[key] = _table(root, lang)
    return dict(_TABLES[key])


def _table(root: Path, lang: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        from neonrp.packs import resolve as _resolve_pack

        pk = _resolve_pack(root)
        name = str(getattr(pk, "name", "") or "").split("+", 1)[0]
        base = Path(__file__).resolve().parents[1] / "packs" / name / "data"
        for cand in (f"status.{lang}.md", "status.en.md", "status.zh.md"):
            if (base / cand).is_file():
                out.update(_read_lines(base / cand))
                break
    except Exception:  # noqa: BLE001 — a world without a pack still has its own table
        pass
    out.update(_read_lines(world_table_path(root)))
    return out


def lookup(tab: dict[str, str], name: str) -> tuple[str, str] | None:
    """The table line for a status name: exact, or the name without a trailing modifier / note (「扭伤 -2」→ 扭伤)."""
    n = str(name or "").strip()
    if n in tab:
        return n, tab[n]
    base = re.split(r"\s+|[((]", n, maxsplit=1)[0]
    if base in tab:
        return base, tab[base]
    return None


def fill(root: Path, op: dict[str, Any]) -> dict[str, Any]:
    """A ``new <effect class>`` op, completed from the rule line (the table's, else the model's own note): the name
    cleaned of a stray modifier, ``each`` normalised, ``turns`` / ``hours`` from the line when the model gave none
    usable, the line kept as ``rule`` (for the narrator and the host). A line not in the table is added to the world's
    table (open rule: 「模型当场写一行新的」), so the next time the same name reads the same rule."""
    props = dict(op.get("props") or {})
    tab = table(root)
    hit = lookup(tab, str(op.get("name") or ""))
    name = hit[0] if hit else re.sub(r"\s+[+-]\d+$", "", str(op.get("name") or "").strip())
    line = hit[1] if hit else str(props.get("rule") or props.get("note") or "")
    mech = parse_rule(line)
    if "each" in props:
        props["each"] = normalize_each(props["each"])
    if not props.get("each") and mech.get("each"):
        props["each"] = mech["each"]
    if not props.get("each"):
        props.pop("each", None)
    t = str(props.get("turns") or "").strip()
    if not t.isdigit() or int(t) <= 0:
        props.pop("turns", None)
        if mech.get("turns"):
            props["turns"] = mech["turns"]
    if mech.get("hours") and not props.get("hours"):
        props["hours"] = mech["hours"]
    if hit:
        props["rule"] = line
    elif line and name and mech:
        _remember(root, name, line)
    return {**op, "name": name, "props": props}


def _remember(root: Path, name: str, line: str) -> None:
    """Append a new rule line to the world's table (once)."""
    p = world_table_path(root)
    try:
        have = _read_lines(p)
        if name in have:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        prefix = "" if p.exists() and p.read_text(encoding="utf-8").endswith("\n") else ("\n" if p.exists() else "")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{prefix}{name}: {' '.join(line.split())}\n")
    except OSError:
        pass
