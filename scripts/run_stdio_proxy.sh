#!/usr/bin/env bash
#
# run_stdio_proxy.sh - Start stdio-to-HTTP proxy for Copilot CLI
#
# This script starts a proxy that bridges stdio (used by Copilot CLI)
# to the HTTP daemon (shared by all clients).
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load configuration
CONFIG_FILE="${HOME}/.ninja-cli-mcp.env"
if [[ -f "$CONFIG_FILE" ]]; then
    set -a
    source "$CONFIG_FILE"
    set +a
fi

# Configuration
PORT="${NINJA_HTTP_PORT:-8947}"
HOST="${NINJA_HTTP_HOST:-127.0.0.1}"
export NINJA_HTTP_URL="http://${HOST}:${PORT}/mcp"

# Ensure daemon is running
if ! curl -s "http://${HOST}:${PORT}/mcp" -X POST \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":0,"method":"ping"}' &>/dev/null; then
    
    echo "Warning: Daemon not responding at http://${HOST}:${PORT}" >&2
    echo "Starting daemon..." >&2
    systemctl --user start ninja-cli-mcp 2>/dev/null || true
    sleep 2
fi

# Run proxy
cd "$PROJECT_ROOT"
exec uv run python scripts/stdio_proxy.py
