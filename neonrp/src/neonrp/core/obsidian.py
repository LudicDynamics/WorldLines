"""Obsidian, the application — getting a projected vault *open* in one step.

`core/vault.py` writes the notes. This module does the part that turned out to
be the actual blocker ("Obsidian 的这个连接,我其实还没有
跑通"): the app on the desktop has to know the folder is a vault, and has to
be pointed at it. Two facts about Obsidian shape everything here, both
verified by hand on macOS 2026-09-08:

1. **`obsidian://open?path=…` only works for a vault Obsidian already knows.**
   An unregistered folder gets "Unable to find a vault for the URL". So we
   register the folder ourselves, in the same JSON file the app keeps its
   vault list in.

2. **Obsidian reads that file only at startup.** Writing to it while the app
   is running changes nothing until the next launch. So "one step" has to
   include a restart when Obsidian is already up — there is no IPC that adds
   a vault to a live instance.

Everything else (graph colours, reading view, the canvas) is plain files in
`.obsidian/`, seeded once and never overwritten: those files are the user's
settings the moment they touch them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIRNAME = ".obsidian"

# Graph colour groups by folder. Obsidian's graph is flat, so colour is the
# one thing that lets kinds be told apart at a glance. Colours are packed
# 0xRRGGBB ints, the way graph.json stores them.
_GRAPH_CONFIG = {
    "colorGroups": [
        {"query": "path:角色", "color": {"a": 1, "rgb": 0xFF4757}},
        {"query": "path:地点", "color": {"a": 1, "rgb": 0x18FF82}},
        {"query": "path:世界设定", "color": {"a": 1, "rgb": 0x5DA9FF}},
        {"query": "path:我的笔记", "color": {"a": 1, "rgb": 0xFFD166}},
        {"query": "path:世界.md", "color": {"a": 1, "rgb": 0xFFFFFF}},
    ],
    "showTags": False,
    "showAttachments": False,
    "hideUnresolved": True,
    "showOrphans": True,
    "nodeSizeMultiplier": 1.2,
}

# Generated notes are read, not edited — open them in reading view so the
# frontmatter shows as properties instead of a YAML block at the top.
_APP_CONFIG = {
    "defaultViewMode": "preview",
    "readableLineLength": True,
}


def registry_path() -> Path:
    """Where this platform's Obsidian keeps its list of vaults."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "obsidian" / "obsidian.json"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "obsidian" / "obsidian.json"


def is_installed() -> bool:
    if sys.platform == "darwin":
        return Path("/Applications/Obsidian.app").exists() or (
            Path.home() / "Applications" / "Obsidian.app"
        ).exists()
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA") or ""
        return bool(local) and (Path(local) / "Obsidian" / "Obsidian.exe").exists()
    return shutil.which("obsidian") is not None or Path("/usr/bin/obsidian").exists()


def is_running() -> bool:
    """Best effort. Only macOS is answered confidently; elsewhere assume not."""
    if sys.platform == "darwin":
        try:
            return subprocess.run(
                ["pgrep", "-x", "Obsidian"], capture_output=True, timeout=3
            ).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    return False


def vault_id(vault_dir: Path) -> str:
    """Obsidian uses 16 hex chars; derive ours from the path so re-registering
    the same folder is idempotent even if the registry was wiped."""
    return hashlib.sha1(str(Path(vault_dir).resolve()).encode("utf-8")).hexdigest()[:16]


