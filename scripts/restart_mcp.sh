#!/usr/bin/env bash
# Restart ninja-cli-mcp MCP server

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "=========================================="
echo "  Restart ninja-cli-mcp MCP Server"
echo "=========================================="
echo ""

# Kill old processes
info "Killing old MCP server processes..."
if pkill -f "ninja_cli_mcp.server" 2>/dev/null; then
    success "Old processes killed"
else
    info "No old processes found"
fi
sleep 1

# Double-check they're gone
if ps aux | grep -E "ninja_cli_mcp.server" | grep -v grep > /dev/null 2>&1; then
    warn "Some processes still running. Force killing..."
    pkill -9 -f "ninja_cli_mcp.server" 2>/dev/null || true
    sleep 1
    
    if ps aux | grep -E "ninja_cli_mcp.server" | grep -v grep > /dev/null 2>&1; then
        error "Failed to kill all processes"
        echo ""
        echo "Running processes:"
        ps aux | grep -E "ninja_cli_mcp.server" | grep -v grep
        echo ""
        echo "Try manually:"
        echo "  pkill -9 -f ninja_cli_mcp.server"
        exit 1
    fi
fi

success "All old processes stopped"
echo ""

# Verify configuration
info "Verifying configuration..."
if [[ -f ~/.ninja-mcp.env ]]; then
    source ~/.ninja-mcp.env
    success "Configuration loaded"
    echo "   NINJA_CODE_BIN: $NINJA_CODE_BIN"
    echo "   NINJA_MODEL: ${NINJA_MODEL:0:40}..."
    echo "   API Key: ${OPENROUTER_API_KEY:0:10}...${OPENROUTER_API_KEY: -4}"
elif [[ -f ~/.ninja-cli-mcp.env ]]; then
    # Legacy config file name - still supported
    source ~/.ninja-cli-mcp.env
    success "Configuration loaded (legacy file)"
    echo "   NINJA_CODE_BIN: $NINJA_CODE_BIN"
    echo "   NINJA_MODEL: ${NINJA_MODEL:0:40}..."
    echo "   API Key: ${OPENROUTER_API_KEY:0:10}...${OPENROUTER_API_KEY: -4}"
else
    error "Configuration file not found: ~/.ninja-mcp.env"
    echo ""
    echo "Create it with:"
    echo "  bash scripts/install_interactive.sh"
    exit 1
fi
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check Aider
info "Checking Aider..."
cd "$PROJECT_ROOT"
if uv run aider --version &> /dev/null; then
    AIDER_VERSION=$(uv run aider --version 2>/dev/null | head -n1)
    success "Aider available: $AIDER_VERSION"
else
    error "Aider not found"
    echo ""
    echo "Install it with:"
    echo "  uv sync --extra aider"
    exit 1
fi
echo ""

# Test server startup
info "Testing server startup..."
timeout 3 bash "$SCRIPT_DIR/run_server.sh" > /tmp/mcp_restart_test.log 2>&1 &
TEST_PID=$!
sleep 2
if ps -p $TEST_PID > /dev/null 2>&1; then
    success "Server starts successfully (PID: $TEST_PID)"
    kill $TEST_PID 2>/dev/null || true
    wait $TEST_PID 2>/dev/null || true
else
    info "Server test completed (this is normal)"
fi
echo ""

# Final check
info "Final verification..."
if ps aux | grep -E "ninja_cli_mcp.server" | grep -v grep > /dev/null 2>&1; then
    warn "MCP server processes detected (from test):"
    ps aux | grep -E "ninja_cli_mcp.server" | grep -v grep | awk '{print "   PID", $2, "-", $(NF-1), $NF}'
    echo ""
    info "Cleaning up test processes..."
    pkill -f "ninja_cli_mcp.server" 2>/dev/null || true
    sleep 1
fi

success "Environment is clean and ready"
echo ""

echo "=========================================="
echo "  Restart Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "  1. Restart GitHub Copilot CLI:"
echo "     • Close and reopen your terminal/IDE"
echo "     • Or run: gh copilot"
echo ""
echo "  2. Test the MCP server:"
echo "     > Use ninja_quick_task to add docstrings to utils.py"
echo ""
echo "  3. Or test directly:"
echo "     cd $PROJECT_ROOT"
echo "     bash scripts/test_aider_integration.sh"
echo ""
echo "Configuration:"
echo "  • Server location: $PROJECT_ROOT"
echo "  • Config file: ~/.ninja-mcp.env"
echo "  • MCP config: ~/.copilot/mcp-config.json"
echo "  • Coding CLI: $NINJA_CODE_BIN (Aider)"
echo "  • Model: ${NINJA_MODEL:0:40}..."
echo ""
