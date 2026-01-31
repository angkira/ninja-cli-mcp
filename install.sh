#!/usr/bin/env bash
#
# Ninja MCP - Fully Autonomous Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash
#
# This installer will:
#   - Install ninja-mcp and all dependencies
#   - Auto-detect and configure Claude Code, VS Code, etc.
#   - Install aider if not present
#   - Configure everything automatically
#

set -euo pipefail

# Parse flags
AUTO_MODE=false
FULL_MODE=false
for arg in "$@"; do
    case "$arg" in
        --auto|--non-interactive|-y)
            AUTO_MODE=true
            ;;
        --full)
            FULL_MODE=true
            ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

info() { echo -e "${BLUE}▸${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }
step() { echo -e "\n${CYAN}${BOLD}[$1]${NC} $2"; }

# Banner
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}                                                          ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}              🥷 ${BOLD}NINJA MCP INSTALLER${NC}                      ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}                                                          ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

info() { echo -e "${BLUE}▸${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }
step() { echo -e "\n${CYAN}${BOLD}[$1]${NC} $2"; }

# Banner
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}                                                          ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}              🥷 ${BOLD}NINJA MCP INSTALLER${NC}                      ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}                                                          ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# STEP 1: System Detection
# ============================================================================
step "1/6" "Detecting system..."

OS="unknown"
DISTRO=""
ARCH=$(uname -m)

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    if command -v apt-get &> /dev/null; then
        DISTRO="debian"
    elif command -v dnf &> /dev/null; then
        DISTRO="fedora"
    elif command -v pacman &> /dev/null; then
        DISTRO="arch"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
fi

info "OS: $OS ${DISTRO:+($DISTRO)} | Arch: $ARCH"

# Check Python
if ! command -v python3 &> /dev/null; then
    error "Python 3.11+ required. Install: https://python.org"
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)'; then
    success "Python $PYTHON_VERSION"
else
    error "Python 3.11+ required (you have $PYTHON_VERSION)"
fi

# ============================================================================
# STEP 2: Install uv (if needed)
# ============================================================================
step "2/6" "Installing package manager..."

if command -v uv &> /dev/null; then
    success "uv already installed"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if command -v uv &> /dev/null; then
        success "uv installed"
    else
        error "Failed to install uv"
    fi
fi

# ============================================================================
# STEP 3: Install ninja-mcp
# ============================================================================
step "3/6" "Installing ninja-mcp..."

INSTALL_SUCCESS=false

# IMPORTANT: Deactivate any virtual environment to avoid PATH conflicts
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    info "Deactivating virtual environment..."
    deactivate 2>/dev/null || true
    unset VIRTUAL_ENV
fi

# Remove .venv/bin from PATH if present (dev directory edge case)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCRIPT_DIR/.venv/bin" ]]; then
    PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$SCRIPT_DIR/.venv/bin" | tr '\n' ':' | sed 's/:$//')
    export PATH
fi

# Ensure ~/.local/bin is at the front of PATH
export PATH="$HOME/.local/bin:$PATH"

# Detect if running from dev directory (has pyproject.toml)
if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    info "Detected dev directory, installing from local source..."
    if uv tool install --force "$SCRIPT_DIR[all]" 2>&1; then
        INSTALL_SUCCESS=true
        success "Installed from local dev directory"

        # Clean up any dev .venv binaries that might conflict
        if [[ -d "$SCRIPT_DIR/.venv/bin" ]]; then
            info "Cleaning dev environment binaries to avoid conflicts..."
            rm -f "$SCRIPT_DIR/.venv/bin/ninja-"* 2>/dev/null || true
        fi
    else
        warn "Local install failed, falling back to remote..."
    fi
fi

