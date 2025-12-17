#!/usr/bin/env bash
#
# install_vscode_mcp.sh - Configure ninja-cli-mcp for VS Code with GitHub Copilot
#
# This script configures ninja-cli-mcp as an MCP server for VS Code's
# GitHub Copilot Chat integration.
#
# Prerequisites:
#   - VS Code 1.99+ with GitHub Copilot extension
#   - ninja-cli-mcp installed and configured
#
# Usage: ./scripts/install_vscode_mcp.sh [--workspace]

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
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

# Parse arguments
WORKSPACE_MODE=0
if [[ "${1:-}" == "--workspace" ]]; then
    WORKSPACE_MODE=1
fi

echo ""
echo "=========================================="
echo "  VS Code MCP Integration"
echo "=========================================="
echo ""

# Check for VS Code
info "Checking for VS Code..."
if ! command -v code &> /dev/null; then
    error "VS Code (code) not found in PATH"
    echo ""
    echo "Please install VS Code from https://code.visualstudio.com/"
    exit 1
fi

VSCODE_VERSION=$(code --version 2>/dev/null | head -n1)
success "VS Code found: $VSCODE_VERSION"

# Check version requirement (1.99+)
VSCODE_MAJOR=$(echo "$VSCODE_VERSION" | cut -d. -f1)
VSCODE_MINOR=$(echo "$VSCODE_VERSION" | cut -d. -f2)

if [[ "$VSCODE_MAJOR" -gt 1 ]] || [[ "$VSCODE_MAJOR" -eq 1 && "$VSCODE_MINOR" -ge 99 ]]; then
    success "VS Code version supports MCP (requires 1.99+)"
else
    warn "VS Code version may not support MCP (requires 1.99+, found $VSCODE_VERSION)"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Exiting."
        exit 1
    fi
fi

# Check for GitHub Copilot extension
info "Checking for GitHub Copilot extension..."
if code --list-extensions 2>/dev/null | grep -q "GitHub.copilot"; then
    success "GitHub Copilot extension found"
else
    warn "GitHub Copilot extension not found"
    echo ""
    echo "To install GitHub Copilot:"
    echo "  1. Open VS Code"
    echo "  2. Go to Extensions (Ctrl+Shift+X)"
    echo "  3. Search for 'GitHub Copilot'"
    echo "  4. Click Install"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Exiting."
        exit 1
    fi
fi

# Get the run_server.sh path
RUN_SERVER="$SCRIPT_DIR/run_server.sh"

if [[ ! -x "$RUN_SERVER" ]]; then
    chmod +x "$RUN_SERVER"
fi

# Determine configuration location
if [[ $WORKSPACE_MODE -eq 1 ]]; then
    # Workspace mode: .vscode/mcp.json
    if [[ ! -d ".vscode" ]]; then
        warn "No .vscode directory found. Are you in a workspace?"
        echo ""
        read -p "Create .vscode directory here? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Exiting."
            exit 1
        fi
        mkdir -p .vscode
    fi
    MCP_CONFIG=".vscode/mcp.json"
    CONFIG_SCOPE="workspace"
else
    # User mode: ~/.config/Code/User/mcp.json
    CONFIG_DIR="$HOME/.config/Code/User"
    mkdir -p "$CONFIG_DIR"
    MCP_CONFIG="$CONFIG_DIR/mcp.json"
    CONFIG_SCOPE="user profile"
fi

info "Setting up MCP configuration for $CONFIG_SCOPE..."

# Build MCP server configuration
MCP_SERVER_CONFIG=$(cat <<EOF
{
  "mcpServers": {
    "ninja-cli-mcp": {
      "command": "$RUN_SERVER",
      "args": [],
      "env": {},
      "disabled": false
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
        echo ""
        echo "To manually add ninja-cli-mcp, edit $MCP_CONFIG and add:"
        echo ""
        echo "$MCP_SERVER_CONFIG"
        echo ""
        exit 0
    fi
fi

echo "$MCP_SERVER_CONFIG" > "$MCP_CONFIG"
success "Configuration created at $MCP_CONFIG"

echo ""
echo "=========================================="
echo "  Configuration Complete!"
echo "=========================================="
echo ""

cat "$MCP_CONFIG"

echo ""
echo "=========================================="
echo "  Next Steps"
echo "=========================================="
echo ""
echo "1. Restart VS Code to load the MCP server"
echo ""
echo "2. Open GitHub Copilot Chat (Ctrl+Shift+I or Cmd+Shift+I)"
echo ""
echo "3. Verify MCP server is available:"
echo "   - Type '@' in chat to see available MCP tools"
echo "   - Look for 'ninja-cli-mcp' in the list"
echo ""
echo "4. Test the integration:"
echo "   @ninja-cli-mcp Execute a simple task like 'echo hello world'"
echo ""
echo "Configuration location: $MCP_CONFIG"
echo "Server command: $RUN_SERVER"
echo ""
echo "For troubleshooting, check:"
echo "  - VS Code Developer Tools (Help > Toggle Developer Tools)"
echo "  - MCP server logs: ~/.ninja-cli-mcp/logs/"
echo ""

# Show environment setup
source "$HOME/.ninja-cli-mcp.env" 2>/dev/null || true

if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    success "Environment configured (OPENROUTER_API_KEY set)"
else
    warn "OPENROUTER_API_KEY not set"
    echo ""
    echo "Make sure to set your OpenRouter API key:"
    echo "  export OPENROUTER_API_KEY='your-key-here'"
    echo ""
    echo "Or add it to ~/.ninja-cli-mcp.env:"
    echo "  echo 'export OPENROUTER_API_KEY=\"your-key\"' >> ~/.ninja-cli-mcp.env"
    echo ""
fi

echo "Supported models (set via NINJA_MODEL environment variable):"
echo "  - anthropic/claude-sonnet-4 (default)"
echo "  - anthropic/claude-3.5-sonnet"
echo "  - openai/gpt-4o"
echo "  - qwen/qwen3-coder"
echo "  - deepseek/deepseek-coder"
echo "  - google/gemini-pro-1.5"
echo "  - And 200+ more via OpenRouter"
echo ""
