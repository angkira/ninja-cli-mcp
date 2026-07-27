#!/usr/bin/env bash
#
# Ninja MCP - Bootstrap Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash
#   ./install.sh              # TUI installer (default)
#   ./install.sh --auto       # Non-interactive / CI mode
#   ./install.sh --minimal    # Minimal install (coder only)
#
# This script:
#   1. Detects system requirements (Python 3.11+)
#   2. Installs ninja-mcp package into a managed venv
#   3. Launches TUI installer for API keys, models, IDE setup
#

set -euo pipefail

REPO_URL="${NINJA_REPO_URL:-https://github.com/angkira/ninja-cli-mcp.git}"
AUTO_MODE=false
MINIMAL_MODE=false

for arg in "$@"; do
    case "$arg" in
        --auto|--non-interactive|-y)
            AUTO_MODE=true
            ;;
        --minimal)
            MINIMAL_MODE=true
            ;;
    esac
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

info()    { echo -e "${BLUE}▸${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC} $1"; }
die()     { echo -e "${RED}✗${NC} $1"; exit 1; }

# ============================================================================
# Banner
# ============================================================================
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
info "Detecting system..."

OS="unknown"
ARCH=$(uname -m)

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
fi

info "OS: $OS | Arch: $ARCH"

if ! command -v python3 &> /dev/null; then
    die "Python 3.11+ required. Install: https://python.org"
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)'; then
    success "Python $PYTHON_VERSION"
else
    die "Python 3.11+ required (you have $PYTHON_VERSION)"
fi

# ============================================================================
# STEP 3: Install ninja-mcp
# ============================================================================
info "Installing ninja-mcp..."

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    info "Deactivating virtual environment..."
    deactivate 2>/dev/null || true
    unset VIRTUAL_ENV
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCRIPT_DIR/.venv/bin" ]]; then
    PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$SCRIPT_DIR/.venv/bin" | tr '\n' ':' | sed 's/:$//')
    export PATH
fi

export PATH="$HOME/.local/bin:$PATH"

INSTALL_SUCCESS=false
INSTALL_EXTRAS="[runtime]"
if [[ "$MINIMAL_MODE" == "true" ]]; then
    INSTALL_EXTRAS="[coder]"
fi

INSTALL_PREFIX="${NINJA_INSTALL_PREFIX:-$HOME/.local/share/ninja-mcp}"
VENV_DIR="$INSTALL_PREFIX/venv"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$INSTALL_PREFIX" "$BIN_DIR"

info "Preparing managed Python environment: $VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip

if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    info "Detected dev directory, installing from local source..."
    if "$VENV_DIR/bin/python" -m pip install --upgrade "${SCRIPT_DIR}${INSTALL_EXTRAS}" 2>&1; then
        INSTALL_SUCCESS=true
        success "Installed from local dev directory"
    else
        warn "Local install failed, falling back to remote..."
    fi
fi

if [[ "$INSTALL_SUCCESS" != "true" ]]; then
    if "$VENV_DIR/bin/python" -m pip install --upgrade "ninja-mcp${INSTALL_EXTRAS}" 2>/dev/null; then
        INSTALL_SUCCESS=true
        success "Installed from PyPI"
    elif "$VENV_DIR/bin/python" -m pip install --upgrade "ninja-mcp${INSTALL_EXTRAS} @ git+${REPO_URL}" 2>&1; then
        INSTALL_SUCCESS=true
        success "Installed from GitHub"
    else
        warn "Direct install failed, trying local build..."
        TEMP_DIR=$(mktemp -d)
        trap "rm -rf $TEMP_DIR" EXIT

        git clone --depth 1 "$REPO_URL" "$TEMP_DIR/ninja-mcp" 2>/dev/null || \
            (curl -sL "${REPO_URL%.git}/archive/main.tar.gz" | tar xz -C "$TEMP_DIR" && \
             mv "$TEMP_DIR/ninja-cli-mcp-main" "$TEMP_DIR/ninja-mcp")

        if "$VENV_DIR/bin/python" -m pip install --upgrade "$TEMP_DIR/ninja-mcp${INSTALL_EXTRAS}"; then
            INSTALL_SUCCESS=true
            success "Installed from local build"
        fi
    fi