# If not in dev dir or local install failed, try PyPI then GitHub
if [[ "$INSTALL_SUCCESS" != "true" ]]; then
    if uv tool install ninja-mcp[all] 2>/dev/null; then
        INSTALL_SUCCESS=true
        success "Installed from PyPI"
    elif uv tool install "ninja-mcp[all] @ git+https://github.com/angkira/ninja-cli-mcp.git" 2>&1; then
        INSTALL_SUCCESS=true
        success "Installed from GitHub"
    else
        # Fallback: clone and install
        warn "Direct install failed, trying local build..."
        TEMP_DIR=$(mktemp -d)
        trap "rm -rf $TEMP_DIR" EXIT

        git clone --depth 1 https://github.com/angkira/ninja-cli-mcp.git "$TEMP_DIR/ninja-mcp" 2>/dev/null || \
            (curl -sL https://github.com/angkira/ninja-cli-mcp/archive/main.tar.gz | tar xz -C "$TEMP_DIR" && \
             mv "$TEMP_DIR/ninja-cli-mcp-main" "$TEMP_DIR/ninja-mcp")

        if uv tool install "$TEMP_DIR/ninja-mcp[all]"; then
            INSTALL_SUCCESS=true
            success "Installed from local build"
        fi
    fi
fi

[[ "$INSTALL_SUCCESS" != "true" ]] && error "Installation failed"

# Verify correct binaries are being used
info "Verifying binary locations..."
for cmd in ninja-coder ninja-researcher ninja-secretary ninja-resources ninja-prompts ninja-config ninja-daemon; do
    cmd_path=$(command -v "$cmd" 2>/dev/null || echo "not found")
    if [[ "$cmd_path" == *"/.local/"* ]]; then
        success "$cmd: $cmd_path"
    elif [[ "$cmd_path" == "not found" ]]; then
        warn "$cmd: not found in PATH"
    else
        warn "$cmd: using non-standard location: $cmd_path"
        warn "This may cause issues. Expected: ~/.local/bin/$cmd"
    fi
done

# Ensure PATH is set
LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    export PATH="$LOCAL_BIN:$PATH"

    # Add to shell config
    SHELL_RC="$HOME/.bashrc"
    [[ "$(basename "$SHELL")" == "zsh" ]] && SHELL_RC="$HOME/.zshrc"

    if ! grep -q '.local/bin' "$SHELL_RC" 2>/dev/null; then
        echo -e '\n# Ninja MCP\nexport PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        info "Added to $SHELL_RC"
    fi
fi

# ============================================================================
# STEP 4: Install dependencies (aider)
# ============================================================================
step "4/6" "Installing dependencies..."

if command -v aider &> /dev/null; then
    success "aider already installed"
else
    info "Installing aider (AI coding assistant)..."
    if uv tool install aider-chat 2>&1; then
        success "aider installed"
    else
        warn "Could not install aider (ninja-coder will have limited functionality)"
    fi
fi

# Set default code CLI to aider (ensures NINJA_CODE_BIN is configured)
if ! grep -q "NINJA_CODE_BIN" "$HOME/.ninja-mcp.env" 2>/dev/null; then
    mkdir -p "$(dirname "$HOME/.ninja-mcp.env")"
    echo "NINJA_CODE_BIN=aider" >> "$HOME/.ninja-mcp.env"
    info "Set NINJA_CODE_BIN=aider"
fi

# ============================================================================
# STEP 5: Interactive Configuration
# ============================================================================
step "5/7" "Configuring AI tools and API keys..."

# Config file - create fresh config
NINJA_CONFIG="$HOME/.ninja-mcp.env"
{
    echo "# Ninja MCP Configuration"
    echo "# Generated on $(date)"
    echo ""
    echo "# ==================================================================="
    echo "# Common Configuration"
    echo "# ==================================================================="
    echo ""
} > "$NINJA_CONFIG"

# Function to prompt for API key
prompt_for_api_key() {
    local service_name="$1"
    local url="$2"
    
    echo ""
    echo -e "${BOLD}${service_name} API Key${NC}"
    echo -e "${DIM}Get your key from: ${CYAN}${url}${NC}"
    echo ""
    
    read -s -p "Enter ${service_name} API key (hidden): " -r API_KEY
    echo ""
    echo "$API_KEY"
}

