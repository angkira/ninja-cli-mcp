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

# Usage
echo ""
echo "Usage: $0 [aider|qwen|opencode|gemini|detect]"
echo ""
echo "Options:"
echo "  aider    - Install Aider CLI (Python-based, OpenRouter integration)"
echo "  qwen     - Install Qwen Code CLI (Node.js-based)"
echo "  opencode  - Install OpenCode CLI (Recommended, MCP-native, z.ai support)"
echo "  gemini   - Install Gemini CLI (Google API)"
echo "  detect    - Auto-detect and use existing CLI"
        fi
        ;;
    *)
        error "Invalid mode: $MODE"
        echo ""
        echo "Usage: $0 [aider|qwen|opencode|gemini|detect]"
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
