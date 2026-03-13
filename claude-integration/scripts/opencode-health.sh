#!/usr/bin/env bash
# Check if opencode serve is healthy for a repo.
# Usage: opencode-health.sh <repo_root>

set -euo pipefail

REPO_ROOT="${1:?Usage: opencode-health.sh <repo_root>}"
REPO_HASH=$(echo -n "$REPO_ROOT" | sha256sum | cut -c1-16)
PORT_FILE="$HOME/.cache/ninja-mcp/opencode-serve-${REPO_HASH}.port"

if [ ! -f "$PORT_FILE" ]; then
    echo "not running"
    exit 1
fi

PORT=$(cat "$PORT_FILE")
if curl -sf "http://127.0.0.1:${PORT}/session" >/dev/null 2>&1; then
    echo "healthy on port $PORT"
    exit 0
else
    rm -f "$PORT_FILE"
    echo "dead (port $PORT)"
    exit 1
fi
