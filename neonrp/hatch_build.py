"""Wheel build hook (10-23): with ``NEONRP_BUNDLE_PRIVATE=<dir of the neonrp_private package>`` the wheel also carries
that package (top level ``neonrp_private``, found by core/paths.private_dir as an installed package). Unset = the
open engine alone — the build the open repo makes. Always (sdist and wheel): the skills for coding agents (``SKILLS``,
10-26), copied from their one source."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


# Skills for coding agents shipped with the engine (neonrp.spec.SKILLS). One source: the workbench folder. The sdist carries
# it as _skills/<name> (a wheel built from the sdist finds it there); the wheel as neonrp/_skills/<name>.
SKILLS = ("world-creation",)


def skill_sources(root: Path) -> dict[str, Path]:
    """name → the skill folder, from a source checkout (worldlines/workbench/.claude/skills), the open repo
    (neonrp/ beside the root .claude/skills) or an unpacked sdist (_skills)."""
    out: dict[str, Path] = {}
    for name in SKILLS:
        for d in (root / "worldlines" / "workbench" / ".claude" / "skills" / name,
                  root.parent / ".claude" / "skills" / name, root / "_skills" / name):
            if (d / "SKILL.md").is_file():
                out[name] = d.resolve()
                break
        else:
            raise RuntimeError(f"skill {name!r} not found under {root} — the wheel would ship without it")
    return out


class BundlePrivate(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        for name, d in skill_sources(Path(self.root)).items():
            build_data["force_include"][str(d)] = (f"neonrp/_skills/{name}" if self.target_name == "wheel" else f"_skills/{name}")
        src = os.environ.get("NEONRP_BUNDLE_PRIVATE", "").strip()
        if not src or self.target_name != "wheel":
            return
        d = Path(src).expanduser().resolve()
        if not (d / "__init__.py").is_file():
            raise RuntimeError(f"NEONRP_BUNDLE_PRIVATE is not a package folder: {d}")
        build_data["force_include"][str(d)] = "neonrp_private"
