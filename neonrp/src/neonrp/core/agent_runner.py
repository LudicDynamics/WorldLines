"""Agent run orchestration for NeonRP.

This module provides the core agent run logic, extracted from CLI commands
to enable reuse by TUI and other interfaces.

M6 additions:
- run_agent_agentic(): Multi-turn agentic loop with tool calling
- _execute_tool(): Execute a skill tool and return result
"""

import contextlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)
_UNSAFE_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

from neonrp.core.apply import ApplyResult, apply_proposal

from neonrp.core.config import load_config, resolve_provider
from neonrp.core.debug_sink import record_llm_call
from neonrp.core.diffing import render_diff, render_diff_summary
from neonrp.core.llm import LLMTurnResult, Message, ToolCall, get_adapter_from_config
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_data_dir_name, get_manifest_path, get_neonrp_dir, get_game_dir
from neonrp.core.proposal import Proposal, parse_proposal
from neonrp.core.retrieval import retrieve_context
from neonrp.core.rules import load_rules_profile
from neonrp.core.skills import SkillRegistry, get_skill_schemas, validate_tool_arguments
from neonrp.core.storage import atomic_write_json, atomic_write_text

# Maximum turns in agentic loop to prevent infinite loops
MAX_AGENTIC_TURNS = 20

# Wall-clock budget for one agentic run (seconds). 0 = unlimited (local
# TUI/CLI default). Hosted play sets NEONRP_TURN_DEADLINE_S so a deep
# sub-agent cascade (e.g. a SAN ruling chain) can never hold the
# player past the line: past the deadline the loop disables tools and
# asks for the final player-facing output NOW — graceful, not an error.
TURN_DEADLINE_S = float(os.environ.get("NEONRP_TURN_DEADLINE_S", "0") or 0)


def _json_dumps(payload: Any) -> str:
    """Serialize JSON payloads for tool results with UTF-8 characters preserved."""
    return json.dumps(payload, ensure_ascii=False)


# Functional sub-agents whose job (generating a named character's
# reaction/dialogue) is owned by that character's soul-agent under M20.
# In a soul playthrough these are removed from the task() enum so the
# world-agent cannot route a soul character's reaction around its soul.
_SOUL_CONFLICTING_SUBAGENTS: frozenset[str] = frozenset({"character-agent"})


def _build_task_tool_schema(root: Path) -> dict[str, Any]:
    """Build the task tool schema with dynamically discovered available agents.

    Shared between conversation mode and agentic mode so the LLM always knows
    which sub-agents it can delegate to.
    """
    agents_dir = root / "agents"
    agent_entries: list[str] = []
    agent_ids: list[str] = []
    if agents_dir.is_dir():
        for d in sorted(agents_dir.iterdir()):
            if d.is_dir() and (d / "agent.json").exists():
                agent_ids.append(d.name)
                try:
                    data = json.loads((d / "agent.json").read_text(encoding="utf-8"))
                    name = data.get("name", d.name)
                    desc = data.get("description", "")
                    entry = f"{d.name} ({name})" if name != d.name else d.name
                    if desc:
                        entry += f" — {desc}"
                    agent_entries.append(entry)
                except Exception:
                    agent_entries.append(d.name)

    # M20 #3 — soul-world tool-gating (deterministic, project-level).
    # In a soul playthrough, a named character's reaction MUST come from its
    # own soul-agent (run in parallel by the multi-agent turn), never from a
    # competing "NPC reaction" functional sub-agent. Telling an LLM
    # orchestrator "don't task that tool" is unreliable, so we remove the
    # competing agent ids from the task enum entirely: the model then
    # *cannot* route around the soul. Fail-open: any error ⇒ no filtering
    # (legacy behaviour unchanged for non-soul worlds).
    if agent_ids:
        try:
            from neonrp.core.playthrough import read_playthrough

            pt = read_playthrough(root)
            if pt is not None and getattr(pt, "souls", None):
                blocked = _SOUL_CONFLICTING_SUBAGENTS
                if any(a in blocked for a in agent_ids):
                    agent_ids = [a for a in agent_ids if a not in blocked]
                    agent_entries = [
                        e for e in agent_entries
                        if e.split(" ", 1)[0] not in blocked
                    ]
        except Exception:
            logger.debug(
                "soul-world task-gating skipped (fail-open)", exc_info=True
            )

    if agent_entries:
        listing = ", ".join(agent_entries)
        agents_help = f"Available agents: {listing}."
    else:
        agents_help = "No sub-agents configured yet."

    agent_id_schema: dict[str, Any] = {
        "type": "string",
        "minLength": 1,
        "description": f"ID of the agent to delegate to. {agents_help}",
    }
    if agent_ids:
        # Constrain the target to existing agent IDs so models don't invent names.
        agent_id_schema["enum"] = agent_ids

    return {
        "name": "task",
        "description": (
            "Delegate a task to another agent (sub-agent). "
            "The sub-agent runs independently with its own conversation loop and returns a result. "
            "IMPORTANT: Delegation persistence is controlled by target agent.json `delegation_mode`: "
            "`one-shot` handles one task and exits, while `sticky` may remain active until it releases control. "
            "Before task() routing, confirm current domain/active-agent state and let the router update it when changed. "
            "The sub-agent inherits project context but has its own tool permissions. "
            "Unless explicitly requested otherwise, keep the same output language as the user. "
            f"{agents_help}"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": agent_id_schema,
                "prompt": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Clear instructions for the sub-agent. Include all necessary context "
                        "— the sub-agent cannot see your conversation history."
                    ),
                },
                "resume_run_id": {
                    "type": "string",
                    "description": "Optional: run_id of a previous sub-agent run to resume instead of starting fresh",
                },
            },
            "required": ["agent_id", "prompt"],
        },
    }

