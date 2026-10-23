"""Agent dispatcher for NeonRP.

This module provides routing logic to select and run agents based on:
- Explicit agent ID (direct call)
- Trigger patterns (regex matching against query)
- Tags (semantic matching)
- Priority (when multiple agents match)

M6-T3: Dispatcher + neonrp run upgrade
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from neonrp.core.agent_runner import AgentRunResult, run_agent, run_agent_agentic


@dataclass
class AgentSpec:
    """Agent specification loaded from agent.json."""

    id: str
    name: str = ""
    description: str = ""
    version: str = "0.1"
    priority: int = 0  # Higher priority = more likely to be selected
    tags: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)  # Regex patterns
    system_prompt: str = "system.md"
    context_limit: int = 20
    permissions: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict) -> "AgentSpec":
        """Create AgentSpec from JSON data."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", data.get("id", "")),
            description=data.get("description", ""),
            version=data.get("version", "0.1"),
            priority=data.get("priority", 0),
            tags=data.get("tags", []),
            triggers=data.get("triggers", []),
            system_prompt=data.get("system_prompt", "system.md"),
            context_limit=data.get("context_limit", 20),
            permissions=data.get("permissions", {}),
        )


@dataclass
class DispatchResult:
    """Result of agent dispatch."""

    success: bool
    agent_id: Optional[str] = None
    run_result: Optional[AgentRunResult] = None
    matched_trigger: Optional[str] = None
    matched_tags: list[str] = field(default_factory=list)
    error: Optional[str] = None
    candidates: list[str] = field(default_factory=list)  # All matching agents


def load_agent_specs(root: Path) -> dict[str, AgentSpec]:
    """Load all agent specifications from agents directory.

    Args:
        root: Project root directory

    Returns:
        Dict mapping agent ID to AgentSpec
    """
    agents_dir = root / "agents"
    if not agents_dir.exists():
        return {}

    specs = {}
    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue

        agent_json = agent_dir / "agent.json"
        if not agent_json.exists():
            continue

        try:
            with open(agent_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            spec = AgentSpec.from_json(data)
            if spec.id:
                specs[spec.id] = spec
        except (json.JSONDecodeError, IOError):
            continue

    return specs


def match_triggers(query: str, triggers: list[str]) -> Optional[str]:
    """Check if query matches any trigger patterns.

    Args:
        query: User query text
        triggers: List of regex patterns

    Returns:
        First matching trigger pattern, or None
    """
    for trigger in triggers:
        try:
            if re.search(trigger, query, re.IGNORECASE):
                return trigger
        except re.error:
            continue  # Invalid regex, skip
    return None


def match_tags(query: str, tags: list[str]) -> list[str]:
    """Check if query mentions any tags (case-insensitive).

    Simple keyword matching for now. Could be enhanced with
    semantic similarity in the future.

    Args:
        query: User query text
        tags: List of tag keywords

    Returns:
        List of matched tags
    """
    query_lower = query.lower()
    return [tag for tag in tags if tag.lower() in query_lower]


def select_agent(
    query: str,
    specs: dict[str, AgentSpec],
    agent_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], list[str], list[str]]:
    """Select the best agent for a query.

    Selection logic:
    1. If agent_id is specified, use it directly
    2. Check trigger patterns (first match wins)
    3. Check tag matches (most matches + highest priority wins)
    4. Fall back to highest priority agent

    Args:
        query: User query text
        specs: Available agent specifications
        agent_id: Explicit agent ID (optional)

    Returns:
        Tuple of (selected_id, matched_trigger, matched_tags, all_candidates)
    """
    if not specs:
        return None, None, [], []

    # Direct agent selection
    if agent_id:
        if agent_id in specs:
            return agent_id, None, [], [agent_id]
        return None, None, [], []

    candidates = []

    # Check triggers first
    for aid, spec in specs.items():
        if spec.triggers:
            matched = match_triggers(query, spec.triggers)
            if matched:
                return aid, matched, [], [aid]

    # Collect tag matches
    tag_scores: dict[str, tuple[int, int, list[str]]] = {}  # id -> (tag_count, priority, tags)
    for aid, spec in specs.items():
        matched = match_tags(query, spec.tags)
        if matched:
            tag_scores[aid] = (len(matched), spec.priority, matched)
            candidates.append(aid)

    # Select by most tags, then priority
    if tag_scores:
        best_id = max(tag_scores.keys(), key=lambda x: (tag_scores[x][0], tag_scores[x][1]))
        return best_id, None, tag_scores[best_id][2], candidates

    # Fall back to highest priority
    all_ids = list(specs.keys())
    best_id = max(specs.keys(), key=lambda x: specs[x].priority)
    return best_id, None, [], all_ids


def dispatch(
    root: Path,
    query: str,
    agent_id: Optional[str] = None,
    provider: Optional[str] = None,
    fixture_path: Optional[str] = None,
    do_apply: bool = False,
    agentic: bool = False,
    on_chunk: Optional[Callable[[str], None]] = None,
    on_ask_user: Optional[Callable[[str, list[str]], str]] = None,
) -> DispatchResult:
    """Dispatch a query to the appropriate agent.

    Args:
        root: Project root directory
        query: User query text
        agent_id: Explicit agent ID (optional)
        provider: LLM provider override
        fixture_path: Path to proposal fixture for stub provider
        do_apply: If True, apply the proposal after generation
        agentic: If True, use the agentic multi-turn loop
        on_chunk: Optional callback for streaming chunks (M7-T8)
        on_ask_user: Optional callback for ask_user skill (M8-T3)

    Returns:
        DispatchResult with agent run outcome
    """
    # Load all agent specs
    specs = load_agent_specs(root)

    if not specs:
        return DispatchResult(
            success=False,
            error="No agents found in project",
        )

    # Select agent
    selected_id, matched_trigger, matched_tags, candidates = select_agent(query, specs, agent_id)

    if not selected_id:
        return DispatchResult(
            success=False,
            error=f"Agent '{agent_id}' not found" if agent_id else "No matching agent found",
            candidates=candidates,
        )

    # Run the selected agent
    if agentic:
        run_result = run_agent_agentic(
            root=root,
            agent_id=selected_id,
            query=query,
            provider=provider,
            fixture_path=fixture_path,
            do_apply=do_apply,
            on_chunk=on_chunk,
            on_ask_user=on_ask_user,
        )
    else:
        run_result = run_agent(
            root=root,
            agent_id=selected_id,
            query=query,
            provider=provider,
            fixture_path=fixture_path,
            do_apply=do_apply,
        )

    return DispatchResult(
        success=run_result.success,
        agent_id=selected_id,
        run_result=run_result,
        matched_trigger=matched_trigger,
        matched_tags=matched_tags,
        error=run_result.error,
        candidates=candidates,
    )
