#!/usr/bin/env bash
#
# install_ide_integrations.sh - Unified IDE MCP integration installer
#
# This script detects which IDEs are installed (VSCode, Zed, Copilot CLI)
# and configures ninja-cli-mcp for all available IDEs.
#
# Prerequisites:
#   - ninja-cli-mcp installed and configured
#   - At least one supported IDE installed
#
# Usage: ./scripts/install_ide_integrations.sh [--all|--vscode|--zed|--copilot]

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
}

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments
INSTALL_ALL=1
INSTALL_VSCODE=0
INSTALL_ZED=0
INSTALL_COPILOT=0

if [[ $# -gt 0 ]]; then
    INSTALL_ALL=0
    for arg in "$@"; do
        case "$arg" in
            --all)
                INSTALL_ALL=1
                ;;
            --vscode)
                INSTALL_VSCODE=1
                ;;
            --zed)
                INSTALL_ZED=1
                ;;
            --copilot)
                INSTALL_COPILOT=1
                ;;
            *)
                error "Unknown option: $arg"
                echo ""
                echo "Usage: $0 [--all|--vscode|--zed|--copilot]"
                echo ""
                echo "Options:"
                echo "  --all        Install for all detected IDEs (default)"
                echo "  --vscode     Install for VS Code only"
                echo "  --zed        Install for Zed only"
                echo "  --copilot    Install for Copilot CLI only"
                echo ""
                exit 1
                ;;
        esac
    done
fi

clear

echo ""
echo "=========================================="
echo "  IDE MCP Integration Installer"
echo "=========================================="
echo ""
echo "This script will configure ninja-cli-mcp for"
echo "compatible IDEs and AI coding assistants."
echo ""

# Detect available IDEs
info "Detecting installed IDEs..."
echo ""

VSCODE_AVAILABLE=0
ZED_AVAILABLE=0
COPILOT_AVAILABLE=0

# Check for VS Code
if command -v code &> /dev/null; then
    VSCODE_VERSION=$(code --version 2>/dev/null | head -n1)
    VSCODE_AVAILABLE=1
    echo -e "  ${GREEN}✓${NC} VS Code: $VSCODE_VERSION"
else
    echo -e "  ${RED}✗${NC} VS Code: Not installed"
fi

# Check for Zed
if command -v zed &> /dev/null; then
    ZED_VERSION=$(zed --version 2>/dev/null | head -n1 || echo "unknown")
    ZED_AVAILABLE=1
    echo -e "  ${GREEN}✓${NC} Zed: $ZED_VERSION"
else
    echo -e "  ${RED}✗${NC} Zed: Not installed"
fi

# Check for Copilot CLI
if gh extension list 2>/dev/null | grep -q "copilot" || command -v github-copilot-cli &> /dev/null; then
    COPILOT_AVAILABLE=1
    echo -e "  ${GREEN}✓${NC} GitHub Copilot CLI: Available"
else
    echo -e "  ${RED}✗${NC} GitHub Copilot CLI: Not installed"
fi

echo ""

# Check if any IDE is available
if [[ $VSCODE_AVAILABLE -eq 0 && $ZED_AVAILABLE -eq 0 && $COPILOT_AVAILABLE -eq 0 ]]; then
    error "No supported IDEs detected"
    echo ""
    echo "Supported IDEs:"
    echo "  - VS Code (https://code.visualstudio.com/)"
    echo "  - Zed (https://zed.dev/)"
    echo "  - GitHub Copilot CLI (gh extension install github/gh-copilot)"
    echo ""
    exit 1
fi

# Determine what to install
if [[ $INSTALL_ALL -eq 1 ]]; then
    INSTALL_VSCODE=$VSCODE_AVAILABLE
    INSTALL_ZED=$ZED_AVAILABLE
    INSTALL_COPILOT=$COPILOT_AVAILABLE
else
    # User specified specific IDEs, verify they're available
    if [[ $INSTALL_VSCODE -eq 1 && $VSCODE_AVAILABLE -eq 0 ]]; then
        error "VS Code not detected but --vscode specified"
        exit 1
    fi
    if [[ $INSTALL_ZED -eq 1 && $ZED_AVAILABLE -eq 0 ]]; then
        error "Zed not detected but --zed specified"
        exit 1
    fi
    if [[ $INSTALL_COPILOT -eq 1 && $COPILOT_AVAILABLE -eq 0 ]]; then
        error "Copilot CLI not detected but --copilot specified"
        exit 1
    fi
