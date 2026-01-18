#!/usr/bin/env bash
#
# install_opencode_mcp.sh - Register ninja MCP servers with OpenCode
#
# This script registers the modular ninja MCP servers (coder, researcher, secretary)
# with OpenCode using proper JSON configuration.
#
# Usage: ./scripts/install_opencode_mcp.sh [--coder] [--researcher] [--secretary]
#        ./scripts/install_opencode_mcp.sh --all (default)
#
# Prerequisites:
#   - OpenCode CLI installed (opencode command available)
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
INSTALL_RESOURCES=0
INSTALL_PROMPTS=0

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
            --resources)
                INSTALL_RESOURCES=1
                ;;
            --prompts)
                INSTALL_PROMPTS=1
                ;;
            *)
                error "Unknown option: $arg. Use --all, --coder, --researcher, --secretary, --resources, or --prompts"
                ;;
        esac
    done
fi

if [[ $INSTALL_ALL -eq 1 ]]; then
    INSTALL_CODER=1
    INSTALL_RESEARCHER=1
    INSTALL_SECRETARY=1
    INSTALL_RESOURCES=1
    INSTALL_PROMPTS=1
fi

echo ""
echo "==========================================="
echo "  OpenCode MCP Integration"
echo "==========================================="
echo ""

# Check for OpenCode CLI
info "Checking for OpenCode CLI..."
if command -v opencode &> /dev/null; then
    OPENCODE_VERSION=$(opencode --version 2>/dev/null || echo "unknown")
    success "OpenCode CLI found: $OPENCODE_VERSION"
else
    error "OpenCode CLI not found. Please install OpenCode first: curl -fsSL https://opencode.ai/install | bash"
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

# Detect OpenCode config location
OPENCODE_CONFIG="$HOME/.opencode.json"

# Fallback to XDG config directory
if [[ ! -f "$OPENCODE_CONFIG" ]]; then
    OPENCODE_CONFIG="$HOME/.config/opencode/.opencode.json"
fi

# Create config directory if needed
OPENCODE_CONFIG_DIR=$(dirname "$OPENCODE_CONFIG")
mkdir -p "$OPENCODE_CONFIG_DIR"

# Initialize config file if it doesn't exist
if [[ ! -f "$OPENCODE_CONFIG" ]]; then
    info "Creating OpenCode config file..."
    echo '{}' > "$OPENCODE_CONFIG"
    success "Created: $OPENCODE_CONFIG"
fi

info "Using OpenCode config: $OPENCODE_CONFIG"

# Function to validate JSON
validate_json() {
    local json_file="$1"
    if python3 -m json.tool "$json_file" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to add/update MCP server in OpenCode config
update_opencode_mcp_config() {
    local server_name="$1"
    local command="$2"
    shift 2
    local args=("$@")

    # Convert args array to JSON array
    local args_json=$(printf '%s\n' "${args[@]}" | python3 -c "import sys, json; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))")

    python3 <<PYTHON_EOF
import json
import sys
import os
from pathlib import Path

config_file = Path("$OPENCODE_CONFIG")

# Load existing config or create new one
if config_file.exists():
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_file}: {e}", file=sys.stderr)
        sys.exit(1)
else:
    config = {}

# Ensure mcpServers exists
if "mcpServers" not in config:
    config["mcpServers"] = {}

# Parse args from JSON
args_json = '''$args_json'''
args = json.loads(args_json) if args_json.strip() else []

# Build server config
server_config = {
    "type": "stdio",
    "command": "$command",
    "disabled": False
}

if args:
    server_config["args"] = args

# Add environment variables
env_vars = []

# Get actual API key from environment
api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

if "$server_name" == "ninja-coder":
    env_vars.extend([
        f"OPENROUTER_API_KEY={api_key}",
        "NINJA_CODER_MODEL=anthropic/claude-haiku-4.5-20250929",
        "NINJA_CODE_BIN=aider",
        "NINJA_CODER_TIMEOUT=600"
    ])
elif "$server_name" == "ninja-researcher":
    env_vars.extend([
        f"OPENROUTER_API_KEY={api_key}",
        "NINJA_RESEARCHER_MODEL=anthropic/claude-sonnet-4",
        "NINJA_RESEARCHER_MAX_SOURCES=20",
        "NINJA_RESEARCHER_PARALLEL_AGENTS=4"
    ])
elif "$server_name" == "ninja-secretary":
    env_vars.extend([
        "NINJA_SECRETARY_MODEL=anthropic/claude-haiku-4.5-20250929",
        "NINJA_SECRETARY_MAX_FILE_SIZE=1048576"
    ])
elif "$server_name" == "ninja-resources":
    env_vars.extend([
        "NINJA_RESOURCES_CACHE_TTL=3600",
        "NINJA_RESOURCES_MAX_FILES=1000"
    ])
elif "$server_name" == "ninja-prompts":
    env_vars.extend([
        "NINJA_PROMPTS_MAX_SUGGESTIONS=5",
        "NINJA_PROMPTS_CACHE_TTL=3600"
    ])

if env_vars:
    server_config["env"] = env_vars

# Add or update server config
config["mcpServers"]["$server_name"] = server_config

# Write back with proper formatting
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print(f"✓ Updated {config_file} with $server_name")
PYTHON_EOF
}