# --- AI Code CLI Selection ---
echo ""
echo -e "${BOLD}AI Code Assistant Selection${NC}"
echo "Choose your preferred AI coding assistant:"
echo "  1) Aider (OpenRouter integration) - recommended"
echo "  2) OpenCode (Multi-provider CLI with 75+ models)"
echo "  3) Gemini CLI (Google models)"
echo "  4) Cursor (IDE with AI)"
echo ""

if [[ "$AUTO_MODE" == "true" ]]; then
    CHOICE="1"
else
    read -p "Select [1-4, or press Enter for Aider]: " -r CHOICE
    CHOICE="${CHOICE:-1}"
fi

case "$CHOICE" in
    1)
        SELECTED_CLI="aider"
        echo ""
        echo -e "${BOLD}Aider Configuration${NC}"
        echo -e "${DIM}Aider uses OpenRouter for AI model access${NC}"
        echo ""
        
        # Check if aider is installed
        if ! command -v aider &> /dev/null; then
            if [[ "$AUTO_MODE" == "true" || "$FULL_MODE" == "true" ]]; then
                info "Installing aider-chat..."
                uv tool install aider-chat >/dev/null 2>&1
            else
                warn "Aider not found. Install with: uv tool install aider-chat"
            fi
        fi
        
        # Get OpenRouter API key
        if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
            OPENROUTER_KEY="${OPENROUTER_API_KEY}"
            success "Using OpenRouter API key from environment"
        else
            OPENROUTER_KEY=$(prompt_for_api_key "OpenRouter" "https://openrouter.ai/keys")
        fi
        
        # Save configuration
        {
            echo "NINJA_CODE_BIN=aider"
            echo "OPENROUTER_API_KEY=${OPENROUTER_KEY}"
        } >> "$NINJA_CONFIG"
        success "Aider configured with OpenRouter"
        ;;
        
    2)
        SELECTED_CLI="opencode"
        echo ""
        echo -e "${BOLD}OpenCode Configuration${NC}"
        echo -e "${DIM}OpenCode supports multiple providers (Anthropic, OpenAI, Google, etc.)${NC}"
        echo ""
        
        # Check if opencode is installed
        if ! command -v opencode &> /dev/null; then
            echo -e "${DIM}Install OpenCode from: https://opencode.ai/download${NC}"
            if [[ "$AUTO_MODE" != "true" ]]; then
                read -p "Press Enter to continue..." -r
            fi
        fi
        
        # OpenCode can use various providers - ask which ones to configure
        echo ""
        echo -e "${BOLD}Provider Configuration${NC}"
        echo "OpenCode supports multiple AI providers. Select which to configure:"
        echo "  1) Anthropic (Claude) - requires API key"
        echo "  2) OpenAI (GPT) - requires API key" 
        echo "  3) Google (Gemini) - requires API key"
        echo "  4) Skip - use anonymously (limited)"
        echo ""
        
        if [[ "$AUTO_MODE" == "true" ]]; then
            PROVIDER_CHOICE="4"
        else
            read -p "Select [1-4, or press Enter to skip]: " -r PROVIDER_CHOICE
            PROVIDER_CHOICE="${PROVIDER_CHOICE:-4}"
        fi
        
        {
            echo "NINJA_CODE_BIN=opencode"
        } >> "$NINJA_CONFIG"
        
        case "$PROVIDER_CHOICE" in
            1)
                ANTHROPIC_KEY=$(prompt_for_api_key "Anthropic" "https://console.anthropic.com/settings/keys")
                echo "ANTHROPIC_API_KEY=${ANTHROPIC_KEY}" >> "$NINJA_CONFIG"
                success "Anthropic configured"
                ;;
            2)
                OPENAI_KEY=$(prompt_for_api_key "OpenAI" "https://platform.openai.com/api-keys")
                echo "OPENAI_API_KEY=${OPENAI_KEY}" >> "$NINJA_CONFIG"
                success "OpenAI configured"
                ;;
            3)
                GOOGLE_KEY=$(prompt_for_api_key "Google" "https://aistudio.google.com/app/apikey")
                echo "GOOGLE_API_KEY=${GOOGLE_KEY}" >> "$NINJA_CONFIG"
                success "Google configured"
                ;;
            *)
                success "Configured for anonymous usage"
                ;;
        esac
        ;;
        
    3)
        SELECTED_CLI="gemini"
        echo ""
        echo -e "${BOLD}Gemini CLI Configuration${NC}"
        echo ""
        
        # Check if gemini is installed
        if ! command -v gemini &> /dev/null; then
            echo -e "${DIM}Install Gemini CLI from: https://ai.google.dev/gemini-api/docs${NC}"
            if [[ "$AUTO_MODE" != "true" ]]; then
                read -p "Press Enter to continue..." -r
            fi
        fi
        
        # Get Google API key
        GOOGLE_KEY=$(prompt_for_api_key "Google" "https://aistudio.google.com/app/apikey")
        
        # Save configuration
        {
            echo "NINJA_CODE_BIN=gemini"
            echo "GOOGLE_API_KEY=${GOOGLE_KEY}"
        } >> "$NINJA_CONFIG"
        success "Gemini CLI configured"
        ;;
        
    4)
        SELECTED_CLI="cursor"
        echo ""
        echo -e "${BOLD}Cursor Configuration${NC}"
        echo ""
        
        # Check if cursor is installed
        if ! command -v cursor &> /dev/null; then
            echo -e "${DIM}Download Cursor from: https://cursor.sh${NC}"
            if [[ "$AUTO_MODE" != "true" ]]; then
                read -p "Press Enter to continue..." -r
            fi
        fi
        
        # Cursor typically uses its own configuration, but we can still set up OpenRouter as backup
        echo ""
        echo -e "${BOLD}Backup Provider (Optional)${NC}"
        echo -e "${DIM}Configure OpenRouter as backup provider${NC}"
        echo ""
        
        if [[ "$AUTO_MODE" != "true" ]]; then
            read -p "Configure OpenRouter backup? [y/N]: " -r BACKUP_CHOICE
            if [[ "${BACKUP_CHOICE:-n}" =~ ^[Yy]$ ]]; then
                OPENROUTER_KEY=$(prompt_for_api_key "OpenRouter" "https://openrouter.ai/keys")
                {
                    echo "NINJA_CODE_BIN=cursor"
                    echo "OPENROUTER_API_KEY=${OPENROUTER_KEY}"
                } >> "$NINJA_CONFIG"
                success "Cursor configured with OpenRouter backup"
            else
                echo "NINJA_CODE_BIN=cursor" >> "$NINJA_CONFIG"
                success "Cursor configured"
            fi
        else
            echo "NINJA_CODE_BIN=cursor" >> "$NINJA_CONFIG"
            success "Cursor configured"
        fi
        ;;
        
    *)
        SELECTED_CLI="aider"
        OPENROUTER_KEY=$(prompt_for_api_key "OpenRouter" "https://openrouter.ai/keys")
        {
            echo "NINJA_CODE_BIN=aider"
            echo "OPENROUTER_API_KEY=${OPENROUTER_KEY}"
        } >> "$NINJA_CONFIG"
        success "Aider configured with OpenRouter (default)"
        ;;
