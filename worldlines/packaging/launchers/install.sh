#!/usr/bin/env sh
# WorldLines / NeonRP bootstrap installer.
#
# Usage:
#   curl -LsSf https://worldlines.gg/install.sh | sh
#
# What it does:
#   1. Ensures `uv` is installed (fetches it from astral.sh if missing).
#   2. Installs `worldlines` (which pins the matching `neonrp` runtime).
#   3. Prints a quick-start hint + the exact PATH line to add to ~/.zshrc
#      / ~/.bashrc — we deliberately don't auto-modify your dotfiles.
#
# Design notes:
#   - POSIX-sh compatible (no bash-isms) so macOS + minimal Linux shells work.
#   - `set -e` so partial failures don't leave the user thinking it worked.
#   - Non-interactive; prints what it's doing so the user can audit via
#     `curl ... | less` before piping to sh.
#   - In-process PATH export lets the *current* shell run `worldlines`
#     immediately. Persistence across new terminals is the user's call.

set -eu

PACKAGE="${WORLDLINES_PACKAGE:-worldlines}"

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*" >&2; }
die() { printf '\033[1;31mxx\033[0m  %s\n' "$*" >&2; exit 1; }

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "required command '$1' not found on PATH"
}

# Make uv-tool default bin dirs visible for this script run + for the
# user's *current* terminal once `curl | sh` finishes. We don't write
# to ~/.zshrc here — that's shown as a copy-paste line at the end.
# Idempotent: case checks make sure we don't double-prepend.
case ":$PATH:" in
    *":$HOME/.local/bin:"*) : ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
case ":$PATH:" in
    *":$HOME/.cargo/bin:"*) : ;;
    *) export PATH="$HOME/.cargo/bin:$PATH" ;;
esac

# Step 1 — ensure uv (astral's Python/tool installer).
if command -v uv >/dev/null 2>&1; then
    log "uv already installed ($(uv --version))"
else
    log "installing uv from astral.sh"
    need_cmd curl
    curl -LsSf https://astral.sh/uv/install.sh | sh

    command -v uv >/dev/null 2>&1 || die "uv installed but not found on PATH; open a new shell and re-run this script"
fi

# Step 1.5 — optional China mirror. Mainland networks often throttle
# PyPI's default CDN; pass `CHINA_MIRROR=1` to route uv through TUNA.
# Respects an explicitly-set UV_DEFAULT_INDEX (user override wins).
if [ "${CHINA_MIRROR:-0}" = "1" ] && [ -z "${UV_DEFAULT_INDEX:-}" ]; then
    export UV_DEFAULT_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
    log "CHINA_MIRROR=1 → using Tsinghua PyPI mirror"
fi

# Step 2 — install the CLI via uv tool.
# The `worldlines` wheel pins `neonrp[discord]` transitively (since
# 0.1.8), so the Discord bridge wires up out of the box — no extra
# spelling needed in the install command.
log "installing $PACKAGE"
uv tool install --force "$PACKAGE"

# Step 2.5 — figure out where uv put the bin and which rc file the user
# is on, so we can show them the exact one-liner to paste. We do NOT
# modify their dotfiles automatically — many devs manage PATH themselves
# (chezmoi / Stow / hand-curated rc), and silent edits break that.
TOOL_BIN_DIR=$(uv tool dir --bin 2>/dev/null || printf '%s' "$HOME/.local/bin")

SHELL_NAME=$(basename "${SHELL:-sh}")
case "$SHELL_NAME" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash) RC_FILE="$HOME/.bashrc" ;;
    fish) RC_FILE="$HOME/.config/fish/config.fish" ;;
    *)    RC_FILE="" ;;
esac

# Step 3 — quick-start hint (printf so ANSI escapes actually render).
GREEN=$(printf '\033[1;32m')
DIM=$(printf '\033[2m')
RESET=$(printf '\033[0m')

printf '\n%s✓ %s installed%s\n\n' "$GREEN" "$PACKAGE" "$RESET"

printf 'Next steps:\n\n'
printf '  %-20s # launch the guided world picker\n' "$PACKAGE"
printf '  %-20s # full engine CLI\n' "neonrp --help"
printf '  %-20s # check for updates\n\n' "neonrp self-update"

# Always show the PATH line. The current terminal is already covered by
# the in-process export at the top — this is for *new* terminals.
printf 'To use %s in any new terminal, add this to your shell config:\n\n' "$PACKAGE"
printf '    %sexport PATH="%s:$PATH"%s\n\n' "$GREEN" "$TOOL_BIN_DIR" "$RESET"

if [ -n "$RC_FILE" ]; then
    printf '  %sOne-liner for %s (%s):%s\n' "$DIM" "$SHELL_NAME" "$RC_FILE" "$RESET"
    printf '    echo '\''export PATH="%s:$PATH"'\'' >> %s\n' "$TOOL_BIN_DIR" "$RC_FILE"
    printf '    source %s\n\n' "$RC_FILE"
fi

printf 'Docs: https://github.com/LudicDynamics/WorldLines\n\n'
