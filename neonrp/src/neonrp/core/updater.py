"""Self-update infrastructure (L14 Phase 1).

Responsibilities:
- Detect install mode (editable vs. released)
- Fetch release manifest from worldlines.gg (fallback to GitHub)
- Compare with running version
- Surface a check result to CLI + TUI callers
- Defer the actual upgrade to `uv tool upgrade neonrp` (or the equivalent
  for worldlines), never rewriting local source

See docs/L14_AUTO_UPDATE_SCHEME.md for the full design.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import neonrp

# Primary CDN (worldlines.gg mirrors the same JSON published as a GitHub
# Release asset by the `release` workflow). Fallback is the raw GitHub API.
PRIMARY_MANIFEST_URL = "https://worldlines.gg/releases.json"
# The release workflow in the private LudicDynamics/NeonRP repo creates
# the public-facing Release (with releases.json + install.sh attached) on
# LudicDynamics/WorldLines, so auto-update clients query THIS public repo.
# NeonRP's own releases are never published directly.
GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/LudicDynamics/WorldLines/releases/latest"

USER_CONFIG_PATH = Path.home() / ".neonrp" / "config.json"
CACHE_PATH = Path.home() / ".neonrp" / "update_cache.json"
DEFAULT_CHANNEL = "stable"
FETCH_TIMEOUT = 4.0


@dataclass
class InstallMode:
    kind: str  # "editable" | "released" | "unknown"
    detail: str
    allow_auto_apply: bool


@dataclass
class UpdateCheckResult:
    current_version: str
    latest_version: str | None
    channel: str
    update_available: bool
    install_mode: InstallMode
    release_notes_url: str | None = None
    error: str | None = None
    # Which distribution this check is about — `worldlines` when you came in
    # through the shim, else `neonrp` (「worldlines 执行的时候
    # 更新依赖(neonrp+worldlines),neonrp 执行的时候只更新 neonrp」).
    package: str = "neonrp"

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["install_mode"] = asdict(self.install_mode)
        return data


# ---------------------------------------------------------------------------
# Install-mode detection
# ---------------------------------------------------------------------------

def detect_install_mode() -> InstallMode:
    """Detect how the running neonrp package was installed."""
    try:
        pkg_path = Path(neonrp.__file__).resolve().parent
    except Exception:
        return InstallMode(kind="unknown", detail="no __file__", allow_auto_apply=False)

    # Editable / source checkout: package parent (src/neonrp → src → repo) contains .git
    for parent in (pkg_path.parent, pkg_path.parent.parent):
        if (parent / ".git").exists() and (parent / "pyproject.toml").exists():
            return InstallMode(
                kind="editable",
                detail=f"source checkout at {parent}",
                allow_auto_apply=False,
            )

    # uv tool install path — typically contains "uv/tools/neonrp" or "pipx"
    path_str = str(pkg_path).replace("\\", "/")
    for marker in ("/uv/tools/", "/pipx/venvs/", "/site-packages/"):
        if marker in path_str:
            return InstallMode(
                kind="released",
                detail=f"installed package at {pkg_path}",
                allow_auto_apply=True,
            )

    return InstallMode(
        kind="unknown",
        detail=f"package at {pkg_path}",
        allow_auto_apply=False,
    )


# ---------------------------------------------------------------------------
# User config
# ---------------------------------------------------------------------------

def _load_user_config() -> dict[str, Any]:
    if not USER_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(USER_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_user_config(data: dict[str, Any]) -> None:
    USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_update_settings() -> dict[str, Any]:
    data = _load_user_config()
    settings = data.get("updates")
    if not isinstance(settings, dict):
        settings = {}
    settings.setdefault("enabled", True)
    settings.setdefault("channel", DEFAULT_CHANNEL)
    settings.setdefault("check_on_launch", True)
    settings.setdefault("mode", "auto")
    return settings


LAUNCH_MODES = ("auto", "prompt", "notify")


def launch_mode(settings: dict[str, Any] | None = None) -> str:
    """What the launch-time check does with a newer release (``updates.mode``): ``auto`` (10-24 niko: a released install
    upgrades itself and relaunches, one line says so) · ``prompt`` (ask: upgrade / skip / later; the old
    ``prompt-and-update``) · ``notify`` (the banner only). An editable / unknown install is always notify-only."""
    raw = str((settings or get_update_settings()).get("mode") or "auto").strip().lower()
    if raw in ("prompt-and-update", "ask"):
        return "prompt"
    return raw if raw in LAUNCH_MODES else "auto"


def set_update_settings(**patch: Any) -> dict[str, Any]:
    data = _load_user_config()
    settings = data.get("updates") if isinstance(data.get("updates"), dict) else {}
    settings.update({k: v for k, v in patch.items() if v is not None})
    data["updates"] = settings
    _save_user_config(data)
    return settings


def mark_version_skipped(version: str) -> None:
    set_update_settings(last_skipped_version=version)


def clear_skipped_version() -> None:
    data = _load_user_config()
    settings = data.get("updates") if isinstance(data.get("updates"), dict) else {}
    if "last_skipped_version" in settings:
        del settings["last_skipped_version"]
        data["updates"] = settings
        _save_user_config(data)


# ---------------------------------------------------------------------------
# Manifest fetching
# ---------------------------------------------------------------------------

def _fetch_json(url: str, *, timeout: float = FETCH_TIMEOUT) -> dict[str, Any] | None:
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "neonrp-updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def fetch_release_manifest(channel: str = DEFAULT_CHANNEL) -> dict[str, Any] | None:
    """Try the primary manifest URL; fall back to GitHub latest release."""
    manifest = _fetch_json(PRIMARY_MANIFEST_URL)
    if manifest and "latest" in manifest:
        return manifest

    # Fallback: synthesize a minimal manifest from GitHub's latest release
    gh = _fetch_json(GITHUB_LATEST_RELEASE_URL)
    if gh and isinstance(gh.get("tag_name"), str):
        tag = gh["tag_name"].lstrip("v")
        return {
            "product": "neonrp",
            "latest": {channel: tag},
            "releases": {
                tag: {
                    "channel": channel,
                    "published_at": gh.get("published_at"),
                    "notes_url": gh.get("html_url"),
                }
            },
        }
    return None


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"(\d+)")


def _version_key(version: str) -> tuple[int, ...]:
    if not isinstance(version, str):
        return ()
    parts = _VERSION_RE.findall(version)
    return tuple(int(p) for p in parts)


def is_newer(candidate: str, current: str) -> bool:
    return _version_key(candidate) > _version_key(current)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_distribution_installed(package: str) -> bool:
    try:
        from importlib.metadata import PackageNotFoundError, version

        version(package)
        return True
    except PackageNotFoundError:
        return False
    except Exception:  # noqa: BLE001
        return False


def upgrade_target() -> str:
    """The distribution an upgrade should act on: the entry point you used
    (`worldlines` → the shim, which pins the engine; `neonrp` → the engine),
    provided that distribution is actually installed here."""
    for name in _default_upgrade_candidates():
        if is_distribution_installed(name):
            return name
    return "neonrp"


def get_current_version(package: str = "neonrp") -> str:
    """Return the version of the installed `neonrp` distribution.

    Reads from `importlib.metadata`, which is what pip / uv recorded in
    `*.dist-info/METADATA` at install time — the authoritative source.
    Falls back to the source `__version__` string only when distribution
    metadata is unavailable (e.g. running straight from a git checkout
    with no install step at all).
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version(package)
    except PackageNotFoundError:
        pass
    except Exception:
        pass
    return getattr(neonrp, "__version__", "0.0.0")


