#!/usr/bin/env bash
# WorldLines — macOS double-clickable launcher.
#
# macOS opens `.command` files in Terminal.app when double-clicked.
# This script:
#   1. Ensures `uv` + `worldlines` are installed (via worldlines.gg/install.sh).
#   2. Runs `uv tool upgrade worldlines` to pull the latest.
#   3. Execs `worldlines` so the TUI takes over the Terminal window.
#
# Companion: WorldLines.sh (Linux), WorldLines.bat (Windows).

set -eu

INSTALLER_URL="${WORLDLINES_INSTALLER_URL:-https://worldlines.gg/install.sh}"
FALLBACK_URL="https://github.com/LudicDynamics/WorldLines/releases/latest/download/install.sh"

printf '\033]0;WorldLines\007'   # tab title
clear 2>/dev/null || true

# Self-repair: if the user got this far (past Gatekeeper via right-click
# → Open), strip the com.apple.quarantine xattr so future double-clicks
# open without any prompt at all.
if command -v xattr >/dev/null 2>&1; then
    xattr -d com.apple.quarantine "$0" >/dev/null 2>&1 || true
fi

echo "  🌍 WorldLines launcher"
echo

have_cmd() { command -v "$1" >/dev/null 2>&1; }

if ! have_cmd worldlines; then
    echo "  worldlines not installed yet — running first-time setup"
    echo
    if ! curl -LsSf "$INSTALLER_URL" | sh; then
        echo "  primary installer failed — falling back to GitHub direct URL"
        curl -LsSf "$FALLBACK_URL" | sh
    fi
    # Refresh PATH so this shell sees the newly-installed binary.
    for p in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        case ":$PATH:" in *":$p:"*) : ;; *) export PATH="$p:$PATH" ;; esac
    done
    hash -r 2>/dev/null || true
else
    echo "  checking for updates..."
    have_cmd uv && uv tool upgrade worldlines 2>/dev/null || true
fi

if ! have_cmd worldlines; then
    echo
    echo "  ✗ setup finished but 'worldlines' is still not on PATH."
    echo "  Open a new terminal and run: worldlines"
    echo
    read -rp "  Press Enter to close this window..." _
    exit 1
fi

echo
exec worldlines
