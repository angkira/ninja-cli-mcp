#!/usr/bin/env bash
#
# install_gemini_mcp.sh - Register ninja MCP servers with Gemini CLI
#
# This script registers modular ninja MCP servers (coder, researcher, secretary)
# with Gemini CLI using proper JSON configuration.
#
# Usage: ./scripts/install_gemini_mcp.sh [--coder] [--researcher] [--secretary]
#        ./scripts/install_gemini_mcp.sh --all (default)
#
# Prerequisites:
#   - Gemini CLI installed (gemini command available)
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

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "=========================================="
echo "  Gemini CLI MCP Integration"
echo "==========================================="
echo ""

# Source shared Gemini config utilities
source "$SCRIPT_DIR/lib/gemini_config.sh"

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
# Check for Gemini CLI
info "Checking for Gemini CLI..."
if command -v gemini &> /dev/null; then
    GEMINI_VERSION=$(gemini --version 2>/dev/null || echo "unknown")
    success "Gemini CLI found: $GEMINI_VERSION"
else
    error "Gemini CLI not found. Please install Gemini CLI first."
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

# Detect Gemini CLI config location and initialize
GEMINI_MCP_CONFIG=$(detect_gemini_mcp_config)
GEMINI_CONFIG_DIR=$(dirname "$GEMINI_MCP_CONFIG")

info "Using Gemini CLI config: $GEMINI_MCP_CONFIG"
init_gemini_mcp_config "$GEMINI_MCP_CONFIG"

# Check if we should migrate from old location
check_config_migration

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

    # Convert args array to JSON
    local args_json=$(printf '%s\n' "${args[@]}" | python3 -c "import sys, json; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))")

    args = json.loads(args_json) if args_json.strip() else []

    # Add or update server config
    server_config = {"command": "$command"}
    if args:
        server_config["args"] = args

    # Get actual API key from environment (expanded, not shell syntax)
    import os
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

    # Add default environment variables with actual API key value
    env_vars = {}
    if "$server_name" == "ninja-coder":
        env_vars = {
            "NINJA_CODER_MODEL": "google/gemini-2.0-flash-exp",
            "NINJA_CODE_BIN": "gemini",
            "NINJA_CODER_TIMEOUT": "300",
        }
    elif "$server_name" == "ninja-researcher":
        env_vars = {
            "NINJA_RESEARCHER_MODEL": "google/gemini-2.0-flash-exp",
            "NINJA_RESEARCHER_MAX_SOURCES": "20",
            "NINJA_RESEARCHER_PARALLEL_AGENTS": "4",
        }
    elif "$server_name" == "ninja-secretary":
        env_vars = {
            "NINJA_SECRETARY_MODEL": "google/gemini-2.0-flash-exp",
            "NINJA_SECRETARY_MAX_FILE_SIZE": "1048576",
        }
    elif "$server_name" == "ninja-resources":
        env_vars = {
            "NINJA_RESOURCES_CACHE_TTL": "3600",
            "NINJA_RESOURCES_MAX_FILES": "1000",
        }
    elif "$server_name" == "ninja-prompts":
        env_vars = {
            "NINJA_PROMPTS_MAX_SUGGESTIONS": "5",
            "NINJA_PROMPTS_CACHE_TTL": "3600",
        }
    fi

    # Add API key if available (use actual value, not shell expansion syntax)
    if api_key:
        env_vars["OPENROUTER_API_KEY"] = api_key

    if env_vars:
        server_config["env"] = env_vars

    config["mcpServers"]["$server_name"] = server_config

    # Write back with proper formatting
    python3 <<PYTHON_EOF
import json
from pathlib import Path

config_file = Path("$GEMINI_MCP_CONFIG")

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

# Add or update server config
server_config = {"command": "$command"}
if args:
    server_config["args"] = args

# Get actual API key from environment (expanded)
import os
api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")

# Add default environment variables
env_vars = {}
if "$server_name" == "ninja-coder":
    env_vars = {
        "NINJA_CODER_MODEL": "google/gemini-2.0-flash-exp",
        "NINJA_CONFIG_NAME": "ninja-coder",
        "NINJA_CONFIG_PATH": "$GEMINI_MCP_CONFIG",
        "NINJA_CONFIG_VERSION": "1.0",
        "NINJA_CODE_BIN": "gemini",
        "NINJA_CODER_TIMEOUT": "300",
    }
elif "$server_name" == "ninja-researcher":
    env_vars = {
        "NINJA_RESEARCHER_MODEL": "google/gemini-2.0-flash-exp",
        "NINJA_RESEARCHER_MAX_SOURCES": "20",
        "NINJA_RESEARCHER_PARALLEL_AGENTS": "4",
    }
elif "$server_name" == "ninja-secretary":
    env_vars = {
        "NINJA_SECRETARY_MODEL": "google/gemini-2.0-flash-exp",
        "NINJA_SECRETARY_MAX_FILE_SIZE": "1048576",
    }
elif "$server_name" == "ninja-resources":
    env_vars = {
        "NINJA_RESOURCES_CACHE_TTL": "3600",
        "NINJA_RESOURCES_MAX_FILES": "1000",
    }
elif "$server_name" == "ninja-prompts":
    env_vars = {
        "NINJA_PROMPTS_MAX_SUGGESTIONS": "5",
        "NINJA_PROMPTS_CACHE_TTL": "3600",
    }

# Add API key if available
if api_key:
    env_vars["OPENROUTER_API_KEY"] = api_key

if env_vars:
    server_config["env"] = env_vars

config["mcpServers"]["$server_name"] = server_config

# Write with proper formatting
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print(f"✓ Updated {config_file} with $server_name")
PYTHON_EOF
}