esac

# --- Search Provider for Researcher Module ---
echo ""
echo -e "${BOLD}Search Provider${NC} ${DIM}(for ninja-researcher)${NC}"
echo "  1) DuckDuckGo (free, no API key needed)"
echo "  2) Serper/Google (better results, needs API key)"
echo "  3) Perplexity AI (best for research, needs API key)"
echo ""

if [[ "$AUTO_MODE" == "true" ]]; then
    SEARCH_CHOICE="1"
else
    read -p "Choose search provider [1-3, or press Enter for DuckDuckGo]: " -r SEARCH_CHOICE
    SEARCH_CHOICE="${SEARCH_CHOICE:-1}"
fi

case "$SEARCH_CHOICE" in
    2)
        SERPER_KEY=$(prompt_for_api_key "Serper" "https://serper.dev")
        {
            echo "NINJA_SEARCH_PROVIDER=serper"
            echo "SERPER_API_KEY=${SERPER_KEY}"
        } >> "$NINJA_CONFIG"
        success "Serper configured"
        ;;
    3)
        PERPLEXITY_KEY=$(prompt_for_api_key "Perplexity" "https://www.perplexity.ai/settings/api")
        {
            echo "NINJA_SEARCH_PROVIDER=perplexity"
            echo "PERPLEXITY_API_KEY=${PERPLEXITY_KEY}"
        } >> "$NINJA_CONFIG"
        success "Perplexity configured"
        ;;
    *)
        echo "NINJA_SEARCH_PROVIDER=duckduckgo" >> "$NINJA_CONFIG"
        success "DuckDuckGo configured (free)"
        ;;
