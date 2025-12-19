#!/usr/bin/env bash
#
# install.sh - Install ninja-cli-mcp and its dependencies
#
# Usage: ./scripts/install.sh
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

cd "$PROJECT_ROOT"

echo ""
echo "=========================================="
echo "  ninja-cli-mcp Installation"
echo "=========================================="
echo ""

# Check Python version
info "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 11 ]]; then
        error "Python 3.11+ is required (found $PYTHON_VERSION)"
    fi
    success "Python $PYTHON_VERSION found"
else
    error "Python 3 is not installed. Please install Python 3.11 or later."
fi

# Check for uv
info "Checking for uv..."
if command -v uv &> /dev/null; then
    UV_VERSION=$(uv --version 2>/dev/null | head -n1)
    success "uv found: $UV_VERSION"
else
    warn "uv is not installed"
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add to PATH for current session
    export PATH="$HOME/.cargo/bin:$PATH"

    if command -v uv &> /dev/null; then
        success "uv installed successfully"
    else
        error "Failed to install uv. Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
    fi
fi

# Check for git
info "Checking for git..."
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version)
    success "git found: $GIT_VERSION"
else
    error "git is not installed. Please install git."
fi

# Sync dependencies with uv
info "Installing dependencies with uv..."
uv sync

if [[ $? -eq 0 ]]; then
    success "Dependencies installed successfully"
else
    error "Failed to install dependencies"
fi

# Install dev dependencies
info "Installing dev dependencies..."
uv sync --all-extras

if [[ $? -eq 0 ]]; then
    success "Dev dependencies installed successfully"
else
    warn "Some dev dependencies may not have installed correctly"
fi

# Make scripts executable
info "Making scripts executable..."
chmod +x "$SCRIPT_DIR"/*.sh
success "Scripts are executable"

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""

# Reminders
echo "Next steps:"
echo ""
echo "1. Set your OpenRouter API key:"
echo "   export OPENROUTER_API_KEY='your-api-key-here'"
echo ""
echo "2. (Optional) Choose a model:"
echo "   export NINJA_MODEL='anthropic/claude-sonnet-4'  # default"
echo "   # Or use any OpenRouter model:"
echo "   export NINJA_MODEL='openai/gpt-4o'"
echo "   export NINJA_MODEL='qwen/qwen3-coder'"
echo "   export NINJA_MODEL='deepseek/deepseek-coder'"
echo ""
echo "3. Install the Ninja Code CLI (or compatible AI CLI):"
echo "   Set NINJA_CODE_BIN to point to your AI code CLI binary"
echo ""
echo "4. Start the MCP server:"
echo "   ./scripts/run_server.sh"
echo ""
echo "5. Connect to your IDE/CLI:"
echo "   • Claude Code:     ./scripts/install_claude_code_mcp.sh"
echo "   • Copilot CLI:     ./scripts/install_copilot_cli_mcp.sh"
echo "   • VS Code:         ./scripts/install_vscode_mcp.sh"
echo "   • All detected:    ./scripts/install_ide_integrations.sh"
echo ""

# Check if OPENROUTER_API_KEY is set
if [[ -z "${OPENROUTER_API_KEY:-}" ]] && [[ -z "${OPENAI_API_KEY:-}" ]]; then
    warn "OPENROUTER_API_KEY or OPENAI_API_KEY is not set"
    echo ""
fi

# Check if Ninja Code CLI is available
NINJA_BIN="${NINJA_CODE_BIN:-ninja-code}"
if ! command -v "$NINJA_BIN" &> /dev/null; then
    warn "Ninja Code CLI not found at '$NINJA_BIN'"
    echo "   Set NINJA_CODE_BIN to the correct path or install Ninja Code CLI"
    echo ""
fi

echo "For more information, see README.md"
echo ""