def latest_for(manifest: dict[str, Any], package: str, channel: str) -> tuple[str | None, dict[str, Any]]:
    """(latest version, release entry) for `package` from a v2 manifest, or
    from the legacy top-level fields when the manifest predates `packages`."""
    pkgs = manifest.get("packages") if isinstance(manifest.get("packages"), dict) else None
    if pkgs and isinstance(pkgs.get(package), dict):
        pk = pkgs[package]
        latest_map = pk.get("latest") if isinstance(pk.get("latest"), dict) else {}
        latest = latest_map.get(channel) or latest_map.get(DEFAULT_CHANNEL)
        releases = pk.get("releases") if isinstance(pk.get("releases"), dict) else {}
        entry = releases.get(latest) if isinstance(latest, str) else None
        if latest:
            return latest, (entry or {})
    latest_map = manifest.get("latest") if isinstance(manifest.get("latest"), dict) else {}
    latest = latest_map.get(channel) or latest_map.get(DEFAULT_CHANNEL)
    entry = {}
    if isinstance(manifest.get("releases"), dict) and isinstance(latest, str):
        entry = manifest["releases"].get(latest) or {}
    return (latest if isinstance(latest, str) else None), entry


def check_for_update(channel: str | None = None, package: str | None = None) -> UpdateCheckResult:
    install_mode = detect_install_mode()
    settings = get_update_settings()
    resolved_channel = channel or settings.get("channel") or DEFAULT_CHANNEL
    target = package or upgrade_target()
    current = get_current_version(target)

    manifest = fetch_release_manifest(resolved_channel)
    if manifest is None:
        return UpdateCheckResult(
            current_version=current,
            latest_version=None,
            channel=resolved_channel,
            update_available=False,
            install_mode=install_mode,
            error="Failed to fetch release manifest",
            package=target,
        )

    latest, release_entry = latest_for(manifest, target, resolved_channel)
    available = bool(latest) and is_newer(latest, current)
    return UpdateCheckResult(
        current_version=current,
        latest_version=latest,
        channel=resolved_channel,
        update_available=available,
        install_mode=install_mode,
        release_notes_url=release_entry.get("notes_url"),
        package=target,
    )


