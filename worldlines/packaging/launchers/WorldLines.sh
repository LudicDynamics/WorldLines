#!/usr/bin/env bash
# WorldLines — Linux double-clickable launcher.
#
# On most Linux desktop environments, marking this file executable
# (chmod +x) and double-clicking runs it in a terminal.
# This script:
#   1. Ensures `uv` + `worldlines` are installed (via worldlines.gg/install.sh).
#   2. Runs `uv tool upgrade worldlines` to pull the latest.
#   3. Execs `worldlines` so the TUI takes over the terminal window.
#
# Companion: WorldLines.command (macOS), WorldLines.bat (Windows).

set -eu

INSTALLER_URL="${WORLDLINES_INSTALLER_URL:-https://worldlines.gg/install.sh}"
FALLBACK_URL="https://github.com/LudicDynamics/WorldLines/releases/latest/download/install.sh"

printf '\033]0;WorldLines\007'   # tab title
clear 2>/dev/null || true

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
