"""Apply engine for NeonRP proposals.

Implements the staging → apply → validate → commit pipeline with permission enforcement.
"""

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import secrets

from neonrp.core.proposal import Proposal, UpsertTextOp, DeleteOp
from neonrp.core.permissions import REQUIRED_DENY_GLOBS, check_ops_permissions, format_permission_error
from neonrp.core.validation import validate_game_data, load_schema
from neonrp.core.config import load_config
from neonrp.core.rules import load_rules_profile, validate_game_rules
from neonrp.core.event_log import GameEvent, append_event, get_event_log_path
from neonrp.core.storage import atomic_write_dir, atomic_write_json, atomic_write_text
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_data_dir_name, get_manifest_path, get_neonrp_dir, get_game_dir
from neonrp.core.checkpoint import create_checkpoint


@dataclass
class ApplyResult:
    """Result of applying a proposal."""

    success: bool
    applied_paths: list[str] = field(default_factory=list)
    event_id: Optional[int] = None
    error: Optional[str] = None
    validation_errors: list[dict] = field(default_factory=list)


def generate_run_id() -> str:
    """Generate a unique run ID in the format YYYYMMDDTHHMMSSZ_6hex."""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    random_hex = secrets.token_hex(3)
    return f"{timestamp}_{random_hex}"


def get_logs_dir(root: Path, run_id: str) -> Path:
    """Get the logs directory for a specific run."""
    return get_neonrp_dir(root) / "logs" / "agents" / run_id


def _rollback_last_event(root: Path, branch: str, event: GameEvent) -> bool:
    """Best-effort rollback for the just-appended event line."""
    events_path = get_event_log_path(root, branch)
    if not events_path.exists():
        return False

    with open(events_path, "r+", encoding="utf-8") as f:
        lines = f.readlines()
        if not lines:
            return False

        try:
            last = json.loads(lines[-1])
        except json.JSONDecodeError:
            return False

        expected_run_id = event.payload.get("run_id")
        if (
            last.get("id") != event.id
            or last.get("actor") != event.actor
            or not isinstance(last.get("payload"), dict)
            or last["payload"].get("run_id") != expected_run_id
        ):
            return False

        f.seek(0)
        f.writelines(lines[:-1])
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
    return True


def _commit_event_and_manifest(root: Path, manifest_path: Path, manifest: Manifest, branch: str, event: GameEvent) -> None:
    """Commit append-only event and branch head update with rollback on failure."""
    append_event(root, branch, event)
    try:
        manifest.branches[branch].head_event = event.id
        if manifest.branches[branch].max_event is None or manifest.branches[branch].max_event < event.id:
            manifest.branches[branch].max_event = event.id
        atomic_write_json(manifest_path, manifest.model_dump())
    except Exception as exc:
        rolled_back = _rollback_last_event(root, branch, event)
        rollback_note = "event rolled back" if rolled_back else "event may need manual cleanup"
        raise RuntimeError(f"Failed to update manifest after append ({rollback_note}): {exc}") from exc