# ---------------------------------------------------------------------------
# Upgrade execution (delegates to `uv tool upgrade`)
# ---------------------------------------------------------------------------

def _find_uv_binary() -> str | None:
    """Locate the `uv` binary, even when it isn't on PATH.

    The Windows double-click launcher (WorldLines.bat) hands control to
    worldlines.exe with a minimal PATH that often omits uv's own bin dir, so
    `shutil.which("uv")` returns None and auto-update silently fell back to a
    no-op pip call. Probe the standard astral install locations too, so the
    `uv tool upgrade` fallback actually runs for already-installed users.
    """
    found = shutil.which("uv")
    if found:
        return found
    home = Path.home()
    names = ("uv.exe", "uv") if os.name == "nt" else ("uv",)
    search_dirs = [home / ".local" / "bin", home / ".cargo" / "bin"]
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        search_dirs.append(Path(local_app) / "Programs" / "uv")
    for d in search_dirs:
        for n in names:
            cand = d / n
            if cand.is_file():
                return str(cand)
    return None


def _install_manager() -> str:
    """Which package manager owns THIS install: 'uv' | 'pipx' | 'pip' | ''.

    Decided by where the installed package lives, not by which managers happen
    to be on PATH. Critical: a pip-installed worldlines must upgrade with `pip`,
    not `uv tool upgrade` — the latter just reports 'Nothing to upgrade' and the
    user stays stuck even though uv is present.
    """
    try:
        p = str(Path(neonrp.__file__).resolve().parent).replace("\\", "/")
    except Exception:
        return ""
    if "/uv/tools/" in p:
        return "uv"
    if "/pipx/venvs/" in p:
        return "pipx"
    if "/site-packages/" in p:
        return "pip"
    return ""


