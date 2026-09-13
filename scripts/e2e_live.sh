#!/usr/bin/env bash
#
# e2e_live.sh - Run live battle E2E tests against real models.
#
# Boots the real ninja-coder and ninja-agent MCP servers over stdio, connects
# an MCP client, and drives real tool calls in a temp git repo using the
# host's configured CLI (opencode by default) + the OPENROUTER key.
#
# These are REAL model runs — slow and billable.
#
# Usage:
#   ./scripts/e2e_live.sh [--repo /tmp/opencode/e2e_battle_repo] [--sequential|--parallel|--delegate|--all]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

REPO="/tmp/opencode/e2e_battle_repo"
SCOPE="all"

while [ $# -gt 0 ]; do
    case "$1" in
        --repo) REPO="$2"; shift 2 ;;
        --sequential) SCOPE="sequential" ; shift ;;
        --parallel) SCOPE="parallel" ; shift ;;
        --delegate) SCOPE="delegate" ; shift ;;
        --all) SCOPE="all" ; shift ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

export REPO_PATH="$REPO"
export E2E_SCOPE="$SCOPE"

echo "Running live E2E (scope=$SCOPE) in $REPO"
echo "  NINJA_CODE_BIN=${NINJA_CODE_BIN:-opencode}"
echo "  model: $(grep '^NINJA_MODEL' ~/.ninja-mcp.env | head -1 | cut -d= -f2-)"

uv run python "$SCRIPT_DIR/e2e_live.py"