#!/usr/bin/env bash
# Build the LocalShell SPA and package it as dist/worldlines-spa.zip.
#
# This is the artifact the engine's SPA assembly seam (NEONRP_SPA_DIR)
# consumes: unzip it into a directory, point NEONRP_SPA_DIR at that
# directory, and `neonrp web` serves it at /local. The zip therefore holds
# the built files at its ROOT (index.html, assets/, …) with no wrapping
# folder — unzip -d <dir> yields a directory that is already a valid
# NEONRP_SPA_DIR.
#
# SAME-ORIGIN build: both endpoint vars are explicitly blanked. Blank is
# meaningful (see ui/src/play/playClient.ts) — it selects relative-path
# fetches, because the engine serves this bundle itself. Leaving them
# merely *unset* is not equivalent: a local .env.production would then
# bake hosted URLs into a bundle meant to talk to localhost.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_DIR="${WORLDLINES_UI_DIR:-$REPO_ROOT/ui}"
OUT_DIR="$REPO_ROOT/dist"
OUT_ZIP="$OUT_DIR/worldlines-spa.zip"

if [ ! -f "$UI_DIR/package.json" ]; then
  echo "error: SPA source not found at $UI_DIR" >&2
  echo "       (override with WORLDLINES_UI_DIR=/path/to/ui)" >&2
  exit 1
fi

command -v zip >/dev/null 2>&1 || { echo "error: 'zip' is required but not installed" >&2; exit 1; }

echo "==> building SPA (same-origin: VITE_PLAY_ENDPOINT= VITE_CREATE_ENDPOINT=)"
(
  cd "$UI_DIR"
  if [ -f package-lock.json ]; then
    npm ci --no-audit --no-fund
  else
    npm install --no-audit --no-fund
  fi
  VITE_CREATE_ENDPOINT= VITE_PLAY_ENDPOINT= npm run build:local
)

if [ ! -f "$UI_DIR/dist-local/index.html" ]; then
  echo "error: build produced no dist-local/index.html in $UI_DIR" >&2
  exit 1
fi

echo "==> packaging $OUT_ZIP"
mkdir -p "$OUT_DIR"
rm -f "$OUT_ZIP"
# -X drops extra file attributes (uid/gid, mac extras) so identical input
# produces an identical archive across machines.
( cd "$UI_DIR/dist-local" && zip -r -q -X "$OUT_ZIP" . )

echo "==> done: $OUT_ZIP ($(du -h "$OUT_ZIP" | cut -f1), $(unzip -l "$OUT_ZIP" | tail -1 | awk '{print $2}') files)"
