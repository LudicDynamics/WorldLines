"""Soul-agent resolver — the engine path that turns a soul folder into a
real agent the existing turn loop can run.

A soul is NOT a bespoke class. It is a regular NeonRP agent whose
definition is *synthesised in memory* from the soul's own
``souls/<sid>-<iid>/agents/manifest.json`` (the M16 specialist roster)
plus its own ``persona/`` — never a hand-authored ``agents/<id>/``. This
keeps the soul folder self-contained / portable (the M16 intent) and
makes ``world-agent`` and a soul the SAME framework: same
``run_conversation_turn`` path, only the synthesised system prompt +
read/write scope differ.

``_load_agent_data_for_mode`` consults :func:`resolve_soul_agent_data`
when an ``agent_id`` has the soul form ``soul:<sid>:<instance_id>``. No
files are written; the synthesised ``agent.json``-shaped dict carries the
prompt inline (the agent loader's priority-3 inline path consumes it).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from neonrp import prompts as _prompts

logger = logging.getLogger(__name__)

# agent_id scheme for a soul turn. Parsed by the agent loader hook.
_SOUL_AGENT_PREFIX = "soul:"

# Soul subfolders that are immutable post-creation (M16 contracts.md:
# "Immutable post-creation: persona/, background/, rules/ — no writer").
_IMMUTABLE_SUBDIRS = ("persona", "background", "rules")


def parse_soul_agent_id(agent_id: str) -> tuple[str, str] | None:
    """``soul:<sid>:<instance_id>`` → ``(sid, instance_id)`` else ``None``."""
    if not agent_id.startswith(_SOUL_AGENT_PREFIX):
        return None
    rest = agent_id[len(_SOUL_AGENT_PREFIX):]
    parts = rest.split(":")
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1]


def make_soul_agent_id(sid: str, instance_id: str) -> str:
    return f"{_SOUL_AGENT_PREFIX}{sid}:{instance_id}"


def _soul_dir(root: Path, sid: str, instance_id: str) -> Path:
    return root / "souls" / f"{sid}-{instance_id}"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _persona_blurb(soul_dir: Path) -> str:
    """Inline the soul's OWN persona so the prompt is self-contained even
    before the agent reads its folder (it still may, via read scope)."""
    chunks: list[str] = []
    pdir = soul_dir / "persona"
    if pdir.is_dir():
        for fp in sorted(pdir.glob("*.json")):
            body = (_read_json(fp) or {})
            if body:
                chunks.append(f"{fp.name}: {json.dumps(body, ensure_ascii=False)}")
    return "\n".join(chunks) if chunks else "(persona 文件缺失)"


def _soul_charter_blurb(soul_dir: Path) -> str:
    """Return the root ``soul.md`` charter when present.

    `soul.md` is the prose-facing integration layer above persona/*.json.
    Runtime prompt synthesis should surface it first so the soul keeps its
    voice and pressure pattern even before it reads any files on-turn.
    """
    path = soul_dir / "soul.md"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "(soul.md 缺失)"
    return text or "(soul.md 为空)"


def _soul_runtime_role(root: Path, sid: str, instance_id: str, soul_dir: Path) -> str:
    """Best-effort runtime role for prompt synthesis.

    The authoritative role lives in playthrough.json. Fall back to the
    soul-local character profile so loose soul tests / authoring tools still
    get a useful prompt when no playthrough exists yet.
    """
    pt_path = root / ".neonrp" / "playthrough.json"
    data = _read_json(pt_path)
    if isinstance(data, dict):
        souls = data.get("souls")
        if isinstance(souls, list):
            for entry in souls:
                if not isinstance(entry, dict):
                    continue
                if entry.get("sid") == sid and entry.get("instance_id") == instance_id:
                    role = str(entry.get("role") or "").strip().lower()
                    if role:
                        return role
    profile = _read_json(soul_dir / "character" / "profile.json")
    if isinstance(profile, dict):
        role = str(profile.get("role") or "").strip().lower()
        if role:
            return role
    return "npc"


def _role_contract(role: str, name: str, lang: str = "zh") -> str:
    """角色权限契约。语言隔离:中/英/日三份,按 output_lang 选。"""
    is_player = str(role or "").strip().lower() == "player"
    bank = _ROLE_CONTRACTS.get(lang, _ROLE_CONTRACTS["zh"])
    return (bank["player"] if is_player else bank["npc"]).replace("{name}", name)


# 角色权限契约 · 中/英/日(与 _SYSTEM_TEMPLATES 同套语言隔离)。{name} 逐字替换。
_ROLE_CONTRACTS: dict[str, dict[str, str]] = _prompts.by_lang("soul_agent", "_ROLE_CONTRACTS")


# 默认 soul-agent 契约(M30:1 soul = 1 agent)。
# 可被该 soul 自己的 `agents/soul-agent/system.md` 整体覆盖(override 文件
# 用同名 {token} 占位符;渲染=逐 token 替换,非 str.format,花括号安全)。
# RP 三原则(M30 §4):视角优先 / 秘密隔离 / 地点一致性。
# soul-agent 隐藏系统模板 · 中/英/日三份(语言隔离:骨架做
# 三份,按本局 output_lang 选用;彻底隔离,含这段隐藏提示词)。token 用
# ``{name}`` 等,渲染=逐 token 替换(见 _render_soul_system),花括号安全。
_SYSTEM_TEMPLATES: dict[str, str] = _prompts.md_by_lang("soul_agent_system")


def _system_template(soul_dir: Path, lang: str = "zh") -> str:
    """soul 的 prompt 契约:该 soul 自己的 override 优先,缺省用引擎模板。

    override 文件 = ``<soul>/agents/soul-agent/system.md``(M30:契约可编辑,
    不再是写死的 Python 字符串;旧 manifest 的 ``system_prompt`` 路径彻底
    废除——运行时从未读过它们)。

    ``lang``(语言隔离):无 override 时,按本局 output_lang 从
    中/英/日三份引擎模板里选;override 存在则整体优先(作者自负语言)。
    """
    override = soul_dir / "agents" / "soul-agent" / "system.md"
    try:
        text = override.read_text(encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    return _SYSTEM_TEMPLATES.get(lang, _SYSTEM_TEMPLATES["zh"])


def _render_soul_system(template: str, **values: str) -> str:
    """逐 token 替换渲染(``{name}`` 等)。不用 str.format——override 是
    用户可编辑的 markdown,正文里任何花括号(JSON 例子等)都必须安全。"""
    out = template
    for key, val in values.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def resolve_soul_agent_data(
    root: Path, sid: str, instance_id: str
) -> dict[str, Any] | None:
    """Synthesise an ``agent.json``-shaped dict for a soul turn.

    **1 soul = 1 agent**(M30,2026-08-12 定案;M16 六路分解废除):写面 =
    manifest roster 各条 ``write_globs`` 的并集(rebase 到 soul 文件夹——
    对新版单条 roster 就是它自己;旧世界的多条 roster 也照样并,兼容不炸)。
    prompt = system.md 契约(soul 自己的 ``agents/soul-agent/system.md``
    可整体覆盖引擎默认)+ 该 soul 的 charter/persona 注入。

    Returns ``None`` when the soul folder / manifest is absent (caller
    falls through to normal agent resolution).
    """
    soul_dir = _soul_dir(root, sid, instance_id)
    manifest = _read_json(soul_dir / "agents" / "manifest.json")
    roster = manifest.get("agents") if isinstance(manifest, dict) else None
    if not isinstance(roster, list) or not roster:
        # Self-heal: a soul minted (or cast/imported) without an agent roster
        # cannot run — returning None here surfaces as "soul agent error". If
        # the soul folder really exists, backfill the deterministic template
        # manifest and re-read. Idempotent; only the first call writes.
        if not soul_dir.is_dir():
            return None
        try:
            from neonrp.core.soul_authoring import ensure_soul_agent

            ensure_soul_agent(soul_dir)
            manifest = _read_json(soul_dir / "agents" / "manifest.json")
            roster = manifest.get("agents") if isinstance(manifest, dict) else None
        except Exception:
            return None
        if not isinstance(roster, list) or not roster:
            return None

    soul_rel = f"souls/{sid}-{instance_id}"
    soul_meta = _read_json(soul_dir / "soul.json") or {}
    name = soul_meta.get("name_local") or soul_meta.get("name") or sid
    role = _soul_runtime_role(root, sid, instance_id, soul_dir)

    # write scope = union of every specialist's write_globs, rebased onto
    # this soul's folder (manifest globs are soul-relative).
    write_globs: list[str] = []
    for entry in roster:
        if not isinstance(entry, dict):
            continue
        for g in entry.get("write_globs", []) or []:
            if isinstance(g, str) and g.strip():
                rebased = f"{soul_rel}/{g}"
                if rebased not in write_globs:
                    write_globs.append(rebased)

    # A soul perceives the SCENE (run_state / timeline / locations), never
    # the world's casting/ontology sheet. game/meta/roster.json declares
    # who the player is and which souls are projections — world-agent
    # territory. Leaking it let a soul read "the player is fixed to X"
    # and meta-reason about player ontology instead of staying in
    # character (the observed context-bleed). Souls also never read
    # game/player/* — that is the human player's own state, not theirs.
    read_globs = [
        f"{soul_rel}/**",
        "game/meta/run_state.json",
        "game/timeline/**",
        "game/locations/**",
        ".neonrp/manifest.json",
    ]
    # Cross-soul isolation comes from SCOPED ALLOW (read/write globs only
    # ever name THIS soul's folder) — NOT a blanket `souls/**` deny, which
    # under deny-first would also kill the soul's OWN writes. Deny only:
    # this soul's immutable subdirs (persona/background/rules — no writer
    # post-creation, M16 contracts) + GM lore + engine internals.
    deny_globs = [
        *[f"{soul_rel}/{d}/**" for d in _IMMUTABLE_SUBDIRS],
        "game/lore/gm-truth.md",
        "game/lore/notes.md",
        # Secrets overlay is GM territory (docs/SECRETS-DESIGN.md §b). The
        # scoped allow-list above already excludes it; this deny makes the
        # boundary explicit rather than an accident of the allow set.
        "game/secrets/**",
        ".neonrp/**",
        "agents/**",
    ]

    # 语言隔离:无 soul override 时,隐藏系统模板 + 角色权限
    # 契约按本局 output_lang 选中/英/日(就近读 run_state,不穿参数)。
    from neonrp.core.output_lang import resolve_output_lang

    lang = resolve_output_lang(root)
    system_prompt = _render_soul_system(
        _system_template(soul_dir, lang),
        name=name,
        sid=sid,
        soul_rel=soul_rel,
        role_contract=_role_contract(role, name, lang),
        charter=_soul_charter_blurb(soul_dir),
        persona=_persona_blurb(soul_dir),
    )

    return {
        "id": make_soul_agent_id(sid, instance_id),
        "name": name,
        "description": f"soul-agent「{name}」(1 soul = 1 agent,M30).",
        "version": "1.0",
        "system_prompt": system_prompt,  # inline text (loader priority 3)
        "context_limit": 20,
        "permissions": {
            "read_globs": read_globs,
            "write_globs": write_globs,
            "deny_globs": deny_globs,
            "direct_write_globs": write_globs,
        },
        "defaults": {"context_limit": 20, "temperature": 0.85},
    }