# Budget thresholds
BUDGET_WARNING_THRESHOLD = 0.8  # Warn at 80%
BUDGET_TERMINATION_THRESHOLD = 1.0  # Terminate at 100%


def _estimate_tokens(messages: list["Message"]) -> int:
    """Estimate token count from messages using char/4 approximation.

    Args:
        messages: List of conversation messages

    Returns:
        Estimated token count
    """
    total_chars = 0
    for msg in messages:
        if msg.content:
            total_chars += len(msg.content)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                total_chars += len(tc.name) + len(json.dumps(tc.arguments, ensure_ascii=False))
    return total_chars // 4


def _build_default_system_prompt(
    agent_id: str, data_dir_name: str = "game", include_resolve_action: bool = True
) -> str:
    """Build a structured default system prompt for agents.

    Args:
        agent_id: The agent identifier

    Returns:
        A comprehensive system prompt with tools, rules, and format documentation
    """
    resolve_line = ""
    if include_resolve_action:
        resolve_line = (
            "5. **resolve_action(action, actor, ...)**: Compute mechanical outcomes for game actions "
            "(damage, heal, buy, sell, move). Use the returned computed values when building your ops.\n"
        )

    submit_index = "6" if include_resolve_action else "5"

    return f"""You are {agent_id}, an AI agent in the NeonRP role-playing game engine.

## Your Role
- Help the player by making changes to the game world
- Gather information using tools before making decisions
- Maintain consistency with existing game state

## Available Tools
1. **read_file(path)**: Read a file's content. Path is relative to project root (e.g., "{data_dir_name}/character/hero.json").
2. **find(query, kind?, tag?)**: Search for entities by ID, keyword, kind, or tag.
3. **list_entities(kind?, tag?)**: List all indexed entities with optional filters.
4. **read_context(query, limit?)**: Get relevant entities for a query.
{resolve_line}{submit_index}. **submit_proposal(...)**: Submit your final changes. Call this when ready.

## Entity Format
Entities are JSON files in {data_dir_name}/<kind>/<id>.json with required fields:
- id: Unique identifier (string)
- kind: Entity type (character, item, location)
- name: Display name (string)

Optional fields: tags (array), summary (string), and kind-specific fields like hp, gold, inventory.

## Rules
- Always read relevant files before modifying them
- Entity paths are relative to {data_dir_name}/ (e.g., "character/hero.json" not "{data_dir_name}/character/hero.json")
- Use upsert_text to create or update files
- Use delete to remove files
- Provide clear rationale for your changes

## Workflow
1. Use tools to gather information about the current game state
2. Analyze what changes are needed
3. Call submit_proposal with your ops array

Remember: You MUST call submit_proposal to complete your task."""


def _contains_unsafe_control_chars(text: str) -> bool:
    """Return True when text includes control characters unsafe for ask_user UI payload."""
    if not isinstance(text, str):
        return False
    return _UNSAFE_CONTROL_RE.search(text) is not None


@dataclass
class AgentRunResult:
    """Result of an agent run."""

    run_id: str
    success: bool
    agent_id: str = ""
    provider: str = ""
    proposal: Optional[Proposal] = None
    diff_content: str = ""
    summary: dict = field(default_factory=dict)
    apply_result: Optional[ApplyResult] = None
    error: Optional[str] = None
    logs_dir: Optional[Path] = None
    turns: int = 0  # M6: number of conversation turns


