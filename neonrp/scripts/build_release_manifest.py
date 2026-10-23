#!/usr/bin/env python3
"""Build / merge `releases.json` for one package (run by release.yml).

「清单里面需要有两个分开的版本号 … 为了兼容以前的版本,
latest.stable 按照 worldlines 的逻辑填写,剩下分开 neonrp 和 worldlines」.

Two repos publish to the SAME manifest, each touching only its own entry:

    NeonRP/release.yml      → python scripts/build_release_manifest.py --package neonrp     --version 0.4.1
    WorldLines/release.yml  → python scripts/build_release_manifest.py --package worldlines --version 0.4.1

Schema v2 (backward compatible — old clients only read `latest` / `releases`):

    {
      "schema": 2,
      "product": "neonrp",
      "latest":   { "stable": "0.4.0" },          # LEGACY: follows worldlines (old worldlines-installed
                                                   #         clients upgrade the shim; never point them at an
                                                   #         engine version their shim does not pin)
      "releases": { ... },                          # LEGACY: union of both packages' releases (notes lookup)
      "packages": {
        "neonrp":     { "latest": { "stable": "0.4.1" }, "releases": { "0.4.1": {...} } },
        "worldlines": { "latest": { "stable": "0.4.0" }, "releases": { "0.4.0": {...} } }
      }
    }

`--existing` is the manifest currently served (fetched by the workflow; may be
missing or empty on the very first run). When the OTHER package has no entry
yet, its latest is seeded from PyPI (`--seed-from-pypi`, best-effort) so the
legacy field is never blank.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKAGES = ("neonrp", "worldlines")
LEGACY_FOLLOWS = "worldlines"


def _load(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def pypi_latest(package: str, timeout: float = 10.0) -> str | None:
    try:
        req = urllib.request.Request(f"https://pypi.org/pypi/{package}/json", headers={"User-Agent": "neonrp-release"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        v = (data.get("info") or {}).get("version")
        return str(v) if v else None
    except Exception:  # noqa: BLE001 — seeding is best-effort
        return None


def build(
    existing: dict[str, Any],
    *,
    package: str,
    version: str,
    channel: str = "stable",
    notes_url: str | None = None,
    published_at: str | None = None,
    seed: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    if package not in PACKAGES:
        raise ValueError(f"package must be one of {PACKAGES}")
    published_at = published_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {
        "channel": channel,
        "published_at": published_at,
        "notes_url": notes_url or f"https://github.com/LudicDynamics/WorldLines/releases/tag/v{version}",
        "artifacts": {"python-wheel": {"kind": "pypi", "version": version, "packages": [package]}},
    }

    out: dict[str, Any] = {"schema": 2, "product": "neonrp"}
    packages: dict[str, Any] = {}
    old_packages = existing.get("packages") if isinstance(existing.get("packages"), dict) else {}
    for name in PACKAGES:
        old = old_packages.get(name) if isinstance(old_packages.get(name), dict) else {}
        packages[name] = {
            "latest": dict(old.get("latest") or {}),
            "releases": dict(old.get("releases") or {}),
        }
    # A v1 manifest (no `packages`) only knew ONE version and it could have been
    # written by either repo (today's was the engine's), so its legacy fields
    # say nothing reliable about the other package. The other package's
    # version comes from PyPI (`seed`); the v1 `releases` history is only
    # kept in the legacy union so old notes links keep resolving.
    legacy_history: dict[str, Any] = {}
    if not old_packages and isinstance(existing.get("releases"), dict):
        legacy_history = dict(existing["releases"])

    packages[package]["latest"][channel] = version
    packages[package]["releases"][version] = entry

    # Seed the other package when we know nothing about it yet (PyPI is the
    # authority for what is actually installable).
    for name in PACKAGES:
        if not packages[name]["latest"].get(channel):
            seeded = (seed or {}).get(name)
            if seeded:
                packages[name]["latest"][channel] = seeded

    out["packages"] = packages
    # Legacy fields: follow worldlines when known, else this package.
    legacy_src = packages[LEGACY_FOLLOWS]["latest"].get(channel) or packages[package]["latest"].get(channel)
    out["latest"] = {channel: legacy_src}
    merged_releases: dict[str, Any] = dict(legacy_history)
    for name in PACKAGES:
        merged_releases.update(packages[name]["releases"])
    out["releases"] = merged_releases
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True, choices=PACKAGES)
    ap.add_argument("--version", required=True)
    ap.add_argument("--channel", default="stable")
    ap.add_argument("--existing", default=None, help="currently served releases.json (optional)")
    ap.add_argument("--out", default="releases.json")
    ap.add_argument("--notes-url", default=None)
    ap.add_argument("--seed-from-pypi", action="store_true", help="fill the other package's latest from PyPI when unknown")
    args = ap.parse_args(argv)

    existing = _load(args.existing)
    seed = {p: pypi_latest(p) for p in PACKAGES if p != args.package} if args.seed_from_pypi else {}
    manifest = build(
        existing,
        package=args.package,
        version=args.version.lstrip("v"),
        channel=args.channel,
        notes_url=args.notes_url,
        seed=seed,
    )
    Path(args.out).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"latest": manifest["latest"], "packages": {k: v["latest"] for k, v in manifest["packages"].items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
