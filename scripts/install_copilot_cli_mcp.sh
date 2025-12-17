#!/usr/bin/env bash
#
# install_copilot_cli_mcp.sh - Set up ninja-cli-mcp for GitHub Copilot CLI
#
# This script helps configure ninja-cli-mcp for use with GitHub Copilot CLI.
# Note: MCP integration with Copilot CLI may vary by version and is evolving.
#
# Usage: ./scripts/install_copilot_cli_mcp.sh
#
# Prerequisites:
#   - GitHub CLI (gh) installed
#   - GitHub Copilot CLI extension or npm package
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
}

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "=========================================="
echo "  Copilot CLI MCP Integration"
echo "=========================================="
echo ""

# Check for GitHub CLI
info "Checking for GitHub CLI (gh)..."
if command -v gh &> /dev/null; then
    GH_VERSION=$(gh --version | head -n1)
    success "GitHub CLI found: $GH_VERSION"
else
    warn "GitHub CLI not found"
    echo ""
    echo "To install GitHub CLI:"
    echo "  macOS:  brew install gh"
    echo "  Linux:  See https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
    echo ""
fi

# Check for Copilot CLI
info "Checking for GitHub Copilot CLI..."

COPILOT_FOUND=0
COPILOT_CMD=""

# Check for gh extension
if command -v gh &> /dev/null && gh extension list 2>/dev/null | grep -q "copilot"; then
    success "GitHub Copilot CLI extension found (gh copilot)"
    COPILOT_FOUND=1
    COPILOT_CMD="gh copilot"
fi

# Check for npm global package (@github/copilot)
if command -v copilot &> /dev/null; then
    COPILOT_VERSION=$(copilot --version 2>/dev/null | head -n1 || echo "unknown")
    success "GitHub Copilot CLI found: v$COPILOT_VERSION"
    COPILOT_FOUND=1
    COPILOT_CMD="copilot"
fi

# Legacy check for github-copilot-cli
if command -v github-copilot-cli &> /dev/null; then
    success "GitHub Copilot CLI npm package found (legacy)"
    COPILOT_FOUND=1
    COPILOT_CMD="github-copilot-cli"
fi

if [[ $COPILOT_FOUND -eq 0 ]]; then
    warn "GitHub Copilot CLI not found"
    echo ""
    echo "Installation options:"
    echo ""
    echo "  Option 1: GitHub CLI extension (recommended)"
    echo "    gh extension install github/gh-copilot"
    echo ""
    echo "  Option 2: npm package"
    echo "    npm install -g @githubnext/github-copilot-cli"
    echo ""
fi

# Create MCP configuration directory
# Copilot CLI v0.0.365+ uses ~/.copilot/mcp-config.json
CONFIG_DIR="$HOME/.copilot"
MCP_CONFIG="$CONFIG_DIR/mcp-config.json"

info "Setting up MCP configuration..."
mkdir -p "$CONFIG_DIR"

# Get the run_server.sh path
RUN_SERVER="$SCRIPT_DIR/run_server.sh"

if [[ ! -x "$RUN_SERVER" ]]; then
    chmod +x "$RUN_SERVER"
fi

# Build MCP server configuration
# Format for Copilot CLI v0.0.365+
MCP_SERVER_CONFIG=$(cat <<EOF
{
  "mcpServers": {
    "ninja-cli-mcp": {
      "command": "$RUN_SERVER",
      "args": [],
      "env": {}
    }
  }
}
EOF
)

# Check if config already exists
if [[ -f "$MCP_CONFIG" ]]; then
    warn "MCP configuration already exists at $MCP_CONFIG"
    echo ""
    echo "Existing configuration:"
    cat "$MCP_CONFIG"
    echo ""
    read -p "Do you want to overwrite it? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing configuration."
    else
        echo "$MCP_SERVER_CONFIG" > "$MCP_CONFIG"
        success "Configuration updated"
    fi
else
    echo "$MCP_SERVER_CONFIG" > "$MCP_CONFIG"
    success "Configuration created at $MCP_CONFIG"
fi

echo ""
echo "=========================================="
echo "  Configuration Complete!"
echo "=========================================="
echo ""

echo "MCP server configuration for Copilot CLI:"
echo ""
cat "$MCP_CONFIG"
echo ""

echo "=========================================="
echo ""
echo "Testing Copilot CLI"
echo "=========================================="
echo ""
echo "The ninja-cli-mcp server is now configured for Copilot CLI."
echo ""
echo "Configuration file: $MCP_CONFIG"
echo "Server command: $RUN_SERVER"
echo ""
echo "To use with Copilot CLI:"
echo ""
if [[ -n "$COPILOT_CMD" ]]; then
    echo "  $COPILOT_CMD"
    echo ""
    echo "The MCP server will be automatically loaded from ~/.copilot/mcp-config.json"
    echo ""
    echo "Copilot CLI will have access to these tools:"
    echo "  - ninja_quick_task - Execute quick tasks"
    echo "  - execute_plan_sequential - Run sequential plan steps"
    echo "  - execute_plan_parallel - Run parallel plan steps"
    echo "  - run_tests - Execute test commands"
    echo ""
else
    echo "  copilot   (if installed via npm)"
    echo "  gh copilot (if installed as gh extension)"
    echo ""
fi
echo "Environment variables (set in ~/.ninja-cli-mcp.env):"
echo "  OPENROUTER_API_KEY - Your OpenRouter API key (required)"
echo "  NINJA_MODEL - Model to use (default: anthropic/claude-sonnet-4)"
echo "  NINJA_CODE_BIN - AI code CLI binary (default: ninja-code)"
echo ""
echo "Supported models (set via NINJA_MODEL):"
echo "  - anthropic/claude-sonnet-4 (default)"
echo "  - anthropic/claude-3.5-sonnet"
echo "  - openai/gpt-4o"
echo "  - qwen/qwen3-coder"
echo "  - deepseek/deepseek-coder"
echo "  - google/gemini-pro-1.5"
echo "  - And many more via OpenRouter"
echo ""
echo "For other IDE integrations (VS Code, Zed):"
echo "  ./scripts/install_ide_integrations.sh"
echo ""
