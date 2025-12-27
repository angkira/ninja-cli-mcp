#!/usr/bin/env bash
#
# update_mcp_config.sh - Update MCP configurations without reinstalling
#
# This script updates MCP server configurations for all installed IDEs
# without going through the full installation process. Useful for:
#   - Updating codebase and dependencies
#   - Updating environment variables
#   - Changing model settings
#   - Switching between daemon and direct mode
#   - Fixing configuration issues
#
# Usage: ./scripts/update_mcp_config.sh [OPTIONS]
#
# Options:
#   --claude        Update Claude Code configuration only
#   --vscode        Update VS Code configuration only
#   --zed           Update Zed configuration only
#   --copilot       Update Copilot CLI configuration only
#   --all           Update all detected IDE configurations (default)
#   --validate      Only validate existing configurations
#   --daemon        Use daemon mode (default if available)
#   --direct        Use direct mode (no daemon)
#   --update-code   Pull latest code from git and update dependencies
#   --skip-restart  Don't restart daemons after update
#

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

# Source shared Claude config utilities
source "$SCRIPT_DIR/lib/claude_config.sh"

# Parse arguments
UPDATE_ALL=1
UPDATE_CLAUDE=0
UPDATE_VSCODE=0
UPDATE_ZED=0
UPDATE_COPILOT=0
VALIDATE_ONLY=0
FORCE_DAEMON=""
UPDATE_CODE=0
SKIP_RESTART=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)
            UPDATE_ALL=1
            shift
            ;;
        --claude)
            UPDATE_ALL=0
            UPDATE_CLAUDE=1
            shift
            ;;
        --vscode)
            UPDATE_ALL=0
            UPDATE_VSCODE=1
            shift
            ;;
        --zed)
            UPDATE_ALL=0
            UPDATE_ZED=1
            shift
            ;;
        --copilot)
            UPDATE_ALL=0
            UPDATE_COPILOT=1
            shift
            ;;
        --validate)
            VALIDATE_ONLY=1
            shift
            ;;
        --daemon)
            FORCE_DAEMON="yes"
            shift
            ;;
        --direct)
            FORCE_DAEMON="no"
            shift
            ;;
        --update-code)
            UPDATE_CODE=1
            shift
            ;;
        --skip-restart)
            SKIP_RESTART=1
            shift
            ;;
        *)
            error "Unknown option: $1"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --all          Update all detected IDE configurations (default)"
            echo "  --claude       Update Claude Code only"
            echo "  --vscode       Update VS Code only"
            echo "  --zed          Update Zed only"
            echo "  --copilot      Update Copilot CLI only"
            echo "  --validate     Only validate configurations"
            echo "  --daemon       Force daemon mode"
            echo "  --direct       Force direct mode (no daemon)"
            echo "  --update-code  Pull latest code and update dependencies"
            echo "  --skip-restart Don't restart daemons after update"
            echo ""
            exit 1
            ;;
    esac
done

echo ""
echo "==========================================="
echo "  MCP Configuration Updater"
echo "==========================================="
echo ""

# Load environment
if [[ -f "$HOME/.ninja-mcp.env" ]]; then
    source "$HOME/.ninja-mcp.env"
    success "Loaded environment from ~/.ninja-mcp.env"
else
    warn "No ~/.ninja-mcp.env found, using current environment"
fi

# Check daemon availability
USE_DAEMON=0
if [[ "$FORCE_DAEMON" == "yes" ]]; then
    USE_DAEMON=1
elif [[ "$FORCE_DAEMON" == "no" ]]; then
    USE_DAEMON=0
elif command -v ninja-daemon &> /dev/null && uv run ninja-daemon status >/dev/null 2>&1; then
    USE_DAEMON=1
    info "Daemon mode available and will be used"
else
    info "Daemon mode not available, using direct mode"
fi

# Function to validate JSON
validate_json() {
    local json_file="$1"
    local name="$2"

    if [[ ! -f "$json_file" ]]; then
        warn "$name: Configuration file not found: $json_file"
        return 1
    fi

    if python3 -m json.tool "$json_file" > /dev/null 2>&1; then
        success "$name: Configuration is valid"
        return 0
    else
        error "$name: Configuration has invalid JSON syntax!"
        python3 -m json.tool "$json_file" 2>&1 | head -10
        return 1
    fi
}

