#!/usr/bin/env bash
#
# install_interactive.sh - Multi-module interactive installer for ninja-mcp
#
# Usage: ./scripts/install_interactive.sh
#

set -euo pipefail

# Colors and formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Unicode characters
CHECK="✓"
CROSS="✗"
ARROW="→"
BULLET="•"

# Helper functions
print_header() {
    echo ""
    echo -e "${BOLD}${MAGENTA}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
    echo -e "${BOLD}${MAGENTA}║${NC}              ${CYAN}${BOLD}🥷 NINJA MCP INSTALLER${NC}                ${BOLD}${MAGENTA}║${NC}"
    echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
    echo -e "${BOLD}${MAGENTA}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

info() {
    echo -e "${BLUE}${BULLET}${NC} $1"
}

success() {
    echo -e "${GREEN}${CHECK}${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

error() {
    echo -e "${RED}${CROSS}${NC} $1"
    exit 1
}

step() {
    echo ""
    echo -e "${BOLD}${CYAN}${ARROW} $1${NC}"
    echo -e "${DIM}─────────────────────────────────────────────────────────${NC}"
}

prompt() {
    echo -ne "${CYAN}?${NC} ${BOLD}$1${NC} "
}

prompt_secret() {
    echo -ne "${CYAN}?${NC} ${BOLD}$1${NC} " >&2
    read -s value
    echo "" >&2
    echo "$value"
}

confirm() {
    echo -ne "${CYAN}?${NC} ${BOLD}$1${NC} ${DIM}[y/N]${NC} " >&2
    read -r response
    [[ "$response" =~ ^[Yy]$ ]]
}

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Configuration file
CONFIG_FILE="$HOME/.ninja-mcp.env"

# Print header
clear
print_header

echo -e "${DIM}Welcome! This installer will help you set up Ninja MCP modules:${NC}"
echo -e "${DIM}  • Coder - AI code execution${NC}"
echo -e "${DIM}  • Researcher - Web search & reports${NC}"
echo -e "${DIM}  • Secretary - Documentation & codebase exploration (coming soon)${NC}"
echo ""

# Step 1: Module selection
step "Step 1: Select modules to install"

echo ""
echo -e "${DIM}Select which modules you want to install:${NC}"
echo ""

INSTALL_CODER=true
INSTALL_RESEARCHER=false
INSTALL_SECRETARY=false

echo -e "  ${BOLD}1.${NC} Coder ${DIM}(AI code execution - recommended)${NC}"
if confirm "Install Coder module?"; then
    INSTALL_CODER=true
    success "Coder module selected"
else
    INSTALL_CODER=false
    info "Coder module skipped"
fi

echo ""
echo -e "  ${BOLD}2.${NC} Researcher ${DIM}(Web search & reports)${NC}"
if confirm "Install Researcher module?"; then
    INSTALL_RESEARCHER=true
    success "Researcher module selected"
else
    INSTALL_RESEARCHER=false
    info "Researcher module skipped"
fi

echo ""
echo -e "  ${BOLD}3.${NC} Secretary ${DIM}(Documentation & codebase - under development)${NC}"
if confirm "Install Secretary module?"; then
    INSTALL_SECRETARY=true
    success "Secretary module selected"
else
    INSTALL_SECRETARY=false
    info "Secretary module skipped"
fi

echo ""
echo -e "${BOLD}Selected modules:${NC}"
[[ "$INSTALL_CODER" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Coder"
[[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Researcher"
[[ "$INSTALL_SECRETARY" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Secretary"

# Step 2: Check dependencies
step "Step 2: Checking dependencies"

# Check Python
info "Checking Python version..."

PYTHON_CMD=""
PYTHON_VERSION=""

if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
    PYTHON_VERSION=$(python3.12 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
    PYTHON_VERSION=$(python3.11 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if [[ "$PYTHON_MAJOR" -ge 3 ]] && [[ "$PYTHON_MINOR" -ge 11 ]]; then
        PYTHON_CMD="python3"
    fi
fi

if [[ -z "$PYTHON_CMD" ]]; then
    error "Python 3.11+ is required"
fi

success "Python $PYTHON_VERSION"

# Check uv
info "Checking for uv package manager..."
if command -v uv &> /dev/null; then
    UV_VERSION=$(uv --version 2>/dev/null | head -n1 | cut -d' ' -f2)
    success "uv $UV_VERSION"
else
    warn "uv not found"
    if confirm "Would you like to install uv now?"; then
        info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
        if command -v uv &> /dev/null; then
            success "uv installed successfully"
        else
            error "Failed to install uv"
        fi
    else
        error "uv is required. Install from: https://docs.astral.sh/uv/"
    fi
fi

# Step 3: Install dependencies
step "Step 3: Installing dependencies"

export UV_PYTHON="$PYTHON_CMD"

# Build extras list based on selected modules
EXTRAS=""
[[ "$INSTALL_CODER" == "true" ]] && EXTRAS="${EXTRAS}coder,"
[[ "$INSTALL_RESEARCHER" == "true" ]] && EXTRAS="${EXTRAS}researcher,"
[[ "$INSTALL_SECRETARY" == "true" ]] && EXTRAS="${EXTRAS}secretary,"
EXTRAS="${EXTRAS%,}"  # Remove trailing comma

if [[ -n "$EXTRAS" ]]; then
    info "Installing modules: $EXTRAS"
    uv sync --extra "$EXTRAS" --python "$PYTHON_CMD" 2>&1 | grep -v "already satisfied" || true
    success "Modules installed"
else
    info "Installing base dependencies only"
    uv sync --python "$PYTHON_CMD" 2>&1 | grep -v "already satisfied" || true
    success "Base dependencies installed"
fi

# Step 4: Configure API keys
step "Step 4: Configuring API keys"

echo ""
echo -e "${DIM}Configure API keys for the selected modules:${NC}"
echo ""

# OpenRouter API key (for Coder)
OPENROUTER_KEY=""
if [[ "$INSTALL_CODER" == "true" ]]; then
    echo -e "${BOLD}OpenRouter API Key${NC} ${DIM}(required for Coder)${NC}"
    echo -e "${DIM}Get your key from: ${CYAN}https://openrouter.ai/keys${NC}"
    echo ""
    
    EXISTING_KEY="${OPENROUTER_API_KEY:-${OPENAI_API_KEY:-}}"
    if [[ -n "$EXISTING_KEY" ]]; then
        MASKED_KEY="${EXISTING_KEY:0:8}...${EXISTING_KEY: -4}"
        info "Found existing API key: $MASKED_KEY"
        if confirm "Use existing key?"; then
            OPENROUTER_KEY="$EXISTING_KEY"
            success "Using existing OpenRouter key"
        else
            OPENROUTER_KEY=$(prompt_secret "Enter OpenRouter API key:")
        fi
    else
        OPENROUTER_KEY=$(prompt_secret "Enter OpenRouter API key:")
    fi
fi

# Serper API key (for Researcher)
SERPER_KEY=""
if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
    echo ""
    echo -e "${BOLD}Serper.dev API Key${NC} ${DIM}(optional for Researcher - DuckDuckGo is free fallback)${NC}"
    echo -e "${DIM}Get your key from: ${CYAN}https://serper.dev${NC}"
    echo -e "${DIM}Free tier: 2,500 searches/month${NC}"
    echo ""
    
    EXISTING_SERPER="${SERPER_API_KEY:-}"
    if [[ -n "$EXISTING_SERPER" ]]; then
        MASKED_SERPER="${EXISTING_SERPER:0:8}...${EXISTING_SERPER: -4}"
        info "Found existing Serper key: $MASKED_SERPER"
        if confirm "Use existing key?"; then
            SERPER_KEY="$EXISTING_SERPER"
            success "Using existing Serper key"
        else
            if confirm "Configure Serper API key?"; then
                SERPER_KEY=$(prompt_secret "Enter Serper API key:")
                success "Serper key configured"
            else
                info "Skipping Serper (will use DuckDuckGo)"
            fi
        fi
    else
        if confirm "Configure Serper API key?"; then
            SERPER_KEY=$(prompt_secret "Enter Serper API key:")
            success "Serper key configured"
        else
            info "Skipping Serper (will use DuckDuckGo)"
        fi
    fi
fi

# Step 5: Model selection
step "Step 5: Selecting AI models"

echo ""
echo -e "${DIM}Choose models for each module:${NC}"
echo ""

# Coder model
CODER_MODEL=""
if [[ "$INSTALL_CODER" == "true" ]]; then
    echo -e "${BOLD}Coder Module Model:${NC}"
    echo -e "  ${BOLD}1.${NC} anthropic/claude-haiku-4.5-20250929 ${DIM}(Fast & capable - recommended)${NC}"
    echo -e "  ${BOLD}2.${NC} anthropic/claude-sonnet-4 ${DIM}(Best for complex code)${NC}"
    echo -e "  ${BOLD}3.${NC} openai/gpt-4o ${DIM}(Fast and capable)${NC}"
    echo -e "  ${BOLD}4.${NC} qwen/qwen3-coder ${DIM}(Free tier available)${NC}"
    echo ""
    
    prompt "Enter choice [1-4] (default: 1):"
    read -r model_choice
    
    case "${model_choice:-1}" in
        1) CODER_MODEL="anthropic/claude-haiku-4.5-20250929" ;;
        2) CODER_MODEL="anthropic/claude-sonnet-4" ;;
        3) CODER_MODEL="openai/gpt-4o" ;;
        4) CODER_MODEL="qwen/qwen3-coder" ;;
        *) CODER_MODEL="anthropic/claude-haiku-4.5-20250929" ;;
    esac
    
    success "Coder model: $CODER_MODEL"
fi

# Researcher model
RESEARCHER_MODEL=""
if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
    echo ""
    echo -e "${BOLD}Researcher Module Model:${NC}"
    echo -e "  ${BOLD}1.${NC} anthropic/claude-sonnet-4 ${DIM}(Best for research synthesis)${NC}"
    echo -e "  ${BOLD}2.${NC} openai/gpt-4o ${DIM}(Fast and capable)${NC}"
    echo ""
    
    prompt "Enter choice [1-2] (default: 1):"
    read -r model_choice
    
    case "${model_choice:-1}" in
        1) RESEARCHER_MODEL="anthropic/claude-sonnet-4" ;;
        2) RESEARCHER_MODEL="openai/gpt-4o" ;;
        *) RESEARCHER_MODEL="anthropic/claude-sonnet-4" ;;
    esac
    
    success "Researcher model: $RESEARCHER_MODEL"
fi

# Secretary model
SECRETARY_MODEL=""
if [[ "$INSTALL_SECRETARY" == "true" ]]; then
    echo ""
    echo -e "${BOLD}Secretary Module Model:${NC}"
    echo -e "  ${BOLD}1.${NC} anthropic/claude-haiku-4.5-20250929 ${DIM}(Fast for summaries - recommended)${NC}"
    echo -e "  ${BOLD}2.${NC} anthropic/claude-sonnet-4 ${DIM}(Better quality)${NC}"
    echo ""
    
    prompt "Enter choice [1-2] (default: 1):"
    read -r model_choice
    
    case "${model_choice:-1}" in
        1) SECRETARY_MODEL="anthropic/claude-haiku-4.5-20250929" ;;
        2) SECRETARY_MODEL="anthropic/claude-sonnet-4" ;;
        *) SECRETARY_MODEL="anthropic/claude-haiku-4.5-20250929" ;;
    esac
    
    success "Secretary model: $SECRETARY_MODEL"
