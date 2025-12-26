#!/usr/bin/env bash
#
# install_zed_mcp.sh - Configure ninja-cli-mcp for Zed editor
#
# This script configures ninja-cli-mcp as a context server for Zed's
# AI assistant integration.
#
# Prerequisites:
#   - Zed editor installed
#   - ninja-cli-mcp installed and configured
#
# Usage: ./scripts/install_zed_mcp.sh

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

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "=========================================="
echo "  Zed MCP Integration"
echo "=========================================="
echo ""

# Check for Zed
info "Checking for Zed editor..."
if ! command -v zed &> /dev/null; then
    error "Zed (zed) not found in PATH"
    echo ""
    echo "Please install Zed from https://zed.dev/"
    exit 1
fi

ZED_VERSION=$(zed --version 2>/dev/null | head -n1 || echo "unknown")
success "Zed found: $ZED_VERSION"

# Get Zed config directory
ZED_CONFIG_DIR="$HOME/.config/zed"
ZED_SETTINGS="$ZED_CONFIG_DIR/settings.json"

if [[ ! -d "$ZED_CONFIG_DIR" ]]; then
    warn "Zed config directory not found, creating: $ZED_CONFIG_DIR"
    mkdir -p "$ZED_CONFIG_DIR"
fi

# Get the run_server.sh path
RUN_SERVER="$SCRIPT_DIR/run_server.sh"

if [[ ! -x "$RUN_SERVER" ]]; then
    chmod +x "$RUN_SERVER"
fi

info "Setting up MCP context server configuration..."

# Check if settings.json exists
if [[ ! -f "$ZED_SETTINGS" ]]; then
    info "Creating new Zed settings.json"

    # Load environment variables for JSON
    source "$HOME/.ninja-cli-mcp.env" 2>/dev/null || true

    # Create minimal settings with just context_servers
    python3 <<PYTHON_EOF
import json
import os

env_vars = {}
if os.environ.get("OPENROUTER_API_KEY"):
    env_vars["OPENROUTER_API_KEY"] = os.environ.get("OPENROUTER_API_KEY")
if os.environ.get("OPENAI_API_KEY"):
    env_vars["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY")
if os.environ.get("NINJA_MODEL"):
    env_vars["NINJA_MODEL"] = os.environ.get("NINJA_MODEL")
if os.environ.get("NINJA_CODE_BIN"):
    env_vars["NINJA_CODE_BIN"] = os.environ.get("NINJA_CODE_BIN")

settings = {
    "context_servers": {
        "ninja-cli-mcp": {
            "command": "$RUN_SERVER",
            "args": [],
            "env": env_vars
        }
    }
}