# Function to update code from git and dependencies
update_code_and_deps() {
    echo ""
    echo "==========================================="
    echo "  Updating Codebase"
    echo "==========================================="
    echo ""

    cd "$PROJECT_ROOT"

    # Check if we're in a git repository
    if [[ ! -d ".git" ]]; then
        warn "Not a git repository, skipping code update"
        return 1
    fi

    # Get current branch and check for uncommitted changes
    local current_branch=$(git rev-parse --abbrev-ref HEAD)
    info "Current branch: $current_branch"

    if [[ -n $(git status --porcelain) ]]; then
        warn "You have uncommitted changes:"
        git status --short
        echo ""
        read -p "Continue with update anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Code update cancelled."
            return 1
        fi
    fi

    # Stop daemons before updating
    if command -v ninja-daemon &> /dev/null; then
        info "Stopping daemons before code update..."
        uv run ninja-daemon stop coder 2>/dev/null || true
        uv run ninja-daemon stop researcher 2>/dev/null || true
        uv run ninja-daemon stop secretary 2>/dev/null || true
        sleep 2
        success "Daemons stopped"
    fi

    # Pull latest code
    info "Pulling latest code from git..."
    local before_commit=$(git rev-parse HEAD)

    if git pull --rebase; then
        local after_commit=$(git rev-parse HEAD)

        if [[ "$before_commit" == "$after_commit" ]]; then
            success "Code is already up to date"
        else
            success "Code updated successfully"
            echo ""
            info "Changes pulled:"
            git log --oneline "$before_commit..$after_commit"
            echo ""
        fi
    else
        error "Failed to pull latest code"
        echo ""
        info "You may need to resolve conflicts manually"
        return 1
    fi

    # Update dependencies
    info "Updating dependencies with uv sync..."
    if uv sync --all-extras; then
        success "Dependencies updated successfully"
    else
        error "Failed to update dependencies"
        return 1
    fi

    echo ""
    success "Code and dependencies updated successfully"
    return 0
}

# Function to restart all daemons
restart_all_daemons() {
    if ! command -v ninja-daemon &> /dev/null; then
        warn "ninja-daemon not available, skipping daemon restart"
        return 0
    fi

    echo ""
    info "Restarting all daemons..."
    echo ""

    local modules=("coder" "researcher" "secretary")
    local restarted=0
    local failed=0

    for module in "${modules[@]}"; do
        info "Restarting $module daemon..."

        # Stop the daemon first
        uv run ninja-daemon stop "$module" 2>/dev/null || true
        sleep 1

        # Start the daemon
        if uv run ninja-daemon start "$module" 2>/dev/null; then
            # Wait a bit for daemon to initialize
            sleep 2

            # Check if it's actually running
            if uv run ninja-daemon status "$module" 2>/dev/null | grep -q '"running": true'; then
                success "$module daemon restarted successfully"
                restarted=$((restarted + 1))
            else
                error "$module daemon failed to start"
                failed=$((failed + 1))
            fi
        else
            error "Failed to restart $module daemon"
            failed=$((failed + 1))
        fi
    done

    echo ""
    if [[ $restarted -gt 0 ]]; then
        success "$restarted daemon(s) restarted successfully"
    fi
    if [[ $failed -gt 0 ]]; then
        error "$failed daemon(s) failed to restart"
        return 1
    fi

    return 0
}

# Function to verify daemon health
verify_daemon_health() {
    if ! command -v ninja-daemon &> /dev/null; then
        return 0
    fi

    echo ""
    info "Verifying daemon health..."
    echo ""

    local status_json=$(uv run ninja-daemon status 2>/dev/null)

    if [[ -z "$status_json" ]]; then
        warn "Could not get daemon status"
        return 1
    fi

    # Parse JSON and check each daemon
    local all_healthy=0
    python3 <<PYTHON_EOF
import json
import sys

status = json.loads('''$status_json''')

healthy = 0
unhealthy = 0

for module, info in status.items():
    if info.get("running"):
        print(f"✓ {module}: Running (PID {info['pid']}, Port {info['port']})")
        healthy += 1
    else:
        print(f"✗ {module}: Not running")
        unhealthy += 1

if unhealthy > 0:
    sys.exit(1)
PYTHON_EOF

    if [[ $? -eq 0 ]]; then
        echo ""
        success "All daemons are healthy"
        return 0
    else
        echo ""
        error "Some daemons are not healthy"
        return 1
    fi
}

