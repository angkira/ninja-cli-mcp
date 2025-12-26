#!/usr/bin/env bash
#
# install_claude_code_mcp.sh - Register ninja MCP servers with Claude Code
#
# This script registers the modular ninja MCP servers (coder, researcher, secretary)
# with Claude Code using proper JSON configuration.
#
# Usage: ./scripts/install_claude_code_mcp.sh [--coder] [--researcher] [--secretary]
#        ./scripts/install_claude_code_mcp.sh --all (default)
#
# Prerequisites:
#   - Claude Code CLI installed (claude command available)
#   - ninja MCP modules installed (via uv sync)
#   - OPENROUTER_API_KEY or OPENAI_API_KEY environment variable set
#

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
    exit 1
}

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Parse arguments
INSTALL_ALL=1
INSTALL_CODER=0
INSTALL_RESEARCHER=0
INSTALL_SECRETARY=0

if [[ $# -gt 0 ]]; then
    INSTALL_ALL=0
    for arg in "$@"; do
        case "$arg" in
            --all)
                INSTALL_ALL=1
                ;;
            --coder)
                INSTALL_CODER=1
                ;;
            --researcher)
                INSTALL_RESEARCHER=1
                ;;
            --secretary)
                INSTALL_SECRETARY=1
                ;;
            *)
                error "Unknown option: $arg. Use --all, --coder, --researcher, or --secretary"
                ;;
        esac
    done
fi

if [[ $INSTALL_ALL -eq 1 ]]; then
    INSTALL_CODER=1
    INSTALL_RESEARCHER=1
    INSTALL_SECRETARY=1
fi

echo ""
echo "==========================================="
echo "  Claude Code MCP Integration"
echo "==========================================="
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
elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
    success "OPENAI_API_KEY is set"
else
    error "Neither OPENROUTER_API_KEY nor OPENAI_API_KEY is set. Please set one of these environment variables."
fi

# Detect Claude Code config location
CLAUDE_CONFIG_DIR="$HOME/.config/claude"
CLAUDE_MCP_CONFIG="$CLAUDE_CONFIG_DIR/mcp.json"

mkdir -p "$CLAUDE_CONFIG_DIR"

# Function to validate JSON
validate_json() {
    local json_file="$1"
    if python3 -m json.tool "$json_file" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to safely update MCP config using Python
update_mcp_config() {
    local server_name="$1"
    local command="$2"
    shift 2
    local args=("$@")

    python3 <<PYTHON_EOF
import json
import sys
from pathlib import Path

config_file = Path("$CLAUDE_MCP_CONFIG")

# Load existing config or create new one
if config_file.exists():
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_file}: {e}", file=sys.stderr)
        sys.exit(1)
else:
    config = {"mcpServers": {}}

# Ensure mcpServers exists
if "mcpServers" not in config:
    config["mcpServers"] = {}

# Parse args array
args = $(printf '%s\n' "${args[@]}" | python3 -c "import sys, json; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))")

# Add or update server
config["mcpServers"]["$server_name"] = {
    "command": "$command",
    "args": args
}

# Write back with proper formatting
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')  # Add trailing newline

print(f"✓ Updated {config_file} with {server_name}")
PYTHON_EOF
}

# Check if daemon mode is available
USE_DAEMON=0
if command -v ninja-daemon &> /dev/null && uv run ninja-daemon status >/dev/null 2>&1; then
    info "Daemon mode detected and available"
    USE_DAEMON=1
fi

info "Installing MCP servers..."
echo ""

# Install each selected module
INSTALL_COUNT=0

