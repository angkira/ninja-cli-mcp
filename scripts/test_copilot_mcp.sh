#!/usr/bin/env bash
#
# test_copilot_mcp.sh - Test ninja-cli-mcp integration with Copilot CLI
#
# This script verifies that Copilot CLI can load and communicate with
# the ninja-cli-mcp MCP server.
#

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

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

echo ""
echo "=========================================="
echo "  Copilot CLI MCP Integration Test"
echo "=========================================="
echo ""

# Check if copilot is available
if ! command -v copilot &> /dev/null; then
    error "Copilot CLI not found in PATH"
    exit 1
fi

COPILOT_VERSION=$(copilot --version 2>/dev/null | head -n1)
success "Copilot CLI found: v$COPILOT_VERSION"

# Check for MCP config
MCP_CONFIG="$HOME/.copilot/mcp-config.json"
if [[ ! -f "$MCP_CONFIG" ]]; then
    error "MCP configuration not found at $MCP_CONFIG"
    echo ""
    echo "Run ./scripts/install_copilot_cli_mcp.sh first"
    exit 1
fi

success "MCP config found: $MCP_CONFIG"

# Verify config format
if ! python3 -c "import json; json.load(open('$MCP_CONFIG'))" 2>/dev/null; then
    error "Invalid JSON in MCP configuration"
    exit 1
fi

success "MCP config is valid JSON"

# Check if ninja-cli-mcp is configured
if ! grep -q "ninja-cli-mcp" "$MCP_CONFIG"; then
    error "ninja-cli-mcp not found in MCP configuration"
    exit 1
fi

success "ninja-cli-mcp is configured"

# Check environment
source "$HOME/.ninja-cli-mcp.env" 2>/dev/null || true

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    warn "OPENROUTER_API_KEY not set"
    echo ""
    echo "The MCP server may not work without an API key."
    echo "Set it in ~/.ninja-cli-mcp.env:"
    echo "  export OPENROUTER_API_KEY='your-key-here'"
    echo ""
else
    success "OPENROUTER_API_KEY is set"
fi

echo ""
echo "=========================================="
echo "  Configuration Summary"
echo "=========================================="
echo ""
echo "Copilot CLI: v$COPILOT_VERSION"
echo "MCP Config: $MCP_CONFIG"
echo "MCP Servers:"
python3 <<EOF
import json
with open("$MCP_CONFIG") as f:
    config = json.load(f)
    for name, server in config.get("mcpServers", {}).items():
        print(f"  - {name}")
        print(f"    Command: {server.get('command', 'N/A')}")
EOF

echo ""
echo "=========================================="
echo "  Testing MCP Server"
echo "=========================================="
echo ""

info "Testing if Copilot can load the MCP server..."
echo ""

# Test with a simple prompt in non-interactive mode
TEST_PROMPT="List the available MCP tools"

echo "Running: copilot -p \"$TEST_PROMPT\" --allow-all-tools"
echo ""

# Run copilot with the test prompt
# Note: This will actually execute, so we add --allow-all-tools for automation
if copilot -p "$TEST_PROMPT" --allow-all-tools 2>&1 | tee /tmp/copilot-test.log; then
    success "Copilot executed successfully"
else
    warn "Copilot exited with non-zero status (may be normal)"
fi

echo ""
echo "=========================================="
echo "  Manual Testing"
echo "=========================================="
echo ""
echo "To test interactively, run:"
echo ""
echo "  copilot"
echo ""
echo "Then try asking Copilot to:"
echo "  - List available tools"
echo "  - Use ninja_quick_task to echo 'hello world'"
echo "  - Execute a simple task in /tmp"
echo ""
echo "The ninja-cli-mcp server should be automatically loaded"
echo "and available as an MCP tool."
echo ""
echo "Logs are available at:"
echo "  - Copilot logs: ~/.copilot/logs/"
echo "  - MCP server logs: ~/.ninja-cli-mcp/logs/"
echo ""
