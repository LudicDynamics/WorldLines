"""Wheel build hook (10-23): with ``NEONRP_BUNDLE_PRIVATE=<dir of the neonrp_private package>`` the wheel also carries
that package (top level ``neonrp_private``, found by core/paths.private_dir as an installed package). Unset = the
open engine alone — the build the open repo makes."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class BundlePrivate(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        src = os.environ.get("NEONRP_BUNDLE_PRIVATE", "").strip()
        if not src or self.target_name != "wheel":
            return
        d = Path(src).expanduser().resolve()
        if not (d / "__init__.py").is_file():
            raise RuntimeError(f"NEONRP_BUNDLE_PRIVATE is not a package folder: {d}")
        build_data["force_include"][str(d)] = "neonrp_private"