if [[ $INSTALL_CODER -eq 1 ]]; then
    info "Configuring ninja-coder..."
    if [[ $USE_DAEMON -eq 1 ]]; then
        # Ensure daemon is started
        uv run ninja-daemon start coder 2>/dev/null || true
        update_mcp_config "ninja-coder" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-daemon" "connect" "coder"
    else
        update_mcp_config "ninja-coder" "uv" "--directory" "$PROJECT_ROOT" "run" "python" "-m" "ninja_coder.server"
    fi
    success "ninja-coder configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_RESEARCHER -eq 1 ]]; then
    info "Configuring ninja-researcher..."
    if [[ $USE_DAEMON -eq 1 ]]; then
        # Ensure daemon is started
        uv run ninja-daemon start researcher 2>/dev/null || true
        update_mcp_config "ninja-researcher" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-daemon" "connect" "researcher"
    else
        update_mcp_config "ninja-researcher" "uv" "--directory" "$PROJECT_ROOT" "run" "python" "-m" "ninja_researcher.server"
    fi
    success "ninja-researcher configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_SECRETARY -eq 1 ]]; then
    info "Configuring ninja-secretary..."
    if [[ $USE_DAEMON -eq 1 ]]; then
        # Ensure daemon is started
        uv run ninja-daemon start secretary 2>/dev/null || true
        update_mcp_config "ninja-secretary" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-daemon" "connect" "secretary"
    else
        update_mcp_config "ninja-secretary" "uv" "--directory" "$PROJECT_ROOT" "run" "python" "-m" "ninja_secretary.server"
    fi
    success "ninja-secretary configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

echo ""

# Validate the final JSON
info "Validating configuration..."
if validate_json "$CLAUDE_MCP_CONFIG"; then
    success "Configuration JSON is valid"
else
    error "Configuration JSON is invalid! Please check $CLAUDE_MCP_CONFIG"
fi

echo ""
echo "==========================================="
echo "  Registration Complete!"
echo "==========================================="
echo ""

echo "Registered $INSTALL_COUNT MCP server(s) with Claude Code."
echo ""

echo "Configuration file: $CLAUDE_MCP_CONFIG"
echo ""
cat "$CLAUDE_MCP_CONFIG"
echo ""

echo "==========================================="
echo "  Verification"
echo "==========================================="
echo ""

info "Testing MCP server connections..."
claude mcp list 2>&1 | head -20
echo ""

echo "==========================================="
echo "  Next Steps"
echo "==========================================="
echo ""

echo "The ninja MCP servers are now registered with Claude Code."
echo ""

if [[ $INSTALL_CODER -eq 1 ]]; then
    echo "📦 ${BOLD}ninja-coder${NC} - AI code execution and modification"
    echo "   Tools: coder_quick_task, coder_execute_plan_*"
    echo ""
fi

if [[ $INSTALL_RESEARCHER -eq 1 ]]; then
    echo "🔍 ${BOLD}ninja-researcher${NC} - Web search and research"
    echo "   Tools: researcher_web_search, researcher_deep_research"
    echo ""
fi

if [[ $INSTALL_SECRETARY -eq 1 ]]; then
    echo "📋 ${BOLD}ninja-secretary${NC} - Codebase exploration and documentation"
    echo "   Tools: secretary_read_file, secretary_grep, secretary_file_tree"
    echo ""
fi

echo "To use in Claude Code:"
echo "  1. Start a conversation: claude"
echo "  2. The MCP tools are automatically available"
echo "  3. Ask Claude to use the tools as needed"
echo ""

echo "To check status:"
echo "  claude mcp list"
echo ""

if [[ $USE_DAEMON -eq 1 ]]; then
    echo "Daemon status:"
    echo "  uv run ninja-daemon status"
    echo ""
fi

echo "Environment configuration:"
if [[ -f "$HOME/.ninja-mcp.env" ]]; then
    echo "  Config file: ~/.ninja-mcp.env"
else
    echo "  OPENROUTER_API_KEY: ${OPENROUTER_API_KEY:+set}${OPENROUTER_API_KEY:-not set}"
fi
echo ""

echo "For troubleshooting:"
echo "  - Check logs: ~/.cache/ninja-mcp/logs/"
echo "  - Validate config: python3 -m json.tool $CLAUDE_MCP_CONFIG"
echo "  - Restart Claude Code if needed"
echo ""