esac

# --- Model Selection ---
echo ""
echo -e "${BOLD}Model Configuration${NC}"
echo "Setting up default models for each module..."
echo ""

# Set intelligent defaults based on selected CLI
case "$SELECTED_CLI" in
    "aider"|"cursor")
        DEFAULT_CODER_MODEL="anthropic/claude-haiku-4.5-20250929"
        DEFAULT_RESEARCHER_MODEL="anthropic/claude-sonnet-4"
        DEFAULT_SECRETARY_MODEL="anthropic/claude-haiku-4.5-20250929"
        ;;
    "opencode")
        DEFAULT_CODER_MODEL="anthropic/claude-haiku-4.5-20250929"
        DEFAULT_RESEARCHER_MODEL="anthropic/claude-sonnet-4"
        DEFAULT_SECRETARY_MODEL="google/gemini-2.0-flash-exp"
        ;;
    "gemini")
        DEFAULT_CODER_MODEL="google/gemini-2.0-flash-exp"
        DEFAULT_RESEARCHER_MODEL="google/gemini-2.0-flash-exp"
        DEFAULT_SECRETARY_MODEL="google/gemini-2.0-flash-exp"
        ;;
    *)
        DEFAULT_CODER_MODEL="anthropic/claude-haiku-4.5-20250929"
        DEFAULT_RESEARCHER_MODEL="anthropic/claude-sonnet-4"
        DEFAULT_SECRETARY_MODEL="anthropic/claude-haiku-4.5-20250929"
        ;;
esac

# Save model configuration
{
    echo "NINJA_CODER_MODEL=$DEFAULT_CODER_MODEL"
    echo "NINJA_RESEARCHER_MODEL=$DEFAULT_RESEARCHER_MODEL"
    echo "NINJA_SECRETARY_MODEL=$DEFAULT_SECRETARY_MODEL"
} >> "$NINJA_CONFIG"

success "Models configured for $SELECTED_CLI"

# Config file
NINJA_CONFIG="$HOME/.ninja-mcp.env"
touch "$NINJA_CONFIG"

# --- OpenRouter API Key ---
API_KEY="${OPENROUTER_API_KEY:-${OPENAI_API_KEY:-}}"