# Detect installation mode
INSTALL_MODE="local"  # default to local development mode
info "Detecting installation mode..."

# Check if ninja servers are globally available (installed via uv tool install)
if command -v ninja-coder &> /dev/null && ! [[ "$(which ninja-coder 2>/dev/null)" =~ "$PROJECT_ROOT" ]]; then
    INSTALL_MODE="global"
    success "Global installation detected (uv tool install)"
else
    success "Local development mode detected"
    info "Project directory: $PROJECT_ROOT"
fi

# Check if daemon mode is available (only for local mode)
USE_DAEMON=0

if [[ $INSTALL_MODE == "local" ]]; then
    if command -v ninja-daemon &> /dev/null && uv run --directory "$PROJECT_ROOT" ninja-daemon status >/dev/null 2>&1; then
        info "Daemon mode detected and available"
        USE_DAEMON=1
    fi
fi

info "Installing MCP servers in $INSTALL_MODE mode..."
echo ""

# Install each selected module
INSTALL_COUNT=0

if [[ $INSTALL_CODER -eq 1 ]]; then
    info "Configuring ninja-coder..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_mcp_config "ninja-coder" "ninja-coder"
    elif [[ $USE_DAEMON -eq 1 ]]; then
        # Ensure daemon is started
        uv run --directory "$PROJECT_ROOT" ninja-daemon start coder 2>/dev/null || true
        update_mcp_config "ninja-coder" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-daemon" "connect" "coder"
    else
        update_mcp_config "ninja-coder" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-coder"
    fi
    success "ninja-coder configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_RESEARCHER -eq 1 ]]; then
    info "Configuring ninja-researcher..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_mcp_config "ninja-researcher" "ninja-researcher"
    elif [[ $USE_DAEMON -eq 1 ]]; then
        # Ensure daemon is started
        uv run --directory "$PROJECT_ROOT" ninja-daemon start researcher 2>/dev/null || true
        update_mcp_config "ninja-researcher" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-daemon" "connect" "researcher"
    else
        update_mcp_config "ninja-researcher" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-researcher"
    fi
    success "ninja-researcher configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_SECRETARY -eq 1 ]]; then
    info "Configuring ninja-secretary..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_mcp_config "ninja-secretary" "ninja-secretary"
    elif [[ $USE_DAEMON -eq 1 ]]; then
        # Ensure daemon is started
        uv run --directory "$PROJECT_ROOT" ninja-daemon start secretary 2>/dev/null || true
        update_mcp_config "ninja-secretary" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-daemon" "connect" "secretary"
    else
        update_mcp_config "ninja-secretary" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-secretary"
    fi
    success "ninja-secretary configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_RESOURCES -eq 1 ]]; then
    info "Configuring ninja-resources..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_mcp_config "ninja-resources" "ninja-resources"
    else
        update_mcp_config "ninja-resources" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-resources"
    fi
    success "ninja-resources configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_PROMPTS -eq 1 ]]; then
    info "Configuring ninja-prompts..."
    if [[ $INSTALL_MODE == "global" ]]; then
        update_mcp_config "ninja-prompts" "ninja-prompts"
    else
        update_mcp_config "ninja-prompts" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-prompts"
    fi
    success "ninja-prompts configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

echo ""

# Validate final JSON
info "Validating configuration..."
if validate_json "$GEMINI_MCP_CONFIG"; then
    success "Configuration JSON is valid"
else
    error "Configuration JSON is invalid! Please check $GEMINI_MCP_CONFIG"
fi

echo ""
echo "=========================================="
echo "  Registration Complete!"
echo "=========================================="
echo ""

echo "Registered $INSTALL_COUNT MCP server(s) with Gemini CLI."
echo ""

echo "Configuration file: $GEMINI_MCP_CONFIG"
echo ""

cat "$GEMINI_MCP_CONFIG"
echo ""

echo "=========================================="
echo "  Verification"
echo "=========================================="
echo ""

info "Testing MCP server connections..."
gemini mcp list 2>&1 | head -20
echo ""

echo "=========================================="
echo "  Next Steps"
echo "=========================================="
echo ""

echo "The ninja MCP servers are now registered with Gemini CLI."
echo ""

if [[ $INSTALL_CODER -eq 1 ]]; then
    echo "📦 ${BOLD}ninja-coder${NC} - AI code execution and modification"
    echo "   Tools: coder_simple_task, coder_execute_plan_sequential, coder_execute_plan_parallel"
    echo ""
fi

if [[ $INSTALL_RESEARCHER -eq 1 ]]; then
    echo "🔍 ${BOLD}ninja-researcher${NC} - Web search and research"
    echo "   Tools: researcher_web_search, researcher_deep_research, researcher_fact_check"
    echo ""
fi

if [[ $INSTALL_SECRETARY -eq 1 ]]; then
    echo "📋 ${BOLD}ninja-secretary${NC} - Codebase exploration and documentation"
    echo "   Tools: secretary_analyse_file, secretary_file_search, secretary_codebase_report"
    echo "         secretary_document_summary, secretary_git_status, secretary_git_diff"
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

echo ""
echo "To use in Gemini CLI:"
echo "  1. Start a conversation: gemini"
echo "  2. The MCP tools are automatically available"
echo "  3. Ask Gemini to use tools as needed"
echo ""
echo ""
echo "To check status:"
echo "  gemini mcp list"
echo ""
echo ""
echo "For troubleshooting:"
echo "  - Check logs: ~/.cache/ninja-mcp/logs/"
echo "  - Validate config: python3 -m json.tool $GEMINI_MCP_CONFIG"
echo "  - Restart Gemini CLI if needed"
echo ""
