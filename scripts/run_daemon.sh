#!/bin/bash
# Start ninja-cli-mcp HTTP/SSE daemon
# This is specifically for daemon mode with systemd

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Load environment
if [[ -f "$HOME/.ninja-cli-mcp.env" ]]; then
    source "$HOME/.ninja-cli-mcp.env"
fi

# Configuration
PORT="${NINJA_HTTP_PORT:-3000}"
HOST="${NINJA_HTTP_HOST:-127.0.0.1}"

echo "Starting ninja-cli-mcp HTTP/SSE daemon on $HOST:$PORT" >&2

# Run HTTP server with uv (uses virtualenv)
exec uv run python "$SCRIPT_DIR/http_server.py" --host "$HOST" --port "$PORT"