# Function to update Claude Code config
update_claude_config() {
    # Detect Claude Code config location
    local claude_config=$(detect_claude_mcp_config)

    info "Updating Claude Code configuration..."
    info "Using config: $claude_config"

    if [[ ! -f "$claude_config" ]]; then
        warn "Claude Code configuration not found at $claude_config"
        echo "Run ./scripts/install_claude_code_mcp.sh to create it"
        return 1
    fi

    # Backup existing config
    cp "$claude_config" "$claude_config.backup.$(date +%s)"
    info "Created backup: $claude_config.backup.*"

    # Update using Python
    python3 <<PYTHON_EOF
import json
import sys
from pathlib import Path

config_file = Path("$claude_config")

try:
    with open(config_file, 'r') as f:
        config = json.load(f)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON in {config_file}: {e}", file=sys.stderr)
    sys.exit(1)

if "mcpServers" not in config:
    config["mcpServers"] = {}

# Update each ninja server
updated = []
for server_name in ["ninja-coder", "ninja-researcher", "ninja-secretary"]:
    if server_name in config["mcpServers"]:
        if $USE_DAEMON:
            # Update to daemon mode
            module = server_name.replace("ninja-", "")
            config["mcpServers"][server_name] = {
                "command": "uv",
                "args": ["--directory", "$PROJECT_ROOT", "run", "ninja-daemon", "connect", module]
            }
        else:
            # Update to direct mode
            module = server_name.replace("ninja-", "")
            config["mcpServers"][server_name] = {
                "command": "uv",
                "args": ["--directory", "$PROJECT_ROOT", "run", "python", "-m", f"ninja_{module}.server"]
            }
        updated.append(server_name)

# Write back
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

if updated:
    print(f"✓ Updated {len(updated)} server(s): {', '.join(updated)}")
else:
    print("⚠ No ninja servers found in configuration")
PYTHON_EOF

    validate_json "$claude_config" "Claude Code"
}