def _load_agent_json(agent_dir: Path) -> dict | None:
    """Load agent.json from agent directory."""
    agent_json_path = agent_dir / "agent.json"
    if not agent_json_path.exists():
        return None
    try:
        with open(agent_json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _build_user_prompt(
    run_id: str,
    agent_id: str,
    branch: str,
    base_head_event: int,
    query: str,
    context_items: list,
    data_dir_name: str = "game",
) -> str:
    """Build user prompt for LLM from query and context."""
    context_json = json.dumps(
        {"run_id": run_id, "agent_id": agent_id, "branch": branch, "base_head_event": base_head_event, "query": query},
        indent=2,
        ensure_ascii=False,
    )

    prompt_parts = [
        "Generate a proposal.json for the following request:\n",
        f"Context:\n```json\n{context_json}\n```\n",
        f"Query: {query}\n",
    ]

    if context_items:
        prompt_parts.append("\nRelevant entities:\n")
        for item in context_items[:10]:
            entity_summary = {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "name": item.get("data", {}).get("name"),
                "path": item.get("path"),
            }
            prompt_parts.append(f"- {json.dumps(entity_summary, ensure_ascii=False)}\n")

    prompt_parts.append("""
Response format: Return a valid proposal.json with this structure:
{
  "proposal_version": "0.1",
  "run_id": "<run_id from context>",
  "agent_id": "<agent_id from context>",
  "branch": "<branch from context>",
  "base_head_event": <base_head_event from context>,
  "query": "<query from context>",
  "rationale": "<explanation of changes>",
  "ops": [
    {"op": "upsert_text", "path": "<kind>/<id>.json", "content": "..."},
    {"op": "delete", "path": "<kind>/<id>.json"}
  ]
}

IMPORTANT: Paths in ops are relative to the game/ directory. Use "<kind>/<id>.json" format, NOT "game/<kind>/<id>.json".
""".replace("game/", f"{data_dir_name}/"))

    return "".join(prompt_parts)


def _execute_tool(
    skill_registry: SkillRegistry,
    tool_call: ToolCall,
    run_context: dict,
    *,
    include_resolve_action: bool = True,
    allowed_tool_names: set[str] | None = None,
) -> tuple[str, dict | None, dict | None, dict | None]:
    """Execute a tool call and return result.

    Args:
        skill_registry: SkillRegistry for executing skills
        tool_call: The tool call to execute
        run_context: Context dict with run_id, agent_id, branch, base_head_event

    Returns:
        Tuple of (result_content, proposal_data, ask_user_data, task_data)
        - proposal_data is set when submit_proposal is called
        - ask_user_data is set when ask_user is called (contains question and options)
        - task_data is set when task is called (contains agent_id, prompt, resume_run_id)
    """
    # task tool schema is built dynamically (not in SKILL_SCHEMAS) — validate inline.
    if tool_call.name == "task":
        target = tool_call.arguments.get("agent_id", "")
        prompt = tool_call.arguments.get("prompt", "")
        if not target:
            return _json_dumps({"status": "error", "error": "Invalid arguments: Missing required field: agent_id"}), None, None, None
        if not prompt:
            return _json_dumps({"status": "error", "error": "Invalid arguments: Missing required field: prompt"}), None, None, None
        resume_run_id = tool_call.arguments.get("resume_run_id")
        return None, None, None, {"agent_id": target, "prompt": prompt, "resume_run_id": resume_run_id}

    # ask_user validates inline to support both new and legacy schemas.
    if tool_call.name == "ask_user":
        # Handle ask_user - return sentinel for callback handling.
        # New schema: {questions: [{question, header, options: [{label, description}], multiSelect}]}
        # Legacy schema: {question: str, options: [str]}
        control_char_error = (
            "ask_user payload contains invalid control characters. "
            "Regenerate question/options with normal readable UTF-8 text."
        )
        questions_raw = tool_call.arguments.get("questions")
        if isinstance(questions_raw, list) and questions_raw:
            # New structured format
            questions = []
            for q in questions_raw:
                if not isinstance(q, dict):
                    continue
                question_text = str(q.get("question", "")).strip()
                if not question_text:
                    continue
                header = str(q.get("header", "")).strip()
                if _contains_unsafe_control_chars(question_text) or _contains_unsafe_control_chars(header):
                    return _json_dumps({"status": "error", "error": control_char_error}), None, None, None
                multi = bool(q.get("multiSelect", False))
                opts = []
                for opt in q.get("options") or []:
                    if isinstance(opt, dict):
                        label = str(opt.get("label", "")).strip()
                        desc = str(opt.get("description", "")).strip()
                        if _contains_unsafe_control_chars(label) or _contains_unsafe_control_chars(desc):
                            return _json_dumps({"status": "error", "error": control_char_error}), None, None, None
                        opts.append({
                            "label": label,
                            "description": desc,
                        })
                    elif isinstance(opt, str):
                        stripped = opt.strip()
                        if _contains_unsafe_control_chars(stripped):
                            return _json_dumps({"status": "error", "error": control_char_error}), None, None, None
                        opts.append({"label": stripped, "description": ""})
                questions.append({
                    "question": question_text,
                    "header": header,
                    "options": opts,
                    "multiSelect": multi,
                })
            if not questions:
                return _json_dumps({"status": "error", "error": "questions array is empty or invalid"}), None, None, None
            return None, None, {"questions": questions}, None
        else:
            # Legacy flat format fallback
            question = str(tool_call.arguments.get("question", "")).strip()
            options = tool_call.arguments.get("options", [])
            if not question:
                return _json_dumps({"status": "error", "error": "questions is required"}), None, None, None
            if _contains_unsafe_control_chars(question):
                return _json_dumps({"status": "error", "error": control_char_error}), None, None, None
            opts = []
            for o in options:
                if not isinstance(o, str):
                    continue
                label = str(o).strip()
                if _contains_unsafe_control_chars(label):
                    return _json_dumps({"status": "error", "error": control_char_error}), None, None, None
                opts.append({"label": label, "description": ""})
            return None, None, {"questions": [{"question": question, "header": "", "options": opts, "multiSelect": False}]}, None

    # Validate arguments against static SKILL_SCHEMAS
    is_valid, error_msg = validate_tool_arguments(
        tool_call.name,
        tool_call.arguments,
        include_resolve_action=include_resolve_action,
        allowed_tool_names=allowed_tool_names,
        root=skill_registry.root,
    )
    if not is_valid:
        logger.warning(
            "Tool call validation failed: tool=%s error=%s arguments=%r",
            tool_call.name,
            error_msg,
            tool_call.arguments,
        )
        return _json_dumps({"status": "error", "error": f"Invalid arguments: {error_msg}"}), None, None, None

    if tool_call.name == "submit_proposal":
        # Handle submit_proposal - this ends the loop
        proposal_data = tool_call.arguments
        return _json_dumps({"status": "proposal_submitted"}), proposal_data, None, None

    # Execute skill via registry
    result = skill_registry.invoke(tool_call.name, tool_call.arguments)

    if result.success:
        return _json_dumps({"status": "success", "data": result.data}), None, None, None
    else:
        return _json_dumps({"status": "error", "error": result.error}), None, None, None


def run_agent(
    root: Path,
    agent_id: str,
    query: str,
    provider: str | None = None,
    fixture_path: str | None = None,
    do_apply: bool = False,
) -> AgentRunResult:
    """Run an agent with LLM to generate and optionally apply a proposal.

    This is the core orchestration function for agent runs. It:
    1. Loads agent spec and system prompt
    2. Retrieves relevant context entities
    3. Calls LLM to generate a proposal
    4. Renders diff preview
    5. Optionally applies the proposal (with do_apply=True)

    All logs are saved to .neonrp/logs/agents/<run_id>/

    Args:
        root: Project root directory
        agent_id: ID of the agent to run
        query: User query/instruction for the agent
        provider: LLM provider override (default: from config or 'stub')
        fixture_path: Path to proposal fixture file for stub provider
        do_apply: If True, apply the proposal after generation

    Returns:
        AgentRunResult with success status and details
    """
    agents_dir = root / "agents"
    agent_dir = agents_dir / agent_id

    # Generate run_id
    run_id = f"{agent_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    if not agent_dir.exists():
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            error=f"Agent '{agent_id}' not found",
        )

    # Load agent spec
    agent_data = _load_agent_json(agent_dir)
    if not agent_data:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            error=f"Cannot read agent.json for '{agent_id}'",
        )

    # Load system prompt (support both relative to agent_dir and full path from root)
    system_prompt_raw = agent_data.get("system_prompt", "system.md")
    # Try as relative to agent dir first
    system_prompt_path = agent_dir / system_prompt_raw
    if not system_prompt_path.exists():
        # Try as path from project root
        system_prompt_path = root / system_prompt_raw
    if system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = f"You are agent '{agent_id}'. Follow instructions and generate valid proposals."

    # Load config and resolve provider (M8-T5: per-agent LLM)
    config = load_config(root)
    agent_llm_config = agent_data.get("llm")  # Optional per-agent LLM config
    provider_config = resolve_provider(config, agent_llm_config, provider)
    provider_name = provider_config.provider

    # Load manifest for context
    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error="NeonRP project not initialized",
        )

    try:
        manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
    except Exception as e:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error=f"Failed to load manifest: {e}",
        )

    branch = manifest.current_branch
    base_head_event = (
        manifest.branches.get(branch, {}).head_event
        if hasattr(manifest.branches.get(branch), "head_event")
        else manifest.branches.get(branch, {}).get("head_event", 0)
    )

    # Retrieve context (check both root level and defaults.context_limit for compatibility)
    context_limit = agent_data.get("context_limit") or agent_data.get("defaults", {}).get("context_limit", 20)
    try:
        context_items = retrieve_context(root, query, max_results=context_limit)
    except Exception:
        context_items = []

    # Build user prompt
    user_prompt = _build_user_prompt(
        run_id, agent_id, branch, base_head_event, query, context_items, get_data_dir_name(root)
    )

    # Get LLM adapter using resolved provider config (M8-T5)
    try:
        adapter_kwargs = {}
        if provider_name == "stub" and fixture_path:
            adapter_kwargs["fixture_path"] = fixture_path
        adapter = get_adapter_from_config(provider_config, **adapter_kwargs)
    except Exception as e:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error=f"Failed to initialize LLM adapter: {e}",
        )

    # Create logs directory
    logs_dir = get_neonrp_dir(root) / "logs" / "agents" / run_id
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Save input for debugging
    input_log = {
        "run_id": run_id,
        "agent_id": agent_id,
        "provider": provider_name,
        "query": query,
        "system_prompt": system_prompt[:500] + "..." if len(system_prompt) > 500 else system_prompt,
        "context_count": len(context_items),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write_json(logs_dir / "input.json", input_log)

    # Call LLM
    tool_schemas = get_skill_schemas(include_resolve_action=config.rules.enable_resolve_action, root=root)
    response = adapter.generate(system_prompt, user_prompt, tools=tool_schemas)

    # Save raw output
    atomic_write_text(logs_dir / "llm_raw.txt", response.raw_output)

    if not response.success:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error=f"LLM call failed: {response.error}",
            logs_dir=logs_dir,
        )

    # Parse proposal
    try:
        proposal_data = json.loads(response.proposal_text)
        proposal = parse_proposal(proposal_data)
    except Exception as e:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error=f"Failed to parse proposal: {e}",
            logs_dir=logs_dir,
        )

    # Save proposal
    atomic_write_json(logs_dir / "proposal.json", proposal_data)

    # Generate diff
    game_root = get_game_dir(root)
    diff_content = render_diff(proposal, game_root)
    summary = render_diff_summary(proposal, game_root)

    # Save diff
    atomic_write_text(logs_dir / "diff.patch", diff_content if diff_content else "(no changes)")

    # Run dry-run validation and save result
    permissions = agent_data.get("permissions", {})
    dry_run_result = apply_proposal(root, proposal, permissions, dry_run=True)
    validation_log = {
        "success": dry_run_result.success,
        "validation_errors": dry_run_result.validation_errors,
        "error": dry_run_result.error,
    }
    atomic_write_json(logs_dir / "validation.json", validation_log)
    atomic_write_json(
        logs_dir / "apply.json",
        {
            "success": None,
            "applied_paths": [],
            "event_id": None,
            "error": "Not applied (--apply not set)",
        },
    )

    # Build result
    result = AgentRunResult(
        run_id=run_id,
        success=True,
        agent_id=agent_id,
        provider=provider_name,
        proposal=proposal,
        diff_content=diff_content or "",
        summary=summary,
        logs_dir=logs_dir,
    )

    # Apply if requested
    if do_apply:
        apply_result = apply_proposal(root, proposal, permissions, dry_run=False)
        result.apply_result = apply_result

        # Save apply result to logs
        apply_log = {
            "success": apply_result.success,
            "applied_paths": apply_result.applied_paths,
            "event_id": apply_result.event_id,
            "error": apply_result.error,
        }
        atomic_write_json(logs_dir / "apply.json", apply_log)

        if not apply_result.success:
            result.success = False
            result.error = f"Apply failed: {apply_result.error}"

    return result