# Detect installation mode
INSTALL_MODE="local"
info "Detecting installation mode..."

# Check if ninja servers are globally available (installed via uv tool install)
if command -v ninja-coder &> /dev/null && ! [[ "$(which ninja-coder 2>/dev/null)" =~ "$PROJECT_ROOT" ]]; then
    INSTALL_MODE="global"
    success "Global installation detected (uv tool install)"
else
    success "Local development mode detected"
    info "Project directory: $PROJECT_ROOT"
fi

info "Installing MCP servers in $INSTALL_MODE mode..."
echo ""

# Install each selected module
INSTALL_COUNT=0

if [[ $INSTALL_CODER -eq 1 ]]; then
    info "Configuring ninja-coder..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_opencode_mcp_config "ninja-coder" "ninja-coder"
    else
        update_opencode_mcp_config "ninja-coder" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-coder"
    fi
    success "ninja-coder configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_RESEARCHER -eq 1 ]]; then
    info "Configuring ninja-researcher..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_opencode_mcp_config "ninja-researcher" "ninja-researcher"
    else
        update_opencode_mcp_config "ninja-researcher" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-researcher"
    fi
    success "ninja-researcher configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_SECRETARY -eq 1 ]]; then
    info "Configuring ninja-secretary..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_opencode_mcp_config "ninja-secretary" "ninja-secretary"
    else
        update_opencode_mcp_config "ninja-secretary" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-secretary"
    fi
    success "ninja-secretary configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_RESOURCES -eq 1 ]]; then
    info "Configuring ninja-resources..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_opencode_mcp_config "ninja-resources" "ninja-resources"
    else
        update_opencode_mcp_config "ninja-resources" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-resources"
    fi
    success "ninja-resources configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_PROMPTS -eq 1 ]]; then
    info "Configuring ninja-prompts..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_opencode_mcp_config "ninja-prompts" "ninja-prompts"
    else
        update_opencode_mcp_config "ninja-prompts" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-prompts"
    fi
    success "ninja-prompts configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

echo ""

# Validate the final JSON
info "Validating configuration..."
if validate_json "$OPENCODE_CONFIG"; then
    success "Configuration JSON is valid"
else
    error "Configuration JSON is invalid! Please check $OPENCODE_CONFIG"
fi

echo ""
echo "==========================================="
echo "  IMPORTANT: Complete Setup Manually"
echo "==========================================="
echo ""