fi

# Show installation plan
info "Installation plan:"
echo ""

INSTALL_COUNT=0

if [[ $INSTALL_VSCODE -eq 1 ]]; then
    echo -e "  ${GREEN}→${NC} Configure VS Code MCP integration"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_ZED -eq 1 ]]; then
    echo -e "  ${GREEN}→${NC} Configure Zed context server"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_COPILOT -eq 1 ]]; then
    echo -e "  ${GREEN}→${NC} Configure Copilot CLI MCP server"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
fi

if [[ $INSTALL_COUNT -eq 0 ]]; then
    warn "No IDEs selected for installation"
    exit 0
fi

echo ""
read -p "Continue with installation? (Y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

echo ""
echo "=========================================="
echo "  Installing Integrations"
echo "=========================================="
echo ""

SUCCESS_COUNT=0
FAIL_COUNT=0

# Install VS Code
if [[ $INSTALL_VSCODE -eq 1 ]]; then
    info "Configuring VS Code..."
    if bash "$SCRIPT_DIR/install_vscode_mcp.sh"; then
        success "VS Code configured"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        error "VS Code configuration failed"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
    echo ""
fi

# Install Zed
if [[ $INSTALL_ZED -eq 1 ]]; then
    info "Configuring Zed..."
    if bash "$SCRIPT_DIR/install_zed_mcp.sh"; then
        success "Zed configured"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        error "Zed configuration failed"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
    echo ""
fi

# Install Copilot CLI
if [[ $INSTALL_COPILOT -eq 1 ]]; then
    info "Configuring Copilot CLI..."
    if bash "$SCRIPT_DIR/install_copilot_cli_mcp.sh"; then
        success "Copilot CLI configured"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        error "Copilot CLI configuration failed"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
    echo ""
fi

echo ""
echo "=========================================="
echo "  Installation Summary"
echo "=========================================="
echo ""

if [[ $SUCCESS_COUNT -gt 0 ]]; then
    success "$SUCCESS_COUNT IDE(s) configured successfully"
fi

if [[ $FAIL_COUNT -gt 0 ]]; then
    error "$FAIL_COUNT IDE(s) failed to configure"
fi

echo ""
echo "=========================================="
echo "  Testing Your Integration"
echo "=========================================="
echo ""

if [[ $INSTALL_VSCODE -eq 1 ]]; then
    echo "${BOLD}VS Code:${NC}"
    echo "  1. Restart VS Code"
    echo "  2. Open Copilot Chat (Ctrl+Shift+I)"
    echo "  3. Type: @ninja-cli-mcp test task"
    echo ""
fi

if [[ $INSTALL_ZED -eq 1 ]]; then
    echo "${BOLD}Zed:${NC}"
    echo "  1. Restart Zed"
    echo "  2. Open Assistant (Cmd+Enter / Ctrl+Enter)"
    echo "  3. Ask: Use ninja-cli-mcp to run a test"
    echo ""
fi

if [[ $INSTALL_COPILOT -eq 1 ]]; then
    echo "${BOLD}Copilot CLI:${NC}"
    echo "  1. Check configuration: cat ~/.config/copilot-cli/mcp-servers.json"
    echo "  2. Refer to Copilot CLI docs for MCP usage"
    echo ""
fi

echo "=========================================="
echo "  Environment Configuration"
echo "=========================================="
echo ""

# Check environment
source "$HOME/.ninja-cli-mcp.env" 2>/dev/null || true

if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    success "OPENROUTER_API_KEY is set"
else
    warn "OPENROUTER_API_KEY not set"
    echo ""
    echo "Set your API key:"
    echo "  export OPENROUTER_API_KEY='your-key-here'"
    echo ""
fi

echo "Current configuration:"
echo "  Model: ${NINJA_MODEL:-anthropic/claude-sonnet-4 (default)}"
echo "  CLI: ${NINJA_CODE_BIN:-ninja-code (default)}"
echo ""

echo "For more information:"
echo "  - Documentation: $SCRIPT_DIR/../README.md"
echo "  - Logs: ~/.ninja-cli-mcp/logs/"
echo "  - MCP Inspector: npx @modelcontextprotocol/inspector"
echo ""
