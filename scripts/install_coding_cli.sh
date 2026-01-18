#!/usr/bin/env bash
#
# install_coding_cli.sh - Install AI coding agent CLI for ninja-cli-mcp
#
# This script installs a coding agent CLI that supports OpenRouter.
# Options: Aider (Python), Qwen Code CLI (Node.js), OpenCode (native MCP), or detect existing.
#
# Usage: ./scripts/install_coding_cli.sh [aider|qwen|opencode|detect]

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "=========================================="
echo "  Install Coding Agent CLI"
echo "=========================================="
echo ""

# Detect existing CLIs
detect_existing() {
    info "Detecting existing coding agent CLIs..."
    
    FOUND_CLIS=()
    
    if command -v aider &> /dev/null; then
        AIDER_VERSION=$(aider --version 2>/dev/null | head -n1 || echo "unknown")
        FOUND_CLIS+=("aider")
        success "Aider found: $AIDER_VERSION"
    fi
    
    if command -v qwen &> /dev/null; then
        QWEN_VERSION=$(qwen --version 2>/dev/null | head -n1 || echo "unknown")
        FOUND_CLIS+=("qwen")
        success "Qwen Code CLI found: $QWEN_VERSION"
    fi
    
    if command -v gemini &> /dev/null; then
        GEMINI_VERSION=$(gemini --version 2>/dev/null | head -n1 || echo "unknown")
        FOUND_CLIS+=("gemini")
        success "Gemini CLI found: $GEMINI_VERSION"
    fi
    
    if command -v claude &> /dev/null; then
        CLAUDE_VERSION=$(claude --version 2>/dev/null | head -n1 || echo "unknown")
        FOUND_CLIS+=("claude")
        warn "Claude CLI found: $CLAUDE_VERSION (Note: Claude CLI doesn't support OpenRouter directly)"
    fi

    if command -v opencode &> /dev/null; then
        OPENCODE_VERSION=$(opencode --version 2>/dev/null | head -n1 || echo "unknown")
        FOUND_CLIS+=("opencode")
        success "OpenCode CLI found: $OPENCODE_VERSION"
    fi

    if [ ${#FOUND_CLIS[@]} -eq 0 ]; then
        info "No coding agent CLIs found"
        return 1
    else
        echo ""
        info "Found ${#FOUND_CLIS[@]} coding agent CLI(s): ${FOUND_CLIS[*]}"
        return 0
    fi
}

# Install Aider
install_aider() {
    info "Installing Aider via uv..."
    
    cd "$PROJECT_ROOT"
    
    # Install with aider extra
    if uv sync --extra aider; then
        success "Aider installed successfully"
        
        # Verify installation
        if uv run aider --version &> /dev/null; then
            AIDER_VERSION=$(uv run aider --version 2>/dev/null | head -n1)
            success "Aider is ready: $AIDER_VERSION"
            echo ""
            echo "To use Aider:"
            echo "  uv run aider"
            echo ""
            return 0
        else
            error "Aider installation verification failed"
            return 1
        fi
    else
        error "Failed to install Aider"
        return 1
    fi
}

# Install Qwen Code CLI
install_qwen() {
    info "Installing Qwen Code CLI via npm..."

    # Check for npm
    if ! command -v npm &> /dev/null; then
        error "npm is not installed"
        echo ""
        echo "Install Node.js and npm first:"
        echo "  https://nodejs.org/"
        echo ""
        return 1
    fi

    # Install globally
    if npm install -g @qwen-code/qwen-code; then
        success "Qwen Code CLI installed successfully"

        # Verify installation
        if command -v qwen &> /dev/null; then
            QWEN_VERSION=$(qwen --version 2>/dev/null | head -n1)
            success "Qwen Code CLI is ready: $QWEN_VERSION"
            echo ""
            echo "To use Qwen Code CLI:"
            echo "  qwen"
            echo ""
            return 0
        else
            error "Qwen Code CLI installation verification failed"
            return 1
        fi
    else
        error "Failed to install Qwen Code CLI"
        return 1
    fi
}

# Install OpenCode CLI
install_opencode() {
    info "Installing OpenCode CLI..."

    if curl -fsSL https://opencode.ai/install | bash; then
        success "OpenCode CLI installed successfully"

        # Verify installation
        if command -v opencode &> /dev/null; then
            OPENCODE_VERSION=$(opencode --version 2>/dev/null | head -n1)
            success "OpenCode CLI is ready: $OPENCODE_VERSION"
            echo ""
            echo "To use OpenCode:"
            echo "  opencode"
            echo ""
            return 0
        else
            error "OpenCode CLI installation verification failed"
            return 1
        fi
    else
        error "Failed to install OpenCode CLI"
        return 1
    fi
}

# Main logic
MODE="${1:-detect}"

case "$MODE" in
    aider)
        install_aider
        RECOMMENDED_BIN="aider"
        ;;
    qwen)
        install_qwen
        RECOMMENDED_BIN="qwen"
        ;;
    opencode)
        install_opencode
        RECOMMENDED_BIN="opencode"
        ;;
    detect)
        if detect_existing; then
            # Use first found CLI
            RECOMMENDED_BIN="${FOUND_CLIS[0]}"
            echo ""
            info "Using existing CLI: $RECOMMENDED_BIN"
        else
            warn "No coding agent CLI found"
            echo ""
            echo "Choose an option:"
            echo "  1. Install Aider (Python-based, recommended)"
            echo "  2. Install Qwen Code CLI (Node.js-based)"
            echo "  3. Install OpenCode CLI (Recommended, MCP-native)"
            echo "  4. Skip installation"
            echo ""
            read -p "Enter choice (1-4): " -n 1 -r
            echo

            case "$REPLY" in
                1)
                    install_aider
                    RECOMMENDED_BIN="aider"
                    ;;
                2)
                    install_qwen
                    RECOMMENDED_BIN="qwen"
                    ;;
                3)
                    install_opencode
                    RECOMMENDED_BIN="opencode"
                    ;;
                4)
                    warn "Skipping installation"
                    echo ""
                    echo "You can install a coding agent CLI later:"
                    echo "  ./scripts/install_coding_cli.sh aider"
                    echo "  ./scripts/install_coding_cli.sh qwen"
                    echo "  ./scripts/install_coding_cli.sh opencode"
                    exit 0
                    ;;
                *)
                    error "Invalid choice"
                    exit 1
                    ;;
            esac
        fi
        ;;
    *)
        error "Invalid mode: $MODE"
        echo ""
        echo "Usage: $0 [aider|qwen|opencode|detect]"
        exit 1
        ;;