with open("$ZED_SETTINGS", 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
PYTHON_EOF
    success "Configuration created at $ZED_SETTINGS"
else
    # Settings file exists, need to merge
    info "Updating existing settings.json"

    # Check if context_servers already exists
    if grep -q '"context_servers"' "$ZED_SETTINGS"; then
        # context_servers exists, need to add our server
        if grep -q '"ninja-cli-mcp"' "$ZED_SETTINGS"; then
            warn "ninja-cli-mcp already configured in Zed settings"
            echo ""
            read -p "Do you want to update the configuration? (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "Keeping existing configuration."
                exit 0
            fi

            # Create backup
            cp "$ZED_SETTINGS" "$ZED_SETTINGS.backup.$(date +%s)"
            success "Created backup: $ZED_SETTINGS.backup.*"
        fi

        # Use Python to update JSON (safer than sed/awk for JSON)
        # Zed uses JSONC (JSON with Comments), so we need to strip comments first
        python3 <<PYTHON_EOF
import json
import sys
import re

settings_file = "$ZED_SETTINGS"

try:
    with open(settings_file, 'r') as f:
        content = f.read()

    # Strip // style comments (JSONC format)
    # This is a simple approach that handles most cases
    lines = []
    for line in content.split('\n'):
        # Remove // comments but preserve URLs like https://
        if '//' in line:
            # Check if it's a comment line
            stripped = line.lstrip()
            if stripped.startswith('//'):
                continue
            # Check if // is in a string (simple heuristic)
            # If it's after a quote and not in a URL context, it's likely a comment
            parts = line.split('//', 1)
            if len(parts) == 2:
                # Simple check: if there's an odd number of quotes before //, it's in a string
                if parts[0].count('"') % 2 == 0:
                    line = parts[0].rstrip()
        lines.append(line)

    content = '\n'.join(lines)
    settings = json.loads(content)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON in settings file: {e}", file=sys.stderr)
    sys.exit(1)

# Ensure context_servers exists
if "context_servers" not in settings:
    settings["context_servers"] = {}

# Load environment variables
import os
env_vars = {}
if os.environ.get("OPENROUTER_API_KEY"):
    env_vars["OPENROUTER_API_KEY"] = os.environ.get("OPENROUTER_API_KEY")
if os.environ.get("OPENAI_API_KEY"):
    env_vars["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY")
if os.environ.get("NINJA_MODEL"):
    env_vars["NINJA_MODEL"] = os.environ.get("NINJA_MODEL")
if os.environ.get("NINJA_CODE_BIN"):
    env_vars["NINJA_CODE_BIN"] = os.environ.get("NINJA_CODE_BIN")

# Add or update ninja-cli-mcp
settings["context_servers"]["ninja-cli-mcp"] = {
    "command": "$RUN_SERVER",
    "args": [],
    "env": env_vars
}

# Write back
with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print("Configuration updated successfully")
PYTHON_EOF

        success "Configuration updated at $ZED_SETTINGS"
    else
        # No context_servers, add the entire section
        python3 <<PYTHON_EOF
import json
import sys
import re

settings_file = "$ZED_SETTINGS"

try:
    with open(settings_file, 'r') as f:
        content = f.read()

    # Strip // style comments (JSONC format)
    lines = []
    for line in content.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('//'):
            continue
        if '//' in line:
            parts = line.split('//', 1)
            if len(parts) == 2 and parts[0].count('"') % 2 == 0:
                line = parts[0].rstrip()
        lines.append(line)

    content = '\n'.join(lines)
    settings = json.loads(content)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON in settings file: {e}", file=sys.stderr)
    sys.exit(1)

# Load environment variables
import os
env_vars = {}
if os.environ.get("OPENROUTER_API_KEY"):
    env_vars["OPENROUTER_API_KEY"] = os.environ.get("OPENROUTER_API_KEY")
if os.environ.get("OPENAI_API_KEY"):
    env_vars["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY")
if os.environ.get("NINJA_MODEL"):
    env_vars["NINJA_MODEL"] = os.environ.get("NINJA_MODEL")
if os.environ.get("NINJA_CODE_BIN"):
    env_vars["NINJA_CODE_BIN"] = os.environ.get("NINJA_CODE_BIN")

# Add context_servers
settings["context_servers"] = {
    "ninja-cli-mcp": {
        "command": "$RUN_SERVER",
        "args": [],
        "env": env_vars
    }
}

# Write back
with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print("Configuration added successfully")
PYTHON_EOF

        success "Configuration added to $ZED_SETTINGS"
    fi
fi

echo ""
echo "=========================================="
echo "  Configuration Complete!"
echo "=========================================="
echo ""

echo "Zed settings.json updated:"
echo ""

# Show the context_servers section
python3 <<PYTHON_EOF
import json

with open("$ZED_SETTINGS", 'r') as f:
    content = f.read()

# Strip // comments for reading
lines = []
for line in content.split('\n'):
    stripped = line.lstrip()
    if stripped.startswith('//'):
        continue
    if '//' in line:
        parts = line.split('//', 1)
        if len(parts) == 2 and parts[0].count('"') % 2 == 0:
            line = parts[0].rstrip()
    lines.append(line)

content = '\n'.join(lines)
settings = json.loads(content)

if "context_servers" in settings:
    print(json.dumps({"context_servers": settings["context_servers"]}, indent=2))
else:
    print("Warning: context_servers not found in settings")
PYTHON_EOF

echo ""
echo "=========================================="
echo "  Next Steps"
echo "=========================================="
echo ""
echo "1. Restart Zed to load the context server"
echo ""
echo "2. Open the Assistant panel (Cmd+Enter or Ctrl+Enter)"
echo ""
echo "3. The ninja-cli-mcp context server should now be available"
echo "   as a tool that the assistant can use"
echo ""
echo "4. Test the integration by asking the assistant to:"
echo "   'Use ninja-cli-mcp to execute: echo hello world'"
echo ""
echo "Configuration location: $ZED_SETTINGS"
echo "Server command: $RUN_SERVER"
echo ""
echo "For troubleshooting:"
echo "  - Open Zed logs: zed: open logs (from command palette)"
echo "  - Check MCP server logs: ~/.ninja-cli-mcp/logs/"
echo "  - Verify environment: source ~/.ninja-cli-mcp.env"
echo ""

# Show environment setup
source "$HOME/.ninja-cli-mcp.env" 2>/dev/null || true

if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    success "Environment configured (OPENROUTER_API_KEY set)"
else
    warn "OPENROUTER_API_KEY not set"
    echo ""
    echo "Make sure to set your OpenRouter API key:"
    echo "  export OPENROUTER_API_KEY='your-key-here'"
    echo ""
    echo "Or add it to ~/.ninja-cli-mcp.env:"
    echo "  echo 'export OPENROUTER_API_KEY=\"your-key\"' >> ~/.ninja-cli-mcp.env"
    echo ""
fi

echo "Supported models (set via NINJA_MODEL environment variable):"
echo "  - anthropic/claude-sonnet-4 (default)"
echo "  - anthropic/claude-3.5-sonnet"
echo "  - openai/gpt-4o"
echo "  - qwen/qwen3-coder"
echo "  - deepseek/deepseek-coder"
echo "  - google/gemini-pro-1.5"
echo "  - And 200+ more via OpenRouter"
echo ""
