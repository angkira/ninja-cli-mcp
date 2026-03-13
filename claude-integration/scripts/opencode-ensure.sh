#!/usr/bin/env bash
# Ensure opencode serve is running for a given project directory.
# Usage: opencode-ensure.sh <repo_root>
# Output: port number on stdout

set -euo pipefail

REPO_ROOT="${1:?Usage: opencode-ensure.sh <repo_root>}"
REPO_HASH=$(echo -n "$REPO_ROOT" | sha256sum | cut -c1-16)
PORT_FILE="$HOME/.cache/ninja-mcp/opencode-serve-${REPO_HASH}.port"
OPENCODE_BIN="${NINJA_CODE_BIN:-$(which opencode 2>/dev/null || echo "$HOME/.opencode/bin/opencode")}"
PORT_START="${NINJA_OPENCODE_SERVE_PORT_START:-20000}"

mkdir -p "$HOME/.cache/ninja-mcp"

# Check if already running
if [ -f "$PORT_FILE" ]; then
    PORT=$(cat "$PORT_FILE")
    if curl -sf "http://127.0.0.1:${PORT}/session" >/dev/null 2>&1; then
        echo "$PORT"
        exit 0
    fi
    rm -f "$PORT_FILE"
fi

# Find free port
PORT=$PORT_START
while [ $PORT -lt 21000 ]; do
    if ! curl -sf "http://127.0.0.1:${PORT}/session" >/dev/null 2>&1; then
        break
    fi
    PORT=$((PORT + 1))
done

# Start server
nohup "$OPENCODE_BIN" serve --port "$PORT" --hostname 127.0.0.1 \
    >/dev/null 2>&1 &

# Wait for ready (max 15s)
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${PORT}/session" >/dev/null 2>&1; then
        echo "$PORT" > "$PORT_FILE"
        echo "$PORT"
        exit 0
    fi
    sleep 0.5
done

echo "ERROR: opencode serve failed to start on port $PORT" >&2
exit 1
