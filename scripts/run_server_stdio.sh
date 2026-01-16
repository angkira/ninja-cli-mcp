#!/bin/bash
# Run ninja-cli-mcp server in STDIO mode (for direct spawning)

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load environment variables if .env file exists
if [ -f "$HOME/.ninja-mcp.env" ]; then
    set -a
    source "$HOME/.ninja-mcp.env"
    set +a
elif [ -f "$HOME/.ninja-cli-mcp.env" ]; then
    # Legacy config file name - still supported
    set -a
    source "$HOME/.ninja-cli-mcp.env"
    set +a
fi

# Run the server
cd "$PROJECT_ROOT"
exec uv run python -m ninja_cli_mcp.server
