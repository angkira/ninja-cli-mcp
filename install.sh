#!/usr/bin/env bash
#
# Quick installer for Ninja MCP
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/angkira/ninja-mcp/main/install.sh | bash
#   or
#   wget -qO- https://raw.githubusercontent.com/angkira/ninja-mcp/main/install.sh | bash
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

# Display banner
cat << "EOF"
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║              🥷 NINJA MCP INSTALLER                      ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
EOF

echo ""
info "Starting installation..."
echo ""

# Detect OS
OS="unknown"
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
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    OS="windows"
fi

info "Detected OS: $OS"

# Check for Python
if ! command -v python3 &> /dev/null; then
    error "Python 3.11+ is required but not found. Please install Python first."
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
info "Python version: $PYTHON_VERSION"

# Check Python version
if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)'; then
    success "Python version is compatible"
else
    error "Python 3.11 or higher is required. You have $PYTHON_VERSION"
fi

# Install uv if not present
if ! command -v uv &> /dev/null; then
    warn "uv package manager not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Source the uv path
    export PATH="$HOME/.cargo/bin:$PATH"

    if command -v uv &> /dev/null; then
        success "uv installed successfully"
    else
        error "Failed to install uv. Please install manually from https://github.com/astral-sh/uv"
    fi
else
    success "uv is already installed"
fi

echo ""
info "Choose installation method:"
echo ""
echo "  1) Interactive installer (recommended) - Full setup with IDE integration"
echo "  2) Quick install (global tool) - Just install the commands"
echo "  3) Development install - Clone repo for contributing"
echo ""
read -p "Enter choice [1-3]: " -n 1 -r choice
echo ""

case $choice in
    1)
        info "Running interactive installer..."

        # Clone or download repo
        if command -v git &> /dev/null; then
            info "Cloning repository..."
            git clone https://github.com/angkira/ninja-mcp.git /tmp/ninja-mcp
        else
            info "Downloading repository..."
            curl -L https://github.com/angkira/ninja-mcp/archive/refs/heads/main.tar.gz | tar xz -C /tmp
            mv /tmp/ninja-mcp-main /tmp/ninja-mcp
        fi

        cd /tmp/ninja-mcp
        ./scripts/install_interactive.sh

        # Cleanup
        cd -
        rm -rf /tmp/ninja-mcp
        ;;

    2)
        info "Installing as global tool..."

        # Check for package managers
        if [[ "$OS" == "macos" ]] && command -v brew &> /dev/null; then
            info "Homebrew detected. Use: brew install angkira/tap/ninja-mcp"
            info "Falling back to uv tool install..."
        elif [[ "$OS" == "linux" ]] && [[ "${DISTRO:-}" == "debian" ]]; then
            info "Debian/Ubuntu detected. Use: sudo apt install ninja-mcp"
            info "Falling back to uv tool install..."
        fi

        # Install from PyPI (or local if in dev)
        uv tool install ninja-mcp[all]

        success "✓ Installation complete!"
        echo ""
        echo "Available commands:"
        echo "  ninja-coder       - Code assistant MCP server"
        echo "  ninja-researcher  - Research MCP server"
        echo "  ninja-secretary   - Secretary MCP server"
        echo "  ninja-config      - Interactive configuration"
        echo ""
        echo "Next steps:"
        echo "  1. Set API key: export OPENROUTER_API_KEY='your-key'"
        echo "  2. Run setup: ninja-config"
        echo "  3. Configure your IDE (Claude Code, VS Code, etc.)"
        ;;

    3)
        info "Setting up for development..."

        # Determine install location
        DEFAULT_DIR="$HOME/Projects/ninja-mcp"
        read -p "Install location [$DEFAULT_DIR]: " INSTALL_DIR
        INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"

        # Clone repo
        if command -v git &> /dev/null; then
            info "Cloning repository to $INSTALL_DIR..."
            git clone https://github.com/angkira/ninja-mcp.git "$INSTALL_DIR"
        else
            error "Git is required for development installation"
        fi

        cd "$INSTALL_DIR"

        # Install dependencies
        info "Installing dependencies..."
        uv sync --all-extras

        success "✓ Development setup complete!"
        echo ""
        echo "Development commands:"
        echo "  cd $INSTALL_DIR"
        echo "  just install-dev     # Install in editable mode"
        echo "  just test            # Run tests"
        echo "  just setup-ide       # Setup IDE integration"
        echo ""
        echo "See justfile for more commands (install just: https://just.systems)"
        ;;

    *)
        error "Invalid choice"
        ;;
esac

success "🥷 Ninja MCP installation complete!"