fi

[[ "$INSTALL_SUCCESS" != "true" ]] && die "Installation failed"

for cmd in ninja-mcp ninja-coder ninja-researcher ninja-secretary ninja-config ninja-daemon; do
    if [[ -x "$VENV_DIR/bin/$cmd" ]]; then
        ln -sf "$VENV_DIR/bin/$cmd" "$BIN_DIR/$cmd"
    fi
done

for cmd in ninja-mcp ninja-coder ninja-researcher ninja-secretary ninja-config ninja-daemon; do
    cmd_path=$(command -v "$cmd" 2>/dev/null || echo "not found")
    if [[ "$cmd_path" == *"/.local/"* ]]; then
        success "$cmd: $cmd_path"
    elif [[ "$cmd_path" == "not found" ]]; then
        warn "$cmd: not found in PATH"
    else
        warn "$cmd: $cmd_path"
    fi
done

LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    export PATH="$LOCAL_BIN:$PATH"
    SHELL_RC="$HOME/.bashrc"
    [[ "$(basename "$SHELL")" == "zsh" ]] && SHELL_RC="$HOME/.zshrc"
    if ! grep -q '.local/bin' "$SHELL_RC" 2>/dev/null; then
        echo -e '\n# Ninja MCP\nexport PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        info "Added to $SHELL_RC"
    fi
fi

# ============================================================================
# STEP 4: Launch TUI Installer
# ============================================================================
if [[ "$AUTO_MODE" == "true" ]]; then
    echo ""
    info "Auto mode: writing minimal config..."

    NINJA_CONFIG="$HOME/.ninja-mcp.env"
    {
        echo "# Ninja MCP Configuration"
        echo "# Generated on $(date)"
        echo ""
        echo "NINJA_CODE_BIN=aider"
        echo "NINJA_SEARCH_PROVIDER=duckduckgo"
        echo "NINJA_ENABLE_DAEMON=true"
        echo "NINJA_ENABLED_MODULES=coder,researcher"
        echo "NINJA_CODER_PORT=8100"
        echo "NINJA_RESEARCHER_PORT=8101"
        echo ""
        echo "# Set your API keys:"
        echo "# OPENROUTER_API_KEY=sk-or-..."
        echo "# NINJA_CODER_MODEL=opencode/glm-4.7-free"
        echo "# NINJA_RESEARCHER_MODEL=sonar"
        echo "# NINJA_SECRETARY_MODEL=opencode/glm-4.7-free"
    } > "$NINJA_CONFIG"

    if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
        echo "OPENROUTER_API_KEY=${OPENROUTER_API_KEY}" >> "$NINJA_CONFIG"
        success "OpenRouter API key from environment"
    else
        warn "No OPENROUTER_API_KEY set. Run 'ninja-config install' to configure."
    fi

    if command -v aider &> /dev/null; then
        success "aider already installed"
    elif command -v pipx &> /dev/null; then
        info "Installing aider..."
        pipx install aider-chat 2>&1 && success "aider installed" || warn "Could not install aider"
    else
        warn "aider not found. Install manually: pipx install aider-chat"
    fi

    success "Auto-mode installation complete"
else
    echo ""
    info "Launching TUI installer..."
    echo ""

    if command -v ninja-config &> /dev/null; then
        exec ninja-config install
    else
        die "ninja-config not found. Installation may have failed."
    fi
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}           ${BOLD}🥷 INSTALLATION COMPLETE!${NC}                      ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo "  ninja-config configure     # Reconfigure any time"
echo "  ninja-config doctor        # Verify installation"
echo "  ninja-config select-model  # Change AI models"
echo ""
echo -e "${DIM}Documentation: https://github.com/angkira/ninja-cli-mcp${NC}"
echo ""
