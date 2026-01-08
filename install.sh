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

# Try PyPI first, then GitHub
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

[[ "$INSTALL_SUCCESS" != "true" ]] && error "Installation failed"

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

# ============================================================================
# STEP 5: Auto-detect and configure IDEs
# ============================================================================
step "5/6" "Configuring IDE integrations..."

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
    info "Detected Claude Code, configuring..."

    mkdir -p "$CLAUDE_CONFIG_DIR"

    # Get API key from environment
    API_KEY="${OPENROUTER_API_KEY:-${OPENAI_API_KEY:-}}"

    # Build server configs
    SERVERS_JSON=$(cat << EOJSON
{
  "ninja-coder": {
    "command": "ninja-coder",
    "args": ["--mode", "stdio"],
    "env": {${API_KEY:+"\"OPENROUTER_API_KEY\": \"$API_KEY\""}}
  },
  "ninja-researcher": {
    "command": "ninja-researcher",
    "args": ["--mode", "stdio"],
    "env": {${API_KEY:+"\"OPENROUTER_API_KEY\": \"$API_KEY\""}}
  },
  "ninja-secretary": {
    "command": "ninja-secretary",
    "args": ["--mode", "stdio"],
    "env": {${API_KEY:+"\"OPENROUTER_API_KEY\": \"$API_KEY\""}}
  }
}
EOJSON
)

    # Merge with existing config or create new
    if [[ -f "$CLAUDE_MCP_CONFIG" ]]; then
        # Backup existing
        cp "$CLAUDE_MCP_CONFIG" "$CLAUDE_MCP_CONFIG.backup"

        # Merge using Python
        python3 << EOPY
import json
from pathlib import Path

config_path = Path("$CLAUDE_MCP_CONFIG")
with config_path.open() as f:
    config = json.load(f)

servers = json.loads('''$SERVERS_JSON''')
config.setdefault("mcpServers", {}).update(servers)

with config_path.open("w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
EOPY
        success "Claude Code configured (merged with existing)"
    else
        # Create new config
        echo "{\"mcpServers\": $SERVERS_JSON}" | python3 -m json.tool > "$CLAUDE_MCP_CONFIG"
        success "Claude Code configured (new)"
    fi

    CONFIGURED_IDES+=("Claude Code")

    if [[ -z "$API_KEY" ]]; then
        warn "No API key found - set OPENROUTER_API_KEY and run: ninja-config setup-claude --force"
    fi
else
    info "Claude Code not detected (install from: https://claude.ai/download)"
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
# STEP 6: Final verification
# ============================================================================
step "6/6" "Verifying installation..."

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
echo "  ninja-config      - Configuration & diagnostics"
echo "  ninja-daemon      - Server management"
echo ""

if [[ ${#CONFIGURED_IDES[@]} -gt 0 ]]; then
    echo -e "${BOLD}Configured IDEs:${NC} ${CONFIGURED_IDES[*]}"
    echo ""
fi

echo -e "${BOLD}Quick start:${NC}"
echo -e "  ${DIM}# Set your API key (if not already set)${NC}"
echo "  export OPENROUTER_API_KEY='sk-or-...'"
echo ""
echo -e "  ${DIM}# Verify everything works${NC}"
echo "  ninja-config doctor"
echo ""
echo -e "  ${DIM}# Reconfigure Claude Code (if needed)${NC}"
echo "  ninja-config setup-claude --force"
echo ""

if [[ "$VERIFY_PASSED" != "true" ]]; then
    echo -e "${YELLOW}⚠ Some commands not in PATH. Restart your shell or run:${NC}"
    echo "  source ~/.bashrc  # or ~/.zshrc"
    echo ""
fi

echo -e "${DIM}Documentation: https://github.com/angkira/ninja-cli-mcp${NC}"
echo ""
