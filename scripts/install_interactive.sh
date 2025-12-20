#!/usr/bin/env bash
#
# install_interactive.sh - Modern interactive installer for ninja-cli-mcp
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
    echo -e "${BOLD}${MAGENTA}║${NC}              ${CYAN}${BOLD}🥷 NINJA CLI MCP INSTALLER${NC}              ${BOLD}${MAGENTA}║${NC}"
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

spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    while ps -p $pid > /dev/null 2>&1; do
        local temp=${spinstr#?}
        printf " ${CYAN}%c${NC} " "$spinstr"
        spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Configuration file
CONFIG_FILE="$HOME/.ninja-cli-mcp.env"

# Print header
clear
print_header

echo -e "${DIM}Welcome! This installer will help you set up ninja-cli-mcp,${NC}"
echo -e "${DIM}an MCP server that delegates code tasks to AI assistants.${NC}"
echo ""

# Step 1: Check dependencies
step "Step 1: Checking dependencies"

# Check Python - prefer 3.12, but accept 3.11+
info "Checking Python version..."

PYTHON_CMD=""
PYTHON_VERSION=""

# Try python3.12 first
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
    echo ""
    error "Python 3.11+ is required (found $PYTHON_VERSION)"
    echo ""
    echo -e "${BOLD}How to install Python 3.12:${NC}"
    echo ""
    echo -e "${DIM}On macOS (using Homebrew):${NC}"
    echo -e "  ${CYAN}brew install python@3.12${NC}"
    echo ""
    echo -e "${DIM}On Ubuntu/Debian:${NC}"
    echo -e "  ${CYAN}sudo apt update${NC}"
    echo -e "  ${CYAN}sudo apt install python3.12${NC}"
    echo ""
    echo -e "${DIM}On Fedora/RHEL:${NC}"
    echo -e "  ${CYAN}sudo dnf install python3.12${NC}"
    echo ""
    echo -e "${DIM}Using pyenv (recommended):${NC}"
    echo -e "  ${CYAN}pyenv install 3.12${NC}"
    echo -e "  ${CYAN}pyenv global 3.12${NC}"
    echo ""
    exit 1
fi

success "Python $PYTHON_VERSION"

# Check if Python 3.12 is available but not being used
if [[ "$PYTHON_CMD" != "python3.12" ]] && command -v python3.12 &> /dev/null; then
    info "Python 3.12 is available but not default"
    echo ""
    echo -e "${DIM}To make Python 3.12 your default:${NC}"
    echo ""
    echo -e "${BOLD}Option 1: Using update-alternatives (Ubuntu/Debian)${NC}"
    echo -e "  ${CYAN}sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1${NC}"
    echo -e "  ${CYAN}sudo update-alternatives --config python3${NC}"
    echo ""
    echo -e "${BOLD}Option 2: Create an alias (add to ~/.bashrc or ~/.zshrc)${NC}"
    echo -e "  ${CYAN}alias python3='python3.12'${NC}"
    echo ""
    echo -e "${BOLD}Option 3: Use pyenv${NC}"
    echo -e "  ${CYAN}pyenv global 3.12${NC}"
    echo ""
    if ! confirm "Continue with Python $PYTHON_VERSION?"; then
        exit 0
    fi
fi

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

# Check git
info "Checking for git..."
if command -v git &> /dev/null; then
    success "git $(git --version | cut -d' ' -f3)"
else
    error "git is not installed"
fi

# Step 2: Install dependencies
step "Step 2: Installing Python dependencies"

# Use the specific Python version we found
export UV_PYTHON="$PYTHON_CMD"

info "Installing project dependencies with $PYTHON_CMD..."
# Capture stderr to show errors, hide stdout for cleaner output
SYNC_ERR=$(uv sync --python "$PYTHON_CMD" 2>&1 >/dev/null)
if [[ $? -eq 0 ]]; then
    success "Dependencies installed"
else
    echo ""
    error "Failed to install dependencies"
    if [[ -n "$SYNC_ERR" ]]; then
        echo "$SYNC_ERR"
    fi
fi

info "Installing dev dependencies..."
# Attempt to install dev dependencies but don't fail if some packages are missing
DEV_ERR=$(uv sync --all-extras --python "$PYTHON_CMD" 2>&1 >/dev/null)
if [[ $? -eq 0 ]]; then
    success "Dev dependencies installed"
else
    warn "Some dev dependencies may have failed"
    if [[ -n "$DEV_ERR" ]] && [[ "$DEV_ERR" != *"already satisfied"* ]]; then
        echo -e "${DIM}You can install them later with: uv sync --all-extras${NC}"
    fi
fi

# Step 3: Configure API keys
step "Step 3: Configuring OpenRouter API"

echo ""
echo -e "${DIM}ninja-cli-mcp uses OpenRouter to access AI models.${NC}"
echo -e "${DIM}Get your API key from: ${CYAN}https://openrouter.ai/keys${NC}"
echo ""

# Check if API key already exists
EXISTING_KEY="${OPENROUTER_API_KEY:-${OPENAI_API_KEY:-}}"
USE_EXISTING_KEY=false

if [[ -n "$EXISTING_KEY" ]]; then
    MASKED_KEY="${EXISTING_KEY:0:8}...${EXISTING_KEY: -4}"
    info "Found existing API key: $MASKED_KEY"
    if ! confirm "Would you like to use a different API key?"; then
        API_KEY="$EXISTING_KEY"
        USE_EXISTING_KEY=true
        success "Using existing API key"
    else
        API_KEY=$(prompt_secret "Enter your OpenRouter API key (input hidden):")
    fi
else
    API_KEY=$(prompt_secret "Enter your OpenRouter API key (input hidden):")
fi

# Only validate new keys, not existing ones (they're already working)
if [[ "$USE_EXISTING_KEY" != "true" ]]; then
    # Strip any ANSI escape codes from the API key (can happen with terminal quirks)
    API_KEY=$(echo "$API_KEY" | sed 's/\x1b\[[0-9;]*m//g')

    # Validate API key format
    if [[ -z "$API_KEY" ]]; then
        warn "No API key provided. You'll need to set OPENROUTER_API_KEY later."
    elif [[ ${#API_KEY} -lt 20 ]]; then
        warn "API key seems too short. Please verify it's correct."
    elif [[ "$API_KEY" =~ [^a-zA-Z0-9_-] ]]; then
        error "API key contains invalid characters. OpenRouter keys should only contain alphanumeric, dash, and underscore."
    elif [[ ${#API_KEY} -gt 100 ]]; then
        warn "API key seems unusually long (${#API_KEY} chars). Please verify it's correct."
    else
        success "API key configured"
    fi
fi

# Step 4: Choose model
step "Step 4: Selecting AI model"

echo ""
echo -e "${DIM}Choose your default model (you can change this anytime):${NC}"
echo ""
echo -e "  ${BOLD}1.${NC} anthropic/claude-sonnet-4     ${DIM}(Recommended - Best for complex code)${NC}"
echo -e "  ${BOLD}2.${NC} openai/gpt-4o                ${DIM}(Fast and capable)${NC}"
echo -e "  ${BOLD}3.${NC} qwen/qwen3-coder              ${DIM}(Free tier available)${NC}"
echo -e "  ${BOLD}4.${NC} deepseek/deepseek-coder       ${DIM}(Cost-effective)${NC}"
echo ""

prompt "Enter choice [1-4] or model ID (e.g., meta-llama/llama-3.1-70b) (default: 1):"
read -r model_choice

case "${model_choice:-1}" in
    1) NINJA_MODEL="anthropic/claude-sonnet-4" ;;
    2) NINJA_MODEL="openai/gpt-4o" ;;
    3) NINJA_MODEL="qwen/qwen3-coder" ;;
    4) NINJA_MODEL="deepseek/deepseek-coder" ;;
    *)
        # If input contains a slash, treat it as a model ID
        if [[ "$model_choice" =~ / ]]; then
            NINJA_MODEL="$model_choice"
        else
            warn "Invalid choice, using default"
            NINJA_MODEL="anthropic/claude-sonnet-4"
        fi
        ;;
esac

success "Model: $NINJA_MODEL"

# Step 5: AI Code CLI path
step "Step 5: Configuring AI Code CLI"

echo ""
echo -e "${DIM}ninja-cli-mcp delegates code work to an AI code CLI binary.${NC}"
echo -e "${DIM}Scanning for available AI code assistants...${NC}"
echo ""

# Auto-detect AI CLIs
DETECTED_CLIS=()

# Helper function to check if a command is a real executable (not a shell built-in)
is_real_executable() {
    local cmd="$1"
    # Check if it's a shell built-in
    if type -t "$cmd" 2>/dev/null | grep -q "builtin"; then
        return 1
    fi
    # Check if the command exists and is executable
    local cmd_path
    cmd_path=$(command -v "$cmd" 2>/dev/null)
    if [[ -n "$cmd_path" ]] && [[ -x "$cmd_path" ]]; then
        return 0
    fi
    return 1
}

# Check for aider
if is_real_executable aider; then
    AIDER_PATH=$(command -v aider)
    DETECTED_CLIS+=("aider|$AIDER_PATH")
    info "Found: aider at $AIDER_PATH"
elif [[ -f "$HOME/.local/bin/aider" ]]; then
    AIDER_PATH="$HOME/.local/bin/aider"
    DETECTED_CLIS+=("aider|$AIDER_PATH")
    info "Found: aider at $AIDER_PATH"
fi

# Check for cursor CLI (the standalone code editor CLI, not cursor for shell)
if is_real_executable cursor; then
    CURSOR_PATH=$(command -v cursor)
    # Verify it's actually the Cursor IDE CLI, not something else
    if [[ "$CURSOR_PATH" == *".cursor"* ]] || cursor --version 2>&1 | grep -iq "cursor"; then
        DETECTED_CLIS+=("cursor|$CURSOR_PATH")
        info "Found: cursor at $CURSOR_PATH"
    fi
elif [[ -f "$HOME/.cursor/bin/cursor" ]]; then
    CURSOR_PATH="$HOME/.cursor/bin/cursor"
    DETECTED_CLIS+=("cursor|$CURSOR_PATH")
    info "Found: cursor at $CURSOR_PATH"
fi

# Check for continue CLI (not the shell built-in!)
# Continue.dev would typically be installed as a real executable
if is_real_executable continue; then
    CONTINUE_PATH=$(command -v continue)
    # Make sure it's not a symlink to bash built-in or shell function
    if [[ -f "$CONTINUE_PATH" ]] && file "$CONTINUE_PATH" 2>/dev/null | grep -qv "shell script"; then
        DETECTED_CLIS+=("continue|$CONTINUE_PATH")
        info "Found: continue at $CONTINUE_PATH"
    fi
fi

# Check for ninja-code (custom)
if is_real_executable ninja-code; then
    NINJA_PATH=$(command -v ninja-code)
    DETECTED_CLIS+=("ninja-code|$NINJA_PATH")
    info "Found: ninja-code at $NINJA_PATH"
fi

# Check for claude (can be used as both MCP host and code executor)
if is_real_executable claude; then
    CLAUDE_PATH=$(command -v claude)
    DETECTED_CLIS+=("claude|$CLAUDE_PATH")
    info "Found: claude at $CLAUDE_PATH"
fi

# Check common bin directories for other CLIs
for bin_dir in "$HOME/.local/bin" "$HOME/bin" "/usr/local/bin" "/opt/homebrew/bin"; do
    if [[ -d "$bin_dir" ]]; then
        for cli in ninja-code aider cursor claude; do
            if [[ -x "$bin_dir/$cli" ]] && ! command -v "$cli" &> /dev/null; then
                DETECTED_CLIS+=("$cli|$bin_dir/$cli")
                info "Found: $cli at $bin_dir/$cli"
            fi
        done
    fi
done

echo ""

# Let user choose from detected CLIs or enter custom path
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

    prompt "Enter your choice [1-${idx}] (default: 1):"
    read -r cli_choice
    cli_choice="${cli_choice:-1}"

    if [[ "$cli_choice" -ge 1 ]] && [[ "$cli_choice" -lt "$idx" ]]; then
        selected_entry="${DETECTED_CLIS[$((cli_choice-1))]}"
        NINJA_CODE_BIN=$(echo "$selected_entry" | cut -d'|' -f2)
        success "Selected: $NINJA_CODE_BIN"
    else
        prompt "Enter path to AI code CLI binary:"
        read -r NINJA_CODE_BIN
    fi
else
    warn "No AI code assistants detected automatically"
    echo ""
    echo -e "${DIM}Popular AI code assistants:${NC}"
    echo -e "  ${BULLET} aider - Install: ${CYAN}uv tool install aider-chat${NC}"
    echo -e "  ${BULLET} cursor - Install: ${CYAN}https://www.cursor.com${NC}"
    echo -e "  ${BULLET} continue - Install: ${CYAN}https://continue.dev${NC}"
    echo -e "  ${BULLET} claude - Can be used as code executor${NC}"
    echo ""
    echo -e "${DIM}Note: The AI code CLI executes code tasks. You can use 'claude'${NC}"
    echo -e "${DIM}as both the MCP host and the code executor.${NC}"
    echo ""
    prompt "Enter path to AI code CLI binary (or press Enter to set later):"
    read -r NINJA_CODE_BIN
    NINJA_CODE_BIN="${NINJA_CODE_BIN:-ninja-code}"
fi

# Validate CLI if it's not empty and not the default placeholder
if [[ -n "$NINJA_CODE_BIN" ]] && [[ "$NINJA_CODE_BIN" != "ninja-code" ]]; then
    info "Validating AI CLI..."

    # Check if the CLI exists and is executable
    if command -v "$NINJA_CODE_BIN" &>/dev/null || [[ -x "$NINJA_CODE_BIN" ]]; then
        # Try to detect CLI type and validate flags
        cli_basename=$(basename "$NINJA_CODE_BIN")

        if [[ "$cli_basename" == *"claude"* ]]; then
            # Validate Claude CLI supports required flags
            if "$NINJA_CODE_BIN" --help 2>&1 | grep -q -- "--print"; then
                success "Claude CLI validated"
            else
                warn "Claude CLI doesn't support --print flag. May need updates."
            fi
        elif [[ "$cli_basename" == *"aider"* ]]; then
            # Validate Aider CLI
            if "$NINJA_CODE_BIN" --help 2>&1 | grep -q -- "--message"; then
                success "Aider CLI validated"
            else
                warn "Aider CLI doesn't support --message flag. May need updates."
            fi
        else
            # Generic validation - just check it runs
            if "$NINJA_CODE_BIN" --version &>/dev/null || "$NINJA_CODE_BIN" --help &>/dev/null; then
                success "AI CLI accessible"
            else
                warn "Could not validate AI CLI. It may not work correctly."
            fi
        fi
    else
        warn "AI CLI not found or not executable: $NINJA_CODE_BIN"
        echo ""
        echo -e "${DIM}You can update this later in: $CONFIG_FILE${NC}"
        echo ""
    fi
fi

# Step 6: HTTP Daemon Port Configuration
step "Step 6: HTTP Daemon Port Configuration"

echo ""
echo -e "${DIM}Configure the port for HTTP/SSE daemon mode${NC}"
echo ""
echo "The daemon listens on this port for MCP client connections."
echo ""
echo "Default: 8947 (less likely to conflict)"
echo "Common alternatives: 3000, 8080, 9000"
echo ""

# Default to a less popular port
DEFAULT_PORT=8947
HTTP_PORT=""

read -p "$(echo -e "${BLUE}?${NC} Enter HTTP port [default: ${DEFAULT_PORT}]: ")" port_input

if [[ -z "$port_input" ]]; then
    HTTP_PORT="$DEFAULT_PORT"
elif [[ "$port_input" =~ ^[0-9]+$ ]] && [[ "$port_input" -ge 1024 ]] && [[ "$port_input" -le 65535" ]]; then
    HTTP_PORT="$port_input"
else
    warn "Invalid port number. Using default: $DEFAULT_PORT"
    HTTP_PORT="$DEFAULT_PORT"
fi

success "HTTP Port: $HTTP_PORT"

# Step 7: Save configuration
step "Step 7: Saving configuration"

echo ""
info "Creating configuration file at: $CONFIG_FILE"

cat > "$CONFIG_FILE" << EOF
# ninja-cli-mcp Configuration
# Generated on $(date)

# OpenRouter API Key
export OPENROUTER_API_KEY='$API_KEY'

# Model Selection
export NINJA_MODEL='$NINJA_MODEL'

# AI Code CLI Binary
export NINJA_CODE_BIN='$NINJA_CODE_BIN'

# HTTP Daemon Port
export NINJA_HTTP_PORT=$HTTP_PORT

# Optional: Timeout in seconds
# export NINJA_TIMEOUT_SEC=600
EOF

chmod 600 "$CONFIG_FILE"
success "Configuration saved"

# Step 8: Shell integration
step "Step 8: Shell integration"

echo ""
SHELL_RC=""
case "$SHELL" in
    */bash) SHELL_RC="$HOME/.bashrc" ;;
    */zsh)  SHELL_RC="$HOME/.zshrc" ;;
    */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
    *) SHELL_RC="" ;;
esac

if [[ -n "$SHELL_RC" ]] && [[ -f "$SHELL_RC" ]]; then
    if ! grep -q "ninja-cli-mcp.env" "$SHELL_RC" 2>/dev/null; then
        if confirm "Add ninja-cli-mcp to your shell startup ($SHELL_RC)?"; then
            echo "" >> "$SHELL_RC"
            echo "# Load ninja-cli-mcp configuration" >> "$SHELL_RC"
            echo "[ -f \"$CONFIG_FILE\" ] && source \"$CONFIG_FILE\"" >> "$SHELL_RC"
            success "Added to $SHELL_RC"
            info "Run: source $SHELL_RC"
        fi
    else
        info "Already integrated with $SHELL_RC"
    fi
fi

# Source the config for current session
source "$CONFIG_FILE"

# Step 9: Claude Code Integration
step "Step 9: Claude Code Integration"

echo ""
echo -e "${DIM}Checking for Claude Code...${NC}"
echo ""

CLAUDE_INSTALLED=false
if command -v claude &> /dev/null; then
    CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
    success "Claude Code CLI found: $CLAUDE_VERSION"
    CLAUDE_INSTALLED=true
else
    warn "Claude Code CLI not found"
    echo ""
    echo -e "${DIM}Claude Code is an AI coding assistant that can use ninja-cli-mcp.${NC}"
    echo -e "${DIM}Install from: ${CYAN}https://claude.ai/code${NC}"
    echo ""
fi

if [[ "$CLAUDE_INSTALLED" == "true" ]]; then
    if confirm "Would you like to register ninja-cli-mcp with Claude Code?"; then
        info "Registering with Claude Code..."

        # Get the run_server.sh path
        RUN_SERVER="$SCRIPT_DIR/run_server.sh"

        if [[ ! -x "$RUN_SERVER" ]]; then
            info "Making run_server.sh executable..."
            chmod +x "$RUN_SERVER"
        fi

        # Check if already registered
        if claude mcp list 2>/dev/null | grep -q "ninja-cli-mcp"; then
            warn "ninja-cli-mcp is already registered"
            if confirm "Re-register?"; then
                info "Removing existing registration..."
                claude mcp remove ninja-cli-mcp 2>/dev/null || true
            else
                info "Keeping existing registration"
                CLAUDE_REGISTERED=true
            fi
        fi

        # Register the MCP server if not already registered
        if [[ "${CLAUDE_REGISTERED:-false}" != "true" ]]; then
            if claude mcp add --scope user --transport stdio ninja-cli-mcp -- "$RUN_SERVER" 2>/dev/null; then
                success "Successfully registered ninja-cli-mcp with Claude Code (user scope)"
                CLAUDE_REGISTERED=true
            else
                warn "Failed to register MCP server (you can do this manually later)"
            fi
        fi
    fi
fi

# Step 9b: Copilot CLI integration
step "Step 9b: Copilot CLI Integration"

echo ""
COPILOT_INSTALLED=false

# Check for copilot command
if command -v copilot &> /dev/null; then
    COPILOT_VERSION=$(copilot --version 2>/dev/null | head -n1 || echo "unknown")
    success "GitHub Copilot CLI found: $COPILOT_VERSION"
    COPILOT_INSTALLED=true
elif command -v gh &> /dev/null && gh extension list 2>/dev/null | grep -q "copilot"; then
    success "GitHub Copilot CLI found: gh extension"
    COPILOT_INSTALLED=true
else
    warn "GitHub Copilot CLI not found"
    echo ""
    echo -e "${DIM}GitHub Copilot CLI can use ninja-cli-mcp via MCP.${NC}"
    echo -e "${DIM}Install: ${CYAN}npm install -g @githubnext/github-copilot-cli${NC}"
    echo -e "${DIM}Or: ${CYAN}gh extension install github/gh-copilot${NC}"
    echo ""
fi

COPILOT_REGISTERED=false
if [[ "$COPILOT_INSTALLED" == "true" ]]; then
    if confirm "Would you like to configure ninja-cli-mcp for Copilot CLI?"; then
        info "Configuring Copilot CLI..."
        
        # Run the Copilot CLI installer script
        if ./scripts/install_copilot_cli_mcp.sh; then
            success "Successfully configured ninja-cli-mcp for Copilot CLI"
            COPILOT_REGISTERED=true
        else
            warn "Failed to configure Copilot CLI (you can do this manually later)"
        fi
    fi
fi

# Step 10: Verification
step "Step 10: Verifying Installation"

echo ""
info "Running installation verification..."
echo ""

VERIFICATION_PASSED=true

# Check 1: Python dependencies
info "Checking Python installation..."
if uv run python -c "import ninja_cli_mcp" 2>/dev/null; then
    success "Python package installed correctly"
else
    error "Python package not found"
    VERIFICATION_PASSED=false
fi

# Check 2: Configuration file
info "Checking configuration..."
if [[ -f "$CONFIG_FILE" ]]; then
    success "Configuration file exists"
    if source "$CONFIG_FILE" 2>/dev/null; then
        if [[ -n "$OPENROUTER_API_KEY" ]] || [[ -n "$OPENAI_API_KEY" ]]; then
            success "API key is set"
        else
            warn "API key not set in config"
            VERIFICATION_PASSED=false
        fi
    else
        warn "Configuration file has errors"
    fi
else
    warn "Configuration file not found"
    VERIFICATION_PASSED=false
fi

# Check 3: AI CLI availability
info "Checking AI CLI..."
if [[ -n "$NINJA_CODE_BIN" ]]; then
    if command -v "$NINJA_CODE_BIN" &>/dev/null || [[ -x "$NINJA_CODE_BIN" ]]; then
        success "AI CLI is accessible: $NINJA_CODE_BIN"
    else
        warn "AI CLI not found at: $NINJA_CODE_BIN"
        info "You can update this later in: $CONFIG_FILE"
    fi
fi

# Check 4: Claude Code integration
if [[ "${CLAUDE_REGISTERED:-false}" == "true" ]]; then
    info "Checking Claude Code registration..."
    if claude mcp list 2>/dev/null | grep -q "ninja-cli-mcp"; then
        success "ninja-cli-mcp is registered with Claude Code"
    else
        warn "Claude Code registration verification failed"
    fi
fi

# Check 5: Run quick tests
echo ""
if confirm "Would you like to run tests to verify functionality?"; then
    info "Running tests..."
    TEST_OUTPUT=$(uv run pytest tests/test_metrics.py tests/test_paths.py -v --tb=short 2>&1)
    TEST_EXIT_CODE=$?
    
    # Show last 20 lines of output
    echo "$TEST_OUTPUT" | tail -20
    
    if [[ $TEST_EXIT_CODE -eq 0 ]]; then
        success "Core tests passed"
    else
        error "Tests failed! Please review the output above."
        warn "This may indicate configuration issues or bugs."
        VERIFICATION_PASSED=false
    fi
fi

# Step 11: Final summary
echo ""
echo -e "${BOLD}${MAGENTA}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
echo -e "${BOLD}${MAGENTA}║${NC}            ${GREEN}${BOLD}${CHECK} Installation Complete!${NC}                 ${BOLD}${MAGENTA}║${NC}"
echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
echo -e "${BOLD}${MAGENTA}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}Configuration Summary:${NC}"
echo -e "  ${BULLET} API Key:    ${DIM}${API_KEY:0:8}...${API_KEY: -4}${NC}"
echo -e "  ${BULLET} Model:      ${CYAN}$NINJA_MODEL${NC}"
echo -e "  ${BULLET} AI CLI:     ${DIM}$NINJA_CODE_BIN${NC}"
echo -e "  ${BULLET} Config:     ${DIM}$CONFIG_FILE${NC}"
echo ""

if [[ "${CLAUDE_REGISTERED:-false}" == "true" ]]; then
    echo -e "${BOLD}Claude Code Integration:${NC}"
    echo -e "  ${GREEN}${CHECK}${NC} ninja-cli-mcp is registered with Claude Code"
    echo ""
    echo -e "${BOLD}To use ninja-cli-mcp in Claude Code:${NC}"
    echo -e "  ${BOLD}1.${NC} Start Claude Code: ${CYAN}claude${NC}"
    echo -e "  ${BOLD}2.${NC} Check available MCP tools: ${CYAN}/mcp${NC}"
    echo -e "  ${BOLD}3.${NC} Ask Claude to use ninja tools for code tasks"
    echo ""
fi

if [[ "${COPILOT_REGISTERED:-false}" == "true" ]]; then
    echo -e "${BOLD}Copilot CLI Integration:${NC}"
    echo -e "  ${GREEN}${CHECK}${NC} ninja-cli-mcp is configured for Copilot CLI"
    echo ""
    echo -e "${BOLD}To use ninja-cli-mcp in Copilot CLI:${NC}"
    echo -e "  ${BOLD}1.${NC} Start Copilot CLI: ${CYAN}copilot${NC}"
    echo -e "  ${BOLD}2.${NC} The MCP server will load automatically"
    echo -e "  ${BOLD}3.${NC} Ask Copilot to use ninja tools for code tasks"
    echo ""
fi

if [[ "${CLAUDE_REGISTERED:-false}" == "true" ]] || [[ "${COPILOT_REGISTERED:-false}" == "true" ]]; then
    echo -e "${DIM}Available MCP tools:${NC}"
    echo -e "  ${BULLET} ninja_quick_task - Quick single-pass task execution"
    echo -e "  ${BULLET} execute_plan_sequential - Execute plan steps in order"
    echo -e "  ${BULLET} execute_plan_parallel - Execute plan steps concurrently"
    echo -e "  ${BULLET} run_tests - Run test commands"
    echo -e "  ${BULLET} apply_patch - Apply patches to code"
    echo ""
fi

echo -e "${BOLD}Next Steps:${NC}"
echo ""
echo -e "  ${BOLD}1.${NC} Load the configuration:"
echo -e "     ${DIM}source $CONFIG_FILE${NC}"
echo ""
if [[ "${CLAUDE_REGISTERED:-false}" != "true" ]] && [[ "${COPILOT_REGISTERED:-false}" != "true" ]]; then
    echo -e "  ${BOLD}2.${NC} (Optional) Register with an IDE/CLI:"
    echo -e "     ${DIM}• Claude Code:  ./scripts/install_claude_code_mcp.sh${NC}"
    echo -e "     ${DIM}• Copilot CLI:  ./scripts/install_copilot_cli_mcp.sh${NC}"
    echo -e "     ${DIM}• VS Code:      ./scripts/install_vscode_mcp.sh${NC}"
    echo -e "     ${DIM}• All detected: ./scripts/install_ide_integrations.sh${NC}"
    echo ""
    echo -e "  ${BOLD}3.${NC} Or start the MCP server standalone:"
    echo -e "     ${DIM}./scripts/run_server.sh${NC}"
    echo ""
    echo -e "  ${BOLD}4.${NC} View available commands:"
    echo -e "     ${DIM}python -m ninja_cli_mcp.cli --help${NC}"
    echo ""
    echo -e "  ${BOLD}5.${NC} List available models:"
    echo -e "     ${DIM}python -m ninja_cli_mcp.cli list-models${NC}"
    echo ""
else
    echo -e "  ${BOLD}2.${NC} View available commands:"
    echo -e "     ${DIM}python -m ninja_cli_mcp.cli --help${NC}"
    echo ""
    echo -e "  ${BOLD}3.${NC} List available models:"
    echo -e "     ${DIM}python -m ninja_cli_mcp.cli list-models${NC}"
    echo ""
fi

echo -e "${DIM}For more information, see: ${CYAN}README.md${NC}"
echo ""
echo -e "${GREEN}Happy coding! 🥷${NC}"
echo ""