if [[ -z "$API_KEY" ]]; then
    if [[ "$AUTO_MODE" == "true" ]]; then
        warn "No API key found (set OPENROUTER_API_KEY before running with --auto)"
    else
        echo ""
        echo -e "${BOLD}OpenRouter API Key${NC} ${DIM}(required for AI features)${NC}"
        echo -e "${DIM}Get your key from: https://openrouter.ai/keys${NC}"
        echo ""
        read -s -p "Enter OpenRouter API key (hidden, or press Enter to skip): " -r API_KEY
        echo ""

        if [[ -n "$API_KEY" ]]; then
            # Remove old key if exists, add new one
            grep -v "OPENROUTER_API_KEY" "$NINJA_CONFIG" > "$NINJA_CONFIG.tmp" 2>/dev/null || true
            mv "$NINJA_CONFIG.tmp" "$NINJA_CONFIG"
            echo "OPENROUTER_API_KEY=$API_KEY" >> "$NINJA_CONFIG"
            export OPENROUTER_API_KEY="$API_KEY"
            success "API key saved to $NINJA_CONFIG"
        else
            warn "No API key set - AI features will not work"
        fi
    fi
else
    success "OpenRouter API key found in environment"
    # Save to config if not already there
    if ! grep -q "OPENROUTER_API_KEY" "$NINJA_CONFIG" 2>/dev/null; then
        echo "OPENROUTER_API_KEY=$API_KEY" >> "$NINJA_CONFIG"
    fi
fi

# --- Search Provider ---
SEARCH_PROVIDER="duckduckgo"

if [[ "$AUTO_MODE" == "true" ]]; then
    success "Using DuckDuckGo (default in auto mode)"
else
    echo ""
    echo -e "${BOLD}Search Provider${NC} ${DIM}(for ninja-researcher)${NC}"
    echo "  1) DuckDuckGo (free, no API key needed) - recommended"
    echo "  2) Serper/Google (better results, needs API key)"
    echo "  3) Perplexity AI (best for research, needs API key)"
    echo ""
    read -p "Choose search provider [1]: " -r SEARCH_CHOICE
    SEARCH_CHOICE="${SEARCH_CHOICE:-1}"

    case "$SEARCH_CHOICE" in
        2)
            SEARCH_PROVIDER="serper"
            echo -e "${DIM}Get Serper API key from: https://serper.dev${NC}"
            read -s -p "Enter Serper API key (hidden): " -r SERPER_KEY
            echo ""
            if [[ -n "$SERPER_KEY" ]]; then
                grep -v "SERPER_API_KEY\|NINJA_SEARCH_PROVIDER" "$NINJA_CONFIG" > "$NINJA_CONFIG.tmp" 2>/dev/null || true
                mv "$NINJA_CONFIG.tmp" "$NINJA_CONFIG"
                echo "SERPER_API_KEY=$SERPER_KEY" >> "$NINJA_CONFIG"
                echo "NINJA_SEARCH_PROVIDER=serper" >> "$NINJA_CONFIG"
                success "Using Serper (Google)"
            else
                warn "No Serper key, falling back to DuckDuckGo"
                SEARCH_PROVIDER="duckduckgo"
            fi
            ;;
        3)
            SEARCH_PROVIDER="perplexity"
            echo -e "${DIM}Get Perplexity API key from: https://www.perplexity.ai/settings/api${NC}"
            read -s -p "Enter Perplexity API key (hidden): " -r PERPLEXITY_KEY
            echo ""
            if [[ -n "$PERPLEXITY_KEY" ]]; then
                grep -v "PERPLEXITY_API_KEY\|NINJA_SEARCH_PROVIDER" "$NINJA_CONFIG" > "$NINJA_CONFIG.tmp" 2>/dev/null || true
                mv "$NINJA_CONFIG.tmp" "$NINJA_CONFIG"
                echo "PERPLEXITY_API_KEY=$PERPLEXITY_KEY" >> "$NINJA_CONFIG"
                echo "NINJA_SEARCH_PROVIDER=perplexity" >> "$NINJA_CONFIG"
                success "Using Perplexity AI"
            else
                warn "No Perplexity key, falling back to DuckDuckGo"
                SEARCH_PROVIDER="duckduckgo"
            fi
            ;;
        *)
            success "Using DuckDuckGo (free)"
            ;;
    esac
fi

