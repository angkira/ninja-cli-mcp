#!/usr/bin/env bash
#
# Configure ninja-coder to use OpenCode with Claude Sonnet 4.5
#
# Usage:
#   1. Exit Claude Code completely
#   2. Run: ./configure-opencode.sh
#   3. Restart Claude Code
#

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info() { echo -e "${BLUE}▸${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}     🥷 ${BOLD}NINJA-CODER OPENCODE CONFIGURATION${NC}           ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

CLAUDE_CONFIG="$HOME/.claude.json"

# Check if Claude Code is running
if pgrep -f "claude|Claude" > /dev/null; then
    error "Claude Code is running. Please exit Claude Code completely before running this script."
fi

# Check if config exists
if [[ ! -f "$CLAUDE_CONFIG" ]]; then
    error "Claude Code config not found at $CLAUDE_CONFIG"
fi

# Check if opencode is available
if ! command -v opencode &> /dev/null; then
    error "OpenCode not found. Install from: https://github.com/stackblitz/opencode"
fi

OPENCODE_PATH=$(command -v opencode)
info "Found OpenCode at: $OPENCODE_PATH"

# Check OpenCode authentication
info "Checking OpenCode authentication..."
if opencode auth list 2>&1 | grep -q "Anthropic"; then
    success "Anthropic authenticated"
else
    warn "Anthropic not authenticated"
    info "Run: opencode auth add anthropic"
fi

# Backup config
BACKUP_FILE="$CLAUDE_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"
cp "$CLAUDE_CONFIG" "$BACKUP_FILE"
success "Backed up config to: $BACKUP_FILE"

# Update configuration using Python
info "Updating ninja-coder configuration..."

python3 -c "
import json
import sys

config_path = '$CLAUDE_CONFIG'
try:
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Update ninja-coder configuration
    if 'mcpServers' not in config:
        config['mcpServers'] = {}

    if 'ninja-coder' not in config['mcpServers']:
        config['mcpServers']['ninja-coder'] = {
            'type': 'stdio',
            'command': 'ninja-coder',
            'args': []
        }

    # Set environment variables
    config['mcpServers']['ninja-coder']['env'] = {
        'NINJA_CODE_BIN': '$OPENCODE_PATH',
        'NINJA_MODEL': 'anthropic/claude-sonnet-4-5'
    }

    # Write back
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
"

if [[ $? -eq 0 ]]; then
    success "Configuration updated successfully!"
    echo ""
    echo -e "${GREEN}Configuration:${NC}"
    echo "  • Binary: $OPENCODE_PATH"
    echo "  • Model: anthropic/claude-sonnet-4-5"
    echo ""
    echo -e "${BOLD}Alternative Models (edit ~/.claude.json NINJA_MODEL):${NC}"
    echo "  • anthropic/claude-opus-4-5      (Most powerful)"
    echo "  • anthropic/claude-sonnet-4-5    (Balanced, recommended)"
    echo "  • google/gemini-2.0-flash-exp    (Fast & cost-effective)"
    echo "  • openai/gpt-4o                  (OpenAI's latest)"
    echo ""
    echo -e "${GREEN}Next steps:${NC}"
    echo "  1. Start Claude Code"
    echo "  2. The config will be automatically detected (fix we implemented)"
    echo "  3. Test with: Try asking me to write some code!"
    echo ""
else
    error "Failed to update configuration"
fi
