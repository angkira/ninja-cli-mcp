#!/usr/bin/env bash
#
# Ninja MCP - Update Script
#
# Updates ninja-mcp while preserving your configuration.
#
# Usage:
#   ./update.sh
#   curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/update.sh | bash
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

info() { echo -e "${BLUE}▸${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }

# Banner
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}              🥷 ${BOLD}NINJA MCP UPDATER${NC}                        ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Config file
NINJA_CONFIG="$HOME/.ninja-mcp.env"

# ============================================================================
# STEP 1: Backup existing configuration
# ============================================================================
info "Backing up configuration..."

BACKUP_DIR=$(mktemp -d)
BACKUP_CONFIG="$BACKUP_DIR/ninja-mcp.env"

# Save environment config
if [[ -f "$NINJA_CONFIG" ]]; then
    cp "$NINJA_CONFIG" "$BACKUP_CONFIG"
    success "Saved $NINJA_CONFIG"
else
    warn "No existing config found at $NINJA_CONFIG"
fi

# Save current API key from environment
SAVED_OPENROUTER_KEY="${OPENROUTER_API_KEY:-}"
SAVED_SERPER_KEY="${SERPER_API_KEY:-}"
SAVED_PERPLEXITY_KEY="${PERPLEXITY_API_KEY:-}"

# Try to load from config file
if [[ -f "$BACKUP_CONFIG" ]]; then
    source "$BACKUP_CONFIG" 2>/dev/null || true
    SAVED_OPENROUTER_KEY="${OPENROUTER_API_KEY:-$SAVED_OPENROUTER_KEY}"
    SAVED_SERPER_KEY="${SERPER_API_KEY:-$SAVED_SERPER_KEY}"
    SAVED_PERPLEXITY_KEY="${PERPLEXITY_API_KEY:-$SAVED_PERPLEXITY_KEY}"
fi

if [[ -n "$SAVED_OPENROUTER_KEY" ]]; then
    success "Found OpenRouter API key"
fi
if [[ -n "$SAVED_SERPER_KEY" ]]; then
    success "Found Serper API key"
fi
if [[ -n "$SAVED_PERPLEXITY_KEY" ]]; then
    success "Found Perplexity API key"
fi

# ============================================================================
# STEP 2: Update ninja-mcp package
# ============================================================================
echo ""
info "Updating ninja-mcp..."

# Check if uv is available
if ! command -v uv &> /dev/null; then
    error "uv not found. Run install.sh first."
fi

UPDATE_SUCCESS=false

# IMPORTANT: Deactivate any virtual environment to avoid PATH conflicts
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    info "Deactivating virtual environment..."
    deactivate 2>/dev/null || true
    unset VIRTUAL_ENV
fi

# Remove .venv/bin from PATH if present (dev directory edge case)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCRIPT_DIR/.venv/bin" ]]; then
    PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "$SCRIPT_DIR/.venv/bin" | tr '\n' ':' | sed 's/:$//')
    export PATH
fi

# Ensure ~/.local/bin is at the front of PATH
export PATH="$HOME/.local/bin:$PATH"

# Detect if running from dev directory (has pyproject.toml)
if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
    info "Detected dev directory, installing from local source..."
    if uv tool install --force "$SCRIPT_DIR[all]" 2>&1; then
        UPDATE_SUCCESS=true
        success "Updated from local dev directory"

        # Clean up any dev .venv binaries that might conflict
        if [[ -d "$SCRIPT_DIR/.venv/bin" ]]; then
            info "Cleaning dev environment binaries to avoid conflicts..."
            rm -f "$SCRIPT_DIR/.venv/bin/ninja-"* 2>/dev/null || true
        fi
    else
        warn "Local install failed, falling back to remote..."
    fi
fi

# If not in dev dir or local install failed, try PyPI then GitHub
if [[ "$UPDATE_SUCCESS" != "true" ]]; then
    if uv tool upgrade ninja-mcp 2>/dev/null; then
        UPDATE_SUCCESS=true
        success "Updated from PyPI"
    elif uv tool install --force "ninja-mcp[all] @ git+https://github.com/angkira/ninja-cli-mcp.git" 2>&1; then
        UPDATE_SUCCESS=true
        success "Updated from GitHub"
    else
        warn "Could not update automatically"
        info "Trying reinstall..."
        uv tool uninstall ninja-mcp 2>/dev/null || true
        if uv tool install "ninja-mcp[all] @ git+https://github.com/angkira/ninja-cli-mcp.git" 2>&1; then
            UPDATE_SUCCESS=true
            success "Reinstalled from GitHub"
        else
            error "Update failed. Please check your internet connection."
        fi
    fi
fi

# Verify correct binaries are being used
info "Verifying binary locations..."
for cmd in ninja-coder ninja-researcher ninja-secretary ninja-resources ninja-prompts; do
    cmd_path=$(command -v "$cmd" 2>/dev/null || echo "not found")
    if [[ "$cmd_path" == *"/.local/"* ]]; then
        success "$cmd: $cmd_path"
    elif [[ "$cmd_path" == "not found" ]]; then
        warn "$cmd: not found in PATH"
    else
        warn "$cmd: using non-standard location: $cmd_path"
        warn "This may cause issues. Expected: ~/.local/bin/$cmd"
    fi
done

# ============================================================================
# STEP 3: Restore configuration
# ============================================================================
echo ""
info "Restoring configuration..."

# Restore config file
if [[ -f "$BACKUP_CONFIG" ]]; then
    cp "$BACKUP_CONFIG" "$NINJA_CONFIG"
    success "Restored $NINJA_CONFIG"