# Save search provider default
if [[ "$SEARCH_PROVIDER" == "duckduckgo" ]]; then
    if ! grep -q "NINJA_SEARCH_PROVIDER" "$NINJA_CONFIG" 2>/dev/null; then
        echo "NINJA_SEARCH_PROVIDER=duckduckgo" >> "$NINJA_CONFIG"
    fi
fi

# --- Configure daemon mode ---
echo ""
echo -e "${BOLD}Daemon Mode${NC} ${DIM}(run modules as background services)${NC}"
echo ""

if [[ "$AUTO_MODE" == "true" ]]; then
    ENABLE_DAEMON="y"
else
    read -p "Enable daemon mode for better performance? [Y/n]: " -r ENABLE_DAEMON
    ENABLE_DAEMON="${ENABLE_DAEMON:-y}"
fi

if [[ "${ENABLE_DAEMON:-y}" =~ ^[Yy]$ ]]; then
    # Configure daemon ports
    {
        echo "NINJA_ENABLE_DAEMON=true"
        echo "NINJA_CODER_PORT=8100"
        echo "NINJA_RESEARCHER_PORT=8101" 
        echo "NINJA_SECRETARY_PORT=8102"
        echo "NINJA_RESOURCES_PORT=8106"
        echo "NINJA_PROMPTS_PORT=8107"
    } >> "$NINJA_CONFIG"
    success "Daemon mode enabled"
else
    echo "NINJA_ENABLE_DAEMON=false" >> "$NINJA_CONFIG"
    success "Daemon mode disabled"
fi

# ============================================================================
# STEP 6: Auto-detect and configure IDEs
# ============================================================================
step "6/7" "Configuring IDE integrations..."

CONFIGURED_IDES=()

# --- Claude Code ---
CLAUDE_CONFIG_DIR="$HOME/.config/claude"
CLAUDE_MCP_CONFIG="$CLAUDE_CONFIG_DIR/mcp.json"

# Check if Claude Code is installed
CLAUDE_INSTALLED=false
if command -v claude &> /dev/null; then
    CLAUDE_INSTALLED=true
elif [[ -d "$CLAUDE_CONFIG_DIR" ]]; then
    CLAUDE_INSTALLED=true
elif [[ -d "$HOME/.claude" ]]; then
    CLAUDE_INSTALLED=true
fi

if [[ "$CLAUDE_INSTALLED" == "true" ]]; then
    info "Detected Claude Code, configuring via 'claude mcp add'..."

    # Use claude mcp add command (the correct way to register MCP servers)
    # Remove existing entries first (ignore errors if they don't exist)
    for server in ninja-coder ninja-researcher ninja-secretary ninja-resources ninja-prompts; do
        claude mcp remove "$server" -s user 2>/dev/null || true
    done

    # Add all 5 servers to user scope
    for server in ninja-coder ninja-researcher ninja-secretary ninja-resources ninja-prompts; do
        if claude mcp add --scope user --transport stdio "$server" -- "$server" 2>/dev/null; then
            success "$server registered"
        else
            warn "Failed to register $server"
        fi
    done

    CONFIGURED_IDES+=("Claude Code")

    info "Run 'claude mcp list' to verify"
else
    info "Claude Code not detected (install from: https://claude.ai/download)"
fi

# --- OpenCode ---
OPENCODE_CONFIG="$HOME/.opencode.json"
[[ ! -f "$OPENCODE_CONFIG" ]] && OPENCODE_CONFIG="$HOME/.config/opencode/.opencode.json"

if command -v opencode &> /dev/null || [[ -f "$OPENCODE_CONFIG" ]]; then
    info "Detected OpenCode, configuring MCP..."

    if [[ -f "$SCRIPT_DIR/scripts/install_opencode_mcp.sh" ]]; then
        bash "$SCRIPT_DIR/scripts/install_opencode_mcp.sh" --all
        CONFIGURED_IDES+=("OpenCode")
    else
        warn "OpenCode installation script not found, skipping..."
    fi
