"""Conversation engine for M9 interactive loop."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from neonrp.core.active_agent import (
    NARRATOR_AGENT,
    get_active_agent_id,
    get_narrator_agent_id,
    write_active_agent,
)
from neonrp.core.agent_runner import _build_task_tool_schema, _execute_tool, run_agent_agentic
from neonrp.core.checkpoint import create_checkpoint
from neonrp.core.config import TUIConfig, load_config, resolve_provider
from neonrp.core.event_log import GameEvent, append_event
from neonrp.core.indexing import refresh_manifest_index
from neonrp.core.llm import LLMTurnResult, Message
from neonrp.core.llm import get_adapter_from_config
from neonrp.core.manifest import EntityRecord, Manifest
from neonrp.core.mcp_pool import MCPPool
from neonrp.core.paths import get_data_dir_name, get_manifest_path
# ── 结算链已抽离——门面 re-export:tests/外部仍从
# conversation 导入同名符号(seam 保留;S1.4 收面时统一转正)。
from neonrp.core.turn_settlement import (  # noqa: F401  (facade re-export)
    MISSING_BLOCK_REMINDER as _MISSING_BLOCK_REMINDER,
    _apply_player_move,
    _apply_soul_move,
    _bump_turn_count,
    _drain_location_judgments,
    _judge_world_agent_move,
    _location_judgments_path,
    _queue_location_judgment,
    _soul_current_location,
    extract_corrections as _extract_corrections,
)
from neonrp.core.prompts import build_system_prompt
from neonrp.core.runtime_contract import (
    get_router_agent_aliases,
    get_router_execution_mode,
    load_runtime_contract,
)
from neonrp.core.session import (
    append_message,
    clear_session,
    read_session_messages,
    sanitize_messages_for_resume,
    truncate_session,
)
from neonrp.core.skill_loader import SkillLoader
from neonrp.core.diffing import TurnChangeLedger
from neonrp.core.skills import SkillRegistry, get_skill_schemas
from neonrp.core.storage import atomic_write_json
from neonrp.core.todo import TodoManager
from neonrp.core.tool_router import ToolRouter

logger = logging.getLogger(__name__)

# Fallback tool-round budget when config is unreadable. Kept in sync with
# TUIConfig.max_tool_rounds (40) — 20 cut orchestrator openings off mid-turn.
MAX_CONVERSATION_TURNS = 40
API_RETRY_DELAYS_S = [2, 7, 15, 30]
ConversationMode = Literal["build", "sandbox", "play"]
# 模式收敛为二:orchestrator 与 multi-agent(产品名 MT Agent
# Team)。本地别名让分支点读起来显式,别硬编码字面量;合法值与 normalize
# (含旧 "fast"→orchestrator 迁移)统一在 runtime_contract。
ROUTER_MODE_MULTI_AGENT = "multi-agent"
ASK_USER_CANCELLED_RESPONSE = "__neonrp_ask_user_cancelled__"
REPEATED_READONLY_TOOL_STREAK_MAX = 4
REPEATED_READONLY_TOOL_BREAKER_MAX = 2
# The same tool with the same arguments, anywhere in one turn's loop (not only back to back — 09-21: the world-agent
# re-read the same set of files round after round, A B C A B C, which the streak breaker above never saw). Past
# TOOL_REPEAT_MAX identical calls the call is answered "already done" without running; after TOOL_REPEAT_TRIPS such
# answers the loop ends with what it has. NEONRP_TOOL_REPEAT_MAX overrides (0 = off).
TOOL_REPEAT_MAX = int(os.environ.get("NEONRP_TOOL_REPEAT_MAX", "3") or 3)
TOOL_REPEAT_TRIPS = 2



def _record_llm_debug(
    *,
    agent_id: str,
    provider: str,
    model: str,
    turn: int,
    duration_ms: float,
    usage: dict[str, Any] | None,
    text_preview: str,
    tool_calls: list[Any],
    error: str | None,
) -> None:
    """One-shot debug record per LLM call — feeds the F12 debug panel."""
    from neonrp.core.debug_sink import record_llm_call

    try:
        _u = usage or {}
        _in = int(_u.get("prompt_tokens") or 0)
        _out = int(_u.get("completion_tokens") or 0)
        _tps = (_out / (duration_ms / 1000.0)) if duration_ms > 0 else 0.0
        record_llm_call(
            {
                "agent_id": agent_id,
                "provider": provider,
                "model": model,
                "turn": turn,
                "duration_ms": round(duration_ms, 1),
                "tokens_per_sec": round(_tps, 1),
                "prompt_tokens": _in,
                "completion_tokens": _out,
                "cache_creation_tokens": int(_u.get("cache_creation_tokens") or 0),
                "cache_read_tokens": int(_u.get("cache_read_tokens") or 0),
                "text_preview": text_preview,
                "tool_calls": [
                    {"name": tc.name, "arguments": tc.arguments}
                    for tc in (tool_calls or [])
                ],
                "error": error or "",
            }
        )
    except Exception:  # noqa: BLE001 — debug must never break a turn
        pass
MISSING_READ_FILE_ERROR_STREAK_MAX = 3


def _is_initial_game_turn(root: Path, data_dir_name: str) -> bool:
    """Return True when the runtime is still at the pre-first-turn startup state."""
    run_state_path = root / data_dir_name / "meta" / "run_state.json"
    if not run_state_path.exists():
        return False
    try:
        payload = json.loads(run_state_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    try:
        turn_count = int(payload.get("turn_count", 0) or 0)
    except Exception:
        return False
    return turn_count <= 0
READONLY_TOOL_LOOP_GUARD = {
    "read_file",
    "read_context",
    "find",
    "list_entities",
    "glob",
    "grep",
    "resolve_action",
}
CONTEXT_PACK_MAX_ENTITIES = 6
CONTEXT_PACK_REGISTRY_MAX_ITEMS = 12
CONTEXT_PACK_ENTITY_MAX_CHARS = 900
CONTEXT_PACK_MAX_CHARS = 7000
_ENTITY_ID_TOKEN_PATTERN = re.compile(r"\b[a-z0-9][a-z0-9._-]{1,63}\b")

_TODO_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "description": "What needs to be done (e.g., 'Create hero backstory')",
        },
        "status": {
            "type": "string",
            "enum": ["pending", "in_progress", "completed"],
            "description": "Current status of this item",
        },
        "activeForm": {
            "type": "string",
            "description": "Present-participle form shown during execution (e.g., 'Creating hero backstory')",
        },
    },
    "required": ["content", "status", "activeForm"],
}

TODO_TOOL_SCHEMA = {
    "name": "TodoWrite",
    "description": (
        "Update the structured todo list for tracking your work. "
        "Pass the COMPLETE list each time (not just changes). "
        "Exactly one item should be in_progress at a time."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "The full todo list. Max 20 items.",
                "items": _TODO_ITEM_SCHEMA,
            },
        },
        "required": ["todos"],
    },
}

HANDOFF_TO_ROUTER_TOOL_SCHEMA = {
    "name": "handoff_to_router",
    "description": (
        "Signal that the current sticky specialist has completed/exited its domain and control should return "
        "to the configured narrator/router agent. Use this instead of embedding protocol markers in reply text."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Short reason for handoff (e.g., 'player left town to forest-path').",
            },
        },
        "required": [],
    },
}


def _skill_tool_schema(loader: SkillLoader) -> dict[str, Any]:
    available = loader.list_skills()
    listing = ", ".join(available) if available else "(none)"
    return {
        "name": "Skill",
        "description": (
            "Load a skill (reusable prompt snippet) by name and return its content. "
            "Skills provide domain-specific instructions or rules (e.g., combat rules, crafting recipes). "
            f"Available skills: {listing}. "
            "Call this when the user mentions a skill by name or when you need specialized guidance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "minLength": 1,
                    "description": f"Skill name to load. Must be one of: {listing}.",
                },
            },
            "required": ["skill"],
        },
    }


# Engine-injected user messages (preflight report, the old host-tool / System One notes) — not the player's words.
_ENGINE_NOTES = ("[Player Controller", "[本回合各在场角色", "[其它场景中", "[预判 · System One]", "[主持工具(M30)]")


def prompt_lang_of(root: Path) -> str:
    from neonrp.core.output_lang import prompt_lang

    return prompt_lang(root)


def v3_history_pairs(messages: list[Any], lang: str = "zh") -> list[dict[str, str]]:
    """{user, assistant} pairs for the narrator's history. Pairing each reply with the LAST user message put
    「[主持工具(M30)] get_roster…」 where the player's line belongs; engine notes are skipped, and a
    Resolve reply (no player line of its own — it carries out what was agreed) gets a plain marker."""
    out: list[dict[str, str]] = []
    pending: str | None = None
    for m in messages:
        role, content = getattr(m, "role", ""), getattr(m, "content", None)
        if role == "user" and content and not str(content).lstrip().startswith(_ENGINE_NOTES):
            pending = str(content)
        elif role == "assistant" and content:
            from neonrp import prompts as _pr

            out.append({"user": pending if pending is not None else _pr.strings("conversation", lang)["resolve_as_agreed"], "assistant": str(content)})
            pending = None
    return out


@dataclass
class ConversationTurnResult:
    """Result for a single conversation send() turn."""

    success: bool
    run_id: str
    assistant_message: str = ""
    assistant_speaker: str | None = None
    handoff_to: str | None = None
    route_decision: str | None = None
    active_agent: str | None = None
    delegated_to: str | None = None
    files_modified: list[str] = field(default_factory=list)
    tool_calls_made: list[str] = field(default_factory=list)
    turns_used: int = 0
    todo_snapshot: list[dict] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    proposal: dict[str, Any] | None = None
    error: str | None = None
    cancelled: bool = False
    # True when the turn ended by hitting the tool-round safety cap rather than
    # the agent finishing. Surfaced as a clean (partial) result, not an error;
    # callers may use this to show a subtle "took too long" hint if they wish.
    max_turns_reached: bool = False
    options: list[str] = field(default_factory=list)  # v3 ADV: what the player might say / do next (shown as choices, never in the prose)
    panels: dict[str, str] = field(default_factory=dict)  # v3: monospace cards for the screen (a layer's <formation>, the engine's [map]); never state
    # beats that ran out of time this turn (core/beat_budget: {beat, where, ms}); the turn still landed — the frontend
    # may say 「这一拍超时了」
    timeouts: list[dict[str, Any]] = field(default_factory=list)


def run_conversation_turn(
    root: Path,
    agent_id: str,
    messages: list[Message],
    mode: ConversationMode = "build",
    provider: str | None = None,
    fixture_path: str | None = None,
    max_turns: int = MAX_CONVERSATION_TURNS,
    on_chunk: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
    on_tool_use: Callable[[str, dict[str, Any]], None] | None = None,
    on_tool_result: Callable[[str, dict[str, Any], str], None] | None = None,
    on_ask_user: Callable[[str, list[str]], str | None] | None = None,
    todo_manager: TodoManager | None = None,
    skill_loader: SkillLoader | None = None,
    current_depth: int = 0,
    max_depth: int = 2,
    cancel_event: threading.Event | None = None,
    on_message_persist: Callable[[Message], None] | None = None,
    run_id: str | None = None,
    disabled_tools: set[str] | None = None,
    change_ledger: "TurnChangeLedger | None" = None,
) -> ConversationTurnResult:
    """Run one user turn with a multi-step tool-calling loop.

    ``change_ledger`` (M31 B2) is caller-owned on purpose: this function has
    a dozen exit paths, and the caller still wants to know what the turn
    wrote on every one of them.
    """
    if mode not in {"build", "sandbox", "play"}:
        return ConversationTurnResult(success=False, run_id="", error=f"Unsupported mode: {mode}")

    router_execution_mode = get_router_execution_mode(root)
    run_id = run_id or f"{agent_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    agent_dir = root / "agents" / agent_id
    agent_json_path = agent_dir / "agent.json"
    narrator_agent_id = get_narrator_agent_id(root)
    allow_router_fallback = agent_id == narrator_agent_id and router_execution_mode == "orchestrator"
    # A soul agent_id (soul:<sid>:<iid>) has no agents/<id>/ dir on disk —
    # it is synthesised in-memory by _load_agent_data_for_mode. Skip the
    # missing-dir rejection so resolution can run.
    from neonrp.core.soul_agent import parse_soul_agent_id as _parse_soul_id

    _is_soul_agent = _parse_soul_id(agent_id) is not None
    if not _is_soul_agent and not agent_dir.exists() and not (mode == "build" and agent_id == narrator_agent_id) and not allow_router_fallback:
        return ConversationTurnResult(success=False, run_id=run_id, error=f"Agent '{agent_id}' not found")
    if agent_dir.exists() and not agent_json_path.exists():
        return ConversationTurnResult(success=False, run_id=run_id, error=f"Cannot read agent.json for '{agent_id}'")
    if agent_json_path.exists():
        try:
            json.loads(agent_json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return ConversationTurnResult(success=False, run_id=run_id, error=f"Cannot read agent.json: {exc}")
    agent_data = _load_agent_data_for_mode(root, agent_id, mode)
    if agent_data is None:
        return ConversationTurnResult(success=False, run_id=run_id, error=f"Agent '{agent_id}' not found")

    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        return ConversationTurnResult(success=False, run_id=run_id, error="NeonRP project not initialized")

    try:
        manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
    except Exception as exc:
        return ConversationTurnResult(success=False, run_id=run_id, error=f"Failed to load manifest: {exc}")

    branch = manifest.current_branch
    if branch not in manifest.branches:
        return ConversationTurnResult(success=False, run_id=run_id, error=f"Branch '{branch}' not found in manifest")
    base_head_event = manifest.branches[branch].head_event

    config = load_config(root)
    if router_execution_mode == "orchestrator" and max_depth < 3:
        max_depth = 3
    runtime_contract = load_runtime_contract(root)
    agent_llm_config = agent_data.get("llm")
    provider_config = resolve_provider(config, agent_llm_config, provider)

    todo_manager = todo_manager or TodoManager()
    skill_loader = skill_loader or SkillLoader(root)

    try:
        adapter_kwargs: dict[str, Any] = {}
        if provider_config.provider == "stub" and fixture_path:
            adapter_kwargs["fixture_path"] = fixture_path
        adapter = get_adapter_from_config(provider_config, **adapter_kwargs)
        if provider_config.disable_streaming:
            logger.info("Streaming disabled for this provider (disable_streaming=true in model config)")
    except Exception as exc:
        return ConversationTurnResult(success=False, run_id=run_id, error=f"Failed to initialize LLM adapter: {exc}")

    # Always keep system prompt at index 0 and refresh on each call.
    agent_name = str(agent_data.get("name") or agent_id)
    # 语言隔离:本局输出语注入 world/keeper 系统提示词,让面向
    # 玩家的叙事/对话用 output_lang,压过 authored 中文世界文件。
    from neonrp.core.output_lang import resolve_output_lang

    base_system_prompt = build_system_prompt(
        agent_name=agent_name,
        project_name=root.name,
        branch=branch,
        mode=mode,
        skill_descriptions=skill_loader.get_descriptions(),
        project_root=str(root.resolve()),
        include_resolve_action=config.rules.enable_resolve_action,
        is_sub_agent=current_depth > 0,
        data_dir_name=runtime_contract.data_dir,
        routing_state_path=runtime_contract.active_agent_relpath,
        startup_path=runtime_contract.startup_relpath,
        location_source_entity_id=runtime_contract.routing.location_source.entity_id,
        location_source_field=runtime_contract.routing.location_source.field,
        output_lang=resolve_output_lang(root),
    )
    agent_policy = _load_agent_system_prompt_text(root, agent_id, agent_data)
    if agent_policy:
        system_prompt = (
            f"{base_system_prompt}\n\n"
            "## Agent-Specific Instructions\n"
            f"{agent_policy.strip()}\n"
        )
    else:
        system_prompt = base_system_prompt
    # Secrets P2 §d — GM agents get the standing "know but don't narrate"
    # contract for unrevealed secrets, plus any queued guardrail corrections
    # (orch delivery; in multi-agent the send()-level preflight drains the
    # same deliver-once queue first, so no double feedback). Non-GM agents
    # can't even read game/secrets/**, so nothing is injected for them.
    # Empty string / empty queue → zero prompt cost; secrets-free worlds
    # never reach past the has_secrets early-returns.
    try:
        from neonrp.core.secrets import (
            drain_guardrail_notices as _sec_drain_guardrail,
            is_gm_agent as _sec_is_gm,
            standing_gm_block as _sec_standing_block,
        )

        _router_id = str(getattr(config.tui, "narrator_agent_id", "") or "").strip() or None
        if _sec_is_gm(agent_id, router_agent_id=_router_id):
            _sec_extra = ""
            _sblock = _sec_standing_block(root)
            if _sblock:
                _sec_extra += f"\n\n{_sblock}"
            _glines = _sec_drain_guardrail(root)
            if _glines:
                _sec_extra += (
                    "\n\n【秘密裁定(上回合护栏;已出口的不再收回,本回合起回避"
                    "展开或引导玩家以行动解锁,勿向玩家复述本条)】\n" + "\n".join(_glines)
                )
            if _sec_extra:
                system_prompt = system_prompt + _sec_extra
    except Exception:
        pass
    if not messages or messages[0].role != "system":
        messages.insert(0, Message(role="system", content=system_prompt))
    else:
        messages[0] = Message(role="system", content=system_prompt)

    permissions = agent_data.get("permissions", {})
    data_dir_name = runtime_contract.data_dir
    if mode == "build":
        # Build mode can write anywhere, including agents/ and .neonrp/.
        read_globs = ["**"]
        deny_globs: list[str] = []
        direct_write_globs = ["**"]
        allow_protected_paths = True
    else:
        read_globs = permissions.get("read_globs", ["**"])
        deny_globs = permissions.get("deny_globs", [])
        if mode == "play":
            # Play mode direct writes are controlled by agent permissions.
            # Prefer explicit direct_write_globs; fall back to write_globs for
            # backward compatibility with existing agent templates.
            configured_direct = permissions.get("direct_write_globs")
            configured_write = permissions.get("write_globs", [])
            if isinstance(configured_direct, list) and any(isinstance(p, str) and p.strip() for p in configured_direct):
                direct_write_globs = [p for p in configured_direct if isinstance(p, str) and p.strip()]
            elif isinstance(configured_write, list):
                direct_write_globs = [p for p in configured_write if isinstance(p, str) and p.strip()]
            else:
                direct_write_globs = []
        else:
            direct_write_globs = []
        allow_protected_paths = False

    # Routing-state ownership policy:
    # - Router agent can manage active-agent state.
    # - Specialists are denied by default unless explicitly opted in.
    routing_state_path = runtime_contract.active_agent_relpath
    allow_routing_state_write = bool(permissions.get("allow_routing_state_write", False))
    if agent_id != narrator_agent_id and not allow_routing_state_write:
        if routing_state_path not in deny_globs:
            deny_globs = [*deny_globs, routing_state_path]

    # Secrets partition (docs/SECRETS-DESIGN.md §b): non-GM agents are denied
    # every game/secrets/ file whose audience does not include them. Per-FILE
    # denies because the permission check is deny-first — a blanket deny could
    # never be re-opened for an audience member. GM agents (world-agent /
    # game-master / the router) keep full sight; build mode is the authoring
    # side and writes these files, so it stays exempt. Worlds without a
    # secrets/ dir get an empty list — zero behavior change.
    if mode != "build":
        from neonrp.core.secrets import secrets_deny_paths

        secret_denies = secrets_deny_paths(
            root, agent_id, router_agent_id=narrator_agent_id
        )
        if secret_denies:
            deny_globs = [*deny_globs, *(p for p in secret_denies if p not in deny_globs)]

    skill_registry = SkillRegistry(
        root,
        run_id,
        agent_id,
        read_globs,
        deny_globs,
        direct_write_globs,
        allow_protected_paths=allow_protected_paths,
        enable_resolve_action=config.rules.enable_resolve_action,
        change_ledger=change_ledger,
    )
    tool_schemas = _get_tool_schemas(
        mode,
        skill_loader,
        root,
        include_resolve_action=config.rules.enable_resolve_action,
    )
    # Prevent infinite sub-agent nesting: strip task tool at depth limit
    if current_depth >= max_depth - 1:
        tool_schemas = [s for s in tool_schemas if s.get("name") != "task"]
    if disabled_tools:
        blocked = {str(name).strip() for name in disabled_tools if isinstance(name, str) and str(name).strip()}
        if blocked:
            tool_schemas = [s for s in tool_schemas if str(s.get("name", "")) not in blocked]

    # MCP integration (M11-T4): create pool + router if MCP servers configured
    mcp_pool: MCPPool | None = None
    tool_router: ToolRouter | None = None
    if config.mcp_servers:
        enabled = {n: c for n, c in config.mcp_servers.items() if c.enabled}
        if enabled:
            mcp_pool = MCPPool(enabled)
            startup_errors = mcp_pool.ensure_started()
            # Surface startup failures (should-fix #3)
            for srv_name, srv_err in startup_errors.items():
                if srv_err:
                    logger.warning("MCP server '%s' failed to start: %s", srv_name, srv_err)
            audit_path = root / ".neonrp" / "logs" / "mcp"
            tool_router = ToolRouter(
                mcp_pool, configs=enabled, audit_path=audit_path, run_id=run_id,
            )
            tool_schemas = tool_router.get_merged_schemas(tool_schemas)

    tool_schemas = _filter_tool_schemas_by_agent_config(tool_schemas, agent_data, mode=mode)
    allowed_tool_names = {schema.get("name", "") for schema in tool_schemas if schema.get("name")}
    active_agent_id = narrator_agent_id  # fast 退役:路由主体恒为 router 本体
    # fast 退役:「narrator 只许经 task() 改实体」守门是 fast
    # 人设遗产;orchestrator/multi-agent 的 router 本体即 world-agent,
    # 自有世界写权,守门恒关。
    enforce_narrator_guardrail = False

    try:  # guarantee MCP pool cleanup (must-fix #1)
        files_modified: list[str] = []
        tool_calls_made: list[str] = []
        assistant_chunks: list[str] = []
        usage: dict[str, Any] = {}
        proposal_data: dict[str, Any] | None = None
        _empty_args_streak = 0  # circuit breaker for empty-argument tool calls
        _EMPTY_ARGS_MAX = 3  # stop after this many consecutive empty-argument failures
        _last_readonly_tool_sig: str | None = None
        _readonly_tool_streak = 0
        _readonly_breaker_trips = 0
        _sig_counts: dict[str, int] = {}  # identical calls anywhere in this loop (TOOL_REPEAT_MAX)
        _repeat_trips = 0
        _missing_read_file_error_streak = 0
        requested_handoff_to: str | None = None
        requested_route_decision: str | None = None
        requested_active_agent: str | None = None
        requested_delegated_to: str | None = None
        checkpoint_created = False

        turn = 0
        api_retries = 0
        while turn < max_turns:
            # --- ESC / cancel check ---
            if cancel_event is not None and cancel_event.is_set():
                return ConversationTurnResult(
                    success=True,
                    run_id=run_id,
                    assistant_message="\n".join(assistant_chunks),
                    files_modified=files_modified,
                    tool_calls_made=tool_calls_made,
                    turns_used=turn,
                    todo_snapshot=todo_manager.snapshot(),
                    usage=usage,
                    cancelled=True,
                )

            # the beat's time is over (core/beat_budget, 10-14: one beat ≤ 20 s), or the model keeps calling the same
            # tools: stop calling it and end with what was written — the same clean partial ending as the round cap
            from neonrp.core import beat_budget as _bb

            if _bb.expired() or (TOOL_REPEAT_MAX > 0 and _repeat_trips >= TOOL_REPEAT_TRIPS):
                if _bb.expired():
                    _bb.note("agent_loop", agent=agent_id, rounds=turn)
                logger.info("agent loop stopped early (beat over or repeated tools): agent=%s rounds=%d", agent_id, turn)
                break
            turn += 1
            short_circuit_turn = False
            _truncate_messages_for_budget(messages, config.llm.max_context_chars)
            # Budget truncation pops messages[1] blindly until under budget,
            # which can split an assistant(tool_calls) + tool-tail block —
            # leaving the LLM call with a dangling assistant or an orphan
            # tool, both of which strict providers (DeepSeek) 400 on. Sanitize
            # is idempotent and O(n); run it unconditionally right before
            # dispatch (the in-place assignment matters even when the count
            # is unchanged — sanitize may strip an assistant's tool_calls
            # field without dropping the message).
            messages[:] = sanitize_messages_for_resume(messages)

            use_streaming = (
                (on_chunk or on_thinking)
                and not provider_config.disable_streaming
                # chat()-only adapters (stubs/tests) stay on the non-streaming
                # path even now that the M18 Phase 1 wrappers make callbacks
                # always present.
                and hasattr(adapter, "chat_stream")
            )
            _llm_start = time.time()
            if use_streaming:
                turn_result = _chat_stream(adapter, messages, tool_schemas, on_chunk, on_thinking, cancel_event)
            else:
                turn_result = adapter.chat(messages, tools=tool_schemas)
                # When streaming is disabled but callbacks exist, deliver the
                # complete response in one shot so the TUI still displays it.
                if turn_result.message and turn_result.message.content and on_chunk:
                    on_chunk(turn_result.message.content)
            _llm_dur_ms = round((time.time() - _llm_start) * 1000, 1)

            _merge_usage(usage, turn_result.usage)

            # --- record every LLM call for the debug panel (F12) ---
            _record_llm_debug(
                agent_id=agent_id,
                provider=provider_config.provider,
                model=provider_config.model,
                turn=turn,
                duration_ms=_llm_dur_ms,
                usage=turn_result.usage,
                text_preview=(turn_result.message.content or "")[:200] if turn_result.message else "",
                tool_calls=getattr(turn_result, "tool_calls", None) or [],
                error=turn_result.error,
            )

            # --- ESC / cancel check right after LLM call returns ---
            if cancel_event is not None and cancel_event.is_set():
                # Preserve any partial content already streamed
                if turn_result.message and turn_result.message.content:
                    assistant_chunks.append(turn_result.message.content)
                return ConversationTurnResult(
                    success=True,
                    run_id=run_id,
                    assistant_message="\n".join(assistant_chunks),
                    files_modified=files_modified,
                    tool_calls_made=tool_calls_made,
                    turns_used=turn,
                    todo_snapshot=todo_manager.snapshot(),
                    usage=usage,
                    cancelled=True,
                )
            if not turn_result.success:
                should_retry = turn_result.retryable or _looks_retryable_error_text(turn_result.error)
                if should_retry and api_retries < len(API_RETRY_DELAYS_S):
                    delay_s = API_RETRY_DELAYS_S[api_retries]
                    api_retries += 1
                    logger.warning(
                        "Retryable API error on turn %d (attempt %d/%d), retrying in %ds: %s",
                        turn, api_retries, len(API_RETRY_DELAYS_S), delay_s, turn_result.error,
                    )
                    time.sleep(delay_s)
                    # Trim the last assistant+tool exchange that may have caused
                    # a 400 Bad Request (e.g. malformed tool_use/tool_result pair).
                    _trim_broken_tail(messages)
                    turn -= 1  # don't count failed attempt
                    continue
                return ConversationTurnResult(
                    success=False,
                    run_id=run_id,
                    files_modified=files_modified,
                    tool_calls_made=tool_calls_made,
                    turns_used=turn,
                    todo_snapshot=todo_manager.snapshot(),
                    usage=usage,
                    error=f"LLM call failed on turn {turn}: {turn_result.error}",
                )
            api_retries = 0  # reset on success

            if turn_result.message:
                messages.append(turn_result.message)
                if on_message_persist:
                    on_message_persist(turn_result.message)
                if turn_result.message.content:
                    assistant_chunks.append(turn_result.message.content)

            if not turn_result.tool_calls:
                if mode == "sandbox":
                    break
                return _finalize_turn(
                    root=root,
                    run_id=run_id,
                    branch=branch,
                    base_head_event=base_head_event,
                    mode=mode,
                    agent_id=agent_id,
                    assistant_chunks=assistant_chunks,
                    files_modified=files_modified,
                    tool_calls_made=tool_calls_made,
                    turns_used=turn,
                    todo_manager=todo_manager,
                    usage=usage,
                    proposal=proposal_data,
                    handoff_to=requested_handoff_to,
                    route_decision=requested_route_decision or "self",
                    active_agent=requested_active_agent or agent_id,
                    delegated_to=requested_delegated_to,
                )

            for tool_call in turn_result.tool_calls:
                # --- ESC / cancel check before each tool ---
                if cancel_event is not None and cancel_event.is_set():
                    return ConversationTurnResult(
                        success=True,
                        run_id=run_id,
                        assistant_message="\n".join(assistant_chunks),
                        route_decision=requested_route_decision,
                        active_agent=requested_active_agent or agent_id,
                        delegated_to=requested_delegated_to,
                        files_modified=files_modified,
                        tool_calls_made=tool_calls_made,
                        turns_used=turn,
                        todo_snapshot=todo_manager.snapshot(),
                        usage=usage,
                        cancelled=True,
                    )

                # Normalize malformed tool names like glob("**/*.json") → name="glob", args merged
                _normalize_tool_call(tool_call, tool_schemas)

                logger.debug(
                    "tool_call start: run=%s turn=%d agent=%s id=%s name=%s args=%s",
                    run_id,
                    turn,
                    agent_id,
                    tool_call.id,
                    tool_call.name,
                    _preview_for_log(tool_call.arguments),
                )
                tool_calls_made.append(tool_call.name)
                if on_tool_use:
                    on_tool_use(tool_call.name, tool_call.arguments)
                tool_cancelled = False

                if tool_call.name not in allowed_tool_names:
                    logger.debug(
                        "tool_call blocked_by_allowlist: run=%s agent=%s id=%s name=%s allowed=%s",
                        run_id,
                        agent_id,
                        tool_call.id,
                        tool_call.name,
                        sorted(allowed_tool_names),
                    )
                    tool_result = _json_dumps(
                        {
                            "status": "error",
                            "error": (
                                f"Tool '{tool_call.name}' is not enabled for agent '{agent_id}'. "
                                "Use one of the configured tools in agent.json."
                            ),
                            "data": {"allowed_tools": sorted(allowed_tool_names)},
                        }
                    )
                    if on_tool_result:
                        on_tool_result(tool_call.name, tool_call.arguments, tool_result)
                    tool_msg = Message(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                    messages.append(tool_msg)
                    if on_message_persist:
                        on_message_persist(tool_msg)
                    continue

                if _should_block_narrator_tool_call(
                    agent_id=agent_id,
                    tool_name=tool_call.name,
                    tool_args=tool_call.arguments,
                    data_dir_name=data_dir_name,
                    enforce_guardrail=enforce_narrator_guardrail,
                    narrator_agent_id=narrator_agent_id,
                ):
                    logger.debug(
                        "tool_call blocked_by_narrator_guardrail: run=%s id=%s name=%s args=%s active_agent=%s",
                        run_id,
                        tool_call.id,
                        tool_call.name,
                        _preview_for_log(tool_call.arguments),
                        active_agent_id,
                    )
                    delegate_hint = (
                        active_agent_id
                        if active_agent_id != narrator_agent_id
                        else "the appropriate specialist agent"
                    )
                    tool_result = _json_dumps(
                        {
                            "status": "error",
                            "error": (
                                "Narrator guardrail: direct game-entity operations are not allowed. "
                                f"Delegate via task() to {delegate_hint}."
                            ),
                            "data": {"active_agent": active_agent_id},
                        }
                    )
                    if on_tool_result:
                        on_tool_result(tool_call.name, tool_call.arguments, tool_result)
                    tool_msg = Message(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                    messages.append(tool_msg)
                    if on_message_persist:
                        on_message_persist(tool_msg)
                    continue

                if (
                    mode in {"build", "play"}
                    and tool_call.name in {"write_file", "edit_file", "delete_file", "ensure_playable_scaffold"}
                    and not checkpoint_created
                ):
                    create_checkpoint(root, branch, base_head_event)
                    checkpoint_created = True

                _any_sig = _tool_call_signature(tool_call.name, tool_call.arguments)
                _sig_counts[_any_sig] = _sig_counts.get(_any_sig, 0) + 1
                if (TOOL_REPEAT_MAX > 0 and _sig_counts[_any_sig] > TOOL_REPEAT_MAX
                        # back-to-back identical read-only calls are the streak breaker's below (its own wording + abort)
                        and not (_is_loop_guard_readonly_tool(tool_call.name) and _any_sig == _last_readonly_tool_sig)):
                    _repeat_trips += 1
                    logger.warning("repeated tool call (%d× this turn), not run: %s args=%s", _sig_counts[_any_sig],
                                   tool_call.name, _preview_for_log(tool_call.arguments, 220))
                    tool_result = _json_dumps(
                        {
                            "status": "error",
                            "error": (
                                "You already made this exact call this turn; its result has not changed. "
                                "Do not call it again — answer from what you already have."
                            ),
                            "data": {"tool": tool_call.name, "repeat_count": _sig_counts[_any_sig], "guard": "repeated_tool_call"},
                        }
                    )
                    if on_tool_result:
                        on_tool_result(tool_call.name, tool_call.arguments, tool_result)
                    tool_msg = Message(role="tool", content=tool_result, tool_call_id=tool_call.id, name=tool_call.name)
                    messages.append(tool_msg)
                    if on_message_persist:
                        on_message_persist(tool_msg)
                    continue

                if _is_loop_guard_readonly_tool(tool_call.name):
                    current_sig = _tool_call_signature(tool_call.name, tool_call.arguments)
                    if current_sig == _last_readonly_tool_sig:
                        _readonly_tool_streak += 1
                    else:
                        _last_readonly_tool_sig = current_sig
                        _readonly_tool_streak = 1
                    if _readonly_tool_streak >= REPEATED_READONLY_TOOL_STREAK_MAX:
                        _readonly_breaker_trips += 1
                        logger.warning(
                            "Circuit breaker: repeated identical read-only tool call (%d): %s args=%s",
                            _readonly_tool_streak,
                            tool_call.name,
                            _preview_for_log(tool_call.arguments, 220),
                        )
                        tool_result = _json_dumps(
                            {
                                "status": "error",
                                "error": (
                                    "Detected repeated identical read-only tool call without progress. "
                                    "Stop repeating this call and either delegate, ask_user, or respond based on known state."
                                ),
                                "data": {
                                    "tool": tool_call.name,
                                    "repeat_count": _readonly_tool_streak,
                                    "guard": "repeated_readonly_tool_loop",
                                },
                            }
                        )
                        if on_tool_result:
                            on_tool_result(tool_call.name, tool_call.arguments, tool_result)
                        tool_msg = Message(
                            role="tool",
                            content=tool_result,
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                        )
                        messages.append(tool_msg)
                        if on_message_persist:
                            on_message_persist(tool_msg)
                        messages.append(
                            Message(
                                role="user",
                                content=(
                                    "[System: You are repeating the same read-only tool call with identical arguments. "
                                    "Do not call it again now. Continue with task(), ask_user(), or a normal reply.]"
                                ),
                            )
                        )
                        _readonly_tool_streak = 0
                        short_circuit_turn = True
                        if _readonly_breaker_trips >= REPEATED_READONLY_TOOL_BREAKER_MAX:
                            return ConversationTurnResult(
                                success=False,
                                run_id=run_id,
                                files_modified=files_modified,
                                tool_calls_made=tool_calls_made,
                                turns_used=turn,
                                todo_snapshot=todo_manager.snapshot(),
                                usage=usage,
                                error=(
                                    "Conversation aborted: repeated identical read-only tool calls "
                                    "indicate an LLM loop."
                                ),
                            )
                        break
                else:
                    _last_readonly_tool_sig = None
                    _readonly_tool_streak = 0

                if tool_call.name == "TodoWrite":
                    tool_result = _handle_todo_tool(todo_manager, tool_call.arguments)
                elif tool_call.name == "Skill":
                    tool_result = _handle_skill_tool(skill_loader, tool_call.arguments)
                elif tool_call.name == "handoff_to_router":
                    if agent_id == narrator_agent_id:
                        tool_result = _json_dumps(
                            {
                                "status": "error",
                                "error": "Narrator/router is already active; handoff_to_router is for specialist agents.",
                            }
                        )
                    else:
                        handoff_reason = str(tool_call.arguments.get("reason", "") or "").strip()
                        requested_handoff_to = narrator_agent_id
                        tool_result = _json_dumps(
                            {
                                "status": "success",
                                "data": {
                                    "handoff_to": narrator_agent_id,
                                    "reason": handoff_reason,
                                    "by": agent_id,
                                },
                            }
                        )
                elif tool_call.name == "task":
                    logger.debug(
                        "tool_call dispatch_sub_agent: run=%s caller=%s id=%s task=%s",
                        run_id,
                        agent_id,
                        tool_call.id,
                        _preview_for_log(tool_call.arguments),
                    )
                    tool_result = _dispatch_sub_agent(
                        task_data=tool_call.arguments,
                        root=root,
                        mode=mode,
                        # Give sub-agents their own turn budget instead of inheriting the
                        # parent's remaining turns (which caused confusing limits like 15).
                        max_turns=max_turns,
                        caller_agent_id=agent_id,
                        on_chunk=on_chunk,
                        on_thinking=on_thinking,
                        on_tool_use=on_tool_use,
                        on_tool_result=on_tool_result,
                        on_ask_user=on_ask_user,
                        current_depth=current_depth,
                        max_depth=max_depth,
                        cancel_event=cancel_event,
                        on_message_persist=on_message_persist,
                        parent_messages=messages,
                    )
                    parsed_task = _parse_task_tool_result(tool_result)
                    if parsed_task is not None:
                        requested_route_decision = str(parsed_task.get("route_decision") or requested_route_decision or "").strip() or requested_route_decision
                        requested_active_agent = str(parsed_task.get("active_agent") or requested_active_agent or "").strip() or requested_active_agent
                        requested_delegated_to = (
                            str(parsed_task.get("delegated_to") or tool_call.arguments.get("agent_id") or requested_delegated_to or "").strip()
                            or requested_delegated_to
                        )
                    # If the nested run was canceled (e.g. sub-agent ask_user Esc),
                    # stop this parent turn as well instead of continuing generation.
                    tool_cancelled = _is_cancelled_tool_result(tool_result)
                else:
                    # Try MCP router first (M11-T4)
                    mcp_handled = False
                    ask_user_data = None
                    if tool_router:
                        router_result = tool_router.dispatch(
                            tool_call.name,
                            tool_call.arguments,
                            run_id=run_id,
                            agent_id=agent_id,
                        )
                        if router_result.handled:
                            # should-fix #1: handle confirm permission flow
                            if router_result.needs_confirm and on_ask_user:
                                confirm_info = json.loads(router_result.result_json)
                                answer = on_ask_user(
                                    f"MCP tool '{confirm_info.get('tool', '')}' on server "
                                    f"'{confirm_info.get('server', '')}' requires confirmation. Allow?",
                                    ["yes", "no"],
                                )
                                if isinstance(answer, tuple):
                                    answer = answer[0]
                                if str(answer).lower() in ("yes", "y", "1"):
                                    router_result = tool_router.dispatch(
                                        tool_call.name,
                                        tool_call.arguments,
                                        run_id=run_id,
                                        agent_id=agent_id,
                                        confirmed=True,
                                    )
                                    tool_result = router_result.result_json
                                else:
                                    tool_result = _json_dumps({
                                        "status": "error",
                                        "error": "MCP tool call rejected by user",
                                    })
                            else:
                                tool_result = router_result.result_json
                            mcp_handled = True

                    if not mcp_handled:
                        run_context = {
                            "run_id": run_id,
                            "agent_id": agent_id,
                            "branch": branch,
                            "base_head_event": base_head_event,
                        }
                        tool_result, submitted_proposal, ask_user_data, _ = _execute_tool(
                            skill_registry,
                            tool_call,
                            run_context,
                            include_resolve_action=config.rules.enable_resolve_action,
                            allowed_tool_names=allowed_tool_names,
                        )
                        if submitted_proposal:
                            proposal_data = submitted_proposal

                        # --- Circuit breaker for empty-argument tool calls ---
                        # Some providers (Ollama) intermittently drop tool call
                        # arguments.  After N consecutive failures, stop retrying
                        # and ask the model to respond with plain text instead.
                        if not tool_call.arguments:
                            _empty_args_streak += 1
                            if _empty_args_streak >= _EMPTY_ARGS_MAX:
                                logger.warning(
                                    "Circuit breaker: %d consecutive empty-argument "
                                    "tool calls for '%s'. Forcing text-only reply.",
                                    _empty_args_streak,
                                    tool_call.name,
                                )
                                # Append the error result so the model sees it
                                messages.append(Message(
                                    role="tool",
                                    content=tool_result,
                                    tool_call_id=tool_call.id,
                                    name=tool_call.name,
                                ))
                                # Inject a user-role hint to break the loop
                                messages.append(Message(
                                    role="user",
                                    content=(
                                        "[System: Tool call arguments are being lost by the API. "
                                        "Stop calling tools. Instead, write your question or "
                                        "choices as plain text in your reply.]"
                                    ),
                                ))
                                _empty_args_streak = 0
                                break  # exit tool-call for-loop → triggers new LLM turn
                        else:
                            _empty_args_streak = 0

                    if ask_user_data:
                        questions_list = ask_user_data.get("questions", [])
                        logger.debug(
                            "tool_call ask_user_prompt: run=%s id=%s questions=%s",
                            run_id,
                            tool_call.id,
                            _preview_for_log(questions_list),
                        )
                        if on_ask_user:
                            answers: dict[str, str] = {}
                            cancelled = False
                            for idx, q_item in enumerate(questions_list):
                                q_text = str(q_item.get("question", ""))
                                labels = [
                                    str(o.get("label", "")) for o in q_item.get("options", [])
                                    if isinstance(o, dict)
                                ]
                                response_raw = on_ask_user(q_text, labels)
                                if isinstance(response_raw, tuple):
                                    response_raw = response_raw[0] if response_raw else ""
                                if response_raw is None or str(response_raw) == ASK_USER_CANCELLED_RESPONSE:
                                    cancelled = True
                                    logger.debug(
                                        "tool_call ask_user_cancelled: run=%s id=%s q_idx=%d",
                                        run_id, tool_call.id, idx,
                                    )
                                    break
                                answers[str(idx)] = str(response_raw or "")
                            if cancelled:
                                tool_cancelled = True
                                tool_result = _json_dumps({"status": "cancelled"})
                            else:
                                logger.debug(
                                    "tool_call ask_user_answers: run=%s id=%s answers=%s",
                                    run_id, tool_call.id, _preview_for_log(answers, 200),
                                )
                                tool_result = _json_dumps({"answers": answers})
                        else:
                            tool_result = _json_dumps(
                                {"status": "error", "error": "ask_user not available (no callback provided)"}
                            )

                logger.debug(
                    "tool_call result: run=%s turn=%d agent=%s id=%s name=%s %s",
                    run_id,
                    turn,
                    agent_id,
                    tool_call.id,
                    tool_call.name,
                    _summarize_tool_result_for_log(tool_result),
                )
                if on_tool_result:
                    on_tool_result(tool_call.name, tool_call.arguments, tool_result)

                _track_modified_files(tool_call.name, tool_result, files_modified)

                if _is_missing_read_file_error(tool_call.name, tool_result):
                    _missing_read_file_error_streak += 1
                elif tool_call.name == "read_file":
                    _missing_read_file_error_streak = 0

                tool_msg = Message(
                    role="tool",
                    content=tool_result,
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                )
                messages.append(tool_msg)
                if on_message_persist:
                    on_message_persist(tool_msg)
                # The sticky short-circuit lets a delegated sub-agent's raw
                # text become the player message verbatim. In multi-agent
                # mode that is exactly the leak we forbid: the world-agent
                # alone speaks to the player; any task-delegated sub-agent
                # output must stay as *context* only (it is already appended
                # as the tool result above) so the world-agent's own loop
                # synthesises the final narration. So: never short-circuit
                # in multi-agent — fall through and keep looping.
                if (
                    agent_id == narrator_agent_id
                    and current_depth == 0
                    and tool_call.name == "task"
                    and _is_sticky_task_success(tool_result)
                    and router_execution_mode != ROUTER_MODE_MULTI_AGENT
                ):
                    payload = _parse_task_tool_result(tool_result) or {}
                    data = payload.get("data")
                    if not isinstance(data, dict):
                        data = {}
                    sub_agent_id = str(data.get("agent_id") or "").strip()
                    sub_assistant_speaker = sub_agent_id or None
                    sub_assistant_text = str(data.get("assistant_text") or "")
                    handoff_target = str(data.get("handoff_to") or "").strip().lower()
                    if sub_assistant_text:
                        assistant_chunks.append(sub_assistant_text)
                        assistant_msg = Message(
                            role="assistant",
                            content=sub_assistant_text,
                            name=sub_assistant_speaker,
                        )
                        messages.append(assistant_msg)
                        if on_message_persist:
                            on_message_persist(assistant_msg)
                    nested_files = [p for p in data.get("files_modified", []) if isinstance(p, str)]
                    for path in nested_files:
                        if path not in files_modified:
                            files_modified.append(path)
                    nested_usage = data.get("usage")
                    if isinstance(nested_usage, dict):
                        _merge_usage(usage, nested_usage)
                    if handoff_target:
                        requested_handoff_to = handoff_target
                    logger.debug(
                        "narrator sticky short-circuit: run=%s turn=%d task=%s assistant_len=%d files=%d",
                        run_id,
                        turn,
                        tool_call.id,
                        len(sub_assistant_text),
                        len(nested_files),
                    )
                    return ConversationTurnResult(
                        success=True,
                        run_id=run_id,
                        assistant_message="\n".join(assistant_chunks),
                        files_modified=files_modified,
                        tool_calls_made=tool_calls_made,
                        turns_used=turn,
                        todo_snapshot=todo_manager.snapshot(),
                        usage=usage,
                        assistant_speaker=sub_assistant_speaker or agent_id,
                        handoff_to=requested_handoff_to,
                    )
                if _missing_read_file_error_streak >= MISSING_READ_FILE_ERROR_STREAK_MAX:
                    logger.warning(
                        "Circuit breaker: %d consecutive read_file not-found errors (run=%s agent=%s).",
                        _missing_read_file_error_streak,
                        run_id,
                        agent_id,
                    )
                    messages.append(
                        Message(
                            role="user",
                            content=(
                                "[System: Multiple read_file attempts failed with File not found. "
                                "Stop guessing file paths. Use find/list_entities/glob to confirm paths first, "
                                "or continue with the context already available.]"
                            ),
                        )
                    )
                    _missing_read_file_error_streak = 0
                    short_circuit_turn = True
                    break
                if tool_cancelled:
                    return ConversationTurnResult(
                        success=True,
                        run_id=run_id,
                        assistant_message="\n".join(assistant_chunks),
                        files_modified=files_modified,
                        tool_calls_made=tool_calls_made,
                        turns_used=turn,
                        todo_snapshot=todo_manager.snapshot(),
                        usage=usage,
                        cancelled=True,
                        handoff_to=requested_handoff_to,
                    )
            if short_circuit_turn:
                continue

            if mode == "sandbox" and proposal_data:
                return _finalize_turn(
                    root=root,
                    run_id=run_id,
                    branch=branch,
                    base_head_event=base_head_event,
                    mode=mode,
                    agent_id=agent_id,
                    assistant_chunks=assistant_chunks,
                    files_modified=files_modified,
                    tool_calls_made=tool_calls_made,
                    turns_used=turn,
                    todo_manager=todo_manager,
                    usage=usage,
                    proposal=proposal_data,
                    route_decision=requested_route_decision or "self",
                    active_agent=requested_active_agent or agent_id,
                    delegated_to=requested_delegated_to,
                )

        if mode == "sandbox" and not proposal_data:
            return ConversationTurnResult(
                success=False,
                run_id=run_id,
                files_modified=files_modified,
                tool_calls_made=tool_calls_made,
                turns_used=turn,
                todo_snapshot=todo_manager.snapshot(),
                usage=usage,
                error="Sandbox mode requires submit_proposal before ending a turn",
            )

        # Hitting the tool-round cap is a SAFETY stop, not a user-facing
        # failure: surface whatever the agent already narrated and end the turn
        # cleanly instead of throwing "exceeded max turns" at the player. Still
        # log it — an empty result here usually means the agent was stuck (e.g.
        # a blocked delegation loop), which is worth investigating.
        partial = "\n".join(c for c in assistant_chunks if c)
        if partial:
            logger.info("Turn hit max_turns=%s; returning partial narration", max_turns)
        else:
            logger.warning(
                "Turn hit max_turns=%s with no narration (agent likely stuck)", max_turns
            )
        return ConversationTurnResult(
            success=True,
            run_id=run_id,
            route_decision=requested_route_decision or "self",
            active_agent=requested_active_agent or agent_id,
            delegated_to=requested_delegated_to,
            assistant_message=partial,
            files_modified=files_modified,
            tool_calls_made=tool_calls_made,
            turns_used=turn,
            todo_snapshot=todo_manager.snapshot(),
            usage=usage,
            max_turns_reached=True,
            handoff_to=requested_handoff_to,
        )

    finally:  # must-fix #1: always stop MCP pool
        if mcp_pool is not None:
            try:
                mcp_pool.stop_all()
            except Exception as exc:
                logger.warning("Error stopping MCP pool: %s", exc)


class ConversationSession:
    """Persistent conversation state for interactive UIs."""

    def __init__(
        self,
        root: Path,
        agent_id: str,
        mode: ConversationMode = "build",
        provider: str | None = None,
        max_turns: int | None = None,
        todo_manager: TodoManager | None = None,
        skill_loader: SkillLoader | None = None,
    ):
        self.root = root
        self.agent_id = agent_id
        self.mode = mode
        self.provider = provider
        # Stage 2: per-soul STICKY conversation history (instance_id →
        # condensed [perception, reaction] exchanges), persisted across
        # turns so a soul-agent is a continuous team member, not a
        # cold-spawned one. Bounded per soul. Retained even when a soul
        # is off-stage (idle/sticky); the team-leader keeps it alive.
        self._soul_histories: dict[str, list[Message]] = {}
        # Read max_turns from config if not explicitly passed
        if max_turns is None:
            try:
                cfg = load_config(root)
                max_turns = cfg.tui.max_tool_rounds
                defaults = TUIConfig()
                # Backward-compatible UX: some users tune only session_max_turns and
                # expect turn budget to follow. If max_tool_rounds is still default,
                # honor the explicit session_max_turns override.
                if (
                    cfg.tui.max_tool_rounds == defaults.max_tool_rounds
                    and cfg.tui.session_max_turns != defaults.session_max_turns
                ):
                    max_turns = cfg.tui.session_max_turns
            except Exception:
                max_turns = MAX_CONVERSATION_TURNS
        self.max_turns = max_turns
        self.todo_manager = todo_manager or TodoManager()
        self.skill_loader = skill_loader or SkillLoader(root)
        # M31 B2/B3: what the current turn wrote. Session-owned so it holds
        # whichever way the turn exits; reset at the top of every send().
        self.change_ledger = TurnChangeLedger()
        self._last_user_text = ""
        self.messages: list[Message] = []
        self.recent_files: list[str] = []
        self.branch = self._current_branch()
        self.total_turns: int = 0
        self.total_usage: dict[str, Any] = {}
        self._persisted_up_to: int = 0  # index of last persisted message
        self._last_run_id: str = ""
        self._cancel_event: threading.Event = threading.Event()
        # M18 Phase A: the singleton world-agent owns the turn-loop entry.
        # Constructed lazily to avoid an import cycle (world_agent imports
        # from this module). Behaviourally it is a thin wrapper that
        # delegates straight back into run_conversation_turn.
        self._world_agent: Any = None
        # M18 §4.2 — the SESSION-level broker. One bus for the whole
        # playthrough session: nodes register once, frontends can subscribe
        # durably, and each turn drains its own recording window into the
        # trace. (Previously a bus was built and discarded every turn —
        # nodes were reborn each turn and nothing could truly subscribe.)
        self._session_bus: Any = None
        self._bus_bootstrapped = False

    def bus(self) -> Any:
        """The session's broker (lazy). Frontends/observers may subscribe to
        it directly — subscriptions survive across turns."""
        if self._session_bus is None:
            from neonrp.core import topics as _topics
            from neonrp.core.message_bus import InProcessBus

            self._session_bus = InProcessBus()
            self._session_bus.start_recording()
            # token-volume deltas are dispatched, never recorded (M18 Phase 1)
            self._session_bus.transient_topics.add(_topics.ENGINE_STREAM)
            self._session_bus.transient_topics.add(_topics.ENGINE_BEAT)
            self._watch_dice()
        return self._session_bus

    def _watch_dice(self) -> None:
        """Every die this world rolls (the narrator's [dice], an agreed check, a skill command, the referee, [san]) goes
        out on engine/beat as ``dice.rolled`` the moment the tool returns — a front end plays it then, not when the
        turn is over (10-17). Held weakly: a session that is gone unwatches itself."""
        import weakref

        from neonrp.core import beat_events as _be
        from neonrp.core import tool_watch as _tw
        from neonrp.core import topics as _tp

        ref, root = weakref.ref(self), str(self.root)
        off: list[Any] = []

        def seen(ev: dict[str, Any]) -> None:
            s = ref()
            if s is None:
                if off:
                    off[0]()
                return
            if ev.get("root") != root or ev.get("tool") not in ("dice", "san"):
                return
            d = _be.live_dice(ev)
            if d is not None and s._session_bus is not None:
                s._session_bus.publish(_tp.ENGINE_BEAT, d)

        off.append(_tw.watch(seen))

    def _ensure_bus_bootstrap(self, playthrough: Any) -> None:
        """M18 §4.2 scene bootstrap — once per session, on the first turn:
        announce the session (roster, players) on engine/event and broadcast
        the initial world/state. Recorded, so it lands in the first turn's
        trace window. Best-effort: bootstrap must never break a turn."""
        if self._bus_bootstrapped:
            return
        self._bus_bootstrapped = True
        try:
            bus = self.bus()
            run_state = {}
            try:
                run_state = json.loads(
                    (
                        self.root / get_data_dir_name(self.root) / "meta" / "run_state.json"
                    ).read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                run_state = {}
            location = run_state.get("location") if isinstance(run_state, dict) else {}
            node = (location or {}).get("node") if isinstance(location, dict) else None
            pids = [p.pid for p in getattr(playthrough, "players", ()) or ()] or ["player"]
            from neonrp.core import topics as _topics

            bus.publish(
                _topics.ENGINE_EVENT,
                {
                    "kind": "session_bootstrap",
                    "world": self.root.name,
                    "world_agent_id": self.agent_id,
                    "branch": self.branch,
                    "players": pids,
                    "souls": [s.instance_id for s in playthrough.souls],
                },
            )
            bus.publish(
                _topics.WORLD_STATE,
                {
                    "turn_seq": int(run_state.get("turn_count") or 0)
                    if isinstance(run_state, dict)
                    else 0,
                    "world_agent_id": self.agent_id,
                    "world_location": node,
                    "active_souls": sorted(playthrough.active_souls),
                    "bootstrap": True,
                },
            )
        except Exception:  # noqa: BLE001 — bootstrap must never break a turn
            logger.debug("session bus bootstrap skipped", exc_info=True)

    def _get_world_agent(self) -> Any:
        if self._world_agent is None:
            from neonrp.core.world_agent import WorldAgent

            self._world_agent = WorldAgent(self.root)
        return self._world_agent

    def join_deferred_settle(self, timeout: float | None = 60.0) -> None:
        """Wait for a soul settle started after the previous reply (no fast judge; 10-01). Never raises."""
        for attr in ("_deferred_settle", "_deferred_place"):  # soul settle · after-turn placement of grown places
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.join(timeout)
                except Exception:  # noqa: BLE001
                    pass
                setattr(self, attr, None)

    def _cs(self) -> dict[str, Any]:
        """Prompt strings of the turn (src/neonrp/prompts/conversation.<lang>.json) in the run's language (10-05 四语)."""
        from neonrp import prompts
        from neonrp.core.output_lang import prompt_lang

        return prompts.strings("conversation", prompt_lang(self.root))

    def _enter_beat(self, node: str, turn: Any = None) -> None:
        """Announce a beat as it STARTS (node.leave / node.enter on engine/beat), before its prose streams — the beat's
        own events follow when its trace lands (and do not repeat the enter: the node is already this one)."""
        prev = getattr(self, "_beat_node", None)
        if prev == node:
            return
        try:
            from neonrp.core import topics as _tp

            bus = self.bus()
            if prev:
                bus.publish(_tp.ENGINE_BEAT, {"kind": "node.leave", "node": prev, "turn": turn})
            bus.publish(_tp.ENGINE_BEAT, {"kind": "node.enter", "node": node, "turn": turn})
        except Exception:  # noqa: BLE001
            logger.debug("beat enter skipped", exc_info=True)
        self._beat_node = node

    def _landing_header(self) -> str:
        """The header of a landing beat as text: the beat's declared name (beat-kinds; else its node id), and — when a
        node before it handed over — why it came (the plugin says)."""
        name = "resolve"
        try:
            from neonrp.core import orchestration as _orc

            k = (_orc.beat_kinds(self.root).get("kinds") or {}).get("resolve") or {}
            name = str(k.get("narr") or k.get("label") or name)
        except Exception:  # noqa: BLE001
            pass
        why = ""
        if getattr(self, "_pl_resolve", None):
            from neonrp.core import node_kinds as _nk_h

            why = str(_nk_h.call("plan", "switch_label", self._pl_resolve, default="") or "")
        return name + (f" · {why}" if why else "")

    def _emit_beats(self, tr: Any) -> None:
        """Each beat as it lands → its contract 1.0 events on engine/beat (10-08: the TUI renders the two beats, the dice
        and the state changes from these instead of parsing the prose). Dispatched, never recorded (derived from the trace)."""
        try:
            from neonrp.core import beat_events as _be
            from neonrp.core import topics as _tp

            evs, self._beat_node = _be.from_traces([tr.to_dict()], getattr(self, "_beat_node", None), root=self.root)
            bus = self.bus()
            for name, data in evs:
                bus.publish(_tp.ENGINE_BEAT, {**data, "kind": name})  # the event name last: a payload never hides it
        except Exception:  # noqa: BLE001 — events must never break a turn
            logger.debug("beat events skipped", exc_info=True)

    TURN_LOCK_WAIT_S = 600.0  # a turn outside the web runtime (TUI / headless) waits this long for the run to be free

    def send(self, user_text: str, *args: Any, **kwargs: Any) -> ConversationTurnResult:
        """One turn, as the run's one writer (core/run_lock, across processes too): the web runtime already holds the
        run's lock for its turn (its ``_busy``); any other caller (the TUI, headless) takes it here, waiting while another
        engine's turn — or a character's world execution — writes the run. Then :meth:`_send`."""
        from neonrp.core import run_lock as _rl

        lk = _rl.of(self.root)
        mine = False
        if not lk.locked():
            mine = lk.acquire(timeout=self.TURN_LOCK_WAIT_S)
            if not mine:
                logger.warning("run %s stayed busy for %.0f s: playing the turn without its lock", self.root, self.TURN_LOCK_WAIT_S)
        try:
            from neonrp.core import write_down_async as _wda

            _wda.cut(self.root)  # the player is ahead of a background write-down: the straight answer stays (10-22)
            _wda.listen(self.root, self._write_down_event)
            return self._send(user_text, *args, **kwargs)
        finally:
            if mine:
                lk.release()

    def _write_down_event(self, ev: dict[str, Any]) -> None:
        """A background write-down's news (pending · corrected · same · cut · timeout · failed) → engine/beat; a correction
        that changed something also as ``state.changed`` (``corrected``: true), so the panels refresh."""
        from neonrp.core import topics as _tp

        bus = self.bus()
        bus.publish(_tp.ENGINE_BEAT, dict(ev))
        if ev.get("kind") == "write_down.corrected":
            bus.publish(_tp.ENGINE_BEAT, {"kind": "state.changed", "corrected": True, "turn": ev.get("turn"),
                                          **{k: ev.get(k) or [] for k in ("applied", "created", "refused")}})

    def _send(
        self,
        user_text: str,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        on_tool_use: Callable[[str, dict[str, Any]], None] | None = None,
        on_tool_result: Callable[[str, dict[str, Any], str], None] | None = None,
        on_ask_user: Callable[[str, list[str]], str | None] | None = None,
        fixture_path: str | None = None,
        on_soul_status: Callable[[dict[str, dict[str, str]]], None] | None = None,
    ) -> ConversationTurnResult:
        """Append user input, execute one turn, and persist session history.

        Messages are persisted incrementally (Claude Code style): each assistant
        response and tool result is appended to the JSONL session file as soon
        as it arrives, so work is never lost even if the process crashes.
        """
        # Reset cancel flag for new turn
        self._cancel_event.clear()
        self.join_deferred_settle()  # last turn's soul settle (run after the reply when Jev was out) lands first
        # M31: this turn's change ledger starts empty; the prompt is kept so
        # the build log can record what was asked for, not just what moved.
        self.change_ledger = TurnChangeLedger()
        self._last_user_text = user_text or ""

        # Secrets: deterministic reveal pass (docs/SECRETS-DESIGN.md §b).
        # Machine-checkable revealed_when conditions (trust/flag/visited) are
        # engine territory — checked once per turn, before any agent context
        # is assembled, so a condition met LAST turn unlocks the text now.
        # Instant no-op for worlds without game/secrets/. Never turn-fatal.
        try:
            from neonrp.core.secrets import check_and_apply_reveals

            check_and_apply_reveals(self.root)
        except Exception:
            pass

        # Secrets P2 (§c/§d): keeper adjudication of fuzzy conditions + the
        # narration guardrail scan — both judged against LAST turn's player
        # action and narration (what actually happened). At most ONE batched
        # LLM call, and only when a judgment-condition secret's host is
        # relevant to the scene; zero calls otherwise, zero without secrets.
        try:
            from neonrp.core.secrets import has_secrets as _has_secrets
            from neonrp.core.secrets import secrets_p2_turn_pass

            if _has_secrets(self.root):
                _last_narration = next(
                    (str(m.content) for m in reversed(self.messages) if m.role == "assistant"),
                    "",
                )
                _last_player = next(
                    (
                        str(m.content)
                        for m in reversed(self.messages)
                        if m.role == "user" and not str(m.content).lstrip().startswith("[")
                    ),
                    "",
                )

                def _keeper_adapter():
                    cfg = load_config(self.root)
                    return get_adapter_from_config(resolve_provider(cfg, None, self.provider))

                secrets_p2_turn_pass(
                    self.root,
                    player_text=_last_player,
                    narration_text=_last_narration,
                    adapter_factory=_keeper_adapter,
                )
        except Exception:
            pass

        run_id = f"{self.agent_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self._last_run_id = run_id
        from neonrp.core import turn_rescue as _rescue_r

        if _rescue_r.resuming() is None:  # a line played on after its talk was cut (「继续生成」) is already in the log
            user_msg = Message(role="user", content=user_text)
            self.messages.append(user_msg)
            # Persist user message immediately
            append_message(self.root, self.branch, user_msg, run_id=run_id)
            self._persisted_up_to = len(self.messages)

        # Incremental persist callback -- saves each message to disk as it arrives
        def _persist_message(msg: Message) -> None:
            append_message(self.root, self.branch, msg, run_id=self._last_run_id)
            # Track that messages list has grown and is persisted
            self._persisted_up_to = len(self.messages)

        # M18 Phase 1 — the typed EngineEvent stream (dual-emit). The session
        # boundary wraps every frontend callback: each callback moment is
        # FIRST published as a typed event on the session bus (engine/event
        # for lifecycle, engine/stream for token-volume deltas — dispatched,
        # never recorded), THEN forwarded to the original callback when one
        # was passed. Frontends can therefore subscribe instead of wiring
        # callbacks; existing callers are byte-identical. ``ask_user`` stays a
        # callback (request/response — the turn blocks on the human's answer).
        from neonrp.core import engine_event as _ev
        from neonrp.core import topics as _ev_topics

        _ev_bus = self.bus()

        def _emit_event(kind: str, **data: Any) -> None:
            try:
                _ev_bus.publish(_ev_topics.ENGINE_EVENT, _ev.EngineEvent(kind, data).payload())
            except Exception:  # noqa: BLE001 — events must never break a turn
                logger.debug("engine event %s skipped", kind, exc_info=True)

        def _emit_stream(kind: str, **data: Any) -> None:
            try:
                _ev_bus.publish(_ev_topics.ENGINE_STREAM, _ev.EngineEvent(kind, data).payload())
            except Exception:  # noqa: BLE001
                logger.debug("engine stream %s skipped", kind, exc_info=True)

        _orig_on_chunk, _orig_on_thinking = on_chunk, on_thinking
        _orig_on_tool_use, _orig_on_tool_result = on_tool_use, on_tool_result
        _orig_on_soul_status = on_soul_status

        def on_chunk(text: str) -> None:  # type: ignore[no-redef]
            _bt = getattr(self, "_beat_node", None)  # R3 (10-09): which beat this piece belongs to — never a stage line in the text
            _emit_stream(_ev.STREAM_CHUNK, text=text, **({"beat": _bt} if _bt else {}))
            if _orig_on_chunk:
                _orig_on_chunk(text)

        def on_thinking(text: str) -> None:  # type: ignore[no-redef]
            _emit_stream(_ev.STREAM_THINKING, text=text)
            if _orig_on_thinking:
                _orig_on_thinking(text)

        def on_tool_use(name: str, args: dict[str, Any]) -> None:  # type: ignore[no-redef]
            _emit_event(_ev.TOOL_USE, name=name)
            # full-grade twin for live frontends (transient — never recorded;
            # args can be write_file-sized)
            _emit_stream(_ev.TOOL_USE, name=name, args=args)
            if _orig_on_tool_use:
                _orig_on_tool_use(name, args)

        def on_tool_result(name: str, args: dict[str, Any], result: str) -> None:  # type: ignore[no-redef]
            # Structured envelope when the result is the JSON tool payload —
            # subscribers (web agent_error line) need status/error without
            # re-parsing a truncated preview.
            _status, _error = "", ""
            try:
                _parsed = json.loads(result)
                if isinstance(_parsed, dict):
                    _status = str(_parsed.get("status") or "")
                    _error = str(_parsed.get("error") or "")[:400]
            except (TypeError, ValueError):
                pass
            _emit_event(
                _ev.TOOL_RESULT,
                name=name,
                status=_status,
                error=_error,
                target=str((args or {}).get("agent_id") or ""),
                result_preview=str(result)[:300],
            )
            # full-grade twin for live frontends (transient — never recorded)
            _emit_stream(_ev.TOOL_RESULT, name=name, args=args, result=str(result))
            if _orig_on_tool_result:
                _orig_on_tool_result(name, args, result)

        def on_soul_status(snapshot: dict[str, dict[str, str]]) -> None:  # type: ignore[no-redef]
            _emit_event(_ev.SOUL_STATUS, statuses=snapshot)
            if _orig_on_soul_status:
                _orig_on_soul_status(snapshot)

        # Streaming gates on callback presence (`use_streaming = on_chunk or
        # on_thinking`): the wrappers exist unconditionally now, which means
        # bus subscribers get live streams even with no callback frontends —
        # the §6 "frontends are pure subscribers" behaviour, by construction.
        _emit_event(_ev.TURN_STARTED, run_id=run_id, input_chars=len(user_text or ""))

        router_execution_mode = get_router_execution_mode(self.root)
        # M18 live-wiring: the ONLY new behaviour. The multi-agent mode is
        # gated behind BOTH (a) router_execution_mode == "multi-agent" AND
        # (b) a valid playthrough.json with >=1 soul. Either condition
        # failing means orchestrator (and legacy single-player
        # multi-agent attempts without a playthrough) fall straight through
        # to the unchanged pass-through call below — byte-identical, because
        # the branch is skipped entirely and the legacy code path is not
        # touched. The committed Phase A-E runtime is reused as-is; this
        # method only decides whether to enter it.
        # Stage 2: the soul-team wrapper fires whenever a soul playthrough
        # exists — under the bespoke "multi-agent" router OR the proven
        # "orchestrator" router (kagura now uses orchestrator: the
        # world-agent turn inside the wrapper is then a real orchestrator
        # turn that task-routes its functional sub-agents, while the
        # wrapper adds the parallel+sticky soul team around it). A world
        # with no soul playthrough (e.g. stoneford-orch) has playthrough
        # None ⇒ inner check fails ⇒ untouched orchestrator path.
        # Soul-team wrapper is a PLAY-mode construct: build/creation turns
        # must stay solo world-agent — a template with bound soul slots (e.g.
        # empty character slots) would otherwise drag empty souls into a
        # parallel deliberation on every studio edit(创作聊天里
        # 冒出「在场灵魂(并行)」,白烧 LLM 且输出噪音)。
        if self.mode == "play" and router_execution_mode in (ROUTER_MODE_MULTI_AGENT, "orchestrator"):
            from neonrp.core.playthrough import read_playthrough

            try:
                playthrough = read_playthrough(self.root)
            except Exception:
                # A malformed manifest must NOT crash the turn; treat it as
                # "no playthrough" so the legacy path still runs (M18 is
                # strictly additive — it can only ever add a code path,
                # never remove the safe default).
                logger.debug(
                    "multi-agent: playthrough.json unreadable; legacy fallback",
                    exc_info=True,
                )
                playthrough = None
            _v3_table = False
            if playthrough is not None and not playthrough.souls and \
                    str(getattr(playthrough.world_agent_team, "seeded_from", "") or "") == "templates/table":
                # a table game (werewolf, 10-09): no souls by design, the pack judges — the v3 turn, not the agent loop
                # (a story world that merely has no one cast yet keeps the world-agent loop that welcomes a character)
                try:
                    from neonrp.core import engine_config as _ec_tb

                    _v3_table = bool(_ec_tb.v3_enabled(self.root))
                except Exception:  # noqa: BLE001
                    _v3_table = False
            if playthrough is not None and (playthrough.souls or _v3_table):
                from neonrp.core import beat_budget as _bb

                # the turn's budget (10-14: the whole turn ≤ 30 s, one beat ≤ 20 s); every beat's timeouts report here
                with _bb.turn(root=self.root) as _timeouts:
                    result = self._run_multi_agent_turn(
                        playthrough=playthrough,
                        user_text=user_text,
                        run_id=run_id,
                        on_chunk=on_chunk,
                        on_thinking=on_thinking,
                        on_tool_use=on_tool_use,
                        on_tool_result=on_tool_result,
                        on_ask_user=on_ask_user,
                        fixture_path=fixture_path,
                        persist_message=_persist_message,
                        on_soul_status=on_soul_status,
                    )
                if _timeouts and isinstance(result, ConversationTurnResult):
                    result.timeouts = list(_timeouts)
                return self._finalize_send_result(result)

        # M18 Phase A (A2): delegate the single-agent keeper/narrator turn
        # through the world-agent singleton. This is pure pass-through:
        # WorldAgent.run_turn forwards every argument to
        # run_conversation_turn unchanged, so without a playthrough.json the
        # behaviour is byte-for-byte identical to the previous direct call.
        result = self._get_world_agent().run_turn(
            root=self.root,
            agent_id=self.agent_id,
            messages=self.messages,
            mode=self.mode,
            provider=self.provider,
            fixture_path=fixture_path,
            max_turns=self.max_turns,
            on_chunk=on_chunk,
            on_thinking=on_thinking,
            on_tool_use=on_tool_use,
            on_tool_result=on_tool_result,
            on_ask_user=on_ask_user,
            todo_manager=self.todo_manager,
            skill_loader=self.skill_loader,
            cancel_event=self._cancel_event,
            on_message_persist=_persist_message,
            run_id=run_id,
            change_ledger=self.change_ledger,
        )
        return self._finalize_send_result(result)

    def _multi_agent_turn_seq(self) -> int:
        """turn_seq for this commit, read from run_state.json's turn_count.

        Mirrors the existing run_state read seam (``_is_initial_game_turn``)
        rather than introducing a second parser — keeps the multi-agent
        branch from diverging on how a turn is counted. Any read failure
        falls back to 0 (a brand-new chain) rather than raising: a missing
        counter must not abort a turn.
        """
        run_state_path = self.root / get_data_dir_name(self.root) / "meta" / "run_state.json"
        try:
            payload = json.loads(run_state_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return int(payload.get("turn_count", 0) or 0)
        except Exception:
            logger.debug("multi-agent: run_state.json unreadable; turn_seq=0", exc_info=True)
        return 0

    def _run_multi_agent_turn(
        self,
        *,
        playthrough: Any,
        user_text: str,
        run_id: str,
        on_chunk: Callable[[str], None] | None,
        on_thinking: Callable[[str], None] | None,
        on_tool_use: Callable[[str, dict[str, Any]], None] | None,
        on_tool_result: Callable[[str, dict[str, Any], str], None] | None,
        on_ask_user: Callable[[str, list[str]], str | None] | None,
        fixture_path: str | None,
        persist_message: Callable[[Message], None],
        on_soul_status: Callable[[dict[str, dict[str, str]]], None] | None = None,
    ) -> ConversationTurnResult:
        """Drive one multi-agent turn (owner-directed orchestration order).

        Only reached when mode == multi-agent AND a playthrough.json with
        >=1 soul exists (the caller already gated this). Sequence:

        1. The active souls think CONCURRENTLY (thread pool; each is a
           real agent on the same ``run_conversation_turn`` path,
           in-memory-resolved from its M16 manifest + persona, write
           scoped to its own folder). Inactive souls get a zero-LLM
           off-stage memo (B-hybrid).
        2. The team-leader collects every soul's first-person output into
           a digest.
        3. THEN the world-agent/narrator runs, with that digest in
           context, so the final player narration integrates what the
           characters actually did this turn (the "end signal" the
           narrator lacked when it ran first).
        4. ``land_turn`` does the §3.4 hash-first compose + committed
           ``land_commit`` over the folder-hash-derived soul deltas.
        """

        _ma_t_start = time.monotonic()
        from neonrp.core.character_agent import _hash_soul_folder
        from neonrp.core.character_agent import CharacterDelta
        from neonrp.core.player_controller import build_scene_packet

        # Correct orchestration order (owner-directed): the active souls
        # think CONCURRENTLY first, the team-leader collects their
        # outputs, THEN the world-agent/narrator integrates those outputs
        # into the final player narration (so the narration actually
        # reflects what the characters did this turn), then the turn is
        # landed. Each soul is a real agent on the SAME
        # run_conversation_turn path, in-memory-resolved from
        # souls/<x>/agents/manifest.json + persona, write-scoped to its
        # own folder; its CharacterDelta is derived from the soul folder
        # content hash (M17 content-addressed dedup ⇒ an unchanged soul is
        # a natural passthrough).
        world_agent = self._get_world_agent()
        souls_root = self.root / "souls"

        # ── intake · clock · scene_route — the steps live in core/turn_runner (10-21 S3), called in today's order ──
        from neonrp.core import turn_runner as _tr

        _c = _tr.TurnCtx(build_scene_packet=build_scene_packet, playthrough=playthrough, user_text=user_text, world_agent=world_agent)
        _tr.intake(self, _c)
        _tr.clock(self, _c)
        _tr.scene_route(self, _c)
        _pa = _c._pa
        _pl_on = _c._pl_on
        _understanding = _c._understanding
        active_refs = _c.active_refs
        broadcast = _c.broadcast
        cap = _c.cap
        player_agents = _c.player_agents
        player_intent = _c.player_intent
        playthrough = _c.playthrough
        scene = _c.scene
        scene_packet = _c.scene_packet
        tick_world = _c.tick_world
        user_text = _c.user_text

        # M18 §7 — per-turn orchestration trace. Best-effort observability;
        # assembled as the turn runs, one JSONL record appended at the end.
        from neonrp.core.orchestration_trace import (
            SoulTraceEntry,
            TurnTrace,
            append_turn_trace,
        )

        _loc = scene_packet.location if isinstance(scene_packet.location, dict) else {}
        _trace = TurnTrace(
            turn_seq=self._multi_agent_turn_seq(),
            player_input=user_text or "",
            player_intent_kind=str(getattr(player_intent, "kind", "") or ""),
            world_location=_loc.get("node") or _loc.get("display"),
        )
        _active_iids_for_trace = {s.instance_id for s in active_refs}

        # A node kind may take the turn before the plain one (10-08 core/node_kinds: the planning beat is such a plugin —
        # private in releases; the public engine has none and every turn is the plain turn below).
        self._pl_resolve = None
        self._companions_judged: dict[str, dict[str, Any]] = {}
        try:
            from neonrp.core import node_kinds as _nk

            # a skill command the engine already rolled (core/player_action) is the player's move, decided: no talk
            # takes it — the plain turn resolves it with that roll (10-17: the planning beat swallowed 「/侦查 壁炉」)
            _decided = bool(((getattr(self, "_act_ctx", None) or {}).get("action") or {}).get("rolled"))
            for _kind in [] if _decided else _nk.turn_order():  # the first active node takes the turn (a game client's interaction · the planning beat …)
                _node = _nk.get(_kind)
                if _node is None or not callable(getattr(_node, "take_turn", None)) or not _node.active(self.root, user_text):
                    continue
                from neonrp.core import orchestration as _orch_nk

                if not _orch_nk.node_kind_live(self.root, _kind):  # its node deleted from the graph (10-11)
                    continue
                from neonrp.core import beat_budget as _bb_pl

                # the planning talk is one beat: ≤ turn.beat_timeout_s, and it leaves the world's share of the turn (10-14);
                # a node kind may size its own beat (``beat_budget(root)`` → {seconds, reserve}: the planning talk, when it
                # does not resolve, is the whole turn — 10-19)
                _nb = _nk.call(_kind, "beat_budget", self.root, default=None)
                _nb = _nb if isinstance(_nb, dict) else {}
                from neonrp.core.llm_openai import thinking as _think_pl

                with _bb_pl.beat(_kind, _nb.get("seconds"), root=self.root,
                                 reserve=float(_nb["reserve"]) if _nb.get("reserve") is not None else _bb_pl.world_reserve_s(self.root)), \
                        _think_pl(_bb_pl.plan_thinking(self.root)):
                    _pl_out = _node.take_turn(self, user_text=user_text, trace=_trace, run_id=run_id, on_chunk=on_chunk)
                if isinstance(_pl_out, ConversationTurnResult):
                    if not (_pl_out.assistant_message or "").strip() and _bb_pl.timed_out(_kind):
                        # the talk ran out of time before anyone said a word: a short line instead of an empty reply
                        from neonrp.core import turn_v3 as _tv3_pl
                        from neonrp.core.output_lang import prompt_lang as _plang_pl

                        _pl_out.assistant_message = str(_tv3_pl._T(_plang_pl(self.root)).get("beat_timeout") or "")
                        if on_chunk is not None and _pl_out.assistant_message:
                            on_chunk(_pl_out.assistant_message)
                    return _pl_out
                if _kind == "plan":
                    self._pl_resolve = _pl_out
                break
        except Exception:  # noqa: BLE001 — the planning layer never blocks a turn; it falls through to the plain turn
            logger.warning("plan loop failed; plain turn", exc_info=True)
            self._pl_resolve = None
            if _pl_on:
                tick_world(self.root)

        # M18 — the turn's message bus. The runtime publishes the turn's
        # lifecycle (scene -> per-soul requests/responses -> narration ->
        # commit) as bus messages; the recorded stream is captured into the
        # trace. The bus now *drives* soul execution: each active soul
        # subscribes to its request topic and is triggered by the broadcast
        # below (see the soul fan-out), not by a direct call. This is the
        # broker as the turn's execution backbone, transport-agnostic.
        # M18 §4.2: the bus is the SESSION's broker (bootstrapped on the
        # first turn) — external subscribers survive across turns; each turn
        # drains its own recording window into the trace.
        from neonrp.core import topics as _topics

        _bus = self.bus()
        self._ensure_bus_bootstrap(playthrough)

        def _publish(topic: str, payload: dict[str, Any]) -> None:
            try:
                _bus.publish(topic, payload)
            except Exception:  # noqa: BLE001 — the bus must never break a turn
                logger.debug("bus publish skipped for %r", topic, exc_info=True)

        _publish(
            _topics.WORLD_SCENE,
            {
                "turn_seq": _trace.turn_seq,
                "world_location": _trace.world_location,
                "scene_label": scene_packet.scene_label or "",
                "active_souls": sorted(_active_iids_for_trace),
                "routing_reasons": dict(_understanding.reasons),
                "routing_fallback": _understanding.fallback_used,
            },
        )

        def _soul_name(d: Path, fallback: str) -> str:
            try:
                m = json.loads((d / "soul.json").read_text(encoding="utf-8"))
                return m.get("name_local") or m.get("name") or fallback
            except (OSError, ValueError):
                return fallback

        def _soul_role(soul: Any) -> str:
            return str(getattr(soul, "role", "") or "npc").strip().lower() or "npc"

        # Persistent per-soul lifecycle for the TUI's CharacterStatusLane.
        # Full snapshot {instance_id: {name, role, state}} emitted on every
        # transition so the panel is a pure repaint target. on_soul_status
        # absent (headless/tests) ⇒ silent no-op.
        _active_iid_set = {s.instance_id for s in active_refs}
        soul_status: dict[str, dict[str, str]] = {}
        for _s in playthrough.souls:
            _sd = souls_root / f"{_s.sid}-{_s.instance_id}"
            soul_status[_s.instance_id] = {
                "name": _soul_name(_sd, _s.sid),
                "role": "active" if _s.instance_id in _active_iid_set else "inactive",
                "state": (
                    "queued"
                    if _s.instance_id in _active_iid_set
                    else "background"
                ),
            }

        def _emit_status() -> None:
            if on_soul_status:
                on_soul_status({k: dict(v) for k, v in soul_status.items()})

        _emit_status()

        deltas: list[CharacterDelta] = []
        # Two-pass turn (Plan→Correct→Apply). Pass A collects each active
        # soul's PROPOSED action/move here without applying it; the world-agent
        # then integrates and MAY emit `_soul_corrections` (iid → {moved_to});
        # Pass B (after integration) applies the corrected-or-proposed move and
        # commits the delta. Empty corrections ⇒ end state identical to the
        # former single-pass flow (full backward-compat).
        _soul_corrections: dict[str, dict] = {}
        # M18 §1 — structured per-soul reports collected OFF THE BUS. Each
        # active soul publishes its report to soul/<iid>/response carrying a
        # `digest`; the world-agent integrates the collected responses (ordered
        # by seq) rather than an in-process list, so a future location/character
        # world-agent integrates via the same topic. (seq, payload) tuples.
        _soul_responses: list[tuple[int, dict[str, Any]]] = []
        # V2b(M30 点名制):引擎不再 fan-out souls —— world-agent 经
        # engage_soul / ask_soul / move_entity 等工具主持回合;感知包仍投
        # mailbox(broadcast:观察面 + T2c 证据面保持),未点名 soul 在
        # 回合末走 off-stage memo(轻心跳,零 LLM)。
        from neonrp.core.engage import (
            drain_turn_engagements,
            reset_turn_engagements,
        )

        reset_turn_engagements()
        try:
            broadcast(_bus, _understanding, root=self.root)
        except Exception:  # noqa: BLE001 — the bus must never break a turn
            logger.debug("scene broadcast skipped", exc_info=True)

        # ── S1 / S2 (exp/jev-system-one) — the steps live in core/turn_runner (10-17 S3), called in today's order ──
        from neonrp.core import turn_runner as _tr

        _c = _tr.TurnCtx(playthrough=playthrough, scene_packet=scene_packet, player_intent=player_intent, _understanding=_understanding, user_text=user_text, _trace=_trace, soul_status=soul_status, _emit_status=_emit_status, cap=cap, _active_iid_set=_active_iid_set, _soul_responses=_soul_responses, scene=scene, _ma_t_start=_ma_t_start)
        _tr.s1_plan(self, _c)
        if _c._s1_mode == "1" and _c._s1_plan is not None:
            _tr.s2_souls(self, _c)
            _tr.followups(self, _c)
        _tr.s1_spans(self, _c)
        (_v3, _v3_spans, _v3_t_base, _s1_mode, _s1_plan, _s1_handled, _s1_hb_lines, _s1_disable_tools, _s1_timing) = (
            _c._v3, _c._v3_spans, _c._v3_t_base, _c._s1_mode, _c._s1_plan, _c._s1_handled, _c._s1_hb_lines, _c._s1_disable_tools, _c._s1_timing)

        turn_seq = self._multi_agent_turn_seq()

        # #2: world-agent/narrator runs — AFTER the souls — as a BUS NODE.
        # A handler is registered on world/integrate; publishing that topic
        # triggers the world-agent inline. For v1 there is exactly one
        # world-agent; when location/character world-agents join they are
        # additional subscribers on the same topic, each producing its own
        # narration (tagged with world_agent_id). The bus drives execution
        # — the turn no longer calls world-agent directly.
        # 重逢一致性(场景拍):若该地点存在场景层记录
        # (scene_state.json,由场景拍/旧地点裁判写入),其叙事尾巴进入
        # primary preflight,world-agent 无缝衔接。
        from neonrp.core.scene_understanding import scene_state_path

        _arrival_state = ""
        if _understanding.player_node:
            try:
                _arrival_state = str(
                    json.loads(
                        scene_state_path(
                            self.root, _understanding.player_node
                        ).read_text(encoding="utf-8")
                    ).get("last_narration")
                    or ""
                )
            except (OSError, ValueError):
                _arrival_state = ""
        # Location-judge verdicts from LAST turn's Pass B (clamped/refused
        # moves): the map already decided where those souls actually are — the
        # world-agent's narration and this turn's移动裁定 must follow, not fight.
        _judge_lines = _drain_location_judgments(self.root)
        # 对话拍结算桥(T1,HARNESS-TEAM-DESIGN):幕间直聊的未固化对话行,
        # deliver-once 进本回合 preflight——world-agent 知道聊了什么,叙事连续。
        from neonrp.core.light_chat import drain_chat_digest as _drain_chats

        _chat_lines = _drain_chats(self.root)
        # Secrets unlocked by last turn's deterministic reveal pass — same
        # deliver-once channel as the location judge: the engine already
        # merged the text into the host entity; this line just tells the
        # world-agent it may now narrate it naturally.
        from neonrp.core.secrets import drain_reveal_notices as _drain_reveals

        _reveal_lines = _drain_reveals(self.root)
        # Guardrail corrections from last turn's post-scan (§d): narration
        # touched a still-unrevealed secret — said words can't be unsaid; the
        # rail keeps this turn from making it worse. Deliver-once (the orch
        # path drains the same queue inside run_conversation_turn; whichever
        # assembles first delivers, so there is no double feedback).
        from neonrp.core.secrets import drain_guardrail_notices as _drain_guardrail

        _guardrail_lines = _drain_guardrail(self.root)
        # soul 上报(escalate 工具,V3):主权在 soul,引擎只送达。
        from neonrp.core.notes import drain_notes as _drain_notes

        _escalation_lines = _drain_notes(self.root, "escalation")
        _heartbeat_lines = _drain_notes(self.root, "heartbeat")
        # V2b:在场/不在场名册不再硬注入(H2 裁决工具化)——
        # world-agent 用 get_roster 自取;秘密/感知边界由 permissions 层守。
        preflight_report = (
            "[Player Controller / World Preflight — control-plane context; "
            "do not expose these labels verbatim]\n"
            f"{player_intent.to_prompt_block()}\n"
            f"{scene_packet.to_prompt_block()}"
            + (
                f"\n【此地刚刚发生(地点裁判记录,无缝衔接,勿复述)】{_arrival_state[:600]}"
                if _arrival_state
                else ""
            )
            + (
                "\n【位置裁定(上回合,地图引擎判定;角色实际位置以此为准,"
                "叙事顺着圆,勿向玩家复述本条)】\n" + "\n".join(_judge_lines)
                if _judge_lines
                else ""
            )
            + (
                "\n【幕间直聊(自上回合以来玩家与角色的轻对话,已发生;"
                "叙事与之连续,勿重演对话内容,勿向玩家复述本条)】\n"
                + "\n".join(_chat_lines)
                if _chat_lines
                else ""
            )
            + (
                "\n【秘密解锁(引擎判定;此后可自然揭示,勿向玩家复述本条)】\n"
                + "\n".join(_reveal_lines)
                if _reveal_lines
                else ""
            )
            + (
                "\n【秘密裁定(上回合护栏;已出口的不再收回,本回合起回避展开"
                "或引导玩家以行动解锁,勿向玩家复述本条)】\n"
                + "\n".join(_guardrail_lines)
                if _guardrail_lines
                else ""
            )
            + (
                "\n【角色上报(souls 主动告知世界的事;按叙事需要回应,"
                "勿向玩家复述本条标签)】\n" + "\n".join(_escalation_lines)
                if _escalation_lines
                else ""
            )
            + (
                "\n【上回合在场角色的细微反应(轻心跳;可自然织入叙事,"
                "勿向玩家复述本条标签)】\n" + "\n".join(_heartbeat_lines)
                if _heartbeat_lines
                else ""
            )
        )
        self.messages.append(Message(role="user", content=preflight_report))
        # M18 §1 / M22 — integrate the soul reports COLLECTED OFF THE BUS
        # (ordered by seq = publish order). M22 perspective split: the PRIMARY
        # world-agent integrates only its own group (souls in the player's
        # scene); away groups are integrated by their location world-agents.
        _digest_rows = [
            (p.get("instance_id"), p.get("digest", ""))
            for _seq, p in sorted(_soul_responses, key=lambda _r: _r[0])
            if p.get("feeds_world") and p.get("digest")
        ]
        _integrations = list(getattr(_understanding, "integrations", ()) or ())
        _primary_iids: set[str] | None = None
        if _integrations:
            _primary_iids = set(_integrations[0].get("souls") or [])
        _soul_digest = [
            d for iid, d in _digest_rows if _primary_iids is None or iid in _primary_iids
        ]
        # Option C — cross-group correction context. Souls who proposed a move
        # this turn but live in ANOTHER scene group (away from the player) are
        # listed for the PRIMARY world-agent as CORRECTABLE context: when its
        # player-scene narration reconciles such a soul's fate (e.g. the player
        # calls Elena back and the narration has her stop), it can cancel or
        # redirect that soul's move via the CORRECTIONS block — even though the
        # soul is integrated by another (location) world-agent. Without this a
        # soul that "walked too fast" into an adjacent group was unreachable by
        # the two-pass: its move landed while the player-scene narration said
        # otherwise (state/story desync). Built from _pending_apply (Pass A).
        _away_moves: list[tuple[str, str, str]] = []  # V2b:无 Pass A,
        # 异地移动意图经 engage/ask 工具带回,leader 直接 move_entity。
        # Send the integration/correction message whenever there is anything to
        # integrate OR correct — NOT gated on primary digests alone, so the
        # directive still reaches the world-agent when no soul is co-located
        # (exactly the "walked too fast" case).
        if True:  # 移动裁定必须每回合送达(玩家单独移动、无 soul 在场也要裁)
            _wa_parts: list[str] = []
            if _soul_digest:
                # Label each digest with its instance_id so the world-agent can
                # address a specific soul in the corrections block.
                _labeled_digest = [
                    f"[soul:{iid}] {d}"
                    for iid, d in _digest_rows
                    if (_primary_iids is None or iid in _primary_iids) and d
                ]
                _wa_parts.append(
                    "[本回合各在场角色的结构化回包,按 system.md 的整合纪律"
                    "处理(decision 输入 vs 声音素材;role=player 主权红线)]\n"
                    + "\n".join(_labeled_digest)
                )
            if _away_moves:
                _wa_parts.append(
                    "[其它场景中、本回合想要移动的角色 —— 它们不在玩家场景里。"
                    "若你的叙事波及它们(如玩家叫住、拦下,或顺势让它们走成),"
                    "用下面的移动裁定块给它们最终位置]\n"
                    + "\n".join(
                        f"[soul:{iid}] {nm} 想去:{intent}"
                        for iid, nm, intent in _away_moves
                    )
                )
            if _s1_mode == "1" and _s1_plan is not None:
                _addr = _s1_plan.souls.get(_s1_plan.addressee) if _s1_plan.addressee else None
                _facts = [
                    f"[预判 · System One] 玩家意图={_s1_plan.intent_kind}"
                    + (f";在对「{_addr.name}」说话" if _addr else "")
                    + (
                        f";要去 {_s1_plan.move_target}(请用 move_entity(entity='player', to=...) 落账)"
                        if _s1_plan.move_target
                        else ""
                    )
                    + f";场景张力={_s1_plan.tension:.2f}"
                ]
                if _s1_handled:
                    _facts.append(
                        "以下角色已按预判并行反应,回包在上方(act=全档;speak=只说话;gesture=神态):"
                        + ";".join(f"{h.get('name') or i}={h['kind']}" for i, h in _s1_handled.items())
                        + "。请直接把它们整合进叙事,不必再点名;只有 engage_soul/ask_soul 仍可用时才追问。"
                    )
                _wa_parts.append("\n".join(_facts))
            _wa_parts.append(
                "[主持工具(M30)] 你以工具主持本回合:get_roster 看在场名册;"
                "engage_soul 点名让某角色全档反应(谁该对眼前之事有反应就点谁,"
                "不必全员);ask_soul 定向问;**位置变更一律经 move_entity 落账**"
                "(叙事里谁走到哪——包括玩家 entity='player'——就调它;裁判拒绝"
                "时顺着结果改叙事)。工具结果是物理事实,叙事不得与之矛盾。"
            )
            self.messages.append(
                Message(role="user", content="\n\n".join(_wa_parts))
            )

        # 地点 agent 并行执行体已拆除(场景拍形态 A 取代;
        # integrations 分组与双视角 per-soul packet 保留,异地 soul 走
        # off-stage memo 路径)。

        # M18 §1 — the world-agent is a BUS NODE: it subscribes to
        # world/integrate and fires when triggered. The same protocol works
        # with N world-agents later (each subscribes, each publishes its own
        # narration tagged with world_agent_id). v1 has exactly one.
        _wa_result: Any = None
        # S3: with the souls already heard, the world-agent should integrate in
        # a couple of rounds; the 40-round ceiling is the old hosting budget.
        _s1_wa_turns = (
            min(self.max_turns, int(os.environ.get("NEONRP_S1_WA_TURNS", "6") or 6))
            if _s1_mode == "1" and _s1_handled
            else self.max_turns
        )
        _wa_t0 = time.monotonic()

        def _world_agent_handler(_msg: Any) -> None:
            nonlocal _wa_result
            # Record what the world-agent SEES (soul digest + preflight) in
            # the F12 debug panel — so you can verify it received the real
            # soul reports, not a corrupted/empty input.
            from neonrp.core.debug_sink import record_llm_call as _debug_record

            _wa_input_preview = ""
            if _soul_digest:
                _wa_input_preview = _soul_digest[-1][:400] if _soul_digest else ""
            elif len(self.messages) >= 1:
                _wa_input_preview = (self.messages[-1].content or "")[:400]
            _debug_record(
                {
                    "agent_id": self.agent_id,
                    "provider": "perception",
                    "model": "",
                    "turn": 0,
                    "duration_ms": 0,
                    "tokens_per_sec": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "text_preview": f"[WORLD-AGENT INPUT] souls={len(_soul_digest)} | {_wa_input_preview}",
                }
            )
            _wa_result = self._get_world_agent().run_turn(
                root=self.root,
                agent_id=self.agent_id,
                messages=self.messages,
                mode=self.mode,
                provider=self.provider,
                fixture_path=fixture_path,
                max_turns=_s1_wa_turns,
                on_chunk=on_chunk,
                on_thinking=on_thinking,
                on_tool_use=on_tool_use,
                on_tool_result=on_tool_result,
                on_ask_user=on_ask_user,
                todo_manager=self.todo_manager,
                skill_loader=self.skill_loader,
                cancel_event=self._cancel_event,
                on_message_persist=persist_message,
                run_id=run_id,
                change_ledger=self.change_ledger,
                # M18 §3.3 strict turn ordering: ask_user mid-integration keeps
                # ONE engine turn alive across many player exchanges — souls
                # then run only once and the world-agent monologues the rest.
                # The integration step must CLOSE the turn; choices go as text,
                # and the next player input enters a fresh pipeline (souls run).
                disabled_tools={"ask_user"} | _s1_disable_tools,
            )

        # ── the v3 Resolve (solve · verify · apply · settle · after_turn) — a step of core/turn_runner (10-21 S3) ──
        from neonrp.core import turn_runner as _tr

        _c = _tr.TurnCtx(_s1_handled=_s1_handled, _s1_plan=_s1_plan, _trace=_trace, _v3=_v3, _v3_spans=_v3_spans, _v3_t_base=_v3_t_base, on_chunk=on_chunk, persist_message=persist_message, run_id=run_id, turn_seq=turn_seq, user_text=user_text)
        _tr.v3_resolve(self, _c)
        _s1_handled = getattr(_c, '_s1_handled', None)
        _v3_out = _c._v3_out
        _wa_result = getattr(_c, '_wa_result', None)

        if _v3_out is None:
            _wa_unsub = _bus.subscribe(_topics.WORLD_INTEGRATE, _world_agent_handler)
            _publish(
                _topics.WORLD_INTEGRATE,
                {
                    "turn_seq": turn_seq,
                    "world_agent_id": self.agent_id,
                    "active_souls": sorted(_active_iids_for_trace),
                },
            )
            try:
                _wa_unsub()
            except Exception:
                pass

        result = _wa_result
        _trace.timing["world_agent_ms"] = round((time.monotonic() - _wa_t0) * 1000, 1)
        if result is None:
            # Safety net: world-agent didn't fire (no subscriber, or a bug).
            # Fall through to the direct call so the turn never silently fails.
            result = self._get_world_agent().run_turn(
                root=self.root,
                agent_id=self.agent_id,
                messages=self.messages,
                mode=self.mode,
                provider=self.provider,
                fixture_path=fixture_path,
                max_turns=_s1_wa_turns,
                on_chunk=on_chunk,
                on_thinking=on_thinking,
                on_tool_use=on_tool_use,
                on_tool_result=on_tool_result,
                on_ask_user=on_ask_user,
                todo_manager=self.todo_manager,
                skill_loader=self.skill_loader,
                cancel_event=self._cancel_event,
                on_message_persist=persist_message,
                run_id=run_id,
                change_ledger=self.change_ledger,
                disabled_tools={"ask_user"} | _s1_disable_tools,  # same §3.3 turn-closure rule
            )

        # ── render · corrections land · the souls' deltas and memos · land — steps of core/turn_runner (10-21 S3; the v2b world-agent above stays: its bus handler writes back through a closure) ──
        from neonrp.core import turn_runner as _tr

        _c = _tr.TurnCtx(CharacterDelta=CharacterDelta, SoulTraceEntry=SoulTraceEntry, _active_iids_for_trace=_active_iids_for_trace, _bus=_bus, _emit_status=_emit_status, _hash_soul_folder=_hash_soul_folder, _ma_t_start=_ma_t_start, _publish=_publish, _s1_handled=_s1_handled, _s1_hb_lines=_s1_hb_lines, _s1_mode=_s1_mode, _s1_plan=_s1_plan, _soul_corrections=_soul_corrections, _soul_name=_soul_name, _topics=_topics, _trace=_trace, _understanding=_understanding, _v3=_v3, _v3_out=_v3_out, append_turn_trace=append_turn_trace, deltas=deltas, drain_turn_engagements=drain_turn_engagements, player_agents=player_agents, playthrough=playthrough, result=result, scene=scene, scene_packet=scene_packet, soul_status=soul_status, souls_root=souls_root, turn_seq=turn_seq, user_text=user_text, world_agent=world_agent)
        _tr.render(self, _c)
        _tr.corrections_land(self, _c)
        _tr.soul_deltas(self, _c)
        _tr.land(self, _c)
        if "_ret" in _c.__dict__:
            return _c._ret

    def _finalize_send_result(self, result: ConversationTurnResult) -> ConversationTurnResult:
        # M18 Phase 1 — close the typed event stream for this turn (every
        # send() path funnels through here).
        try:
            from neonrp.core import engine_event as _ev
            from neonrp.core import topics as _topics

            self.bus().publish(
                _topics.ENGINE_EVENT,
                _ev.EngineEvent(
                    _ev.TURN_FINISHED,
                    {
                        "run_id": result.run_id,
                        "success": result.success,
                        "route_decision": result.route_decision,
                        "error": result.error,
                    },
                ).payload(),
            )
        except Exception:  # noqa: BLE001 — events must never break a turn
            logger.debug("turn_finished event skipped", exc_info=True)
        # M31 B3: an authoring turn that moved files leaves a trace in the
        # run folder, so "the world is being edited" is visible to any file
        # client (Obsidian today) instead of only to whoever watched the TUI.
        if self.mode == "build":
            from neonrp.core.player_artifacts import append_build_artifacts

            append_build_artifacts(
                self.root,
                self.branch,
                author_input=self._last_user_text,
                narration=result.assistant_message or "",
                ledger=self.change_ledger,
            )
        # M31: keep the Obsidian face current. The whole point of the vault is
        # watching the world move, so it re-projects as turns land rather than
        # waiting to be asked. Only when a vault already exists — projecting
        # into a world nobody opened in Obsidian would just litter it.
        try:
            from neonrp.core.vault import VAULT_DIRNAME, project_vault

            if (self.root / VAULT_DIRNAME).is_dir():
                project_vault(self.root)
        except Exception:  # noqa: BLE001 — the vault must never break a turn
            logger.debug("vault projection skipped", exc_info=True)
        self._last_run_id = result.run_id or self._last_run_id
        # Flush any remaining unpersisted messages (safety net)
        self.flush()
        truncate_session(self.root, self.branch, max_turns=load_config(self.root).tui.session_max_turns)

        self.total_turns += result.turns_used
        _merge_usage(self.total_usage, result.usage)

        for path in result.files_modified:
            if path not in self.recent_files:
                self.recent_files.append(path)
        self.recent_files = self.recent_files[-20:]

        return result

    def flush(self) -> None:
        """Persist any unsaved messages to the session file.

        Safe to call at any time (e.g. on Ctrl+Q) -- only writes messages
        that haven't been persisted yet, avoiding duplicates.
        """
        if self._persisted_up_to >= len(self.messages):
            return
        run_id = self._last_run_id or "unsaved"
        for message in self.messages[self._persisted_up_to:]:
            append_message(self.root, self.branch, message, run_id=run_id)
        self._persisted_up_to = len(self.messages)

    def set_mode(self, mode: ConversationMode) -> None:
        if mode not in {"build", "sandbox", "play"}:
            raise ValueError(f"Unsupported mode: {mode}")
        self.mode = mode

    def cancel(self) -> None:
        """Signal the running conversation turn to stop after the current step."""
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        """Whether a cancellation has been requested."""
        return self._cancel_event.is_set()

    def clear(self) -> None:
        self.messages = []
        self.recent_files = []
        self._persisted_up_to = 0
        self._last_run_id = ""
        self._cancel_event.clear()
        self.todo_manager.update([])
        clear_session(self.root, self.branch)

    def compact(self, keep_recent: int = 10) -> int:
        """Compact conversation by summarizing old messages and keeping recent ones.

        Follows the Claude Code pattern: instead of silently dropping messages,
        creates a structured summary of what happened so the LLM retains context.

        Returns the number of messages removed.
        """
        if len(self.messages) <= keep_recent + 1:
            return 0
        system = self.messages[0] if self.messages and self.messages[0].role == "system" else None
        # Messages to drop (between system prompt and the kept tail)
        start = 1 if system else 0
        end = len(self.messages) - keep_recent
        dropped = self.messages[start:end]
        removed_count = len(dropped)
        if removed_count == 0:
            return 0

        summary = _build_compact_summary(dropped, self.recent_files, self.todo_manager)

        recent = self.messages[end:]
        compacted: list[Message] = []
        if system:
            compacted.append(system)
        compacted.append(Message(role="user", content=summary))
        compacted.append(
            Message(
                role="assistant",
                content="Understood. I have the summary of our previous conversation and will continue from here.",
            )
        )
        compacted.extend(recent)
        self.messages = compacted
        return removed_count

    def resume(self) -> int:
        """Load messages from persisted branch session."""
        self.branch = self._current_branch()
        raw = read_session_messages(self.root, self.branch)
        # Repair orphan tool_call / tool-result sequences before the
        # next LLM call. Strict providers (DeepSeek) 400 on dangling
        # tool_calls; the on-disk log stays untouched.
        self.messages = sanitize_messages_for_resume(raw)
        if len(self.messages) != len(raw):
            logger.warning(
                "resume: dropped %d orphan tool messages during sanitize",
                len(raw) - len(self.messages),
            )
        # Rebuild TodoWrite state from persisted tool outputs so resumed sessions
        # keep consistent todo snapshots in following turns.
        self.todo_manager.update([])
        for message in self.messages:
            if message.role != "tool" or message.name != "TodoWrite":
                continue
            content = message.content or ""
            if not isinstance(content, str) or not content:
                continue
            try:
                payload = json.loads(content)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            data = payload.get("data")
            if not isinstance(data, dict):
                continue
            items = data.get("items")
            if not isinstance(items, list):
                continue
            try:
                self.todo_manager.update(items)
            except ValueError:
                continue
        # Resumed messages are already on disk — mark them as persisted.
        self._persisted_up_to = len(self.messages)
        return len(self.messages)

    def get_messages(self) -> list[Message]:
        """Return current message list (for TUI restore)."""
        return self.messages

    def _current_branch(self) -> str:
        manifest_path = get_manifest_path(self.root)
        if not manifest_path.exists():
            return "main"
        try:
            manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
            return manifest.current_branch
        except Exception:
            return "main"


_TRACE_JUDGMENT_KEYS = ("attitude", "register", "urgency", "want_move", "move_to", "follow", "stay", "confides", "source", "confidence")


def _trace_judgment(turn: dict[str, Any] | None, companion: dict[str, Any] | None) -> dict[str, Any] | None:
    """The numbers that decided a soul this turn, for the trace: her own turn's judgment (the scalar fields, not every
    answer) and, after the player moved, the companions decision (follow / stay / what answered / moved)."""
    out = {k: turn[k] for k in _TRACE_JUDGMENT_KEYS if isinstance(turn, dict) and turn.get(k) not in (None, "", 0, 0.0, False)}
    if companion:
        out["companion"] = {k: companion[k] for k in ("follow", "stay", "src", "moved") if k in companion}
    return out or None


def _build_compact_summary(
    dropped: list[Message],
    recent_files: list[str],
    todo_manager: TodoManager,
) -> str:
    """Build a structured summary of compacted conversation messages.

    Instead of just "[Previous conversation compacted]", we extract meaningful
    context so the LLM knows what happened and can continue coherently.
    """
    parts = ["[System: Previous conversation was compacted. Summary follows.]", ""]

    # Extract user requests
    user_messages = [m.content for m in dropped if m.role == "user" and m.content]
    if user_messages:
        parts.append("## User Requests")
        for msg in user_messages[-5:]:  # Keep last 5 user messages
            truncated = msg[:200] + "..." if len(msg) > 200 else msg
            parts.append(f"- {truncated}")
        parts.append("")

    # Extract tool calls made
    tool_names: list[str] = []
    for m in dropped:
        if m.role == "assistant" and m.tool_calls:
            for tc in m.tool_calls:
                tool_names.append(tc.name)
    if tool_names:
        # Deduplicate while preserving order, show counts
        seen: dict[str, int] = {}
        for name in tool_names:
            seen[name] = seen.get(name, 0) + 1
        summary_items = [f"{name} x{count}" if count > 1 else name for name, count in seen.items()]
        parts.append(f"## Tools Used: {', '.join(summary_items)}")
        parts.append("")

    # Files modified
    if recent_files:
        parts.append(f"## Files Modified: {', '.join(recent_files[-10:])}")
        parts.append("")

    # Current todo state
    todo_text = todo_manager.render()
    if todo_text != "(no todos)":
        parts.append(f"## Current Todo State\n{todo_text}")
        parts.append("")

    return "\n".join(parts)


def _chat_stream(
    adapter: Any,
    messages: list[Message],
    tools: list[dict],
    on_chunk: Callable[[str], None] | None,
    on_thinking: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> LLMTurnResult:
    """Collect streaming chunks into a standard turn result."""
    content = ""
    reasoning = ""
    tool_calls = None
    finished = False
    usage: dict[str, Any] = {}
    error = None
    retryable = False
    try:
        with contextlib.closing(adapter.chat_stream(messages, tools=tools)) as gen:  # a cancel's break closes the stream now, not the GC (10-11)
            for chunk in gen:
                if cancel_event is not None and cancel_event.is_set():
                    break
                if chunk.delta:
                    content += chunk.delta
                    if on_chunk:
                        on_chunk(chunk.delta)
                if chunk.thinking:
                    reasoning += chunk.thinking
                    if on_thinking:
                        on_thinking(chunk.thinking)
                if chunk.tool_call_starts and on_chunk:
                    names = ", ".join(chunk.tool_call_starts)
                    on_chunk(f"\n[calling {names}...]\n")
                if chunk.tool_calls:
                    tool_calls = chunk.tool_calls
                if chunk.usage:
                    usage = chunk.usage
                if chunk.finished:
                    finished = True
                if chunk.error:
                    error = chunk.error
                    retryable = bool(getattr(chunk, "retryable", False)) or _looks_retryable_error_text(chunk.error)
                    break
    except Exception as exc:
        return LLMTurnResult(error=str(exc), finished=True, retryable=_looks_retryable_error_text(str(exc)))

    # Some thinking-mode models (Qwen3 MoE thinking variants on
    # SiliconFlow / DashScope, observed with Qwen3.5-397B-A17B) emit
    # the entire response into `reasoning_content` and leave `content`
    # empty. Without this swap, the TUI would render an empty main
    # area while the actual narrative sits invisible inside the
    # thinking fold. Only swap when the agent isn't mid-tool-call —
    # DeepSeek's thinking mode legitimately produces (empty content +
    # tool_calls + reasoning) and we must preserve reasoning there
    # for the multi-turn echo requirement.
    if not (content or "").strip() and not tool_calls and reasoning.strip():
        content = reasoning
        reasoning = ""

    message = Message(
        role="assistant",
        content=content or None,
        tool_calls=tool_calls,
        reasoning_content=reasoning or None,
    )
    return LLMTurnResult(
        message=message,
        tool_calls=tool_calls,
        finished=finished,
        usage=usage,
        error=error,
        retryable=retryable,
    )


def _looks_retryable_error_text(error_text: str | None) -> bool:
    """Best-effort classifier for transient errors from adapters/chunks."""
    if not error_text:
        return False
    from neonrp.core import billing_stop

    if billing_stop.from_text(error_text):  # quota / credits / claim: the player acts; retrying only waits (the text holds "429")
        return False
    text = str(error_text).lower()
    markers = (
        "network connection lost",
        "connection reset",
        "connection aborted",
        "connection refused",
        "connection error",
        "api connection error",
        # httpx.RemoteProtocolError surfaces as one of these when a
        # provider (DeepSeek in particular) drops mid-stream. These
        # aren't a content issue — same prompt usually succeeds on retry.
        "peer closed connection",
        "incomplete chunked read",
        "incomplete read",
        "remote protocol error",
        "remoteprotocolerror",  # bare exception class name (no spaces)
        "connection broken",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "rate limit",
        "429",
        "503",
        "502",
        "500",
        "retryable",
    )
    return any(marker in text for marker in markers)


def _preview_for_log(value: Any, max_len: int = 260) -> str:
    """Render compact one-line preview for debug logs."""
    try:
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = str(value)
    text = text.replace("\n", "\\n")
    if len(text) > max_len:
        return f"{text[:max_len]}...(+{len(text) - max_len} chars)"
    return text


def _json_dumps(value: Any) -> str:
    """Serialize tool/session payloads with readable UTF-8 characters."""
    return json.dumps(value, ensure_ascii=False, default=str)


def _truncate_for_prompt(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    keep = max(0, max_chars - 48)
    return f"{text[:keep]}\n... [truncated {len(text) - keep} chars]"


def _latest_parent_user_message(messages: list[Message] | None) -> str:
    """Return the latest non-empty parent user message for sub-agent prompt injection."""
    for message in reversed(messages or []):
        if message.role != "user":
            continue
        content = str(message.content or "").strip()
        if content:
            return content
    return ""


def _build_sub_agent_language_hint(parent_messages: list[Message] | None) -> str:
    """Build a language-context section for delegated sub-agent prompts."""
    latest_user_message = _latest_parent_user_message(parent_messages)
    if not latest_user_message:
        return ""
    quoted_message = _truncate_for_prompt(latest_user_message, 240)
    return (
        "Parent conversation language context:\n"
        "- The latest end-user message from the parent conversation is quoted below.\n"
        "- Match that language for all natural-language output, reasoning summaries, tool narration, and "
        "`ask_user` question/options unless the user explicitly asks to switch languages.\n"
        f"- Latest end-user message:\n{quoted_message}\n"
    )


def _load_indexed_entities_for_context_pack(root: Path) -> dict[str, EntityRecord]:
    """Best-effort manifest entity index refresh for prompt-time context packing."""
    try:
        manifest, _, warnings = refresh_manifest_index(root, full_rebuild=False)
    except Exception as exc:
        logger.debug("context_pack: failed to refresh manifest index: %s", exc)
        return {}
    if warnings:
        logger.debug("context_pack: index refresh warnings=%d", len(warnings))
    entities = manifest.entities
    return entities if isinstance(entities, dict) else {}


def _entities_by_id(entities: dict[str, EntityRecord]) -> dict[str, EntityRecord]:
    by_id: dict[str, EntityRecord] = {}
    for record in entities.values():
        if not isinstance(record, EntityRecord):
            continue
        entity_id = str(record.id or "").strip()
        if not entity_id or entity_id in by_id:
            continue
        by_id[entity_id] = record
    return by_id


def _extract_prompt_entity_ids(task_prompt: str, by_id: dict[str, EntityRecord]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for match in _ENTITY_ID_TOKEN_PATTERN.finditer(str(task_prompt or "").lower()):
        token = match.group(0)
        if token in by_id and token not in seen:
            ids.append(token)
            seen.add(token)
    return ids


def _read_player_location_id(root: Path, by_id: dict[str, EntityRecord]) -> str:
    contract = load_runtime_contract(root)
    source_entity_id = contract.routing.location_source.entity_id
    source_field = contract.routing.location_source.field
    source_record = by_id.get(source_entity_id)
    if not source_record:
        return ""
    try:
        payload = json.loads((root / source_record.path).read_text(encoding="utf-8"))
    except Exception:
        return ""
    location = payload.get(source_field) if isinstance(payload, dict) else None
    if isinstance(location, str):
        return location.strip()
    return ""


def _preferred_kinds_for_agent(
    root: Path,
    target_agent_id: str,
    by_id: dict[str, EntityRecord],
) -> tuple[str, ...]:
    preferred: list[str] = []
    for kind in sorted(_get_agent_sticky_domain_kinds(root, target_agent_id)):
        if kind not in preferred:
            preferred.append(kind)

    all_kinds = sorted(
        {str(record.kind or "").strip() for record in by_id.values() if str(record.kind or "").strip()},
        key=lambda kind: ({"meta": 0, "player": 1}.get(kind, 10), kind),
    )
    for kind in all_kinds:
        if kind not in preferred:
            preferred.append(kind)
    return tuple(preferred)


def _select_context_pack_entity_ids(
    *,
    root: Path,
    target_agent_id: str,
    task_prompt: str,
    by_id: dict[str, EntityRecord],
) -> list[str]:
    contract = load_runtime_contract(root)
    max_entities = max(1, contract.context_pack.max_entities)
    selected: list[str] = []

    def _add(entity_id: str) -> None:
        key = str(entity_id or "").strip()
        if not key or key not in by_id or key in selected:
            return
        selected.append(key)

    for entity_id in _extract_prompt_entity_ids(task_prompt, by_id):
        _add(entity_id)
        if len(selected) >= max_entities:
            return selected

    for seed in contract.context_pack.seed_entity_ids:
        _add(seed)
        if len(selected) >= max_entities:
            return selected

    location_id = _read_player_location_id(root, by_id)
    if location_id:
        _add(location_id)
        if len(selected) >= max_entities:
            return selected

    preferred_kinds = _preferred_kinds_for_agent(root, target_agent_id, by_id)
    for kind in preferred_kinds:
        for record in sorted(by_id.values(), key=lambda item: item.id):
            if record.kind != kind:
                continue
            _add(record.id)
            if len(selected) >= max_entities:
                return selected

    return selected


def _build_registry_ids(
    *,
    root: Path,
    selected_ids: list[str],
    by_id: dict[str, EntityRecord],
    target_agent_id: str,
) -> list[str]:
    registry_ids: list[str] = []
    seen: set[str] = set()

    def _add(entity_id: str) -> None:
        key = str(entity_id or "").strip()
        if not key or key in seen or key not in by_id:
            return
        seen.add(key)
        registry_ids.append(key)

    for entity_id in selected_ids:
        _add(entity_id)
        if len(registry_ids) >= CONTEXT_PACK_REGISTRY_MAX_ITEMS:
            return registry_ids

    preferred_kinds = set(_preferred_kinds_for_agent(root, target_agent_id, by_id))
    for record in sorted(by_id.values(), key=lambda item: item.id):
        if record.kind not in preferred_kinds:
            continue
        _add(record.id)
        if len(registry_ids) >= CONTEXT_PACK_REGISTRY_MAX_ITEMS:
            return registry_ids
    return registry_ids


def _build_task_context_pack(root: Path, target_agent_id: str, task_prompt: str) -> str:
    entities = _load_indexed_entities_for_context_pack(root)
    if not entities:
        return ""
    by_id = _entities_by_id(entities)
    if not by_id:
        return ""

    selected_ids = _select_context_pack_entity_ids(
        root=root,
        target_agent_id=target_agent_id,
        task_prompt=task_prompt,
        by_id=by_id,
    )
    if not selected_ids:
        return ""

    registry_ids = _build_registry_ids(
        root=root,
        selected_ids=selected_ids,
        by_id=by_id,
        target_agent_id=target_agent_id,
    )
    registry_lines = [
        f"- {entity_id} -> {by_id[entity_id].path}"
        for entity_id in registry_ids
    ]

    snapshots: list[str] = []
    for entity_id in selected_ids:
        record = by_id[entity_id]
        abs_path = root / record.path
        try:
            raw = abs_path.read_text(encoding="utf-8")
        except Exception:
            raw = f'{{"error":"Failed to read {record.path}"}}'
        excerpt = _truncate_for_prompt(raw, CONTEXT_PACK_ENTITY_MAX_CHARS)
        snapshots.append(
            "\n".join(
                [
                    f"### {entity_id} ({record.kind})",
                    f"path: {record.path}",
                    excerpt,
                ]
            )
        )

    section = "\n".join(
        [
            "## Context Pack (preloaded canonical paths + entity snapshots)",
            "Use these canonical paths directly before any broad discovery calls.",
            "### Entity Path Registry",
            *registry_lines,
            "",
            "### Preloaded Entity Snapshots",
            *snapshots,
        ]
    )
    return _truncate_for_prompt(section, CONTEXT_PACK_MAX_CHARS)


def _is_loop_guard_readonly_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() in READONLY_TOOL_LOOP_GUARD


def _tool_call_signature(tool_name: str, tool_args: dict[str, Any]) -> str:
    """Build a stable signature for repeated-tool loop detection."""
    try:
        args_json = json.dumps(tool_args or {}, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))
    except Exception:
        args_json = str(tool_args)
    return f"{str(tool_name or '').strip()}::{args_json}"


def _summarize_tool_result_for_log(tool_result: str) -> str:
    """Extract stable high-signal fields from tool result payload."""
    try:
        payload = json.loads(tool_result)
    except Exception:
        return f"non_json len={len(tool_result)} preview={_preview_for_log(tool_result)}"
    if not isinstance(payload, dict):
        return f"json_non_object type={type(payload).__name__} preview={_preview_for_log(payload)}"
    status = str(payload.get("status", ""))
    error = payload.get("error")
    data = payload.get("data")
    data_keys: list[str] = []
    path = None
    if isinstance(data, dict):
        data_keys = [str(k) for k in sorted(data.keys())]
        if isinstance(data.get("path"), str):
            path = data.get("path")
    parts = [f"status={status or '?'}"]
    if error:
        parts.append(f"error={_preview_for_log(error, 180)}")
    if path:
        parts.append(f"path={path}")
    if data_keys:
        parts.append(f"data_keys={data_keys}")
    return " ".join(parts)


def _tag_sub_agent_event(agent_id: str, payload: str) -> str:
    """Attach a lightweight sub-agent tag so UI can route nested stream events."""
    safe_agent = str(agent_id or "").strip()
    text = payload if isinstance(payload, str) else str(payload)
    if not safe_agent:
        return text
    return f"[[subagent:{safe_agent}]]{text}"


def _is_cancelled_tool_result(tool_result: str) -> bool:
    """Return True when a tool result payload explicitly reports cancellation."""
    try:
        payload = json.loads(tool_result)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    return str(payload.get("status", "")).strip().lower() == "cancelled"


def _parse_task_tool_result(tool_result: str) -> dict[str, Any] | None:
    """Parse task() tool result payload when it is valid JSON object."""
    try:
        payload = json.loads(tool_result)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _is_sticky_task_success(tool_result: str) -> bool:
    payload = _parse_task_tool_result(tool_result)
    if not payload:
        return False
    if str(payload.get("status", "")).strip().lower() != "success":
        return False
    data = payload.get("data")
    if not isinstance(data, dict):
        return False
    return str(data.get("delegation_mode", "")).strip().lower() == "sticky"


def _is_missing_read_file_error(tool_name: str, tool_result: str) -> bool:
    """True when read_file result indicates a missing path."""
    if tool_name != "read_file":
        return False
    try:
        payload = json.loads(tool_result)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    if str(payload.get("status", "")).strip().lower() != "error":
        return False
    error_text = str(payload.get("error", "")).strip().lower()
    return error_text.startswith("file not found:")


def _load_agent_data(root: Path, agent_id: str) -> dict[str, Any] | None:
    """Load agent.json for the given agent id, returning None on errors."""
    agent_json = root / "agents" / agent_id / "agent.json"
    if not agent_json.exists():
        return None
    try:
        payload = json.loads(agent_json.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _build_default_build_agent_data(root: Path, agent_id: str) -> dict[str, Any]:
    """Provide a safe default build-mode agent for init-only projects."""
    narrator_agent_id = get_narrator_agent_id(root)
    display_name = "Workspace Agent" if agent_id == narrator_agent_id else agent_id.replace("-", " ").title()
    return {
        "id": agent_id,
        "name": display_name,
        "description": (
            "Fallback build-mode agent for initialized projects without explicit agents. "
            "Behaves like a general workspace coding agent."
        ),
        "system_prompt": (
            "You are the default build-mode workspace agent. "
            "Work like Claude Code: inspect the repository, read before writing, "
            "edit carefully, and keep changes scoped to the user's request."
        ),
        "policy": {
            "role": "builder",
            "disallow_direct_game_tools": False,
        },
        "permissions": {
            "read_globs": ["**"],
            "deny_globs": [],
            "write_globs": ["**"],
            "direct_write_globs": ["**"],
        },
    }


def _build_default_orchestrator_agent_data(root: Path, agent_id: str) -> dict[str, Any]:
    """Provide a safe fallback orchestrator when projects define no router agent."""
    del root
    return {
        "id": agent_id,
        "name": "Default Orchestrator",
        "description": (
            "Fallback orchestrator for play/build flows when the project does not define "
            "a narrator/orchestrator agent."
        ),
        "system_prompt": (
            "You are the default orchestrator for a role-playing game world. "
            "You are always the player-facing speaker. Read the current game state, decide whether to "
            "use tools directly or delegate to a specialist via task(), and then produce the final player-visible narration. "
            "Use tools for deterministic mechanics and local state operations; use specialists for domain reasoning."
        ),
        "policy": {
            "role": "router",
            "disallow_direct_game_tools": False,
        },
        "permissions": {
            "read_globs": ["game/**", ".neonrp/manifest.json"],
            "deny_globs": [],
            "write_globs": ["game/**"],
            "direct_write_globs": ["game/**"],
        },
    }


def _load_agent_data_for_mode(root: Path, agent_id: str, mode: ConversationMode) -> dict[str, Any] | None:
    """Load agent.json, or synthesize a default build agent after plain init."""
    # A soul is a regular agent whose definition is synthesised in memory
    # from its OWN souls/<sid>-<iid>/agents/manifest.json + persona — never
    # a hand-authored agents/<id>/. Same run_conversation_turn path as the
    # world-agent; only the synthesised prompt + scope differ.
    from neonrp.core.soul_agent import parse_soul_agent_id, resolve_soul_agent_data

    parsed = parse_soul_agent_id(agent_id)
    if parsed is not None:
        return resolve_soul_agent_data(root, parsed[0], parsed[1])

    agent_dir = root / "agents" / agent_id
    agent_json = agent_dir / "agent.json"
    if agent_json.exists():
        try:
            payload = json.loads(agent_json.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None
    narrator_agent_id = get_narrator_agent_id(root)
    router_execution_mode = get_router_execution_mode(root)
    if mode == "build" and agent_id == narrator_agent_id and not agent_dir.exists():
        return _build_default_build_agent_data(root, agent_id)
    if agent_id == narrator_agent_id and router_execution_mode == "orchestrator" and not agent_dir.exists():
        return _build_default_orchestrator_agent_data(root, agent_id)
    return None


def _get_agent_policy(
    root: Path,
    agent_id: str,
    agent_data: dict[str, Any] | None = None,
    *,
    narrator_agent_id: str | None = None,
) -> dict[str, Any]:
    agent_data = agent_data if isinstance(agent_data, dict) else (_load_agent_data(root, agent_id) or {})
    narrator_agent_id = narrator_agent_id or load_runtime_contract(root).router.agent_id
    policy = agent_data.get("policy")
    role = ""
    disallow_direct_game_tools = None
    if isinstance(policy, dict):
        raw_role = policy.get("role")
        if isinstance(raw_role, str) and raw_role.strip():
            role = raw_role.strip().lower()
        raw_disallow = policy.get("disallow_direct_game_tools")
        if isinstance(raw_disallow, bool):
            disallow_direct_game_tools = raw_disallow

    if not role:
        role = "router" if agent_id == narrator_agent_id else "specialist"
    if disallow_direct_game_tools is None:
        disallow_direct_game_tools = role == "router"

    return {
        "role": role,
        "disallow_direct_game_tools": bool(disallow_direct_game_tools),
    }


def _load_agent_system_prompt_text(root: Path, agent_id: str, agent_data: dict[str, Any]) -> str:
    """Load agent-specific system instructions from file path or inline text.

    Priority:
    1) agents/<agent_id>/<system_prompt> when value looks like file name/path
    2) <project_root>/<system_prompt> fallback
    3) inline string value from agent.json
    """
    raw = agent_data.get("system_prompt")
    if not isinstance(raw, str):
        return ""
    candidate = raw.strip()
    if not candidate:
        return ""

    def _read_if_exists(path: Path) -> str:
        try:
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
        return ""

    agent_local = _read_if_exists(root / "agents" / agent_id / candidate)
    if agent_local:
        return agent_local

    project_relative = _read_if_exists(root / candidate)
    if project_relative:
        return project_relative

    looks_like_file_ref = _looks_like_prompt_file_reference(candidate)
    if looks_like_file_ref:
        logger.warning(
            "Agent '%s' system_prompt references missing file '%s'; continuing without agent-specific prompt",
            agent_id,
            candidate,
        )
        return ""

    return candidate


def _looks_like_prompt_file_reference(candidate: str) -> bool:
    """Heuristic: decide whether `system_prompt` looks like a file path."""
    if not isinstance(candidate, str):
        return False
    text = candidate.strip()
    if not text:
        return False
    if "\n" in text or "\r" in text:
        return False
    if len(text) > 240:
        return False
    has_sep = "/" in text or "\\" in text
    has_ws = bool(re.search(r"\s", text))
    lowered = text.lower()
    if lowered.endswith((".md", ".txt", ".prompt", ".rst")) and not has_ws:
        return True
    if has_sep and not has_ws:
        return True
    if "." in text and re.fullmatch(r"[A-Za-z0-9_.-]+", text):
        return True
    return False


def _normalize_delegation_mode(raw: object) -> str:
    text = str(raw or "").strip().lower().replace("_", "-")
    if text in {"oneshot", "one-shot"}:
        return "one-shot"
    if text == "sticky":
        return "sticky"
    return ""


def _get_agent_delegation_mode(root: Path, agent_id: str) -> str:
    """Resolve delegation mode from agent.json.

    Priority:
    1) explicit `delegation_mode` (`sticky` / `one-shot`)
    2) legacy `handoff_when` present -> sticky
    3) fallback -> one-shot
    """
    agent_data = _load_agent_data(root, agent_id)
    if not isinstance(agent_data, dict):
        return "one-shot"

    explicit = _normalize_delegation_mode(agent_data.get("delegation_mode"))
    if explicit:
        return explicit

    handoff_when = agent_data.get("handoff_when")
    if isinstance(handoff_when, dict) and handoff_when:
        return "sticky"
    return "one-shot"


def _get_agent_sticky_domain_kinds(root: Path, agent_id: str) -> set[str]:
    """Resolve allowed location kinds for sticky lock ownership.

    Source priority:
    1) agent.json `sticky_domain_kinds` (list[str])
    2) runtime contract `routing.domain_agent_map`
    """
    agent_data = _load_agent_data(root, agent_id) or {}
    raw = agent_data.get("sticky_domain_kinds")
    if isinstance(raw, list):
        parsed = {str(item).strip().lower() for item in raw if isinstance(item, str) and str(item).strip()}
        if parsed:
            return parsed
    contract = load_runtime_contract(root)
    return {
        domain
        for domain, mapped_agent in contract.routing.domain_agent_map.items()
        if str(mapped_agent or "").strip() == agent_id
    }


def _read_player_location_state(root: Path, data_dir_name: str) -> tuple[str, str]:
    """Best-effort current player location id + entity kind."""
    contract = load_runtime_contract(root)
    data_dir_name = contract.data_dir or data_dir_name
    source_entity_id = contract.routing.location_source.entity_id
    source_field = contract.routing.location_source.field
    location_id = ""
    entities = _load_indexed_entities_for_context_pack(root)
    by_id = _entities_by_id(entities) if entities else {}
    if by_id:
        source_record = by_id.get(source_entity_id)
        if isinstance(source_record, EntityRecord):
            try:
                payload = json.loads((root / source_record.path).read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                raw_location = payload.get(source_field)
                if isinstance(raw_location, str):
                    location_id = raw_location.strip()
        if location_id:
            record = by_id.get(location_id)
            if isinstance(record, EntityRecord):
                return location_id, str(record.kind or "").strip().lower()

    if not location_id:
        data_root = root / data_dir_name
        if data_root.exists():
            for candidate_path in sorted(data_root.rglob(f"{source_entity_id}.json"), key=lambda path: path.as_posix()):
                try:
                    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(payload, dict) or payload.get("id") != source_entity_id:
                    continue
                raw_location = payload.get(source_field)
                if isinstance(raw_location, str) and raw_location.strip():
                    location_id = raw_location.strip()
                    break

    if not location_id:
        return "", ""

    data_root = root / data_dir_name
    if data_root.exists():
        for candidate_path in sorted(data_root.rglob(f"{location_id}.json"), key=lambda path: path.as_posix()):
            try:
                payload = json.loads(candidate_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict) and payload.get("id") == location_id:
                kind = str(payload.get("kind") or "").strip().lower()
                return location_id, kind
    return location_id, ""


def _should_release_active_agent_lock(
    root: Path,
    data_dir_name: str,
    user_text: str,
    active_agent: str,
    *,
    narrator_agent_id: str = NARRATOR_AGENT,
) -> bool:
    """Decide whether the current active-agent lock should be cleared.

    Release conditions:
    1) The locked agent no longer exists or has invalid config.
    2) The locked agent is configured as one-shot (no persistent control).
    3) Sticky agent domain no longer matches player's current location kind.
    """
    _ = user_text  # reserved for future policy usage
    if not isinstance(active_agent, str) or not active_agent.strip():
        return True
    if active_agent == narrator_agent_id:
        return False
    active_agent_id = active_agent.strip()
    if _load_agent_data(root, active_agent_id) is None:
        return True
    if _get_agent_delegation_mode(root, active_agent_id) == "one-shot":
        return True

    domain_kinds = _get_agent_sticky_domain_kinds(root, active_agent_id)
    if not domain_kinds:
        return False
    location_id, location_kind = _read_player_location_state(root, data_dir_name)
    if not location_kind:
        return False
    should_release = location_kind not in domain_kinds
    if should_release:
        logger.info(
            "Active agent '%s' released: player location '%s' kind='%s' outside sticky_domain_kinds=%s",
            active_agent_id,
            location_id or "?",
            location_kind,
            sorted(domain_kinds),
        )
    return should_release


def _iter_configured_agent_ids(root: Path, narrator_agent_id: str) -> list[str]:
    agents_root = root / "agents"
    if not agents_root.exists():
        return []
    router_aliases = get_router_agent_aliases(narrator_agent_id)
    ids: list[str] = []
    for child in sorted(agents_root.iterdir()):
        if not child.is_dir():
            continue
        agent_json = child / "agent.json"
        if not agent_json.exists():
            continue
        agent_id = child.name.strip()
        if not agent_id or agent_id in router_aliases:
            continue
        ids.append(agent_id)
    return ids


def _select_router_target_agent(
    root: Path,
    data_dir_name: str,
    narrator_agent_id: str,
) -> str | None:
    """Pick a specialist agent for narrator routing without narrator LLM narration."""
    contract = load_runtime_contract(root)
    location_id, location_kind = _read_player_location_state(root, data_dir_name)
    agent_ids = _iter_configured_agent_ids(root, narrator_agent_id)
    if not agent_ids:
        return None

    # 1) Exact domain mapping from runtime contract wins.
    if location_kind:
        mapped_agent = contract.routing.domain_agent_map.get(location_kind)
        if mapped_agent in agent_ids:
            return mapped_agent

    # 2) Fallback agent if it is a configured specialist.
    fallback_agent = str(contract.routing.fallback_agent or "").strip()
    if fallback_agent and fallback_agent != narrator_agent_id and fallback_agent in agent_ids:
        return fallback_agent

    # 3) Stable compatibility fallback: first configured specialist.
    if location_id:
        logger.warning(
            "Router fell back to first configured specialist for location '%s' (kind='%s'); runtime contract lacks a match",
            location_id,
            location_kind or "?",
        )
    return agent_ids[0]


def _build_router_task_prompt(
    data_dir_name: str,
    player_request: str,
    *,
    previous_agent_id: str = "",
    previous_assistant_text: str = "",
) -> str:
    routing_guard = f"Do NOT edit `{data_dir_name}/meta/active-agent.json`; routing state is managed by the router."
    if not previous_agent_id:
        return (
            "Handle this player request within your domain. "
            "Update game state as needed and return player-facing narration. "
            f"{routing_guard}\n\n"
            f"Player request: {player_request}"
        )

    handoff_summary = previous_assistant_text.strip()
    handoff_section = (
        f"Previous specialist handoff summary:\n{handoff_summary}\n\n"
        if handoff_summary
        else ""
    )
    return (
        "Continue this same player turn after a router handoff. "
        "Another specialist already handled the domain transition and released control to narrator. "
        "Read current state, continue seamlessly from there, and avoid repeating the handoff narration verbatim. "
        f"{routing_guard}\n\n"
        f"Original player request: {player_request}\n"
        f"Previous specialist: {previous_agent_id}\n\n"
        f"{handoff_section}"
        "Return player-facing narration for what happens next in your domain."
    )


def _is_game_path(path_value: object, data_dir_name: str) -> bool:
    if not isinstance(path_value, str):
        return False
    normalized = path_value.replace("\\", "/").lstrip("./")
    return normalized == data_dir_name or normalized.startswith(f"{data_dir_name}/")


def _should_block_narrator_tool_call(
    *,
    agent_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    data_dir_name: str,
    enforce_guardrail: bool,
    narrator_agent_id: str = NARRATOR_AGENT,
) -> bool:
    if not enforce_guardrail or agent_id != narrator_agent_id:
        return False
    if tool_name == "resolve_action":
        return True
    if tool_name in {"write_file", "edit_file", "delete_file"}:
        return _is_game_path(tool_args.get("path"), data_dir_name)
    return False


# Authoring tools that write the world. Build mode IS the authoring mode —
# it already grants free file-write permissions (see the `mode == "build"`
# block in run_conversation), so it must also keep these TOOLS callable even
# when an agent.json `tools` allowlist (written for play-time routing, e.g.
# the `default` router narrator) would otherwise strip them. Without this,
# a build-mode scaffold agent can write files glob-wise but can't call
# write_file / import_sillytavern_card — breaking world/card-import skills.
_BUILD_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "delete_file",
        "import_sillytavern_card",
        "ensure_playable_scaffold",
        # M31: authoring a soul folder is worthless if the agent can't put
        # it in the world, so casting travels with the write tools.
        "cast_soul",
        # M31 B4: showing the author what just changed is part of authoring.
        "open_in_viewer",
        # 任务 B2: places are authored (and refined) as folders.
        "new_location",
        "update_location",
    }
)

# Tools every agent may use while PLAYING regardless of its agent.json
# allowlist: the story walks into places that do not exist yet, and the
# world must be able to grow under it (「大部分 agent 默认可以
# new 一个 location … 游玩过程中」).
_PLAY_WORLD_TOOLS: frozenset[str] = frozenset({"new_location", "update_location"})


def _filter_tool_schemas_by_agent_config(
    tool_schemas: list[dict[str, Any]],
    agent_data: dict[str, Any],
    *,
    mode: "ConversationMode | None" = None,
) -> list[dict[str, Any]]:
    """Apply agent.json `tools` allowlist to runtime tool schemas.

    When `tools` is absent or empty, keep current behavior for backwards
    compatibility. When present, only listed tools are exposed — except in
    build mode, where the authoring/write tools (`_BUILD_WRITE_TOOLS`) stay
    callable regardless of the allowlist, mirroring build mode's relaxed
    file-write permissions.
    """
    allowlist = _get_agent_tool_allowlist(agent_data)
    if allowlist is None:
        return tool_schemas
    if mode == "build":
        allowlist = allowlist | _BUILD_WRITE_TOOLS | {"read_spec"}
    elif mode == "play":
        allowlist = allowlist | _PLAY_WORLD_TOOLS
    return [schema for schema in tool_schemas if schema.get("name") in allowlist]


def _get_agent_tool_allowlist(agent_data: dict[str, Any]) -> set[str] | None:
    configured_tools = agent_data.get("tools")
    if not isinstance(configured_tools, list):
        return None
    allowlist = {str(name).strip() for name in configured_tools if isinstance(name, str) and str(name).strip()}
    if not allowlist or "*" in allowlist:
        return None
    return allowlist


def _dispatch_sub_agent(
    task_data: dict[str, Any],
    root: Path,
    mode: ConversationMode,
    max_turns: int,
    caller_agent_id: str | None = None,
    on_chunk: Callable[[str], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
    on_tool_use: Callable[[str, dict[str, Any]], None] | None = None,
    on_tool_result: Callable[[str, dict[str, Any], str], None] | None = None,
    on_ask_user: Callable[[str, list[str]], str | None] | None = None,
    current_depth: int = 0,
    max_depth: int = 2,
    cancel_event: threading.Event | None = None,
    on_message_persist: Callable[[Message], None] | None = None,
    parent_messages: list[Message] | None = None,
) -> str:
    """Dispatch a sub-agent for the task tool and return a JSON result string."""
    target_agent_id = str(task_data.get("agent_id", "")).strip()
    prompt = str(task_data.get("prompt", "")).strip()
    caller = str(caller_agent_id or "").strip()
    data_dir_name = get_data_dir_name(root)
    narrator_agent_id = get_narrator_agent_id(root)
    router_execution_mode = get_router_execution_mode(root)

    if not target_agent_id:
        return _json_dumps({"status": "error", "error": "Missing required field: agent_id"})
    if not prompt:
        return _json_dumps({"status": "error", "error": "Missing required field: prompt"})
    if caller and caller == target_agent_id:
        logger.debug("sub_agent dispatch blocked_self_delegate: caller=%s target=%s", caller, target_agent_id)
        return _json_dumps(
            {
                "status": "error",
                "error": f"Agent '{caller}' cannot delegate to itself via task()",
                "data": {"agent_id": caller, "target_agent_id": target_agent_id},
            }
        )

    # Sub-agent delegation policy:
    # - Router/narrator can delegate to any agent.
    # - In fast mode, non-router agents can only delegate back to narrator.
    # - In orchestrator mode, depth-1 specialists may delegate one layer deeper.
    if (
        caller
        and caller != narrator_agent_id
        and target_agent_id != narrator_agent_id
        and (
            router_execution_mode != "orchestrator"
            or current_depth >= max_depth - 1
        )
    ):
        logger.debug(
            "sub_agent dispatch blocked_non_router_delegate: caller=%s target=%s narrator=%s",
            caller,
            target_agent_id,
            narrator_agent_id,
        )
        return _json_dumps(
            {
                "status": "error",
                "error": (
                    f"Agent '{caller}' can only delegate to narrator '{narrator_agent_id}' via task()"
                ),
                "data": {
                    "agent_id": caller,
                    "target_agent_id": target_agent_id,
                    "narrator_agent_id": narrator_agent_id,
                    "policy": "subagent_task_only_to_narrator",
                },
            }
        )

    target_agent_data = _load_agent_data(root, target_agent_id) or {}
    target_allowlist = _get_agent_tool_allowlist(target_agent_data)
    delegation_mode = _get_agent_delegation_mode(root, target_agent_id)
    sticky_ask_user_enabled = delegation_mode == "sticky" and on_ask_user is not None
    if (
        sticky_ask_user_enabled
        and target_allowlist is not None
        and "ask_user" not in target_allowlist
    ):
        return _json_dumps(
            {
                "status": "error",
                "error": (
                    f"Agent '{target_agent_id}' is sticky but cannot call ask_user. "
                    "Add 'ask_user' to agent.json tools."
                ),
                "data": {
                    "agent_id": target_agent_id,
                    "delegation_mode": delegation_mode,
                    "required_tool": "ask_user",
                    "configured_tools": sorted(target_allowlist),
                },
            }
        )

    if "max_task_turns" in target_agent_data:
        logger.debug(
            "sub_agent dispatch: agent-level max_task_turns is ignored; using session/config max_turns=%d",
            max_turns,
        )
    effective_max_turns = max_turns

    logger.debug(
        "sub_agent dispatch start: caller=%s target=%s mode=%s depth=%d/%d max_turns=%d effective_max_turns=%d prompt=%s",
        caller or "?",
        target_agent_id or "?",
        mode,
        current_depth,
        max_depth,
        max_turns,
        effective_max_turns,
        _preview_for_log(prompt, 240),
    )
    # Persist active-agent transitions only for top-level build/play routing.
    # fast 模式退役:active-agent 转移不再持久化。
    track_active_agent_state = False

    def _release_active_agent_lock(outcome: str, *, force: bool = False) -> None:
        if not track_active_agent_state:
            return
        if delegation_mode == "sticky" and not force:
            return
        try:
            write_active_agent(
                root,
                narrator_agent_id,
                reason=f"dispatch exit: {outcome} from '{target_agent_id}'",
                exit_condition="",
                updated_by=narrator_agent_id,
            )
            logger.debug(
                "active-agent exit: target=%s outcome=%s force=%s -> %s",
                target_agent_id,
                outcome,
                force,
                narrator_agent_id,
            )
        except Exception:
            logger.debug("Failed to write active-agent exit state (non-fatal)", exc_info=True)

    try:
        if mode == "sandbox":
            # Sandbox: use agentic workflow with proposals, apply on success
            sub_result = run_agent_agentic(
                root=root,
                agent_id=target_agent_id,
                query=prompt,
                do_apply=True,
                max_turns=effective_max_turns,
                on_ask_user=on_ask_user,
                current_depth=current_depth + 1,
                max_depth=max_depth,
            )
            if not sub_result.success:
                _release_active_agent_lock("sandbox_error", force=True)
                logger.debug(
                    "sub_agent sandbox result: target=%s success=%s turns=%s error=%s",
                    target_agent_id,
                    sub_result.success,
                    sub_result.turns,
                    _preview_for_log(sub_result.error or "", 180),
                )
                return _json_dumps({
                    "status": "error",
                    "error": sub_result.error or f"Sub-agent '{target_agent_id}' failed",
                    "data": {
                        "run_id": sub_result.run_id,
                        "agent_id": target_agent_id,
                        "success": sub_result.success,
                        "turns": sub_result.turns,
                    },
                })
            logger.debug(
                "sub_agent sandbox result: target=%s success=%s turns=%s",
                target_agent_id,
                sub_result.success,
                sub_result.turns,
            )
            _release_active_agent_lock("sandbox_success")
            return _json_dumps({
                "status": "success",
                "data": {
                    "run_id": sub_result.run_id,
                    "agent_id": target_agent_id,
                    "success": sub_result.success,
                    "error": sub_result.error,
                    "turns": sub_result.turns,
                },
            })
        else:
            # Build/play: run as nested conversation — sub-agent can directly
            # read/write files just like Claude Code.
            context_pack = _build_task_context_pack(root, target_agent_id, prompt)
            context_pack_section = f"{context_pack}\n\n" if context_pack else ""
            language_hint = _build_sub_agent_language_hint(parent_messages)
            language_hint_section = f"{language_hint}\n" if language_hint else ""
            allow_subagent_ask_user = sticky_ask_user_enabled
            logger.debug(
                "sub_agent contract: target=%s delegation_mode=%s ask_user_enabled=%s context_pack=%s",
                target_agent_id,
                delegation_mode,
                allow_subagent_ask_user,
                bool(context_pack),
            )
            # Differentiate contract by delegation_mode:
            # - sticky agents may remain active across turns
            # - one-shot agents complete a single task and return
            common_rules = (
                "- Stay within your own domain defined in agent.json.\n"
                "- If the action crosses into another domain, stop at boundary handling and return a handoff suggestion.\n"
                "- Do NOT guess file paths from entity IDs.\n"
                "- If a path is uncertain, use find/list_entities/glob to confirm before read_file.\n"
                "- If read_file returns File not found, do not repeat path variants; move on with confirmed data.\n"
                "- Prefer canonical reads/edits over exploratory search.\n"
            )
            if delegation_mode == "sticky":
                ask_user_rule = (
                    "- For meaningful player choices, call ask_user and wait for the player's answer.\n"
                    if allow_subagent_ask_user
                    else "- ask_user callback is unavailable in this run; present explicit options in response text instead.\n"
                )
                wrapped_prompt = (
                    "Sub-agent execution contract (sticky mode):\n"
                    "- You are the active domain specialist. Handle the player's request interactively.\n"
                    "- You will remain active until the player leaves your domain.\n"
                    f"{ask_user_rule}"
                    "- Information-first rule: when the player asks to clarify details (e.g., '先问清楚', '任务细节', '具体怎么做'),\n"
                    "  you MUST provide concrete details first (objective, location, risks, completion criteria, rewards),\n"
                    "  then ask follow-up choices only after the details are presented.\n"
                    "- ask_user pacing rule: do NOT issue back-to-back ask_user calls without substantial new narrative/state info between them.\n"
                    "  Do not use ask_user to merely re-confirm or paraphrase the player's previous answer.\n"
                    "- Choice capture rule: when you present 2+ concrete player options, call ask_user to capture the choice instead of ending with a plain-text question.\n"
                    "- End-of-turn interaction rule: if you are staying in-domain (no handoff), end by calling ask_user with 2-4 concrete options.\n"
                    "  Do NOT end the turn with only a plain-text question.\n"
                    "- Hard completion rule (sticky): each turn MUST end with exactly one of:\n"
                    "  (A) ask_user(...) when you are still in your domain, OR\n"
                    "  (B) handoff_to_router(reason) when domain change is confirmed.\n"
                    "- If your draft reply ends with plain text choices but no ask_user/handoff tool call, it is INVALID.\n"
                    "  Stop and issue the required tool call instead.\n"
                    f"{common_rules}"
                    "- Exit authority: when the player explicitly leaves your domain, or your applied state update moves the player outside your domain,\n"
                    "  call handoff_to_router(reason) in this turn to release control back to narrator.\n"
                    "- Sticky handoff validity: do NOT call handoff_to_router just because you finished one reply.\n"
                    "  Handoff is valid only after domain change is confirmed (e.g., player location moved outside your domain this turn).\n"
                    "- After calling handoff_to_router, do NOT call ask_user again in this turn.\n"
                    f"- Keep tool usage compact and finish within about {effective_max_turns} turns.\n"
                    "- Target <= 4 tool calls total; only exceed when correctness strictly requires it.\n"
                    "- Keep narration concise and immersive, then offer 2-3 concrete next actions.\n\n"
                    f"{language_hint_section}"
                    f"{context_pack_section}"
                    f"{prompt}"
                )
            else:
                wrapped_prompt = (
                    "Sub-agent execution contract (one-shot mode):\n"
                    "- Complete this as a single delegated task response.\n"
                    "- Do NOT call ask_user; provide options in your final response text instead.\n"
                    f"{common_rules}"
                    f"- Keep tool usage compact and finish within about {effective_max_turns} turns.\n"
                    "- Target <= 4 tool calls total; only exceed when correctness strictly requires it.\n"
                    "- Keep final narration concise, then provide 2-3 actionable options.\n\n"
                    f"{language_hint_section}"
                    f"{context_pack_section}"
                    f"{prompt}"
                )
            sub_messages: list[Message] = [Message(role="user", content=wrapped_prompt)]
            nested_on_ask_user = on_ask_user if allow_subagent_ask_user else None
            nested_disabled_tools = None if allow_subagent_ask_user else {"ask_user"}

            # Forward nested callbacks with sub-agent tags so callers can
            # render real-time details under the correct speaker identity.
            def _forward_chunk(chunk: str) -> None:
                if on_chunk:
                    on_chunk(_tag_sub_agent_event(target_agent_id, chunk))

            def _forward_thinking(thinking: str) -> None:
                if on_thinking:
                    on_thinking(_tag_sub_agent_event(target_agent_id, thinking))

            def _forward_tool_use(tool_name: str, tool_args: dict[str, Any]) -> None:
                if on_tool_use:
                    on_tool_use(_tag_sub_agent_event(target_agent_id, tool_name), tool_args)

            def _forward_tool_result(tool_name: str, tool_args: dict[str, Any], result: str) -> None:
                if on_tool_result:
                    on_tool_result(_tag_sub_agent_event(target_agent_id, tool_name), tool_args, result)

            def _persist_nested_transcript(message: Message) -> None:
                """Persist resumable sub-agent transcript into the parent session.

                Only persist user-visible nested transcript elements:
                - assistant messages that carry tool calls (ask_user prompt/options live here)
                - tool results that resolve those calls

                Plain assistant narration is still persisted by the parent task/task-result
                flow after successful completion, which avoids duplicate restored replies.
                """
                if on_message_persist is None:
                    return
                if message.role == "assistant":
                    if not getattr(message, "tool_calls", None):
                        return
                    nested_message = Message(
                        role="assistant",
                        content=message.content,
                        tool_calls=message.tool_calls,
                        name=target_agent_id,
                    )
                    on_message_persist(nested_message)
                    return
                if message.role == "tool":
                    on_message_persist(message)

            sub_result = run_conversation_turn(
                root=root,
                agent_id=target_agent_id,
                messages=sub_messages,
                mode=mode,
                max_turns=effective_max_turns,
                on_chunk=_forward_chunk,
                on_thinking=_forward_thinking,
                on_tool_use=_forward_tool_use,
                on_tool_result=_forward_tool_result,
                on_ask_user=nested_on_ask_user,
                current_depth=current_depth + 1,
                max_depth=max_depth,
                cancel_event=cancel_event,
                on_message_persist=_persist_nested_transcript,
                disabled_tools=nested_disabled_tools,
            )
            if sub_result.cancelled:
                _release_active_agent_lock("cancelled")
                logger.debug(
                    "sub_agent nested result: target=%s cancelled turns=%s files=%d",
                    target_agent_id,
                    sub_result.turns_used,
                    len(sub_result.files_modified),
                )
                return _json_dumps({
                    "status": "cancelled",
                    "error": f"Sub-agent '{target_agent_id}' canceled by user",
                    "data": {
                        "run_id": sub_result.run_id,
                        "agent_id": target_agent_id,
                        "success": sub_result.success,
                        "turns_used": sub_result.turns_used,
                        "files_modified": sub_result.files_modified,
                        "usage": sub_result.usage,
                    },
                })
            if not sub_result.success:
                _release_active_agent_lock("error", force=True)
                logger.debug(
                    "sub_agent nested result: target=%s failed turns=%s error=%s",
                    target_agent_id,
                    sub_result.turns_used,
                    _preview_for_log(sub_result.error or "", 180),
                )
                return _json_dumps({
                    "status": "error",
                    "error": sub_result.error or f"Sub-agent '{target_agent_id}' failed",
                    "data": {
                        "run_id": sub_result.run_id,
                        "agent_id": target_agent_id,
                        "success": sub_result.success,
                        "turns_used": sub_result.turns_used,
                        "files_modified": sub_result.files_modified,
                        "usage": sub_result.usage,
                    },
                })
            assistant_text = sub_result.assistant_message or ""
            handoff_target = str(sub_result.handoff_to or "").strip().lower()
            if delegation_mode == "sticky":
                try:
                    domain_kinds = _get_agent_sticky_domain_kinds(root, target_agent_id)
                    location_id, location_kind = _read_player_location_state(root, data_dir_name)
                    if handoff_target and handoff_target == narrator_agent_id:
                        if domain_kinds and location_kind and location_kind in domain_kinds:
                            logger.warning(
                                "active-agent sticky handoff rejected: target=%s location=%s kind=%s domain_kinds=%s",
                                target_agent_id,
                                location_id or "?",
                                location_kind,
                                sorted(domain_kinds),
                            )
                            handoff_target = ""
                        else:
                            _release_active_agent_lock("sticky_handoff", force=True)
                            logger.info(
                                "active-agent sticky release by explicit handoff: target=%s handoff_to=%s",
                                target_agent_id,
                                narrator_agent_id,
                            )

                    # Respect explicit in-task handoff/release decisions made by
                    # the sticky agent itself (e.g., it switched active_agent to narrator).
                    current_active = get_active_agent_id(root)
                    if current_active == target_agent_id:
                        if domain_kinds and location_kind and location_kind not in domain_kinds:
                            _release_active_agent_lock("sticky_domain_exit", force=True)
                            logger.info(
                                "active-agent sticky auto-release: target=%s location=%s kind=%s domain_kinds=%s",
                                target_agent_id,
                                location_id or "?",
                                location_kind,
                                sorted(domain_kinds),
                            )
                        else:
                            write_active_agent(
                                root,
                                target_agent_id,
                                reason=f"sticky delegation: router keeps '{target_agent_id}' active",
                                exit_condition="router updates active-agent state before routing changes",
                                updated_by=narrator_agent_id,
                            )
                    else:
                        logger.debug(
                            "active-agent sticky release respected: target=%s current_active=%s",
                            target_agent_id,
                            current_active,
                        )
                except Exception:
                    logger.debug("Failed to update active-agent state (non-fatal)", exc_info=True)
            else:
                _release_active_agent_lock("success")
                logger.debug(
                    "sub_agent delegation one-shot: target=%s no active-agent lock persisted",
                    target_agent_id,
                )

            logger.debug(
                "sub_agent nested result: target=%s success turns=%s files=%d usage_keys=%s",
                target_agent_id,
                sub_result.turns_used,
                len(sub_result.files_modified),
                sorted(sub_result.usage.keys()) if isinstance(sub_result.usage, dict) else [],
            )
            return _json_dumps({
                "status": "success",
                "data": {
                    "run_id": sub_result.run_id,
                    "agent_id": target_agent_id,
                    "route_decision": sub_result.route_decision,
                    "active_agent": sub_result.active_agent,
                    "delegated_to": sub_result.delegated_to,
                    "success": sub_result.success,
                    "error": sub_result.error,
                    "turns_used": sub_result.turns_used,
                    "files_modified": sub_result.files_modified,
                    "assistant_text": assistant_text,
                    "delegation_mode": delegation_mode,
                    "handoff_to": handoff_target or None,
                    "usage": sub_result.usage,
                },
            })
    except Exception as e:
        _release_active_agent_lock("exception", force=True)
        logger.debug("sub_agent dispatch exception: target=%s error=%s", target_agent_id, _preview_for_log(e), exc_info=True)
        return _json_dumps({"status": "error", "error": f"Sub-agent '{target_agent_id}' failed: {e}"})


def _get_tool_schemas(
    mode: ConversationMode,
    loader: SkillLoader,
    root: Path | None = None,
    include_resolve_action: bool = True,
) -> list[dict[str, Any]]:
    schemas = get_skill_schemas(include_resolve_action=include_resolve_action, root=root, include_spec=mode == "build")  # read_spec: authoring only
    if mode in {"build", "play"}:
        schemas = [schema for schema in schemas if schema.get("name") != "submit_proposal"]
        if mode == "play":
            # M31 mental model: build *creates*, play only
            # *admits* — an already-authored character can be brought into a
            # running world, but nothing new is written here. So `cast_soul`
            # stays (it is the admitting act, and it writes the roster through
            # the deterministic projector, never by hand), while opening things
            # on the player's desktop mid-scene does not belong in a scene.
            schemas = [s for s in schemas if s.get("name") != "open_in_viewer"]
    else:
        # Sandbox mode must route state changes via submit_proposal.
        # Hiding direct-write tools avoids repeated, guaranteed-to-fail calls.
        schemas = [
            schema
            for schema in schemas
            if schema.get("name") not in _BUILD_WRITE_TOOLS
        ]
    schemas.append(TODO_TOOL_SCHEMA)
    schemas.append(HANDOFF_TO_ROUTER_TOOL_SCHEMA)
    schemas.append(_skill_tool_schema(loader))
    if root:
        schemas.append(_build_task_tool_schema(root))
    return schemas


def _estimate_tokens(messages: list[Message]) -> int:
    total_chars = 0
    for message in messages:
        if message.content:
            total_chars += len(message.content)
        if message.tool_calls:
            for tool_call in message.tool_calls:
                total_chars += len(tool_call.name) + len(json.dumps(tool_call.arguments, ensure_ascii=False))
    return total_chars // 4


def _normalize_tool_call(tool_call: Any, tool_schemas: list[dict[str, Any]]) -> None:
    """Fix malformed tool calls from non-Anthropic models served via compatible APIs.

    Some models (e.g. GLM) generate tool names like ``glob("**/*.json")`` instead
    of ``name="glob", input={"pattern": "**/*.json"}``.  This mutates the ToolCall
    in-place to extract the real name and merge positional arguments.
    """
    raw_name = tool_call.name
    # Fast path: name is clean
    if "(" not in raw_name:
        return

    # Try to match  name(args...)
    m = re.match(r'^(\w+)\((.*)?\)$', raw_name, re.DOTALL)
    if not m:
        return

    real_name = m.group(1)
    args_str = (m.group(2) or "").strip()

    # Look up the schema so we can map positional args to the first required param
    schema = None
    for s in tool_schemas:
        if s.get("name") == real_name:
            schema = s
            break

    merged_args = dict(tool_call.arguments) if tool_call.arguments else {}

    if args_str and schema:
        params = schema.get("parameters", {})
        required = params.get("required", [])
        first_param = required[0] if required else None
        if first_param and first_param not in merged_args:
            # Strip surrounding quotes from the value
            value = args_str.strip("'\"")
            merged_args[first_param] = value

    tool_call.name = real_name
    tool_call.arguments = merged_args
    logger.info("Normalized malformed tool call: %s → %s(%s)", raw_name, real_name, merged_args)


def _trim_broken_tail(messages: list[Message]) -> None:
    """Remove the trailing assistant + tool_result messages that may have caused an API error.

    When the Anthropic API returns a 400 Bad Request, it's often because the
    last assistant message contained a malformed tool_use block (e.g. the model
    hallucinated a tool name the API doesn't recognise in the message history).
    Trimming the broken exchange lets the loop retry cleanly.
    """
    # Walk backwards: remove trailing tool messages, then the assistant message
    while len(messages) > 1 and messages[-1].role == "tool":
        messages.pop()
    if len(messages) > 1 and messages[-1].role == "assistant":
        messages.pop()


def _truncate_messages_for_budget(messages: list[Message], max_context_chars: int) -> None:
    if max_context_chars <= 0 or len(messages) <= 3:
        return
    while len(messages) > 3 and (_estimate_tokens(messages) * 4) > max_context_chars:
        # Keep system at index 0 and trim earliest non-system entry.
        messages.pop(1)


def _handle_todo_tool(todo_manager: TodoManager, args: dict[str, Any]) -> str:
    # Accept both "todos" (Claude Code convention) and "items" (legacy)
    items = args.get("todos") or args.get("items")
    if not isinstance(items, list):
        return _json_dumps({"status": "error", "error": "TodoWrite requires a 'todos' array"})
    try:
        snapshot = todo_manager.update(items)
    except ValueError as exc:
        return _json_dumps({"status": "error", "error": str(exc)})
    return _json_dumps(
        {
            "status": "success",
            "data": {
                "items": snapshot,
                "rendered": todo_manager.render(),
            },
        }
    )


def _handle_skill_tool(loader: SkillLoader, args: dict[str, Any]) -> str:
    skill_name = str(args.get("skill", "")).strip()
    if not skill_name:
        return _json_dumps({"status": "error", "error": "Skill requires a non-empty skill name"})
    content = loader.get_content(skill_name)
    if content is None:
        return _json_dumps({"status": "error", "error": f"Skill not found: {skill_name}"})
    return _json_dumps({"status": "success", "data": {"skill": skill_name, "content": content}})


def _track_modified_files(tool_name: str, tool_result: str | None, files_modified: list[str]) -> None:
    if tool_name not in _BUILD_WRITE_TOOLS or not tool_result:
        return
    try:
        payload = json.loads(tool_result)
    except json.JSONDecodeError:
        return
    if payload.get("status") != "success":
        return
    data = payload.get("data", {})
    files = data.get("files")
    if isinstance(files, list):
        for path in files:
            if isinstance(path, str) and path and path not in files_modified:
                files_modified.append(path)
    path = data.get("path")
    if isinstance(path, str) and path and path not in files_modified:
        files_modified.append(path)


def _merge_usage(total: dict[str, Any], part: dict[str, Any] | None) -> None:
    if not part:
        return
    for key, value in part.items():
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value
        else:
            total[key] = value


def _finalize_turn(
    root: Path,
    run_id: str,
    branch: str,
    base_head_event: int,
    mode: ConversationMode,
    agent_id: str,
    assistant_chunks: list[str],
    files_modified: list[str],
    tool_calls_made: list[str],
    turns_used: int,
    todo_manager: TodoManager,
    usage: dict[str, Any],
    proposal: dict[str, Any] | None,
    handoff_to: str | None = None,
    route_decision: str | None = None,
    active_agent: str | None = None,
    delegated_to: str | None = None,
) -> ConversationTurnResult:
    assistant_message = "".join(chunk for chunk in assistant_chunks if chunk)
    if mode in {"build", "play"} and files_modified:
        manifest_path = get_manifest_path(root)
        manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
        current_head = manifest.branches[branch].head_event
        if current_head != base_head_event:
            # Mid-turn applies advance the head while the turn is still
            # running — e.g. a sub-agent's submit_proposal being applied
            # (the exact workflow the engine mandates for game/ changes).
            # This append is journal-only: every write already landed, so
            # there is nothing to roll back — failing the turn here only
            # mislabels finished work. Rebase onto the fresh head instead.
            logger.warning(
                "finalize: head moved %d -> %d during turn (mid-turn applies); "
                "rebasing the journal event",
                base_head_event,
                current_head,
            )

        new_event_id = current_head + 1
        event = GameEvent(
            id=new_event_id,
            type=mode,
            actor=agent_id,
            payload={
                "run_id": run_id,
                "files_modified": files_modified,
                "tool_calls": tool_calls_made,
            },
        )
        append_event(root, branch, event)
        manifest.branches[branch].head_event = new_event_id
        if manifest.branches[branch].max_event is None or manifest.branches[branch].max_event < new_event_id:
            manifest.branches[branch].max_event = new_event_id
        atomic_write_json(manifest_path, manifest.model_dump())

    return ConversationTurnResult(
        success=True,
        run_id=run_id,
        assistant_message=assistant_message,
        assistant_speaker=agent_id,
        route_decision=route_decision,
        active_agent=active_agent or agent_id,
        delegated_to=delegated_to,
        files_modified=files_modified,
        tool_calls_made=tool_calls_made,
        turns_used=turns_used,
        todo_snapshot=todo_manager.snapshot(),
        usage=usage,
        proposal=proposal,
        handoff_to=handoff_to,
    )
