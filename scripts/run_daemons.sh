#!/usr/bin/env bash
#
# run_daemons.sh - Launch ninja-mcp module daemons with a robust PATH.
#
# Designed for systemd user services, where the shell environment (nvm,
# ~/.local/bin, operator CLIs) is not available. Builds PATH from the common
# user tool directories, sources ~/.ninja-mcp.env, then delegates to the
# ninja-mcp daemon manager.
#
# Usage: run_daemons.sh [start|stop|restart|status]

set -euo pipefail

ACTION="${1:-start}"

# User-writable tool dirs that hold operator binaries (opencode, aider, uv…).
_extra=(
    "$HOME/.local/bin"
    "$HOME/.opencode/bin"
    "$HOME/.bun/bin"
    "$HOME/.cargo/bin"
    "$HOME/.local/share/uv/tools/ninja-mcp/bin"
)
# nvm-managed Node bins (codex is installed here on this host).
if [ -d "$HOME/.nvm/versions/node" ]; then
    for _d in "$HOME"/.nvm/versions/node/*/bin; do
        [ -d "$_d" ] && _extra+=("$_d")
    done
fi
for _d in "${_extra[@]}"; do
    [ -d "$_d" ] && export PATH="$_d:$PATH"
done

# Load user config (NINJA_* settings incl. NINJA_CODE_BIN, ports).
if [ -f "$HOME/.ninja-mcp.env" ]; then
    set -a
    # shellcheck disable=SC1090,SC1091
    . "$HOME/.ninja-mcp.env"
    set +a
fi

exec ninja-mcp daemon "$ACTION"