def register_vault(vault_dir: Path, registry: Path | None = None) -> bool:
    """Add the folder to Obsidian's vault list. Returns True if it was new.

    Never removes or rewrites other entries — that file is the user's.
    """
    registry = registry or registry_path()
    target = str(Path(vault_dir).resolve())
    data: dict = {}
    if registry.exists():
        try:
            data = json.loads(registry.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            data = {}
    vaults = data.setdefault("vaults", {})
    if not isinstance(vaults, dict):
        vaults = data["vaults"] = {}
    for entry in vaults.values():
        if isinstance(entry, dict) and entry.get("path") == target:
            return False
    vaults[vault_id(vault_dir)] = {"path": target, "ts": int(time.time() * 1000)}
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return True


def is_registered(vault_dir: Path, registry: Path | None = None) -> bool:
    registry = registry or registry_path()
    if not registry.exists():
        return False
    try:
        data = json.loads(registry.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return False
    target = str(Path(vault_dir).resolve())
    vaults = data.get("vaults") or {}
    return any(
        isinstance(v, dict) and v.get("path") == target for v in vaults.values()
    )


def seed_config(vault_dir: Path) -> list[str]:
    """Write `.obsidian/` defaults that make a generated vault readable on
    first open. Only files that do not exist yet — once Obsidian or the user
    has touched them they are settings, not ours."""
    cfg = Path(vault_dir) / _CONFIG_DIRNAME
    written: list[str] = []
    for name, payload in (("graph.json", _GRAPH_CONFIG), ("app.json", _APP_CONFIG)):
        path = cfg / name
        if path.exists():
            continue
        try:
            cfg.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(name)
        except OSError:
            logger.debug("obsidian config seed skipped: %s", name, exc_info=True)
    return written


def open_uri(vault_dir: Path, file: str | None = None) -> str:
    """`obsidian://open?path=<vault>` — or a file inside it, so the app lands
    on the world page rather than whatever was open last."""
    target = Path(vault_dir).resolve()
    if file:
        target = target / file
    return "obsidian://open?path=" + urllib.parse.quote(str(target))


def quit_app(timeout: float = 6.0) -> bool:
    """Ask Obsidian to quit and wait for it. macOS only; elsewhere returns False
    so the caller tells the user instead of pretending."""
    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(
            ["osascript", "-e", 'quit app "Obsidian"'], capture_output=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_running():
            return True
        time.sleep(0.25)
    return not is_running()


@dataclass
class OpenReport:
    vault_dir: Path
    registered: bool = False  # newly added to the registry this time
    seeded: list[str] = field(default_factory=list)
    restarted: bool = False
    launched: bool = False
    needs_restart: bool = False  # running, registry changed, and we did not restart
    installed: bool = True
    notes: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = []
        if not self.installed:
            out.append("没找到 Obsidian —— 装好之后再跑一次就能一键打开。")
        if self.registered:
            out.append("已把这个 vault 登记进 Obsidian。")
        if self.seeded:
            out.append("已写入初始配置(图谱按类型上色、默认阅读视图)。")
        if self.restarted:
            out.append("Obsidian 在跑且不认识新 vault,已替你重启它。")
        if self.needs_restart:
            out.append("Obsidian 只在启动时读 vault 列表 —— 重启一次它就能打开这个 vault。")
        if self.launched:
            out.append("已打开。")
        out.extend(self.notes)
        return out


def open_vault(
    vault_dir: Path,
    *,
    land_on: str | None = "世界.canvas",
    restart: bool = True,
    launcher=None,
) -> OpenReport:
    """The one step: register → seed config → (restart if needed) → open.

    `restart=False` for callers who must not yank the user's app out from
    under them (an agent tool call); they get `needs_restart` back instead.
    """
    vault_dir = Path(vault_dir)
    report = OpenReport(vault_dir=vault_dir, installed=is_installed())
    report.seeded = seed_config(vault_dir)

    try:
        report.registered = register_vault(vault_dir)
    except OSError:
        logger.debug("obsidian registry write failed", exc_info=True)
        report.notes.append("写不进 Obsidian 的 vault 列表;请手动「打开文件夹作为仓库」。")
        return report

    if not report.installed:
        return report

    # A freshly registered vault is invisible to a running instance.
    if report.registered and is_running():
        if restart and quit_app():
            report.restarted = True
        elif restart:
            report.notes.append("没能让 Obsidian 退出;请手动重启它。")
            report.needs_restart = True
            return report
        else:
            report.needs_restart = True
            return report

    uri = open_uri(vault_dir, land_on if land_on and (vault_dir / land_on).exists() else None)
    try:
        (launcher or webbrowser.open)(uri)
        report.launched = True
    except Exception:  # noqa: BLE001 — a failed open is a message, not a crash
        logger.debug("obsidian open failed", exc_info=True)
        report.notes.append(f"打不开 Obsidian;可以手动访问 {uri}")
    return report