else
    info "OpenCode not detected (install from: https://opencode.ai/download)"
fi

# --- VS Code ---
VSCODE_CONFIG="$HOME/.config/Code/User/settings.json"
[[ "$OS" == "macos" ]] && VSCODE_CONFIG="$HOME/Library/Application Support/Code/User/settings.json"

if [[ -f "$VSCODE_CONFIG" ]] || command -v code &> /dev/null; then
    info "Detected VS Code"
    # VS Code MCP support would go here when available
    # For now, just note it
    CONFIGURED_IDES+=("VS Code (detected)")
fi

# --- Cursor ---
CURSOR_CONFIG="$HOME/.config/Cursor/User/settings.json"
[[ "$OS" == "macos" ]] && CURSOR_CONFIG="$HOME/Library/Application Support/Cursor/User/settings.json"

if [[ -f "$CURSOR_CONFIG" ]] || command -v cursor &> /dev/null; then
    info "Detected Cursor"
    CONFIGURED_IDES+=("Cursor (detected)")
fi

# --- Zed ---
if command -v zed &> /dev/null || [[ -d "$HOME/.config/zed" ]]; then
    info "Detected Zed"
    CONFIGURED_IDES+=("Zed (detected)")
fi

if [[ ${#CONFIGURED_IDES[@]} -eq 0 ]]; then
    warn "No supported IDEs detected"
else
    success "Configured: ${CONFIGURED_IDES[*]}"
fi

# ============================================================================
# STEP 7: Final verification
# ============================================================================
step "7/7" "Verifying installation..."

VERIFY_PASSED=true

# Check commands exist
for cmd in ninja-config ninja-coder ninja-researcher ninja-secretary ninja-daemon; do
    if command -v "$cmd" &> /dev/null; then
        success "$cmd"
    else
        warn "$cmd not in PATH"
        VERIFY_PASSED=false
    fi
done

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}           ${BOLD}🥷 INSTALLATION COMPLETE!${NC}                      ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}Installed commands:${NC}"
echo "  ninja-coder       - AI code assistant (MCP server)"
echo "  ninja-researcher  - Web research (MCP server)"
echo "  ninja-secretary   - File operations (MCP server)"
echo "  ninja-resources   - Resource templates (MCP server)"
echo "  ninja-prompts     - Prompt management (MCP server)"
echo "  ninja-config      - Configuration & diagnostics"
echo "  ninja-daemon      - Server management"
echo ""

echo -e "${BOLD}Configuration:${NC} ~/.ninja-mcp.env"
echo -e "  - AI Code CLI: $SELECTED_CLI"
echo -e "  - Search provider: $(grep NINJA_SEARCH_PROVIDER "$NINJA_CONFIG" | cut -d= -f2)"
echo -e "  - Models configured for optimal performance"
echo -e "  - API keys collected and secured"
echo ""

if [[ ${#CONFIGURED_IDES[@]} -gt 0 ]]; then
    echo -e "${BOLD}Configured IDEs:${NC} ${CONFIGURED_IDES[*]}"
    echo ""
fi

echo -e "${BOLD}Quick start:${NC}"
echo -e "  ${DIM}# Load configuration${NC}"
echo "  source ~/.ninja-mcp.env"
echo ""
echo -e "  ${DIM}# Verify everything works${NC}"
echo "  ninja-config doctor"
echo ""
echo -e "  ${DIM}# Select your preferred operator and model${NC}"
echo "  ninja-config select-model"
echo ""

if [[ "$VERIFY_PASSED" != "true" ]]; then
    echo -e "${YELLOW}⚠ Some commands not in PATH. Restart your shell or run:${NC}"
    echo "  source ~/.bashrc  # or ~/.zshrc"
    echo ""
fi

echo -e "${DIM}Documentation: https://github.com/angkira/ninja-cli-mcp${NC}"
echo ""