# Function to update VS Code config
update_vscode_config() {
    local vscode_config="$HOME/.config/Code/User/mcp.json"

    info "Updating VS Code configuration..."

    if [[ ! -f "$vscode_config" ]]; then
        warn "VS Code configuration not found at $vscode_config"
        echo "Run ./scripts/install_vscode_mcp.sh to create it"
        return 1
    fi

    # Backup existing config
    cp "$vscode_config" "$vscode_config.backup.$(date +%s)"
    info "Created backup: $vscode_config.backup.*"

    # Get run_server.sh path
    local run_server="$SCRIPT_DIR/run_server.sh"

    # Update using Python
    python3 <<PYTHON_EOF
import json
import sys
import os
from pathlib import Path

config_file = Path("$vscode_config")

try:
    with open(config_file, 'r') as f:
        config = json.load(f)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON in {config_file}: {e}", file=sys.stderr)
    sys.exit(1)

if "mcpServers" not in config:
    config["mcpServers"] = {}

# Update ninja-cli-mcp server with environment variables
if "ninja-cli-mcp" in config["mcpServers"]:
    env_vars = {}
    if os.environ.get("OPENROUTER_API_KEY"):
        env_vars["OPENROUTER_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
    if os.environ.get("OPENAI_API_KEY"):
        env_vars["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
    if os.environ.get("NINJA_MODEL"):
        env_vars["NINJA_MODEL"] = os.environ["NINJA_MODEL"]
    if os.environ.get("NINJA_CODE_BIN"):
        env_vars["NINJA_CODE_BIN"] = os.environ["NINJA_CODE_BIN"]

    config["mcpServers"]["ninja-cli-mcp"]["env"] = env_vars
    print("✓ Updated ninja-cli-mcp environment variables")
else:
    print("⚠ ninja-cli-mcp not found in VS Code configuration")

# Write back
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
PYTHON_EOF

    validate_json "$vscode_config" "VS Code"
}

# Function to update Zed config
update_zed_config() {
    local zed_config="$HOME/.config/zed/settings.json"

    info "Updating Zed configuration..."

    if [[ ! -f "$zed_config" ]]; then
        warn "Zed configuration not found at $zed_config"
        echo "Run ./scripts/install_zed_mcp.sh to create it"
        return 1
    fi

    # Backup existing config
    cp "$zed_config" "$zed_config.backup.$(date +%s)"
    info "Created backup: $zed_config.backup.*"

    # Update using Python
    python3 <<PYTHON_EOF
import json
import sys
import os
import re
from pathlib import Path

config_file = Path("$zed_config")

try:
    with open(config_file, 'r') as f:
        content = f.read()

    # Strip // comments (JSONC format)
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
    config = json.loads(content)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON in {config_file}: {e}", file=sys.stderr)
    sys.exit(1)

if "context_servers" not in config:
    print("⚠ No context_servers found in Zed configuration")
    sys.exit(0)

# Update ninja-cli-mcp server with environment variables
if "ninja-cli-mcp" in config["context_servers"]:
    env_vars = {}
    if os.environ.get("OPENROUTER_API_KEY"):
        env_vars["OPENROUTER_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
    if os.environ.get("OPENAI_API_KEY"):
        env_vars["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
    if os.environ.get("NINJA_MODEL"):
        env_vars["NINJA_MODEL"] = os.environ["NINJA_MODEL"]
    if os.environ.get("NINJA_CODE_BIN"):
        env_vars["NINJA_CODE_BIN"] = os.environ["NINJA_CODE_BIN"]

    config["context_servers"]["ninja-cli-mcp"]["env"] = env_vars
    print("✓ Updated ninja-cli-mcp environment variables")
else:
    print("⚠ ninja-cli-mcp not found in Zed configuration")

# Write back
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
PYTHON_EOF

    validate_json "$zed_config" "Zed"
}

# Function to update Copilot CLI config
update_copilot_config() {
    local copilot_config="$HOME/.copilot/mcp-config.json"

    info "Updating Copilot CLI configuration..."

    if [[ ! -f "$copilot_config" ]]; then
        warn "Copilot CLI configuration not found at $copilot_config"
        echo "Run ./scripts/install_copilot_cli_mcp.sh to create it"
        return 1
    fi

    # Backup existing config
    cp "$copilot_config" "$copilot_config.backup.$(date +%s)"
    info "Created backup: $copilot_config.backup.*"

    # Update using Python
    python3 <<PYTHON_EOF
import json
import sys
import os
from pathlib import Path

config_file = Path("$copilot_config")

try:
    with open(config_file, 'r') as f:
        config = json.load(f)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON in {config_file}: {e}", file=sys.stderr)
    sys.exit(1)

if "mcpServers" not in config:
    config["mcpServers"] = {}

# Update ninja-cli-mcp server with environment variables
if "ninja-cli-mcp" in config["mcpServers"]:
    env_vars = {}
    if os.environ.get("OPENROUTER_API_KEY"):
        env_vars["OPENROUTER_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
    if os.environ.get("OPENAI_API_KEY"):
        env_vars["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]
    if os.environ.get("NINJA_MODEL"):
        env_vars["NINJA_MODEL"] = os.environ["NINJA_MODEL"]
    if os.environ.get("NINJA_CODE_BIN"):
        env_vars["NINJA_CODE_BIN"] = os.environ["NINJA_CODE_BIN"]

    config["mcpServers"]["ninja-cli-mcp"]["env"] = env_vars
    print("✓ Updated ninja-cli-mcp environment variables")
else:
    print("⚠ ninja-cli-mcp not found in Copilot CLI configuration")

# Write back
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
PYTHON_EOF

    validate_json "$copilot_config" "Copilot CLI"
}

# Validation mode
if [[ $VALIDATE_ONLY -eq 1 ]]; then
    echo ""
    info "Validating all MCP configurations..."
    echo ""

    VALID_COUNT=0
    INVALID_COUNT=0

    # Detect Claude config location
    CLAUDE_CONFIG=$(detect_claude_mcp_config)
    if [[ -f "$CLAUDE_CONFIG" ]]; then
        validate_json "$CLAUDE_CONFIG" "Claude Code" && VALID_COUNT=$((VALID_COUNT + 1)) || INVALID_COUNT=$((INVALID_COUNT + 1))
    fi

    if [[ -f "$HOME/.config/Code/User/mcp.json" ]]; then
        validate_json "$HOME/.config/Code/User/mcp.json" "VS Code" && VALID_COUNT=$((VALID_COUNT + 1)) || INVALID_COUNT=$((INVALID_COUNT + 1))
    fi

    if [[ -f "$HOME/.config/zed/settings.json" ]]; then
        validate_json "$HOME/.config/zed/settings.json" "Zed" && VALID_COUNT=$((VALID_COUNT + 1)) || INVALID_COUNT=$((INVALID_COUNT + 1))
    fi

    if [[ -f "$HOME/.copilot/mcp-config.json" ]]; then
        validate_json "$HOME/.copilot/mcp-config.json" "Copilot CLI" && VALID_COUNT=$((VALID_COUNT + 1)) || INVALID_COUNT=$((INVALID_COUNT + 1))
    fi

    echo ""
    echo "==========================================="
    echo "  Validation Summary"
    echo "==========================================="
    echo ""
    success "$VALID_COUNT configuration(s) are valid"
    if [[ $INVALID_COUNT -gt 0 ]]; then
        error "$INVALID_COUNT configuration(s) have errors"
    fi
    echo ""

    exit 0
fi

# Code update mode
if [[ $UPDATE_CODE -eq 1 ]]; then
    if update_code_and_deps; then
        if [[ $SKIP_RESTART -eq 0 ]]; then
            restart_all_daemons
            verify_daemon_health
        else
            warn "Skipping daemon restart (--skip-restart)"
        fi

        echo ""
        success "Code update completed successfully"
        echo ""
        echo "Next steps:"
        echo "  - Verify daemons: uv run ninja-daemon status"
        echo "  - Test MCP servers: claude mcp list"
        echo ""
    else
        error "Code update failed"
        exit 1
    fi

    # If only code update was requested, exit now
    if [[ $UPDATE_CLAUDE -eq 0 && $UPDATE_VSCODE -eq 0 && $UPDATE_ZED -eq 0 && $UPDATE_COPILOT -eq 0 ]]; then
        exit 0
    fi
fi

# Determine what to update
if [[ $UPDATE_ALL -eq 1 ]]; then
    CLAUDE_CONFIG=$(detect_claude_mcp_config)
    [[ -f "$CLAUDE_CONFIG" ]] && UPDATE_CLAUDE=1
    [[ -f "$HOME/.config/Code/User/mcp.json" ]] && UPDATE_VSCODE=1
    [[ -f "$HOME/.config/zed/settings.json" ]] && UPDATE_ZED=1
    [[ -f "$HOME/.copilot/mcp-config.json" ]] && UPDATE_COPILOT=1
fi

# Show update plan
echo ""
info "Update plan:"
echo ""

UPDATE_COUNT=0
[[ $UPDATE_CLAUDE -eq 1 ]] && echo "  → Claude Code" && UPDATE_COUNT=$((UPDATE_COUNT + 1))
[[ $UPDATE_VSCODE -eq 1 ]] && echo "  → VS Code" && UPDATE_COUNT=$((UPDATE_COUNT + 1))
[[ $UPDATE_ZED -eq 1 ]] && echo "  → Zed" && UPDATE_COUNT=$((UPDATE_COUNT + 1))
[[ $UPDATE_COPILOT -eq 1 ]] && echo "  → Copilot CLI" && UPDATE_COUNT=$((UPDATE_COUNT + 1))

if [[ $UPDATE_COUNT -eq 0 ]]; then
    warn "No configurations found to update"
    echo ""
    echo "Install MCP integrations first:"
    echo "  ./scripts/install_claude_code_mcp.sh"
    echo "  ./scripts/install_ide_integrations.sh"
    echo ""
    exit 0
fi

echo ""
echo "Mode: $([ $USE_DAEMON -eq 1 ] && echo 'Daemon' || echo 'Direct')"
echo ""

read -p "Continue with update? (Y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "Update cancelled."
    exit 0
fi

echo ""
echo "==========================================="
echo "  Updating Configurations"
echo "==========================================="
echo ""

SUCCESS_COUNT=0
FAIL_COUNT=0

# Update each IDE
[[ $UPDATE_CLAUDE -eq 1 ]] && { update_claude_config && SUCCESS_COUNT=$((SUCCESS_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1)); echo ""; }
[[ $UPDATE_VSCODE -eq 1 ]] && { update_vscode_config && SUCCESS_COUNT=$((SUCCESS_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1)); echo ""; }
[[ $UPDATE_ZED -eq 1 ]] && { update_zed_config && SUCCESS_COUNT=$((SUCCESS_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1)); echo ""; }
[[ $UPDATE_COPILOT -eq 1 ]] && { update_copilot_config && SUCCESS_COUNT=$((SUCCESS_COUNT + 1)) || FAIL_COUNT=$((FAIL_COUNT + 1)); echo ""; }

# Restart daemons if needed
if [[ $USE_DAEMON -eq 1 && $SKIP_RESTART -eq 0 ]]; then
    restart_all_daemons
    verify_daemon_health
elif [[ $SKIP_RESTART -eq 1 ]]; then
    warn "Skipping daemon restart (--skip-restart)"
fi

echo "==========================================="
echo "  Update Summary"
echo "==========================================="
echo ""

if [[ $SUCCESS_COUNT -gt 0 ]]; then
    success "$SUCCESS_COUNT configuration(s) updated successfully"
fi

if [[ $FAIL_COUNT -gt 0 ]]; then
    error "$FAIL_COUNT configuration(s) failed to update"
fi

echo ""
echo "Next steps:"
echo "  - Restart your IDE to apply changes"
if [[ $USE_DAEMON -eq 1 ]]; then
    echo "  - Check daemon status: uv run ninja-daemon status"
fi
echo "  - Validate configurations: $0 --validate"
echo ""