fi

# Step 6: AI Code CLI (for Coder module)
NINJA_CODE_BIN=""
if [[ "$INSTALL_CODER" == "true" ]]; then
    step "Step 6: Configuring AI Code CLI (for Coder)"
    
    echo ""
    echo -e "${DIM}Scanning for AI code assistants...${NC}"
    echo ""
    
    DETECTED_CLIS=()
    
    # Check for aider
    if command -v aider &> /dev/null; then
        AIDER_PATH=$(command -v aider)
        DETECTED_CLIS+=("aider|$AIDER_PATH")
        info "Found: aider at $AIDER_PATH"
    fi
    
    # Check for cursor
    if command -v cursor &> /dev/null; then
        CURSOR_PATH=$(command -v cursor)
        if [[ "$CURSOR_PATH" == *".cursor"* ]] || cursor --version 2>&1 | grep -iq "cursor"; then
            DETECTED_CLIS+=("cursor|$CURSOR_PATH")
            info "Found: cursor at $CURSOR_PATH"
        fi
    fi
    
    echo ""
    
    if [[ ${#DETECTED_CLIS[@]} -gt 0 ]]; then
        success "Found ${#DETECTED_CLIS[@]} AI code assistant(s)"
        echo ""
        echo -e "${DIM}Select an AI code assistant:${NC}"
        echo ""
        
        idx=1
        for cli_entry in "${DETECTED_CLIS[@]}"; do
            cli_name=$(echo "$cli_entry" | cut -d'|' -f1)
            cli_path=$(echo "$cli_entry" | cut -d'|' -f2)
            echo -e "  ${BOLD}${idx}.${NC} ${cli_name} ${DIM}(${cli_path})${NC}"
            ((idx++))
        done
        echo -e "  ${BOLD}${idx}.${NC} Enter custom path"
        echo ""
        
        prompt "Enter choice [1-${idx}] (default: 1):"
        read -r cli_choice
        cli_choice="${cli_choice:-1}"
        
        if [[ "$cli_choice" -ge 1 ]] && [[ "$cli_choice" -lt "$idx" ]]; then
            selected_entry="${DETECTED_CLIS[$((cli_choice-1))]}"
            NINJA_CODE_BIN=$(echo "$selected_entry" | cut -d'|' -f2)
            success "Selected: $NINJA_CODE_BIN"
        else
            prompt "Enter path to AI code CLI:"
            read -r NINJA_CODE_BIN
        fi
    else
        warn "No AI code assistants detected"
        echo ""
        echo -e "${DIM}Install aider: ${CYAN}uv tool install aider-chat${NC}"
        echo ""
        prompt "Enter path to AI code CLI (or press Enter to set later):"
        read -r NINJA_CODE_BIN
        NINJA_CODE_BIN="${NINJA_CODE_BIN:-aider}"
    fi
fi

# Step 7: Daemon configuration
step "Step 7: Daemon configuration"

echo ""
ENABLE_DAEMON=false
if confirm "Run modules as daemons (background processes)?"; then
    ENABLE_DAEMON=true
    success "Daemon mode enabled"
else
    info "Daemon mode disabled (will run in foreground)"
fi

# Step 8: Save configuration
step "Step 8: Saving configuration"

echo ""
info "Creating configuration file at: $CONFIG_FILE"

cat > "$CONFIG_FILE" << EOF
# Ninja MCP Configuration
# Generated on $(date)

# ============================================================================
# Common Configuration
# ============================================================================

# OpenRouter API Key (for Coder and Researcher)
export OPENROUTER_API_KEY='$OPENROUTER_KEY'

EOF

if [[ "$INSTALL_CODER" == "true" ]]; then
    cat >> "$CONFIG_FILE" << EOF
# ============================================================================
# Coder Module
# ============================================================================

# Coder model
export NINJA_CODER_MODEL='$CODER_MODEL'

# AI Code CLI binary
export NINJA_CODE_BIN='$NINJA_CODE_BIN'

# Coder timeout (seconds)
export NINJA_CODER_TIMEOUT=600

EOF
fi

if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
    cat >> "$CONFIG_FILE" << EOF
# ============================================================================
# Researcher Module
# ============================================================================

# Researcher model
export NINJA_RESEARCHER_MODEL='$RESEARCHER_MODEL'

# Serper.dev API key (optional - DuckDuckGo is free fallback)
export SERPER_API_KEY='$SERPER_KEY'

# Max sources per research
export NINJA_RESEARCHER_MAX_SOURCES=20

# Parallel research agents
export NINJA_RESEARCHER_PARALLEL_AGENTS=4

EOF
fi

if [[ "$INSTALL_SECRETARY" == "true" ]]; then
    cat >> "$CONFIG_FILE" << EOF
# ============================================================================
# Secretary Module
# ============================================================================

# Secretary model
export NINJA_SECRETARY_MODEL='$SECRETARY_MODEL'

# Max file size to analyze (bytes)
export NINJA_SECRETARY_MAX_FILE_SIZE=1048576

# Cache directory
export NINJA_SECRETARY_CACHE_DIR=~/.cache/ninja-secretary

EOF
fi

chmod 600 "$CONFIG_FILE"
success "Configuration saved"

# Step 9: IDE Integration
step "Step 9: IDE Integration"

echo ""
echo -e "${DIM}Checking for supported IDEs...${NC}"
echo ""

CLAUDE_INSTALLED=false
if command -v claude &> /dev/null; then
    success "Claude Code CLI found"
    CLAUDE_INSTALLED=true
fi

VSCODE_INSTALLED=false
if command -v code &> /dev/null; then
    success "VS Code found"
    VSCODE_INSTALLED=true
fi

ZED_INSTALLED=false
if command -v zed &> /dev/null || [[ -d "$HOME/.config/zed" ]]; then
    success "Zed found"
    ZED_INSTALLED=true
fi

echo ""
echo -e "${BOLD}Register with IDEs:${NC}"
echo ""

# Claude Code
if [[ "$CLAUDE_INSTALLED" == "true" ]]; then
    if confirm "Register modules with Claude Code?"; then
        info "Registering with Claude Code..."
        
        # Create Claude MCP config directory
        CLAUDE_CONFIG_DIR="$HOME/.config/claude"
        mkdir -p "$CLAUDE_CONFIG_DIR"
        
        # Create or update mcp.json
        CLAUDE_MCP_CONFIG="$CLAUDE_CONFIG_DIR/mcp.json"
        
        if [[ -f "$CLAUDE_MCP_CONFIG" ]]; then
            info "Backing up existing Claude config..."
            cp "$CLAUDE_MCP_CONFIG" "$CLAUDE_MCP_CONFIG.backup"
        fi
        
        # Build MCP config
        cat > "$CLAUDE_MCP_CONFIG" << 'EOF'
{
  "mcpServers": {
EOF
        
        if [[ "$INSTALL_CODER" == "true" ]]; then
            cat >> "$CLAUDE_MCP_CONFIG" << 'EOF'
    "ninja-coder": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_coder.server"]
    },
EOF
        fi
        
        if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
            cat >> "$CLAUDE_MCP_CONFIG" << 'EOF'
    "ninja-researcher": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_researcher.server"]
    },
EOF
        fi
        
        if [[ "$INSTALL_SECRETARY" == "true" ]]; then
            cat >> "$CLAUDE_MCP_CONFIG" << 'EOF'
    "ninja-secretary": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_secretary.server"]
    },
EOF
        fi
        
        # Remove trailing comma and close JSON
        cat >> "$CLAUDE_MCP_CONFIG" << 'EOF'
  }
}
EOF
        
        # Fix trailing comma issue
        sed -i.tmp 's/},$/}/g' "$CLAUDE_MCP_CONFIG" 2>/dev/null || sed -i '' 's/},$/}/g' "$CLAUDE_MCP_CONFIG" 2>/dev/null || true
        rm -f "$CLAUDE_MCP_CONFIG.tmp"
        
        success "Registered with Claude Code"
    fi
