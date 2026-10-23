"""Permission checking for NeonRP agents.

Implements glob-based permission boundaries with deny-first priority.
"""

import fnmatch
from dataclasses import dataclass
from typing import Optional


@dataclass
class PermissionResult:
    """Result of a permission check."""

    allowed: bool
    reason: str
    matched_glob: Optional[str] = None


def normalize_path(path: str) -> str:
    """Normalize a path for permission checking.

    Args:
        path: The path to normalize

    Returns:
        Normalized path using forward slashes

    Raises:
        ValueError: If path contains path traversal (..)
    """
    # Convert to forward slashes
    normalized = path.replace("\\", "/")

    # Check for path traversal
    parts = normalized.split("/")
    if ".." in parts:
        raise ValueError(f"Path traversal not allowed: {path}")

    # Remove leading/trailing slashes for consistency
    normalized = normalized.strip("/")

    return normalized


def match_glob(path: str, pattern: str) -> bool:
    """Check if a path matches a glob pattern.

    Args:
        path: Normalized path to check
        pattern: Glob pattern (supports *, **, ?)

    Returns:
        True if path matches the pattern

    Note:
        - `*` matches any characters within a single path segment (not /)
        - `**` matches any number of path segments (including /)
        - `?` matches a single character
    """
    # Normalize both path and pattern
    path = path.replace("\\", "/").strip("/")
    pattern = pattern.replace("\\", "/").strip("/")

    path_parts = path.split("/")
    pattern_parts = pattern.split("/")

    return _match_segments(path_parts, pattern_parts)


def _match_segments(path_parts: list[str], pattern_parts: list[str]) -> bool:
    """Recursively match path segments against pattern segments."""
    if not pattern_parts:
        return not path_parts

    if not path_parts:
        # Pattern remaining - only valid if all remaining are **
        return all(p == "**" for p in pattern_parts)

    current_pattern = pattern_parts[0]

    if current_pattern == "**":
        # ** can match zero or more segments
        # Try matching with zero segments consumed
        if _match_segments(path_parts, pattern_parts[1:]):
            return True
        # Try matching with one segment consumed
        if _match_segments(path_parts[1:], pattern_parts):
            return True
        return False

    # Match current segment using fnmatch (handles * and ?)
    if fnmatch.fnmatch(path_parts[0], current_pattern):
        return _match_segments(path_parts[1:], pattern_parts[1:])

    return False


def check_permission(path: str, write_globs: list[str], deny_globs: list[str]) -> PermissionResult:
    """Check if an operation on a path is allowed.

    Permission rules:
    1. deny_globs are checked first - if any match, access is denied
    2. write_globs are checked second - at least one must match for access

    Args:
        path: The path being accessed (will be normalized)
        write_globs: List of allowed write patterns
        deny_globs: List of denied patterns (checked first)

    Returns:
        PermissionResult indicating if access is allowed

    Raises:
        ValueError: If path contains path traversal
    """
    # Normalize path
    try:
        normalized = normalize_path(path)
    except ValueError as e:
        return PermissionResult(allowed=False, reason=str(e))

    # Check deny_globs first (deny has priority)
    for pattern in deny_globs:
        if match_glob(normalized, pattern):
            return PermissionResult(allowed=False, reason=f"Path '{path}' matches deny pattern", matched_glob=pattern)

    # Check write_globs (at least one must match)
    for pattern in write_globs:
        if match_glob(normalized, pattern):
            return PermissionResult(allowed=True, reason=f"Path '{path}' matches write pattern", matched_glob=pattern)

    # No write_glob matched
    return PermissionResult(allowed=False, reason=f"Path '{path}' does not match any write pattern", matched_glob=None)


def check_ops_permissions(
    ops: list, write_globs: list[str], deny_globs: list[str]
) -> list[tuple[int, PermissionResult]]:
    """Check permissions for a list of operations.

    Args:
        ops: List of Op objects with 'path' attribute
        write_globs: List of allowed write patterns
        deny_globs: List of denied patterns

    Returns:
        List of (index, PermissionResult) for failed permission checks.
        Empty list if all operations are allowed.
    """
    failures = []
    for i, op in enumerate(ops):
        result = check_permission(op.path, write_globs, deny_globs)
        if not result.allowed:
            failures.append((i, result))
    return failures


