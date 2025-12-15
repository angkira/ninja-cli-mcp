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

# Check for Copilot CLI extension
info "Checking for GitHub Copilot CLI..."

COPILOT_FOUND=0

# Check for gh extension
if gh extension list 2>/dev/null | grep -q "copilot"; then
    success "GitHub Copilot CLI extension found (gh copilot)"
    COPILOT_FOUND=1
fi

# Check for npm global package
if command -v github-copilot-cli &> /dev/null; then
    success "GitHub Copilot CLI npm package found"
    COPILOT_FOUND=1
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
CONFIG_DIR="$HOME/.config/copilot-cli"
MCP_CONFIG="$CONFIG_DIR/mcp-servers.json"

info "Setting up MCP configuration..."
mkdir -p "$CONFIG_DIR"

# Get the run_server.sh path
RUN_SERVER="$SCRIPT_DIR/run_server.sh"

if [[ ! -x "$RUN_SERVER" ]]; then
    chmod +x "$RUN_SERVER"
fi

# Build MCP server configuration
MCP_SERVER_CONFIG=$(cat <<EOF
{
  "servers": {
    "ninja-cli-mcp": {
      "transport": "stdio",
      "command": "$RUN_SERVER",
      "description": "AI code executor for code operations (supports any OpenRouter model)",
      "env": {
        "OPENROUTER_API_KEY": "\${OPENROUTER_API_KEY}",
        "NINJA_MODEL": "\${NINJA_MODEL:-anthropic/claude-sonnet-4}",
        "NINJA_CODE_BIN": "\${NINJA_CODE_BIN:-ninja-code}"
      }
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
echo "IMPORTANT: MCP integration with Copilot CLI"
echo "=========================================="
echo ""
echo "GitHub Copilot CLI's MCP support is evolving. The configuration"
echo "above may need adjustment based on your Copilot CLI version."
echo ""
echo "Current status:"
echo "  - The MCP config file is at: $MCP_CONFIG"
echo "  - The server command is: $RUN_SERVER"
echo ""
echo "Manual integration steps (if automatic config doesn't work):"
echo ""
echo "1. Check Copilot CLI documentation for MCP support:"
echo "   https://docs.github.com/en/copilot"
echo ""
echo "2. The MCP server can be started manually:"
echo "   $RUN_SERVER"
echo ""
echo "3. For stdio transport, the server communicates via stdin/stdout"
echo "   using the MCP protocol."
echo ""
echo "Environment variables to set before running Copilot CLI:"
echo "  export OPENROUTER_API_KEY='your-key-here'"
echo "  export NINJA_MODEL='anthropic/claude-sonnet-4'  # optional, this is the default"
echo "  export NINJA_CODE_BIN='ninja-code'              # optional"
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

# Alternative: VS Code settings hint
echo "Alternative: VS Code with GitHub Copilot"
echo "=========================================="
echo ""
echo "If using VS Code with GitHub Copilot Chat, you can configure"
echo "MCP servers in your VS Code settings.json:"
echo ""
echo "  \"github.copilot.chat.mcpServers\": {"
echo "    \"ninja-cli-mcp\": {"
echo "      \"command\": \"$RUN_SERVER\","
echo "      \"transport\": \"stdio\""
echo "    }"
echo "  }"
echo ""