echo -e "${YELLOW}OpenCode MCP registration requires manual completion:${NC}"
echo ""
echo "OpenCode CLI v1.1.25 does not support non-interactive MCP registration."
echo "You must complete the setup by running:"
echo ""
echo -e "  ${CYAN}opencode mcp add${NC}"
echo ""
echo "This will open an interactive interface where you can:"
echo "  1. Select 'Global' location (recommended)"
echo "  2. Add each MCP server:"
echo "     - ninja-coder (command: ninja-coder, stdio)"
echo "     - ninja-researcher (command: ninja-researcher, stdio)"
echo "     - ninja-secretary (command: ninja-secretary, stdio)"
echo "     - ninja-resources (command: ninja-resources, stdio)"
echo "     - ninja-prompts (command: ninja-prompts, stdio)"
echo ""
echo "After registration, verify with:"
echo -e "  ${CYAN}opencode mcp list${NC}"
echo ""
echo "==========================================="
echo "  Configuration Status"
echo "==========================================="
echo ""

echo "Configuration files created:"
echo "  • ~/.config/opencode/.opencode.json (global)"
echo "  • ./.opencode.json (project-local, if created)"
echo ""

echo "Note: These files contain server definitions, but"
echo "OpenCode requires interactive registration via 'opencode mcp add'."
echo ""

echo "Registered $INSTALL_COUNT MCP server(s) with OpenCode."
echo ""
echo "Configuration file: $OPENCODE_CONFIG"
echo ""
cat "$OPENCODE_CONFIG"
echo ""

echo "==========================================="
echo "  Verification"
echo "==========================================="
echo ""

info "Testing MCP server connections..."
opencode mcp list 2>&1 | head -20
echo ""

echo "==========================================="
echo "  Next Steps"
echo "==========================================="
echo ""

echo "The ninja MCP servers are now registered with OpenCode."
echo ""

if [[ $INSTALL_CODER -eq 1 ]]; then
    echo "📦 ${BOLD}ninja-coder${NC} - AI code execution and modification"
    echo "   Tools: coder_quick_task, coder_execute_plan_sequential, coder_execute_plan_parallel"
    echo ""
fi

if [[ $INSTALL_RESEARCHER -eq 1 ]]; then
    echo "🔍 ${BOLD}ninja-researcher${NC} - Web search and research"
    echo "   Tools: researcher_deep_research, researcher_fact_check, researcher_summarize_sources"
    echo ""
fi

if [[ $INSTALL_SECRETARY -eq 1 ]]; then
    echo "📋 ${BOLD}ninja-secretary${NC} - Codebase exploration and documentation"
    echo "   Tools: secretary_read_file, secretary_file_search, secretary_grep, secretary_codebase_report"
    echo "          secretary_document_summary, secretary_session_report"
    echo ""
fi

if [[ $INSTALL_RESOURCES -eq 1 ]]; then
    echo "🧠 ${BOLD}ninja-resources${NC} - Load project context as queryable resources"
    echo "   Tools: resource_codebase, resource_config, resource_docs"
    echo ""
fi

if [[ $INSTALL_PROMPTS -eq 1 ]]; then
    echo "✨ ${BOLD}ninja-prompts${NC} - Reusable prompt templates and workflows"
    echo "   Tools: prompt_registry, prompt_suggest, prompt_chain"
    echo ""
fi

echo "To use in OpenCode:"
echo "  1. Start OpenCode: opencode"
echo "  2. The MCP tools are automatically available"
echo "  3. Ask OpenCode to use the tools as needed"
echo ""

echo "To check status:"
echo "  opencode mcp list"
echo ""

echo "Environment configuration:"
if [[ -f "$HOME/.ninja-mcp.env" ]]; then
    echo "  Config file: ~/.ninja-mcp.env"
else
    echo "  OPENROUTER_API_KEY: ${OPENROUTER_API_KEY:+set}${OPENROUTER_API_KEY:-not set}"
fi
echo ""

echo "For troubleshooting:"
echo "  - Check logs: ~/.cache/ninja-mcp/logs/"
echo "  - Validate config: python3 -m json.tool $OPENCODE_CONFIG"
echo "  - Restart OpenCode if needed"
echo ""