def run_agent_agentic(
    root: Path,
    agent_id: str,
    query: str,
    provider: str | None = None,
    fixture_path: str | None = None,
    do_apply: bool = False,
    max_turns: int = MAX_AGENTIC_TURNS,
    on_chunk: Callable[[str], None] | None = None,
    on_ask_user: Callable[[str, list[str]], str] | None = None,
    current_depth: int = 0,
    max_depth: int | None = None,  # None = read from config
    parent_run_id: str | None = None,
) -> AgentRunResult:
    """Run an agent with agentic multi-turn loop (M6).

    This function uses the chat() method for multi-turn conversations with
    tool calling. The agent can use skills (read_file, find, etc.) and
    returns a proposal via submit_proposal tool.

    M7-T8: When on_chunk is provided, uses chat_stream() for incremental token
    rendering. Each chunk's delta is passed to the callback.

    M8-T3: When agent calls ask_user, the loop pauses and calls on_ask_user
    to get the user's response, which is injected as the tool result.

    M8-T4: Depth control for sub-agent orchestration. Sub-agents (depth >= 1)
    cannot call the task tool to prevent infinite nesting.

    Args:
        root: Project root directory
        agent_id: ID of the agent to run
        query: User query/instruction for the agent
        provider: LLM provider override
        fixture_path: Path to proposal fixture for stub provider
        do_apply: If True, apply the proposal after generation
        max_turns: Maximum conversation turns to prevent infinite loops
        on_chunk: Optional callback for streaming chunks (M7-T8)
        on_ask_user: Optional callback for ask_user skill (M8-T3)
        current_depth: Current nesting depth (0 = parent, 1 = sub-agent)
        max_depth: Maximum allowed depth (default 2 = parent + 1 sub-agent)
        parent_run_id: Parent run ID if this is a sub-agent

    Returns:
        AgentRunResult with success status and details
    """
    agents_dir = root / "agents"
    agent_dir = agents_dir / agent_id

    # Generate run_id
    run_id = f"{agent_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    if not agent_dir.exists():
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            error=f"Agent '{agent_id}' not found",
        )

    # Load agent spec
    agent_data = _load_agent_json(agent_dir)
    if not agent_data:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            error=f"Cannot read agent.json for '{agent_id}'",
        )

    # Load config and resolve provider (M8-T5: per-agent LLM)
    config = load_config(root)

    # Load system prompt
    system_prompt_raw = agent_data.get("system_prompt", "system.md")
    system_prompt_path = agent_dir / system_prompt_raw
    if not system_prompt_path.exists():
        system_prompt_path = root / system_prompt_raw
    if system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = _build_default_system_prompt(
            agent_id,
            get_data_dir_name(root),
            include_resolve_action=config.rules.enable_resolve_action,
        )

    agent_llm_config = agent_data.get("llm")  # Optional per-agent LLM config
    provider_config = resolve_provider(config, agent_llm_config, provider)

    # Resolve max_depth from config if not explicitly provided (M8 fix)
    if max_depth is None:
        max_depth = config.max_sub_agent_depth
    provider_name = provider_config.provider

    # Load manifest
    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error="NeonRP project not initialized",
        )

    try:
        manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
    except Exception as e:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error=f"Failed to load manifest: {e}",
        )

    branch = manifest.current_branch
    base_head_event = (
        manifest.branches.get(branch, {}).head_event
        if hasattr(manifest.branches.get(branch), "head_event")
        else manifest.branches.get(branch, {}).get("head_event", 0)
    )

    # Create logs directory
    logs_dir = get_neonrp_dir(root) / "logs" / "agents" / run_id
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Get LLM adapter using resolved provider config (M8-T5)
    try:
        adapter_kwargs = {}
        if provider_name == "stub" and fixture_path:
            adapter_kwargs["fixture_path"] = fixture_path
        adapter = get_adapter_from_config(provider_config, **adapter_kwargs)
    except Exception as e:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error=f"Failed to initialize LLM adapter: {e}",
        )

    # Create skill registry
    permissions = agent_data.get("permissions", {})
    read_globs = permissions.get("read_globs", ["**"])
    deny_globs = permissions.get("deny_globs", [])
    direct_write_globs = permissions.get("direct_write_globs", [])
    rules_profile = load_rules_profile(root, config.rules.profile_path)
    skill_registry = SkillRegistry(
        root,
        run_id,
        agent_id,
        read_globs,
        deny_globs,
        direct_write_globs,
        enable_resolve_action=config.rules.enable_resolve_action,
        rules_profile=rules_profile,
    )

    # Prepare tool schemas
    tool_schemas = get_skill_schemas(include_resolve_action=config.rules.enable_resolve_action, root=root)
    # Add task tool schema (dynamically lists available agents)
    tool_schemas.append(_build_task_tool_schema(root))
    # M8-T4: Filter out 'task' tool for sub-agents (depth >= max_depth - 1)
    if current_depth >= max_depth - 1:
        tool_schemas = [s for s in tool_schemas if s.get("name") != "task"]
    allowed_tool_names = {schema.get("name", "") for schema in tool_schemas if schema.get("name")}

    # Build initial context
    context_limit = agent_data.get("context_limit") or agent_data.get("defaults", {}).get("context_limit", 20)
    try:
        context_items = retrieve_context(root, query, max_results=context_limit)
    except Exception:
        context_items = []

    # Build initial messages
    run_context = {
        "run_id": run_id,
        "agent_id": agent_id,
        "branch": branch,
        "base_head_event": base_head_event,
        "query": query,
    }

    context_summary = json.dumps(run_context, indent=2, ensure_ascii=False)
    entity_summary = "\n".join([f"- {item.get('id')}: {item.get('kind')}" for item in context_items[:10]])

    user_content = f"""Context:
```json
{context_summary}
```

Query: {query}

Available entities:
{entity_summary if entity_summary else "(no entities indexed yet)"}

Use the available tools to gather information, then call submit_proposal with your changes."""

    messages: list[Message] = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_content),
    ]

    # Save input log
    input_log = {
        "run_id": run_id,
        "agent_id": agent_id,
        "provider": provider_name,
        "query": query,
        "mode": "agentic",
        "context_count": len(context_items),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write_json(logs_dir / "input.json", input_log)

    # Get budget config
    max_context_chars = config.llm.max_context_chars
    budget_warned = False

    # Agentic loop
    proposal_data: dict | None = None
    turn = 0
    conversation_log: list[dict] = []
    loop_started = time.monotonic()
    deadline_hit = False
    active_tools = tool_schemas

    while turn < max_turns:
        turn += 1

        # Wall-clock deadline (NEONRP_TURN_DEADLINE_S, hosted play): past
        # the line, stop the tool cascade — disable tools and ask for the
        # final player-facing output in THIS completion. The model answers
        # with prose, the loop exits normally. No hang, no error.
        from neonrp.core import beat_budget as _bb

        _left = _bb.remaining()  # the beat's budget (core/beat_budget, 10-14): the last stretch is for the final answer
        if (
            not deadline_hit
            and (
                (TURN_DEADLINE_S > 0 and time.monotonic() - loop_started >= TURN_DEADLINE_S)
                or (_left is not None and turn > 1 and _left < _bb.settle_s())
            )
        ):
            if _left is not None and _left < _bb.settle_s():
                _bb.note("agent_runner", rounds=turn)
            deadline_hit = True
            active_tools = None
            messages.append(Message(
                role="user",
                content=(
                    "[SYSTEM: time budget for this turn is reached. Produce "
                    "your final player-facing output NOW in this reply, from "
                    "what you already know. Do not call any more tools; keep "
                    "any remaining ruling simple and conservative.]"
                ),
            ))

        # Check token budget before calling LLM
        estimated_tokens = _estimate_tokens(messages)
        current_chars = estimated_tokens * 4  # Convert back to chars for comparison
        budget_ratio = current_chars / max_context_chars if max_context_chars > 0 else 0

        # Terminate at 100% budget
        if budget_ratio >= BUDGET_TERMINATION_THRESHOLD:
            atomic_write_json(logs_dir / "conversation.json", conversation_log)
            return AgentRunResult(
                run_id=run_id,
                success=False,
                agent_id=agent_id,
                provider=provider_name,
                error=f"Token budget exhausted ({int(budget_ratio * 100)}% of {max_context_chars} chars). Reduce context or simplify query.",
                logs_dir=logs_dir,
                turns=turn,
            )

        # Inject warning at 80% budget (only once)
        if budget_ratio >= BUDGET_WARNING_THRESHOLD and not budget_warned:
            budget_warned = True
            warning_msg = f"[SYSTEM WARNING: Context is at {int(budget_ratio * 100)}% of budget. Please submit your proposal soon to avoid termination.]"
            messages.append(Message(role="user", content=warning_msg))

        # Call LLM - use streaming if on_chunk callback provided (M7-T8)
        _llm_t0 = time.perf_counter()
        if on_chunk:
            # Streaming mode: accumulate content and tool calls
            accumulated_content = ""
            result_tool_calls: list[Any] = []
            result_error: str | None = None
            result_finished = False
            result_usage: dict[str, Any] = {}

            try:
                with contextlib.closing(adapter.chat_stream(messages, tools=active_tools)) as gen:  # closed here, not by the GC (10-11)
                    for chunk in gen:
                        if chunk.delta:
                            accumulated_content += chunk.delta
                            on_chunk(chunk.delta)
                        if chunk.tool_call_starts:
                            names = ", ".join(chunk.tool_call_starts)
                            on_chunk(f"\n[calling {names}...]\n")
                        if chunk.tool_calls:
                            result_tool_calls = chunk.tool_calls
                        if chunk.finished:
                            result_finished = True
                        if chunk.usage:
                            result_usage = chunk.usage
                        if chunk.error:
                            result_error = chunk.error
                            break

                # Build result from accumulated data
                result = LLMTurnResult(
                    message=Message(
                        role="assistant", content=accumulated_content or None, tool_calls=result_tool_calls or None
                    ),
                    tool_calls=result_tool_calls or None,
                    finished=result_finished or not result_tool_calls,
                    usage=result_usage,
                    error=result_error,
                )
            except Exception as e:
                result = LLMTurnResult(error=str(e))
        else:
            # Non-streaming fallback
            result = adapter.chat(messages, tools=active_tools)

        _llm_dur_ms = (time.perf_counter() - _llm_t0) * 1000.0
        # Debug sink — no-op unless NEONRP_DEBUG=1. Exposes the call's
        # tokens, cache hits, thinking text, and tools to the TUI debug panel.
        try:
            _u = result.usage or {}
            _out_tok = int(_u.get("completion_tokens") or 0)
            _tps = (_out_tok / (_llm_dur_ms / 1000.0)) if _llm_dur_ms > 0 else 0.0
            record_llm_call(
                {
                    "agent_id": agent_id,
                    "provider": provider_name,
                    "turn": turn,
                    "duration_ms": round(_llm_dur_ms, 1),
                    "tokens_per_sec": round(_tps, 1),
                    "prompt_tokens": int(_u.get("prompt_tokens") or 0),
                    "completion_tokens": _out_tok,
                    "cache_creation_tokens": int(_u.get("cache_creation_tokens") or 0),
                    "cache_read_tokens": int(_u.get("cache_read_tokens") or 0),
                    "model": str(_u.get("model") or ""),
                    "thinking": str(_u.get("thinking") or ""),
                    "tool_calls": [
                        {"name": tc.name, "arguments": tc.arguments}
                        for tc in (result.tool_calls or [])
                    ],
                    "text_preview": (
                        (result.message.content or "")[:200]
                        if result.message and result.message.content
                        else ""
                    ),
                    "error": result.error or "",
                }
            )
        except Exception:  # noqa: BLE001 — telemetry must never break a turn
            logger.debug("debug_sink record failed", exc_info=True)

        # Log the turn with budget info
        turn_log = {
            "turn": turn,
            "success": result.success,
            "tool_calls": [{"id": tc.id, "name": tc.name} for tc in (result.tool_calls or [])],
            "finished": result.finished,
            "error": result.error,
            "budget_ratio": round(budget_ratio, 2),
            "budget_warned": budget_warned,
        }
        conversation_log.append(turn_log)

        if not result.success:
            # Save conversation log
            atomic_write_json(logs_dir / "conversation.json", conversation_log)
            return AgentRunResult(
                run_id=run_id,
                success=False,
                agent_id=agent_id,
                provider=provider_name,
                error=f"LLM call failed on turn {turn}: {result.error}",
                logs_dir=logs_dir,
                turns=turn,
            )

        # Add assistant message to history
        if result.message:
            messages.append(result.message)

        # Check if finished (no tool calls)
        if result.finished or not result.tool_calls:
            break

        # Process tool calls
        for tool_call in result.tool_calls:
            tool_result, submitted_proposal, ask_user_data, task_data = _execute_tool(
                skill_registry,
                tool_call,
                run_context,
                include_resolve_action=config.rules.enable_resolve_action,
                allowed_tool_names=allowed_tool_names,
            )

            if submitted_proposal:
                proposal_data = submitted_proposal

            # Handle ask_user sentinel
            if ask_user_data:
                if on_ask_user:
                    answers: dict[str, str] = {}
                    for idx, q in enumerate(ask_user_data.get("questions", [])):
                        labels = [o["label"] for o in q.get("options", []) if isinstance(o, dict)]
                        user_response = on_ask_user(q["question"], labels)
                        answers[str(idx)] = str(user_response or "")
                    tool_result = _json_dumps({"answers": answers})
                else:
                    tool_result = _json_dumps(
                        {"status": "error", "error": "ask_user not available (no callback provided)"}
                    )

            # Handle task sentinel (M8-T4)
            if task_data:
                target_agent_id = task_data["agent_id"]
                prompt = task_data["prompt"]
                # Check if we can delegate (depth limit)
                if current_depth >= max_depth - 1:
                    tool_result = _json_dumps(
                        {"status": "error", "error": "Cannot delegate: maximum sub-agent depth reached"}
                    )
                else:
                    # Execute sub-agent
                    try:
                        sub_result = run_agent_agentic(
                            root=root,
                            agent_id=target_agent_id,
                            query=prompt,
                            provider=provider,
                            fixture_path=fixture_path,
                            do_apply=False,  # Sub-agents don't auto-apply
                            max_turns=max_turns,
                            on_chunk=None,  # Sub-agents don't stream to parent
                            on_ask_user=on_ask_user,  # Pass through ask_user
                            current_depth=current_depth + 1,
                            max_depth=max_depth,
                            parent_run_id=run_id,
                        )
                        # Serialize sub-agent result
                        tool_result = _json_dumps(
                            {
                                "status": "success",
                                "data": {
                                    "run_id": sub_result.run_id,
                                    "agent_id": target_agent_id,
                                    "success": sub_result.success,
                                    "error": sub_result.error,
                                    "turns": sub_result.turns,
                                    "proposal_submitted": sub_result.proposal is not None,
                                },
                            }
                        )
                    except Exception as e:
                        tool_result = _json_dumps({"status": "error", "error": f"Sub-agent failed: {e}"})

            # Add tool result to messages
            messages.append(
                Message(
                    role="tool",
                    content=tool_result,
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                )
            )

        # If we got a proposal, we're done
        if proposal_data:
            break

    # Save conversation log
    atomic_write_json(logs_dir / "conversation.json", conversation_log)

    # Save skill audit log
    skill_registry.save_audit_log()

    # Handle no proposal submitted
    if not proposal_data:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error=f"Agent did not submit a proposal after {turn} turns",
            logs_dir=logs_dir,
            turns=turn,
        )

    # Parse and validate proposal
    try:
        proposal = parse_proposal(proposal_data)
    except Exception as e:
        return AgentRunResult(
            run_id=run_id,
            success=False,
            agent_id=agent_id,
            provider=provider_name,
            error=f"Failed to parse submitted proposal: {e}",
            logs_dir=logs_dir,
            turns=turn,
        )

    # Save proposal
    atomic_write_json(logs_dir / "proposal.json", proposal_data)

    # Generate diff
    game_root = get_game_dir(root)
    diff_content = render_diff(proposal, game_root)
    summary = render_diff_summary(proposal, game_root)

    # Save diff
    atomic_write_text(logs_dir / "diff.patch", diff_content if diff_content else "(no changes)")

    # Validation
    dry_run_result = apply_proposal(root, proposal, permissions, dry_run=True)
    validation_log = {
        "success": dry_run_result.success,
        "validation_errors": dry_run_result.validation_errors,
        "error": dry_run_result.error,
    }
    atomic_write_json(logs_dir / "validation.json", validation_log)
    atomic_write_json(
        logs_dir / "apply.json",
        {
            "success": None,
            "applied_paths": [],
            "event_id": None,
            "error": "Not applied (--apply not set)",
        },
    )

    # Build result
    result_obj = AgentRunResult(
        run_id=run_id,
        success=True,
        agent_id=agent_id,
        provider=provider_name,
        proposal=proposal,
        diff_content=diff_content or "",
        summary=summary,
        logs_dir=logs_dir,
        turns=turn,
    )

    # Apply if requested
    if do_apply:
        apply_result = apply_proposal(root, proposal, permissions, dry_run=False)
        result_obj.apply_result = apply_result

        apply_log = {
            "success": apply_result.success,
            "applied_paths": apply_result.applied_paths,
            "event_id": apply_result.event_id,
            "error": apply_result.error,
        }
        atomic_write_json(logs_dir / "apply.json", apply_log)

        if not apply_result.success:
            result_obj.success = False
            result_obj.error = f"Apply failed: {apply_result.error}"

    return result_obj

