import re
import sys
from pathlib import Path
from typing import Any

NEONRP_DIR_NAME = ".neonrp"
MANIFEST_FILENAME = "manifest.json"
DEFAULT_SCHEMA_FILENAME = "game_entity.schema.json"
RULES_DIR_NAME = "rules"
GAME_DIR_NAME = "game"


def get_project_root(cwd: Path | None = None) -> Path:
    """Find the project root (where .neonrp exists) or return cwd if creating new."""
    # Simplified for M0: Assumes current directory or simple lookup.
    # In M0 init, we construct it in CWD.
    if cwd is None:
        return Path.cwd()
    return cwd


def get_neonrp_dir(root: Path) -> Path:
    return root / NEONRP_DIR_NAME


def get_rules_dir(root: Path) -> Path:
    return root / RULES_DIR_NAME


def get_index_dir(root: Path) -> Path:
    return get_neonrp_dir(root) / "index"


def get_game_dir(root: Path) -> Path:
    """Get canonical game data directory."""
    return root / get_data_dir_name(root)


def get_data_dir_name(root: Path) -> str:
    """Return active game data directory name."""
    try:
        from neonrp.core.runtime_contract import load_data_dir

        return load_data_dir(root)
    except Exception:
        return GAME_DIR_NAME


def get_manifest_path(root: Path) -> Path:
    return get_neonrp_dir(root) / MANIFEST_FILENAME


_BRANCH_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def validate_branch_name(name: str) -> str | None:
    """Validate a branch/sandbox name for filesystem safety.

    Returns None if valid, or an error message string if invalid.
    Rejects names containing path separators, traversal sequences,
    drive letters, or other unsafe patterns.
    """
    if not name:
        return "Branch name cannot be empty"

    # Reject path separators and traversal
    if "/" in name or "\\" in name:
        return "Branch name must not contain path separators ('/' or '\\\\')"

    if ".." in name:
        return "Branch name must not contain '..'"

    # Reject Windows drive letters (e.g., "C:")
    if len(name) >= 2 and name[1] == ":" and name[0].isalpha():
        return "Branch name must not contain drive letters"

    # Reject reserved names
    if name in (".", ".."):
        return "Branch name must not be '.' or '..'"

    # Must match safe pattern: alphanumeric start, then alphanumeric/dot/hyphen/underscore
    if not _BRANCH_NAME_RE.match(name):
        return "Branch name must start with alphanumeric and contain only alphanumeric, '.', '-', or '_'"

    # Reject excessively long names
    if len(name) > 128:
        return "Branch name must be 128 characters or fewer"

    return None


def shell_dir(sub: str) -> Path | None:
    """A folder the installed WorldLines shell ships (``worldlines_shim/<sub>``: spa · templates · contracts), found
    without importing it (10-08: in a release the product's templates, contracts and screen live in the worldlines
    wheel, and the engine's own ``worldlines`` / ``neonrp`` commands must see them whichever package was installed last)."""
    import importlib.util

    try:
        spec = importlib.util.find_spec("worldlines_shim")
    except (ImportError, ValueError):
        return None
    locs = list(spec.submodule_search_locations or []) if spec else []
    d = Path(locs[0]) / sub if locs else None
    return d if d is not None and d.is_dir() else None


_PRIVATE_BASE: dict[str, Any] = {"key": None, "base": None}


def _find_private_base(util: Any) -> Path | None:
    try:
        spec = util.find_spec("neonrp_private")
    except (ImportError, ValueError):
        spec = None
    locs = list(spec.submodule_search_locations or []) if spec else []
    if locs:
        return Path(locs[0])
    # the whole private folder copied into the WorldLines shell (10-08): its package, or the source tree
    src = Path(__file__).resolve().parents[3] / "worldlines" / "private"
    return shell_dir("private") or (src if src.is_dir() else None)


def private_dir(sub: str | None = None) -> Path | None:
    """Ludic Dynamics' private orchestration layer (10-08: open engine · private orchestration) — our prompts, pack
    orchestration, contract turn settings and templates, laid over the engine's public ones. Found, not imported:
    ``NEONRP_PRIVATE_DIR``, else an installed ``neonrp_private`` package, else the folder copied into the WorldLines
    shell (``worldlines_shim/private`` / ``worldlines/private``). ``NEONRP_PRIVATE=off`` = the public engine.
    With ``sub``, that folder of it (None when absent). Without a private layer the engine is the complete public one."""
    import importlib.util
    import os

    if os.environ.get("NEONRP_PRIVATE", "").strip().lower() in ("off", "0", "false", "no"):
        return None
    env = os.environ.get("NEONRP_PRIVATE_DIR", "").strip()
    base: Path | None = Path(env).expanduser() if env else None
    if base is None:
        # 10-18: the package lookup (find_spec) is asked ~1700 times in one world build (every prompt table read):
        # remembered per import path and lookup functions (a test that swaps find_spec / shell_dir gets a fresh lookup);
        # a remembered folder that is gone is looked up again
        key = (tuple(sys.path), id(importlib.util.find_spec), id(shell_dir))
        if _PRIVATE_BASE.get("key") != key or not (_PRIVATE_BASE["base"] is None or _PRIVATE_BASE["base"].is_dir()):
            _PRIVATE_BASE.update(key=key, base=_find_private_base(importlib.util))
        base = _PRIVATE_BASE["base"]
    if base is None or not base.is_dir():
        return None
    d = base / sub if sub else base
    return d if d.is_dir() else None


def ensure_template_store() -> Path:
    """The player's own templates (forked / new) live in ``~/.worldlines/templates`` (10-08; the launcher owns
    ~/.worldlines): written there by default, and looked up before the shipped ones (a fork with the same id wins)."""
    import os

    store = Path.home() / ".worldlines" / "templates"  # same home as worlds.py / players.py
    os.environ.setdefault("NEONRP_TEMPLATE_WRITE_DIR", str(store))
    os.environ.setdefault("NEONRP_OFFICIAL_DIR", str(Path.home() / ".worldlines" / "official"))  # 10-17: see official_dir
    cur = [x for x in os.environ.get("NEONRP_TEMPLATE_PATH", "").split(os.pathsep) if x.strip()]
    if str(store) not in cur:
        os.environ["NEONRP_TEMPLATE_PATH"] = os.pathsep.join([str(store), *cur])
    return store


def official_dir() -> Path | None:
    """Official worlds fetched with a Worldlines account (10-17: the local edition ships two; the rest are downloaded
    to play): ``NEONRP_OFFICIAL_DIR`` (``ensure_template_store`` sets ``~/.worldlines/official``). Read-only to the
    author tools (not the write store): played, never exported or copied. None when not set."""
    import os

    env = os.environ.get("NEONRP_OFFICIAL_DIR", "").strip()
    return Path(env).expanduser() if env else None
