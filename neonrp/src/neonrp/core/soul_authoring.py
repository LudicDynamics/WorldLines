"""LLM-driven scaffolder for the ``soul-authoring`` builtin skill.

The ``soul-authoring`` skill (``builtin_skills/soul-authoring/SKILL.md``)
is the soul-side mirror of ``world-game-authoring``: given a one-line
soul description plus an ``agent_template``, it fills the empty subfolders
that :func:`neonrp.core.souls.create_soul_dir` mints with real content.

``world-game-authoring`` realises that contract purely as agent
instructions driven by the conversation runtime. Souls additionally get
this thin, importable, *testable* scaffolder so the create flow can run
the skill once headlessly and so the folder shape can be asserted under
a stubbed LLM (no network in tests). The skill document is still the
authoritative instruction surface — this module only enforces the
on-disk contract (M16 §2 schema + §2.3 write-permission boundaries) and
guarantees a valid ``agents/manifest.json`` regardless of what the model
returns.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from neonrp.core.souls import SOUL_CHARTER_FILENAME, SOUL_SUBFOLDERS


# 统一 roster(2026-08-12):**1 soul = 1 agent**。
# 旧 M16 六路分解(orchestrator/mind/memory/action/dialogue/narrative)
# 与 `.claude/agents/soul-*.md` 硬编码全部废除——运行时从未读过那些
# 路径(prompt 由 soul_agent 的 system.md 契约合成),数据面不再说谎。
# write_globs = soul 自己的 context 全域(M30:soul 只改自己,对世界只读;
# 写世界=world-agent 经 ontology 工具)——即旧六路 write 面的并集。
_SOUL_AGENT_ROSTER: list[dict[str, Any]] = [
    {
        "id": "soul-agent",
        "role": "soul",
        "write_globs": [
            "run_state.json",
            "trajectory/**",
            "short-term-memo/**",
            "long-term-memo/**",
            "character/**",
        ],
    },
]

# The files each content subfolder must contain after scaffolding, per
# the M16 §2 / WORLD_SOUL_FOLDERS §2 schema. ``.json`` files hold
# structured facts; ``.md`` files hold prose. ``agents/`` and
# ``.commits/`` are handled separately (manifest is template-driven;
# ``.commits/`` is the version store, not authored content).
_PERSONA_FILES: tuple[str, ...] = (
    "core_traits.json",
    "motivations.json",
    "values.json",
    "relationships.json",
)
_BACKGROUND_FILES: tuple[str, ...] = ("origin.md", "history.md", "secrets.md")
_CHARACTER_FILES: tuple[str, ...] = (
    "stats.json",
    "inventory.json",
    "equipment.json",
    "wallet.json",
    "status.json",
    "profile.json",
)
_RULES_FILES: tuple[str, ...] = (
    "decision_rules.md",
    "interaction_rules.md",
    "action_rules.md",
)
_SHORT_TERM_FILES: tuple[str, ...] = (
    "current_context.json",
    "conversation_cache.json",
    "recent_events.json",
)
_LONG_TERM_FILES: tuple[str, ...] = (
    "important_events.md",
    "learned_facts.json",
    "emotional_memories.json",
)


class _LLMLike(Protocol):
    """Minimal slice of :class:`neonrp.core.llm.LLMAdapter` we depend on.

    Declared structurally (not imported) so tests can pass any stub with
    a compatible ``generate`` without dragging in the full adapter graph.
    """

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any: ...


def _agents_for_template(agent_template: str) -> list[dict[str, Any]]:
    # M30 收敛:模板名(heroine-classic/minimal/…)保留为创作口味标记,
    # 但 roster 统一为单 soul-agent——1 soul = 1 agent,无分解。
    del agent_template
    return [dict(agent) for agent in _SOUL_AGENT_ROSTER]


def build_manifest(agent_template: str) -> dict[str, Any]:
    """Return the ``agents/manifest.json`` payload for ``agent_template``.

    Deterministic and LLM-free: the roster is policy, not generated
    content, so the manifest is always valid even if the model misbehaves.
    """
    return {
        "schema_version": 1,
        "agent_template": agent_template,
        "agents": _agents_for_template(agent_template),
    }


def ensure_soul_agent(soul_dir: Path, *, agent_template: str = "heroine-classic") -> bool:
    """Idempotently guarantee a soul can run as a multi-agent soul.

    The ONLY thing the runtime needs to spin up a soul-agent is a valid
    ``agents/manifest.json`` with a non-empty ``agents`` roster —
    :func:`neonrp.core.soul_agent.resolve_soul_agent_data` derives the soul's
    write-scope from it and synthesises the prompt inline from the soul's own
    persona (the manifest's ``system_prompt`` paths are NOT read). When that
    manifest is missing it returns ``None`` and the soul-agent turn errors out
    ("soul agent error"). Created/cast/imported souls have historically been
    minted without it; this backfills the deterministic template roster so any
    soul folder is runnable. Returns ``True`` iff it wrote the manifest.

    Mirror of :func:`neonrp.core.runtime_contract.ensure_playable_world` but
    for the soul side of the multi-agent contract.
    """
    soul_dir = Path(soul_dir)
    manifest_path = soul_dir / "agents" / "manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("agents"), list) and data["agents"]:
            return False  # already runnable — leave it
    except (OSError, ValueError):
        pass  # absent or malformed → (re)write below

    _write_json(manifest_path, build_manifest(agent_template))
    contracts_path = soul_dir / "agents" / "contracts.md"
    if not contracts_path.exists():
        sid = ""
        try:
            meta = json.loads((soul_dir / "soul.json").read_text(encoding="utf-8"))
            sid = str(meta.get("sid") or "")
        except (OSError, ValueError):
            pass
        sid = sid or soul_dir.name
        _write_md(
            contracts_path,
            f"# Soul Agent Contract — {sid}\n\n"
            "1 soul = 1 agent(M30)。写面 = manifest.json 的 `write_globs`"
            "(soul 只改自己的 context;越界写入被 apply 管线拒绝)。\n"
            "prompt 契约:引擎默认 system.md 模板,可被本 soul 的 "
            "`agents/soul-agent/system.md` 覆盖。\n",
        )
    return True


def _system_prompt(skill_body: str) -> str:
    return (
        "You are the soul-authoring skill. Fill a freshly-minted NeonRP "
        "soul folder with content consistent with the user's description.\n\n"
        + skill_body
    )


def _user_prompt(description: str, sid: str, agent_template: str) -> str:
    # The model is asked for one JSON object whose keys are
    # "<subfolder>/<file>" and whose values are the file *contents*
    # (objects for .json, strings for .md). We extract whatever it
    # returns and backfill anything missing so the on-disk contract
    # always holds — same defensive posture worlds rely on.
    return json.dumps(
        {
            "sid": sid,
            "agent_template": agent_template,
            "description": description,
            "instruction": (
                "Return a single JSON object mapping "
                '"<subfolder>/<filename>" to that file\'s content. '
                'Use "soul.md" for the root soul charter, plus the persona/background/character/rules/'
                "short-term-memo/long-term-memo files named in the skill. "
                "Do not include soul.json, run_state.json, or agents/."
            ),
        },
        ensure_ascii=False,
    )


def _coerce_files(raw: Any, *, repair_llm: _LLMLike | None = None) -> dict[str, Any]:
    """Best-effort extraction of a ``{path: content}`` map from LLM output.

    Tolerant of stub/real adapters that surface text via ``proposal_text``
    or ``raw_output``, and of models that wrap the object in prose.
    Returns ``{}`` (never raises) so scaffolding can fall back to seeds.

    Escalation before giving up: strict parse → deterministic repair
    (:func:`neonrp.core.json_repair.loads_repaired`) → when ``repair_llm`` is
    given, ONE last-resort LLM repair request — a hollow seeds-only soul is
    strictly worse than one extra focused call with the adapter we already
    hold. Only then fall back to ``{}``.
    """
    text: str | None = None
    if isinstance(raw, str):
        text = raw
    else:
        text = getattr(raw, "proposal_text", None) or getattr(raw, "raw_output", None)
    if not text:
        return {}

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    sliced = text[start : end + 1]
    try:
        parsed = json.loads(sliced)
    except (ValueError, TypeError):
        from neonrp.core.json_repair import (
            JsonRepairError,
            loads_repaired,
            repair_json_with_llm,
        )

        try:
            parsed = loads_repaired(sliced)
        except JsonRepairError as exc:
            if repair_llm is None:
                return {}
            try:
                parsed = repair_json_with_llm(sliced, repair_llm, error=exc)
            except JsonRepairError:
                return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _seed_json(rel: str, sid: str, description: str) -> dict[str, Any]:
    # Plausible-but-minimal defaults so a soul is structurally complete
    # even when the LLM omits a file. Keeps persona/background/rules
    # non-empty (nothing writes them after creation — §2.3).
    if rel == "character/profile.json":
        return {"sid": sid, "name": sid, "name_local": "", "summary": description}
    if rel == "character/stats.json":
        return {"level": 1, "hp": 10, "mp": 5}
    if rel == "character/status.json":
        return {"hp": 10, "mp": 5, "energy": 100, "mood": "neutral"}
    if rel in ("character/inventory.json", "character/equipment.json"):
        return {"items": []}
    if rel == "character/wallet.json":
        return {"currency": "credits", "amount": 0}
    if rel == "persona/relationships.json":
        return {"dispositions": []}
    if rel == "short-term-memo/recent_events.json":
        return {"events": []}
    if rel == "long-term-memo/learned_facts.json":
        return {"facts": []}
    if rel == "long-term-memo/emotional_memories.json":
        return {"memories": []}
    # Generic structured seed carries the seed description so the file is
    # never an empty husk.
    return {"sid": sid, "seed": description}


def _seed_md(rel: str, sid: str, description: str) -> str:
    if rel == SOUL_CHARTER_FILENAME:
        return (
            f"# Soul Charter — {sid}\n\n"
            "## Core Presence\n\n"
            f"{description}\n\n"
            "## Voice And Social Posture\n\n"
            "Fill this charter during soul authoring so the runtime has a fast natural-language "
            "anchor for how this soul should feel and behave.\n"
        )
    if rel == "trajectory/action_log.md":
        # Header only — the runtime appends; never fabricate history.
        return f"# Trajectory — {sid}\n\n<!-- append-only; runtime writes below -->\n"
    title = rel.split("/")[-1].removesuffix(".md").replace("_", " ").title()
    return f"# {title} — {sid}\n\n{description}\n"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _scaffold_group(
    soul_dir: Path,
    subfolder: str,
    files: tuple[str, ...],
    *,
    json_files: bool,
    llm_files: dict[str, Any],
    sid: str,
    description: str,
) -> list[str]:
    written: list[str] = []
    for fname in files:
        rel = f"{subfolder}/{fname}"
        dest = soul_dir / subfolder / fname
        if json_files:
            value = llm_files.get(rel)
            data = value if isinstance(value, (dict, list)) else _seed_json(rel, sid, description)
            _write_json(dest, data)
        else:
            value = llm_files.get(rel)
            text = value if isinstance(value, str) and value.strip() else _seed_md(rel, sid, description)
            _write_md(dest, text)
        written.append(rel)
    return written


def scaffold_soul(
    soul_dir: Path,
    *,
    description: str,
    sid: str,
    agent_template: str,
    llm: _LLMLike,
    skill_body: str = "",
) -> dict[str, Any]:
    """Fill an already-minted soul folder with authored content.

    Mirrors ``world-game-authoring``'s IO contract: the folder skeleton
    already exists (from :func:`create_soul_dir`); this runs the skill
    once via ``llm`` and writes the seed files. The LLM result is treated
    as best-effort — every required file is backfilled with a structural
    seed so the M16 §2 schema always holds. ``agents/manifest.json`` is
    deterministic (template policy, never LLM-authored).

    Returns a summary ``{"written": [...], "manifest": {...}}``.
    """
    soul_dir = Path(soul_dir)
    # Defensive: re-assert the skeleton in case the caller passed a bare
    # path. Matches `create_soul_dir`'s subfolder set exactly.
    for sub in SOUL_SUBFOLDERS:
        (soul_dir / sub).mkdir(parents=True, exist_ok=True)

    response = llm.generate(
        system_prompt=_system_prompt(skill_body),
        user_prompt=_user_prompt(description, sid, agent_template),
    )
    # Same adapter doubles as the last-resort JSON repairer: an output the
    # deterministic passes can't parse gets ONE focused repair request
    # before we settle for a hollow seeds-only soul.
    llm_files = _coerce_files(response, repair_llm=llm)

    written: list[str] = []
    root_charter = llm_files.get(SOUL_CHARTER_FILENAME)
    charter_text = (
        root_charter
        if isinstance(root_charter, str) and root_charter.strip()
        else _seed_md(SOUL_CHARTER_FILENAME, sid, description)
    )
    _write_md(soul_dir / SOUL_CHARTER_FILENAME, charter_text)
    written.append(SOUL_CHARTER_FILENAME)
    written += _scaffold_group(
        soul_dir, "persona", _PERSONA_FILES,
        json_files=True, llm_files=llm_files, sid=sid, description=description,
    )
    written += _scaffold_group(
        soul_dir, "background", _BACKGROUND_FILES,
        json_files=False, llm_files=llm_files, sid=sid, description=description,
    )
    written += _scaffold_group(
        soul_dir, "character", _CHARACTER_FILES,
        json_files=True, llm_files=llm_files, sid=sid, description=description,
    )
    written += _scaffold_group(
        soul_dir, "rules", _RULES_FILES,
        json_files=False, llm_files=llm_files, sid=sid, description=description,
    )
    written += _scaffold_group(
        soul_dir, "short-term-memo", _SHORT_TERM_FILES,
        json_files=True, llm_files=llm_files, sid=sid, description=description,
    )
    written += _scaffold_group(
        soul_dir, "long-term-memo", _LONG_TERM_FILES,
        json_files=False, llm_files=llm_files, sid=sid, description=description,
    )

    # trajectory/ stays empty except for an append-only header stub —
    # never pre-populate autonomous actions that did not happen (§2.3).
    _write_md(
        soul_dir / "trajectory" / "action_log.md",
        _seed_md("trajectory/action_log.md", sid, description),
    )
    written.append("trajectory/action_log.md")

    manifest = build_manifest(agent_template)
    _write_json(soul_dir / "agents" / "manifest.json", manifest)
    written.append("agents/manifest.json")

    # contracts.md documents the per-agent IO surface; prose companion to
    # the manifest, same as the world bundle's agents/ companion files.
    _write_md(
        soul_dir / "agents" / "contracts.md",
        f"# Soul Agent Contracts — {sid}\n\n"
        f"Template: `{agent_template}`. "
        "Each agent's write surface is the `write_globs` in manifest.json; "
        "the apply pipeline rejects writes outside it.\n",
    )
    written.append("agents/contracts.md")

    return {"written": written, "manifest": manifest}