fi

# Ensure NINJA_CODE_BIN is set (fix for upgrades from older versions)
if ! grep -q "NINJA_CODE_BIN" "$NINJA_CONFIG" 2>/dev/null; then
    echo "NINJA_CODE_BIN=aider" >> "$NINJA_CONFIG"
    success "Added NINJA_CODE_BIN=aider to config"
fi

# Ensure daemon ports are configured (fix for upgrades from older versions)
is_port_free() {
    ! nc -z 127.0.0.1 "$1" 2>/dev/null
}

find_free_port() {
    local start_port=$1
    local port=$start_port
    while ! is_port_free "$port" && [ "$port" -lt $((start_port + 100)) ]; do
        port=$((port + 1))
    done
    echo "$port"
}

for module_port in "CODER:8100" "RESEARCHER:8101" "SECRETARY:8102" "RESOURCES:8106" "PROMPTS:8107"; do
    module="${module_port%%:*}"
    default_port="${module_port##*:}"
    env_key="NINJA_${module}_PORT"

    if ! grep -q "$env_key" "$NINJA_CONFIG" 2>/dev/null; then
        free_port=$(find_free_port "$default_port")
        echo "$env_key=$free_port" >> "$NINJA_CONFIG"
        if [ "$free_port" != "$default_port" ]; then
            warn "$module: port $default_port busy, using $free_port"
        else
            success "Added $env_key=$free_port"
        fi
    fi
done

# Export keys for current session
[[ -n "$SAVED_OPENROUTER_KEY" ]] && export OPENROUTER_API_KEY="$SAVED_OPENROUTER_KEY"
[[ -n "$SAVED_SERPER_KEY" ]] && export SERPER_API_KEY="$SAVED_SERPER_KEY"
[[ -n "$SAVED_PERPLEXITY_KEY" ]] && export PERPLEXITY_API_KEY="$SAVED_PERPLEXITY_KEY"

# ============================================================================
# STEP 4: Start daemons
# ============================================================================
echo ""
info "Starting ninja daemons..."

if ninja-daemon start 2>&1 | grep -q "✓\|already running"; then
    success "All daemons started"
else
    warn "Some daemons may have failed to start"
    info "Check daemon status with: ninja-daemon status"
fi

# ============================================================================
# STEP 5: Re-register Claude Code MCP servers
# ============================================================================
echo ""
info "Updating Claude Code MCP servers..."

if command -v claude &> /dev/null; then
    # Remove and re-add to ensure clean state
    # Use daemon proxy mode for hot-reload support
    for server_config in "ninja-coder:coder" "ninja-researcher:researcher" "ninja-secretary:secretary" "ninja-resources:resources" "ninja-prompts:prompts"; do
        server="${server_config%%:*}"
        module="${server_config##*:}"
        claude mcp remove "$server" -s user 2>/dev/null || true
        if claude mcp add --scope user --transport stdio "$server" -- ninja-daemon connect "$module" 2>/dev/null; then
            success "$server registered (daemon proxy mode)"
        else
            warn "Failed to register $server"
        fi
    done

    # Configure OpenCode if available (write to centralized config only)
    if command -v opencode &> /dev/null; then
        OPENCODE_PATH=$(command -v opencode)

        # Update NINJA_CODE_BIN in centralized config if not already set
        if ! grep -q "^NINJA_CODE_BIN=" "$NINJA_CONFIG" 2>/dev/null; then
            echo "NINJA_CODE_BIN=$OPENCODE_PATH" >> "$NINJA_CONFIG"
            success "Set NINJA_CODE_BIN=$OPENCODE_PATH in $NINJA_CONFIG"
        else
            info "NINJA_CODE_BIN already configured in $NINJA_CONFIG"
        fi

        # Update NINJA_MODEL if not already set
        if ! grep -q "^NINJA_MODEL=" "$NINJA_CONFIG" 2>/dev/null; then
            echo "NINJA_MODEL=anthropic/claude-sonnet-4-5" >> "$NINJA_CONFIG"
            success "Set NINJA_MODEL=anthropic/claude-sonnet-4-5 in $NINJA_CONFIG"
        else
            info "NINJA_MODEL already configured in $NINJA_CONFIG"
        fi

        info "OpenCode configured - MCP servers will read from $NINJA_CONFIG"
    elif ! command -v opencode &> /dev/null; then
        info "OpenCode not found - keeping current configuration"
        info "Install OpenCode from: https://github.com/stackblitz/opencode"
    fi
else
    warn "Claude Code CLI not found - skipping MCP registration"
    info "Run 'ninja-config setup-claude' after installing Claude Code"
fi

# ============================================================================
# STEP 6: Verify installation
# ============================================================================
echo ""
info "Verifying installation..."

VERIFY_PASSED=true
for cmd in ninja-coder ninja-researcher ninja-secretary ninja-resources ninja-prompts ninja-config; do
    if command -v "$cmd" &> /dev/null; then
        success "$cmd"
    else
        warn "$cmd not found"
        VERIFY_PASSED=false
    fi
done

# Cleanup
rm -rf "$BACKUP_DIR"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║${NC}              ${BOLD}🥷 UPDATE COMPLETE!${NC}                         ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$VERIFY_PASSED" == "true" ]]; then
    echo -e "${GREEN}All components updated successfully.${NC}"
else
    echo -e "${YELLOW}Some components may need attention.${NC}"
fi

echo ""
echo -e "${BOLD}Verify:${NC}"
echo "  ninja-config doctor"
echo "  claude mcp list"
echo ""
