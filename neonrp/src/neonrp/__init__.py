"""NeonRP — file-backed text RPG engine with agent-driven storytelling."""

# Single source of truth: read the installed distribution's version from its
# metadata (set from pyproject.toml at build time). A hardcoded literal here
# used to drift — the release flow only bumps pyproject.toml, so __version__
# stayed at an old value and the UI showed e.g. 0.2.4 while the code was 0.2.5.
# Deriving it means the displayed version can never be stale again.
try:
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("neonrp")
    except PackageNotFoundError:
        __version__ = "0.0.0+dev"  # running from a source checkout with no install
except Exception:
    __version__ = "0.0.0+dev"