esac

# Update configuration if needed
CONFIG_FILE="$HOME/.ninja-cli-mcp.env"

if [ -f "$CONFIG_FILE" ]; then
    info "Updating NINJA_CODE_BIN in $CONFIG_FILE..."
    
    # Check if NINJA_CODE_BIN is already set correctly
    if grep -q "^export NINJA_CODE_BIN='$RECOMMENDED_BIN'" "$CONFIG_FILE" 2>/dev/null; then
        success "NINJA_CODE_BIN is already set to $RECOMMENDED_BIN"
    else
        # Update or add NINJA_CODE_BIN
        if grep -q "^export NINJA_CODE_BIN=" "$CONFIG_FILE"; then
            # Update existing line
            sed -i "s|^export NINJA_CODE_BIN=.*|export NINJA_CODE_BIN='$RECOMMENDED_BIN'|" "$CONFIG_FILE"
            success "Updated NINJA_CODE_BIN to $RECOMMENDED_BIN"
        else
            # Add new line
            echo "export NINJA_CODE_BIN='$RECOMMENDED_BIN'" >> "$CONFIG_FILE"
            success "Added NINJA_CODE_BIN=$RECOMMENDED_BIN"
        fi
    fi
fi

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Recommended configuration:"
echo "  export NINJA_CODE_BIN='$RECOMMENDED_BIN'"
echo ""
echo "Full setup:"
echo "  export OPENROUTER_API_KEY='your-api-key'"
echo "  export NINJA_MODEL='anthropic/claude-sonnet-4'"
echo "  export NINJA_CODE_BIN='$RECOMMENDED_BIN'"
echo ""
echo "For more information, see:"
echo "  docs/CODING_AGENT_CLI_OPTIONS.md"
echo ""
