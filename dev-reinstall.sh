#!/usr/bin/env bash
#
# Ninja MCP - Dev Reinstall Script
#
# Quick script for developers to reinstall after making code changes
# This ensures the system uses the latest code, not stale .venv binaries
#

set -euo pipefail

echo "🥷 Ninja MCP - Dev Reinstall"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check we're in dev directory
if [[ ! -f "pyproject.toml" ]]; then
    echo "❌ Error: Run this script from the ninja-cli-mcp project directory"
    exit 1
fi

# Deactivate venv if active
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    echo -e "${BLUE}▸${NC} Deactivating virtual environment..."
    deactivate 2>/dev/null || true
    unset VIRTUAL_ENV
fi

# Clean up .venv binaries to avoid conflicts
if [[ -d ".venv/bin" ]]; then
    echo -e "${BLUE}▸${NC} Cleaning .venv binaries..."
    rm -f .venv/bin/ninja-* 2>/dev/null || true
fi

# Reinstall with uv tool
echo -e "${BLUE}▸${NC} Reinstalling from local source..."
if uv tool install --force ".[all]" 2>&1 | grep -v "Resolved\|Uninstalled\|Installed"; then
    echo -e "${GREEN}✓${NC} Reinstalled successfully"
else
    echo -e "${YELLOW}⚠${NC} Install completed with warnings (check output above)"
fi

# Verify binaries
echo ""
echo -e "${BLUE}▸${NC} Verifying binary locations..."
all_good=true
for cmd in ninja-coder ninja-researcher ninja-secretary ninja-resources ninja-prompts; do
    cmd_path=$(command -v "$cmd" 2>/dev/null || echo "")
    if [[ "$cmd_path" == *"/.local/"* ]]; then
        echo -e "${GREEN}✓${NC} $cmd: $cmd_path"
    elif [[ -z "$cmd_path" ]]; then
        echo -e "${YELLOW}⚠${NC} $cmd: not found in PATH"
        all_good=false
    else
        echo -e "${YELLOW}⚠${NC} $cmd: unexpected location: $cmd_path"
        all_good=false
    fi
done

echo ""
if [[ "$all_good" == "true" ]]; then
    echo -e "${GREEN}✓${NC} All binaries installed correctly in ~/.local/bin"
    echo ""
    echo "Next steps:"
    echo "  1. Restart daemons: ninja-daemon restart"
    echo "  2. Restart Claude Code to pick up changes"
else
    echo -e "${YELLOW}⚠${NC} Some binaries not in expected location"
    echo "You may need to check your PATH or run ./update.sh"
fi
