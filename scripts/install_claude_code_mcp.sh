#!/usr/bin/env bash
#
# install_claude_code_mcp.sh - Register ninja-cli-mcp with Claude Code
#
# This script registers the MCP server with Claude Code using the
# `claude mcp add` command.
#
# Usage: ./scripts/install_claude_code_mcp.sh
#
# Prerequisites:
#   - Claude Code CLI installed (claude command available)
#   - OPENROUTER_API_KEY or OPENAI_API_KEY environment variable set
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "=========================================="
echo "  Claude Code MCP Integration"
echo "=========================================="
echo ""

# Check for Claude CLI
info "Checking for Claude Code CLI..."
if command -v claude &> /dev/null; then
    CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
    success "Claude Code CLI found: $CLAUDE_VERSION"
else
    error "Claude Code CLI not found. Please install Claude Code first."
fi

# Check for API key
info "Checking for API key..."
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    success "OPENROUTER_API_KEY is set"
    API_KEY_VAR="OPENROUTER_API_KEY"
elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
    success "OPENAI_API_KEY is set"
    API_KEY_VAR="OPENAI_API_KEY"
else
    error "Neither OPENROUTER_API_KEY nor OPENAI_API_KEY is set. Please set one of these environment variables."
fi

# Get the run_server.sh path
RUN_SERVER="$SCRIPT_DIR/run_server.sh"

if [[ ! -x "$RUN_SERVER" ]]; then
    info "Making run_server.sh executable..."
    chmod +x "$RUN_SERVER"
fi

# Check if already registered
info "Checking existing MCP registrations..."
if claude mcp list 2>/dev/null | grep -q "ninja-cli-mcp"; then
    warn "ninja-cli-mcp is already registered"
    read -p "Do you want to re-register it? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing registration."
        exit 0
    fi

    info "Removing existing registration..."
    claude mcp remove ninja-cli-mcp 2>/dev/null || true
fi

# Register the MCP server
info "Registering ninja-cli-mcp with Claude Code..."

# Build the command with environment variable passthrough
# Note: We pass the API key through so the server subprocess has access
claude mcp add \
    --transport stdio \
    ninja-cli-mcp \
    -- "$RUN_SERVER"

if [[ $? -eq 0 ]]; then
    success "Successfully registered ninja-cli-mcp with Claude Code"
else
    error "Failed to register MCP server"
fi

echo ""
echo "=========================================="
echo "  Registration Complete!"
echo "=========================================="
echo ""

echo "The ninja-cli-mcp server is now registered with Claude Code."
echo ""
echo "Available tools:"
echo "  - ninja_quick_task: Quick single-pass task execution"
echo "  - execute_plan_sequential: Execute plan steps in order"
echo "  - execute_plan_parallel: Execute plan steps concurrently"
echo "  - run_tests: Run test commands"
echo "  - apply_patch: Apply patches (delegated to AI code CLI)"
echo ""
echo "To verify the integration:"
echo "  1. Start Claude Code: claude"
echo "  2. Check MCP tools: /mcp"
echo "  3. Look for ninja-cli-mcp tools in the list"
echo ""
echo "Example usage in Claude Code:"
echo "  Ask Claude to use ninja_quick_task to implement a feature"
echo "  in a specific repository."
echo ""

# Note about environment variables
echo "Note: Make sure these environment variables are set when running Claude Code:"
if [[ "$API_KEY_VAR" == "OPENROUTER_API_KEY" ]]; then
    echo "  export OPENROUTER_API_KEY='your-key-here'"
else
    echo "  export OPENAI_API_KEY='your-key-here'"
fi
echo ""
echo "Optional environment variables:"
echo "  NINJA_MODEL        - Model to use (default: anthropic/claude-sonnet-4)"
echo "  OPENROUTER_MODEL   - Alternative model setting"
echo "  NINJA_CODE_BIN     - Path to AI Code CLI (default: ninja-code)"
echo ""
echo "Supported models:"
echo "  - anthropic/claude-sonnet-4 (default)"
echo "  - anthropic/claude-3.5-sonnet"
echo "  - openai/gpt-4o"
echo "  - qwen/qwen3-coder"
echo "  - deepseek/deepseek-coder"
echo "  - And many more via OpenRouter"
echo ""