fi

# VS Code
if [[ "$VSCODE_INSTALLED" == "true" ]]; then
    if confirm "Register modules with VS Code?"; then
        info "Registering with VS Code..."
        warn "VS Code integration coming soon - manual configuration required"
        echo -e "${DIM}See README.md for VS Code setup instructions${NC}"
    fi
fi

# Zed
if [[ "$ZED_INSTALLED" == "true" ]]; then
    if confirm "Register modules with Zed?"; then
        info "Registering with Zed..."
        warn "Zed integration coming soon - manual configuration required"
        echo -e "${DIM}See README.md for Zed setup instructions${NC}"
    fi
fi

# Step 10: Final summary
echo ""
echo -e "${BOLD}${MAGENTA}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
echo -e "${BOLD}${MAGENTA}║${NC}            ${GREEN}${BOLD}${CHECK} Installation Complete!${NC}                 ${BOLD}${MAGENTA}║${NC}"
echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
echo -e "${BOLD}${MAGENTA}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}Installed Modules:${NC}"
[[ "$INSTALL_CODER" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Coder - AI code execution"
[[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Researcher - Web search & reports"
[[ "$INSTALL_SECRETARY" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Secretary - Documentation & codebase"
echo ""

echo -e "${BOLD}Configuration:${NC}"
echo -e "  ${BULLET} Config file: ${DIM}$CONFIG_FILE${NC}"
[[ -n "$CODER_MODEL" ]] && echo -e "  ${BULLET} Coder model: ${CYAN}$CODER_MODEL${NC}"
[[ -n "$RESEARCHER_MODEL" ]] && echo -e "  ${BULLET} Researcher model: ${CYAN}$RESEARCHER_MODEL${NC}"
[[ -n "$SECRETARY_MODEL" ]] && echo -e "  ${BULLET} Secretary model: ${CYAN}$SECRETARY_MODEL${NC}"
[[ -n "$SERPER_KEY" ]] && echo -e "  ${BULLET} Serper.dev: ${GREEN}Configured${NC}"
[[ -z "$SERPER_KEY" ]] && [[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "  ${BULLET} Serper.dev: ${DIM}Not configured (using DuckDuckGo)${NC}"
echo ""

echo -e "${BOLD}Next Steps:${NC}"
echo ""
echo -e "  ${BOLD}1.${NC} Load configuration:"
echo -e "     ${DIM}source $CONFIG_FILE${NC}"
echo ""

if [[ "$ENABLE_DAEMON" == "true" ]]; then
    echo -e "  ${BOLD}2.${NC} Start daemons:"
    [[ "$INSTALL_CODER" == "true" ]] && echo -e "     ${DIM}ninja-daemon start coder${NC}"
    [[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "     ${DIM}ninja-daemon start researcher${NC}"
    [[ "$INSTALL_SECRETARY" == "true" ]] && echo -e "     ${DIM}ninja-daemon start secretary${NC}"
    echo ""
    echo -e "  ${BOLD}3.${NC} Check daemon status:"
    echo -e "     ${DIM}ninja-daemon status${NC}"
else
    echo -e "  ${BOLD}2.${NC} Run servers directly:"
    [[ "$INSTALL_CODER" == "true" ]] && echo -e "     ${DIM}ninja-coder${NC}"
    [[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "     ${DIM}ninja-researcher${NC}"
    [[ "$INSTALL_SECRETARY" == "true" ]] && echo -e "     ${DIM}ninja-secretary${NC}"
fi

echo ""
echo -e "  ${BOLD}3.${NC} Test the installation:"
if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
    echo -e "     ${DIM}# Test researcher${NC}"
    echo -e "     ${DIM}source $CONFIG_FILE${NC}"
    echo -e "     ${DIM}ninja-researcher${NC}"
    echo -e "     ${DIM}# Then in Claude/IDE: researcher_web_search({\"query\": \"test\"})${NC}"
fi
echo ""

echo -e "${DIM}For more information, see: ${CYAN}README.md${NC}"
echo ""
echo -e "${GREEN}Happy coding! 🥷${NC}"
echo ""