# Paths that are ALWAYS denied for direct writes, regardless of agent config
REQUIRED_DENY_GLOBS = [".neonrp/**", "agents/**"]


def check_write_permission(
    path: str,
    direct_write_globs: list[str],
    deny_globs: list[str],
    *,
    allow_protected_paths: bool = False,
) -> PermissionResult:
    """Check if a direct write to a path is allowed.

    For use with write_file/edit_file skills that bypass submit_proposal.

    Permission rules:
    1. Path traversal (..) is rejected
    2. REQUIRED_DENY_GLOBS are checked first - always denied (unless allow_protected_paths=True)
    3. deny_globs are checked second - if any match, access is denied
    4. direct_write_globs are checked third - at least one must match

    Args:
        path: The path being written (will be normalized)
        direct_write_globs: List of allowed direct write patterns
        deny_globs: List of denied patterns (checked after REQUIRED_DENY_GLOBS)
        allow_protected_paths: If True, skip REQUIRED_DENY_GLOBS protection

    Returns:
        PermissionResult indicating if access is allowed
    """
    # Normalize path
    try:
        normalized = normalize_path(path)
    except ValueError as e:
        return PermissionResult(allowed=False, reason=str(e))

    # Check REQUIRED_DENY_GLOBS first (unless explicitly disabled)
    if not allow_protected_paths:
        for pattern in REQUIRED_DENY_GLOBS:
            if match_glob(normalized, pattern):
                return PermissionResult(
                    allowed=False,
                    reason=f"Path '{path}' is in a protected directory",
                    matched_glob=pattern,
                )

    # Check deny_globs second
    for pattern in deny_globs:
        if match_glob(normalized, pattern):
            return PermissionResult(
                allowed=False,
                reason=f"Path '{path}' matches deny pattern",
                matched_glob=pattern,
            )

    # Check direct_write_globs (at least one must match)
    for pattern in direct_write_globs:
        if match_glob(normalized, pattern):
            return PermissionResult(
                allowed=True,
                reason=f"Path '{path}' matches direct write pattern",
                matched_glob=pattern,
            )

    # No direct_write_glob matched.
    # For game-state paths, guide toward submit_proposal.
    if (
        normalized == "game"
        or normalized.startswith("game/")
    ):
        return PermissionResult(
            allowed=False,
            reason=f"Path '{path}' is not in direct_write_globs. Use submit_proposal for game/ changes.",
            matched_glob=None,
        )

    return PermissionResult(
        allowed=False,
        reason=f"Path '{path}' is not in direct_write_globs.",
        matched_glob=None,
    )


def format_permission_error(
    agent_id: str, path: str, result: PermissionResult, write_globs: list[str], deny_globs: list[str]
) -> str:
    """Format a permission error with actionable suggestions.

    Args:
        agent_id: The agent that attempted the operation
        path: The path that was denied
        result: The PermissionResult from check_permission
        write_globs: The agent's write_globs
        deny_globs: The agent's deny_globs

    Returns:
        Formatted error message with suggestions
    """
    lines = [
        f"Permission denied for agent '{agent_id}':",
        f"  Path: {path}",
        f"  Reason: {result.reason}",
    ]

    if result.matched_glob:
        lines.append(f"  Matched glob: {result.matched_glob}")

    lines.append("")
    lines.append("Suggestions:")

    if result.matched_glob and result.matched_glob in deny_globs:
        lines.append(f"  - Remove '{result.matched_glob}' from deny_globs if this path should be writable")
    else:
        lines.append(f"  - Add a pattern matching '{path}' to write_globs in agent.json")
        # Suggest a glob pattern
        parts = path.replace("\\", "/").split("/")
        if len(parts) >= 2:
            suggested = f"{parts[0]}/{parts[1]}/**"
            lines.append(f'  - Example: "{suggested}"')

    return "\n".join(lines)
