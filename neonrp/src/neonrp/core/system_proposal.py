"""System proposal helpers for CLI commands.

Provides utilities to create and apply system proposals for commands
that modify game data files (import, game new, etc.).
"""

import json
from pathlib import Path

from neonrp.core.apply import ApplyResult, apply_proposal, generate_run_id, get_logs_dir
from neonrp.core.diffing import render_diff
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_manifest_path, get_game_dir
from neonrp.core.proposal import DeleteOp, Proposal, UpsertTextOp
from neonrp.core.storage import atomic_write_json, atomic_write_text


def create_system_proposal(
    root: Path,
    ops: list[UpsertTextOp | DeleteOp],
    rationale: str,
    command: str,
) -> tuple[Proposal, str]:
    """Create a system proposal for a CLI command.

    Args:
        root: Project root directory.
        ops: List of operations to apply.
        rationale: Human-readable rationale for the change.
        command: Command name (e.g., "import", "game_new").

    Returns:
        Tuple of (proposal, run_id).
    """
    manifest_path = get_manifest_path(root)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = Manifest(**json.load(f))

    run_id = generate_run_id()
    branch = manifest.current_branch
    base_head_event = manifest.branches[branch].head_event

    proposal = Proposal(
        proposal_version="0.1",
        agent_id="system",
        branch=branch,
        base_head_event=base_head_event,
        rationale=rationale,
        ops=ops,
        run_id=run_id,
        query=command,
    )

    return proposal, run_id


def apply_system_proposal(
    root: Path,
    ops: list[UpsertTextOp | DeleteOp],
    rationale: str,
    command: str,
) -> ApplyResult:
    """Create and apply a system proposal.

    This is a convenience function that creates a system proposal and
    applies it using the standard pipeline, but with system permissions.

    Args:
        root: Project root directory.
        ops: List of operations to apply.
        rationale: Human-readable rationale for the change.
        command: Command name (e.g., "import", "game_new").

    Returns:
        ApplyResult with success status and details.
    """
    proposal, run_id = create_system_proposal(root, ops, rationale, command)

    # System proposals: write anywhere inside the data dir. `apply_proposal`
    # already scopes every op.path to `<root>/<data_dir>/...` via
    # `staging_game / op.path` and refuses paths that resolve outside, so
    # there's no way for a system op to escape into top-level `agents/` or
    # `.neonrp/`. The old deny_globs `["agents/**", ".neonrp/**"]` were
    # matching `op.path` *as a string* — which broke templates that carry
    # a `game/agents/` subtree of data files (e.g. stoneford-orch's
    # `agents/manifest.json` is template content, NOT a runtime agent dir).
    system_permissions = {
        "write_globs": ["**/*"],
        "deny_globs": [],
    }

    # Generate diff before apply for logging
    game_root = get_game_dir(root)
    diff_content = render_diff(proposal, game_root)

    # System proposals are trusted author-driven scaffolds, NOT LLM-authored
    # content. They:
    # - already resolve under `<root>/game/...` via apply_proposal's staging,
    #   so the REQUIRED_DENY_GLOBS safety net (targets top-level `agents/`
    #   and `.neonrp/`) is redundant AND breaks templates that carry a
    #   `game/agents/` subtree of data files.
    # - contain mixed content including state/config files (run_state.json,
    #   active-agent.json, schedule.json) that don't conform to the generic
    #   entity-schema id/kind/name contract, so validation would reject them.
    # Bypass both gates — the template content is maintained by us and is
    # the baseline we trust.
    result = apply_proposal(
        root,
        proposal,
        system_permissions,
        bypass_required_deny_globs=True,
        bypass_validation=True,
    )

    # Always save logs (success and failure) for replay support and auditability
    _save_system_logs(root, run_id, proposal, command, diff_content, result)

    return result


def _save_system_logs(
    root: Path,
    run_id: str,
    proposal: Proposal,
    command: str,
    diff_content: str,
    result: ApplyResult,
) -> None:
    """Save system proposal logs for replay support.

    Logs the standard set: input.json, proposal.json, diff.patch,
    validation.json, apply.json — matching the agent run log spec.
    """
    logs_dir = get_logs_dir(root, run_id)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # input.json
    input_data = {
        "command": command,
        "run_id": run_id,
        "agent_id": "system",
    }
    atomic_write_json(logs_dir / "input.json", input_data)

    # proposal.json
    proposal_data = proposal.model_dump()
    atomic_write_json(logs_dir / "proposal.json", proposal_data)

    # diff.patch
    atomic_write_text(logs_dir / "diff.patch", diff_content)

    # validation.json
    validation_data = {
        "issues": [
            {"file": e["file"], "path": e.get("path", ""), "message": e.get("message", "")}
            for e in result.validation_errors
        ]
    }
    atomic_write_json(logs_dir / "validation.json", validation_data)

    # apply.json
    apply_data = {
        "success": result.success,
        "applied_paths": result.applied_paths,
        "event_id": result.event_id,
        "error": result.error,
    }
    atomic_write_json(logs_dir / "apply.json", apply_data)