def apply_proposal(
    root: Path,
    proposal: Proposal,
    agent_permissions: dict,
    dry_run: bool = False,
    *,
    bypass_required_deny_globs: bool = False,
    bypass_validation: bool = False,
) -> ApplyResult:
    """Apply a proposal to the game state using staging strategy.

    Pipeline:
    1. Check base_head_event matches current head
    2. Check permissions for all ops
    3. Copy game data to staging
    4. Apply ops to staging
    5. Validate staging (skipped when bypass_validation=True)
    6. If valid and not dry_run: atomic commit + event append

    Args:
        root: Project root directory
        proposal: The proposal to apply
        agent_permissions: Agent's permissions dict with write_globs/deny_globs
        dry_run: If True, don't actually commit changes
        bypass_required_deny_globs: when True, skip the REQUIRED_DENY_GLOBS
            safety net. Intended ONLY for system-initiated proposals (e.g.
            `apply_system_proposal` doing initial scaffolding). All agent-
            originated calls MUST leave this False so an agent can never
            write into top-level `agents/` or `.neonrp/`.
        bypass_validation: when True, skip schema + rules validation of the
            staged content. Intended ONLY for system-initiated proposals
            copying author-maintained template data (which may include
            state/config files that don't conform to the generic
            entity-schema id/kind/name contract). Agent-originated calls
            MUST leave this False so LLM-authored content is schema-checked.

    Returns:
        ApplyResult with success status and details
    """
    config = load_config(root)

    write_globs = agent_permissions.get("write_globs", [])
    # Merge agent deny_globs with required denies (agent cannot bypass protected paths)
    agent_deny_globs = agent_permissions.get("deny_globs", [])
    if bypass_required_deny_globs:
        deny_globs = list(set(agent_deny_globs))
    else:
        deny_globs = list(set(REQUIRED_DENY_GLOBS + agent_deny_globs))

    game_root = get_game_dir(root)
    data_dir_name = get_data_dir_name(root)

    # 1. Check base_head_event
    manifest_path = get_manifest_path(root)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = Manifest(**json.load(f))

    # Check that proposal.branch exists in manifest
    if proposal.branch not in manifest.branches:
        return ApplyResult(
            success=False,
            error=f"Branch '{proposal.branch}' not found in manifest. Available branches: {list(manifest.branches.keys())}",
        )
    if proposal.branch != manifest.current_branch:
        return ApplyResult(
            success=False,
            error=(
                f"Branch mismatch: proposal targets '{proposal.branch}' but current branch is "
                f"'{manifest.current_branch}'. Switch branch or regenerate proposal."
            ),
        )

    current_head = manifest.branches[proposal.branch].head_event
    if proposal.base_head_event != current_head:
        return ApplyResult(
            success=False,
            error=f"base_head_event mismatch: proposal has {proposal.base_head_event}, "
            f"current head is {current_head}. Please rerun with updated context.",
        )

    # 2. Check permissions
    permission_failures = check_ops_permissions(proposal.ops, write_globs, deny_globs)
    if permission_failures:
        idx, result = permission_failures[0]
        error_msg = format_permission_error(proposal.agent_id, proposal.ops[idx].path, result, write_globs, deny_globs)
        return ApplyResult(success=False, error=error_msg)

    # 3. Create staging area
    staging_dir = None
    try:
        staging_dir = Path(tempfile.mkdtemp(prefix="neonrp_staging_"))
        staging_game = staging_dir / data_dir_name

        # Copy game data to staging (if exists)
        if game_root.exists():
            shutil.copytree(game_root, staging_game)
        else:
            staging_game.mkdir(parents=True)

        # 4. Apply ops to staging (with defense-in-depth path safety)
        applied_paths = []
        for op in proposal.ops:
            target_path = (staging_game / op.path).resolve()
            # Defense-in-depth: ensure resolved path stays within staging_game
            try:
                target_path.relative_to(staging_game.resolve())
            except ValueError:
                return ApplyResult(
                    success=False,
                    error=f"Path traversal detected: op path '{op.path}' resolves outside {data_dir_name} directory",
                )

            if isinstance(op, UpsertTextOp):
                # Ensure parent directory exists
                target_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(target_path, op.content)
                applied_paths.append(op.path)
            elif isinstance(op, DeleteOp):
                if target_path.exists():
                    target_path.unlink()
                applied_paths.append(op.path)

        # 5. Validate staging (skipped for trusted system scaffolds)
        if not bypass_validation:
            schema = load_schema(root)
            validation_issues, _ = validate_game_data(staging_dir, schema)
            validation_errors = [
                {"file": issue.file, "path": issue.path, "message": issue.message} for issue in validation_issues
            ]

            if validation_issues:
                return ApplyResult(
                    success=False, error="Validation failed after applying proposal", validation_errors=validation_errors
                )

            # 5b. Validate optional domain rules (post-staging hook)
            if config.rules.enable_domain_validation:
                rules_profile = load_rules_profile(root, config.rules.profile_path)
                rule_violations = validate_game_rules(staging_dir, proposal, profile=rules_profile)
                if rule_violations:
                    rule_errors = [v.to_dict() for v in rule_violations]
                    return ApplyResult(
                        success=False,
                        error="Game rules validation failed",
                        validation_errors=rule_errors,
                    )

        # 6. Commit if not dry_run
        if not dry_run:
            # Create checkpoint before modifying game state (enables undo)
            # Use proposal.branch to ensure checkpoint goes to the correct branch
            create_checkpoint(root, proposal.branch, proposal.base_head_event)

            # Atomically replace game directory from validated staging copy.
            atomic_write_dir(game_root, staging_game)

            # Append event
            new_event_id = current_head + 1
            event = GameEvent(
                id=new_event_id,
                type="agent",
                actor=proposal.agent_id,
                payload={
                    "run_id": proposal.run_id,
                    "query": proposal.query,
                    "ops_count": len(proposal.ops),
                    "applied_paths": applied_paths,
                },
            )
            _commit_event_and_manifest(root, manifest_path, manifest, proposal.branch, event)

            return ApplyResult(success=True, applied_paths=applied_paths, event_id=new_event_id)
        else:
            # Dry run - return success without committing
            return ApplyResult(
                success=True,
                applied_paths=applied_paths,
                event_id=None,  # No event created in dry run
            )

    finally:
        # Clean up staging
        if staging_dir and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def save_run_logs(
    root: Path,
    run_id: str,
    input_data: dict,
    proposal: Proposal,
    diff_content: str,
    validation_result: list,
    apply_result: ApplyResult,
) -> Path:
    """Save logs for a run.

    Args:
        root: Project root
        run_id: The run ID
        input_data: Input context data
        proposal: The proposal applied
        diff_content: The rendered diff
        validation_result: Validation results
        apply_result: The apply result

    Returns:
        Path to the logs directory
    """
    logs_dir = get_logs_dir(root, run_id)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # input.json
    atomic_write_json(logs_dir / "input.json", input_data)

    # proposal.json
    atomic_write_json(logs_dir / "proposal.json", proposal.model_dump())

    # diff.patch
    atomic_write_text(logs_dir / "diff.patch", diff_content)

    # validation.json
    atomic_write_json(logs_dir / "validation.json", {"issues": validation_result})

    # apply.json
    apply_data = {
        "success": apply_result.success,
        "applied_paths": apply_result.applied_paths,
        "event_id": apply_result.event_id,
        "error": apply_result.error,
    }
    atomic_write_json(logs_dir / "apply.json", apply_data)

    return logs_dir