def build_upgrade_command(package: str = "neonrp") -> list[str] | None:
    """Return the shell command to upgrade this install, matched to HOW it was
    installed (uv tool / pipx / pip), or None if unsupported."""
    mgr = _install_manager()
    uv = _find_uv_binary()
    pipx = shutil.which("pipx")
    pip_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", package]

    # uv 不用 `tool upgrade`:它尊重安装收据里的版本约束——桌面壳引导装的
    # 是 `--force worldlines==<壳版本>`,收据钉死后 upgrade 永远无操作,
    # 用户每次启动都被问"更新吗"、答应了也停在原版本(0.3.1 死循环实锤)。
    # `install --force` 重新解析最新版并改写收据,一次性打破钉版。
    if mgr == "uv" and uv:
        return [uv, "tool", "install", "--force", package]
    if mgr == "pipx" and pipx:
        return [pipx, "upgrade", package]
    if mgr == "pip":
        return pip_cmd
    # Unknown install layout → best-effort chain (old behaviour): uv → pipx → pip.
    if uv:
        return [uv, "tool", "install", "--force", package]
    if pipx:
        return [pipx, "upgrade", package]
    return pip_cmd


# Substrings that mean "the package manager ran cleanly but did not actually
# upgrade anything." `uv tool upgrade` exits 0 in all of these cases — without
# this gate we used to print "Upgrade complete" while the user stayed pinned
# at the old version. See CHANGELOG v0.1.11 for the incident.
_NO_OP_MARKERS = (
    "nothing to upgrade",
    "already at the latest",
    "up to date",
    "no upgrade necessary",
)

# A returncode==0 with this in the output means a real failure that uv
# downgraded to a warning. We treat it as failure so the user sees it.
_DEPENDENCY_FAILURE_MARKERS = (
    "does not have an extra named",
    "no solution found",
    "resolution failed",
)


def apply_update_in_background(package: str | None = None) -> tuple[bool, str]:
    """Run the upgrade command. Returns (success, stdout+stderr merged).

    If `package` is None, try the distribution the user most likely has
    installed. `worldlines` is our primary brand (pins neonrp), and
    `neonrp` is the direct-install alternative. If one reports "is not
    installed" we silently fall through to the next candidate before
    surfacing an error.

    A successful return code is *not* sufficient: `uv tool upgrade` exits 0
    even when nothing changed (already-latest, dependency conflict that
    uv treats as a warning, etc.). We also scan stdout for known no-op
    and dependency-failure markers and downgrade those to (False, output)
    so the caller can surface the real outcome to the user.
    """
    candidates = [package] if package else _default_upgrade_candidates()
    last_output = ""
    for pkg in candidates:
        cmd = build_upgrade_command(pkg)
        if cmd is None:
            return False, "No supported package manager (uv / pipx / pip) found on PATH."
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "CLICOLOR": "0"},
            )
        except Exception as exc:
            return False, f"Failed to run upgrade command: {exc}"
        output = (proc.stdout or "") + (proc.stderr or "")
        last_output = output
        lowered = output.lower()
        if proc.returncode == 0:
            if any(marker in lowered for marker in _DEPENDENCY_FAILURE_MARKERS):
                return False, output.strip()
            if any(marker in lowered for marker in _NO_OP_MARKERS):
                return False, output.strip()
            # Invalidate the on-disk check cache so the next launch
            # re-queries with the freshly-installed version instead of
            # re-offering the same upgrade from a stale snapshot.
            try:
                CACHE_PATH.unlink(missing_ok=True)
            except Exception:
                pass
            return True, output.strip()
        # Try the next candidate only when the failure was clearly "wrong
        # package name" — any other error (network, perms, etc.) should
        # surface immediately without retrying against another target.
        if "is not installed" not in lowered:
            break
    return False, last_output.strip()


