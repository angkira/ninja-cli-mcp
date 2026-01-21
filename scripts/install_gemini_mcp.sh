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

# Remove existing ninja MCP servers first
info "Removing existing ninja MCP servers..."
gemini mcp remove ninja-coder 2>/dev/null || true
gemini mcp remove ninja-researcher 2>/dev/null || true
gemini mcp remove ninja-secretary 2>/dev/null || true
gemini mcp remove ninja-resources 2>/dev/null || true
gemini mcp remove ninja-prompts 2>/dev/null || true

# Helper function to add MCP server with environment variables
add_mcp_server() {
    local server_name="$1"
    local command="$2"
    shift 2
    local args=("$@")
    
    # Set default environment variables based on server type
    local env_vars=()
    if [[ "$server_name" == "ninja-coder" ]]; then
        env_vars+=("-e" "NINJA_CODER_MODEL=google/gemini-2.0-flash-exp")
        env_vars+=("-e" "NINJA_CODE_BIN=gemini")
        env_vars+=("-e" "NINJA_CODER_TIMEOUT=300")
    elif [[ "$server_name" == "ninja-researcher" ]]; then
        env_vars+=("-e" "NINJA_RESEARCHER_MODEL=google/gemini-2.0-flash-exp")
        env_vars+=("-e" "NINJA_RESEARCHER_MAX_SOURCES=20")
        env_vars+=("-e" "NINJA_RESEARCHER_PARALLEL_AGENTS=4")
    elif [[ "$server_name" == "ninja-secretary" ]]; then
        env_vars+=("-e" "NINJA_SECRETARY_MODEL=google/gemini-2.0-flash-exp")
        env_vars+=("-e" "NINJA_SECRETARY_MAX_FILE_SIZE=1048576")
    elif [[ "$server_name" == "ninja-resources" ]]; then
        env_vars+=("-e" "NINJA_RESOURCES_CACHE_TTL=3600")
        env_vars+=("-e" "NINJA_RESOURCES_MAX_FILES=1000")
    elif [[ "$server_name" == "ninja-prompts" ]]; then
        env_vars+=("-e" "NINJA_PROMPTS_MAX_SUGGESTIONS=5")
        env_vars+=("-e" "NINJA_PROMPTS_CACHE_TTL=3600")
    fi
    
    # Add API key if available
    if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
        env_vars+=("-e" "OPENROUTER_API_KEY=$OPENROUTER_API_KEY")
    elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
        env_vars+=("-e" "OPENAI_API_KEY=$OPENAI_API_KEY")
    fi
    
    # Add server
    if [[ ${#args[@]} -gt 0 ]]; then
        gemini mcp add "${env_vars[@]}" "$server_name" "$command" "${args[@]}"
    else
        gemini mcp add "${env_vars[@]}" "$server_name" "$command"
    fi
}

if [[ $INSTALL_CODER -eq 1 ]]; then
    info "Configuring ninja-coder..."
    if [[ $INSTALL_MODE == "global" ]]; then
        add_mcp_server "ninja-coder" "ninja-coder"
    elif [[ $USE_DAEMON -eq 1 ]]; then
        # Ensure daemon is started
        uv run --directory "$PROJECT_ROOT" ninja-daemon start coder 2>/dev/null || true
        add_mcp_server "ninja-coder" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-daemon" "connect" "coder"
    else
        add_mcp_server "ninja-coder" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-coder"
    fi
    success "ninja-coder configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_RESEARCHER -eq 1 ]]; then
    info "Configuring ninja-researcher..."
    if [[ $INSTALL_MODE == "global" ]]; then
        add_mcp_server "ninja-researcher" "ninja-researcher"
    elif [[ $USE_DAEMON -eq 1 ]]; then
        # Ensure daemon is started
        uv run --directory "$PROJECT_ROOT" ninja-daemon start researcher 2>/dev/null || true
        add_mcp_server "ninja-researcher" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-daemon" "connect" "researcher"
    else
        add_mcp_server "ninja-researcher" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-researcher"
    fi
    success "ninja-researcher configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_SECRETARY -eq 1 ]]; then
    info "Configuring ninja-secretary..."
    if [[ $INSTALL_MODE == "global" ]]; then
        add_mcp_server "ninja-secretary" "ninja-secretary"
    elif [[ $USE_DAEMON -eq 1 ]]; then
        # Ensure daemon is started
        uv run --directory "$PROJECT_ROOT" ninja-daemon start secretary 2>/dev/null || true
        add_mcp_server "ninja-secretary" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-daemon" "connect" "secretary"
    else
        add_mcp_server "ninja-secretary" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-secretary"
    fi
    success "ninja-secretary configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_RESOURCES -eq 1 ]]; then
    info "Configuring ninja-resources..."
    if [[ $INSTALL_MODE == "global" ]]; then
        add_mcp_server "ninja-resources" "ninja-resources"
    else
        add_mcp_server "ninja-resources" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-resources"
    fi
    success "ninja-resources configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_PROMPTS -eq 1 ]]; then
    info "Configuring ninja-prompts..."
    if [[ $INSTALL_MODE == "global" ]]; then
        add_mcp_server "ninja-prompts" "ninja-prompts"
    else
        add_mcp_server "ninja-prompts" "uv" "--directory" "$PROJECT_ROOT" "run" "ninja-prompts"
    fi
    success "ninja-prompts configured"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

echo ""

# Validate final JSON
info "Validating configuration..."
if python3 -m json.tool "$GEMINI_MCP_CONFIG" > /dev/null 2>&1; then
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

echo "To use in Gemini CLI:"
echo "  1. Start a conversation: gemini"
echo "  2. The MCP tools are automatically available"
echo "  3. Ask Gemini to use tools as needed"
echo ""
echo "To check status:"
echo "  gemini mcp list"
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
echo "  - Validate config: python3 -m json.tool $GEMINI_MCP_CONFIG"
echo "  - Restart Gemini CLI if needed"
echo ""