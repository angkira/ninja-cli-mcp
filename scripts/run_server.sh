#!/usr/bin/env bash
#
# run_server.sh - Start the ninja-cli-mcp MCP server
#
# This script runs the MCP server in stdio mode for integration with
# Claude Code, Copilot CLI, or other MCP clients.
#
# Usage: ./scripts/run_server.sh
#
# Environment variables:
#   OPENROUTER_API_KEY  - API key for OpenRouter (required)
#   NINJA_MODEL         - Model to use (default: anthropic/claude-sonnet-4)
#   OPENROUTER_MODEL    - Alternative model setting
#   NINJA_CODE_BIN      - Path to AI Code CLI (default: ninja-code)
#   OPENAI_BASE_URL     - OpenAI-compatible API URL (default: https://openrouter.ai/api/v1)
#

set -euo pipefail

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Load environment config if it exists
if [[ -f "$HOME/.ninja-cli-mcp.env" ]]; then
    source "$HOME/.ninja-cli-mcp.env"
fi

# Check for API key
if [[ -z "${OPENROUTER_API_KEY:-}" ]] && [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "Warning: Neither OPENROUTER_API_KEY nor OPENAI_API_KEY is set" >&2
    echo "The server will start but AI code CLI calls may fail" >&2
fi

# Set defaults
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://openrouter.ai/api/v1}"

# Model priority: NINJA_MODEL > OPENROUTER_MODEL > OPENAI_MODEL > default
if [[ -n "${NINJA_MODEL:-}" ]]; then
    export OPENAI_MODEL="${NINJA_MODEL}"
elif [[ -n "${OPENROUTER_MODEL:-}" ]]; then
    export OPENAI_MODEL="${OPENROUTER_MODEL}"
elif [[ -z "${OPENAI_MODEL:-}" ]]; then
    export OPENAI_MODEL="anthropic/claude-sonnet-4"
fi

# If OPENROUTER_API_KEY is set, use it as OPENAI_API_KEY
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    export OPENAI_API_KEY="${OPENROUTER_API_KEY}"
fi

# Run the server
exec uv run python -m ninja_cli_mcp.server