def relaunch_self() -> None:
    """Re-exec the current command so the just-upgraded code is loaded.

    `uv tool upgrade` replaces the package on disk, but THIS process still
    holds the old modules in memory — without a re-exec the user would keep
    running the old version (or have to quit and re-run by hand). Re-exec
    starts a fresh process on the new code. Best-effort: returns if exec
    fails so the caller can fall back to asking the user to restart.
    """
    import sys

    try:
        os.execv(sys.argv[0], sys.argv)
    except Exception:
        try:
            os.execv(sys.executable, [sys.executable, *sys.argv])
        except Exception:
            return  # caller prints "restart to use the new version"


def _default_upgrade_candidates() -> list[str]:
    """Ordered fallback list for `uv tool upgrade <name>`.

    Prefers whatever entry point the user invoked (argv[0]) — if they
    ran `worldlines`, try `worldlines` first; if they ran `neonrp`, try
    `neonrp` first. Falls back to the opposite name so whichever one is
    actually installed as a uv / pipx tool wins.
    """
    import sys
    from pathlib import Path

    names = ["worldlines", "neonrp"]
    try:
        argv0 = Path(sys.argv[0]).stem.lower()
        if argv0 in names:
            names.remove(argv0)
            names.insert(0, argv0)
    except Exception:
        pass
    return names


# ---------------------------------------------------------------------------
# Cache (avoid hitting network on every single launch)
# ---------------------------------------------------------------------------

def _read_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_cache(payload: dict[str, Any]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def check_for_update_cached(
    *,
    channel: str | None = None,
    max_age_seconds: int = 1 * 3600,
) -> UpdateCheckResult:
    """Like check_for_update, but cache the result for `max_age_seconds`.

    This is what launch-time callers should use to avoid slowing every
    startup with a network round-trip.
    """
    import time

    cache = _read_cache()
    ts = cache.get("ts")
    payload = cache.get("result")
    fresh = isinstance(ts, (int, float)) and (time.time() - float(ts)) < max_age_seconds
    if fresh and isinstance(payload, dict):
        try:
            # The cache only authoritatively holds remote-fetched fields
            # (latest_version, release_notes_url, channel). Local state
            # — current_version and install_mode — is re-read every time
            # so a silent upgrade or switch between editable / released
            # installs is reflected immediately and never loops on a
            # stale "update available" decision.
            target = upgrade_target()
            if payload.get("package", "neonrp") != target:
                raise ValueError("cache is for another package")
            latest = payload.get("latest_version")
            current = get_current_version(target)
            install_mode = detect_install_mode()
            latest_str = latest if isinstance(latest, str) else None
            update_available = bool(latest_str) and is_newer(latest_str, current)
            return UpdateCheckResult(
                current_version=current,
                latest_version=latest_str,
                channel=payload.get("channel", DEFAULT_CHANNEL),
                update_available=update_available,
                install_mode=install_mode,
                release_notes_url=payload.get("release_notes_url"),
                error=payload.get("error"),
                package=target,
            )
        except Exception:
            pass

    result = check_for_update(channel=channel)
    _write_cache({"ts": time.time(), "result": result.to_json()})
    return result


def format_result_for_human(result: UpdateCheckResult) -> str:
    lines: list[str] = []
    lines.append(f"  current: {result.current_version}")
    lines.append(f"  channel: {result.channel}")
    lines.append(f"  install: {result.install_mode.kind} ({result.install_mode.detail})")
    if result.error:
        lines.append(f"  error:   {result.error}")
        return "\n".join(lines)
    if not result.latest_version:
        lines.append("  latest:  (unknown)")
        return "\n".join(lines)
    lines.append(f"  latest:  {result.latest_version}")
    if result.update_available:
        lines.append("  status:  update available")
        if result.release_notes_url:
            lines.append(f"  notes:   {result.release_notes_url}")
        if not result.install_mode.allow_auto_apply:
            lines.append("  note:    auto-apply disabled for this install (editable/unknown)")
    else:
        lines.append("  status:  up-to-date")
    return "\n".join(lines)
