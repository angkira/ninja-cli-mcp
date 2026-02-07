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

set -eo pipefail

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
# STEP 1: Backup and migrate existing configuration
# ============================================================================
info "Detecting and migrating configuration..."

BACKUP_DIR=$(mktemp -d)
BACKUP_CONFIG="$BACKUP_DIR/ninja-mcp.env"
BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ARCHIVE="$HOME/.ninja-mcp-backups/backup_$BACKUP_TIMESTAMP.env"

# Create backup directory
mkdir -p "$HOME/.ninja-mcp-backups"

# List of all config keys to migrate (bash 3.2 compatible)
CONFIG_KEYS="OPENROUTER_API_KEY SERPER_API_KEY PERPLEXITY_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY ZHIPU_API_KEY NINJA_MODEL NINJA_CODER_MODEL NINJA_RESEARCHER_MODEL NINJA_SECRETARY_MODEL NINJA_RESOURCES_MODEL NINJA_PROMPTS_MODEL NINJA_MODEL_QUICK NINJA_MODEL_SEQUENTIAL NINJA_MODEL_PARALLEL NINJA_PREFER_COST NINJA_PREFER_QUALITY NINJA_SEARCH_PROVIDER NINJA_CODE_BIN OPENAI_BASE_URL NINJA_CODER_PORT NINJA_RESEARCHER_PORT NINJA_SECRETARY_PORT NINJA_RESOURCES_PORT NINJA_PROMPTS_PORT OPENCODE_DISABLE_DAEMON"

# Initialize saved values (using SAVED_ prefix for bash 3.2 compatibility)
for key in $CONFIG_KEYS; do
    eval "SAVED_$key=''"
done

# Function to extract value from config file
extract_value() {
    local file="$1"
    local key="$2"
    local value=""

    if [[ -f "$file" ]]; then
        # Try exact match first
        value=$(grep "^${key}=" "$file" 2>/dev/null | head -1 | cut -d'=' -f2- | sed 's/^["'"'"']//;s/["'"'"']$//' || echo "")

        # If not found, try with export
        if [[ -z "$value" ]]; then
            value=$(grep "^export ${key}=" "$file" 2>/dev/null | head -1 | cut -d'=' -f2- | sed 's/^["'"'"']//;s/["'"'"']$//' || echo "")
        fi
    fi

    echo "$value"
}

# Function to check if value looks like a real API key (not placeholder)
is_real_value() {
    local value="${1:-}"
    [[ -n "$value" ]] && \
    [[ "$value" != "your-"* ]] && \
    [[ "$value" != *"placeholder"* ]] && \
    [[ "$value" != "REPLACE"* ]] && \
    [[ "$value" != "TODO"* ]] && \
    [[ "$value" != "xxx"* ]] && \
    [[ "$value" != "..."* ]]
}

# Function to get saved value
get_saved() {
    local key="$1"
    eval "echo \"\$SAVED_$key\""
}

# Function to set saved value
set_saved() {
    local key="$1"
    local value="$2"
    eval "SAVED_$key='$value'"
}

info "Searching for existing configurations..."

# 1. Check current config file
if [[ -f "$NINJA_CONFIG" ]]; then
    cp "$NINJA_CONFIG" "$BACKUP_CONFIG"
    cp "$NINJA_CONFIG" "$BACKUP_ARCHIVE"
    success "Backed up current config to $BACKUP_ARCHIVE"

    # Extract all values from current config
    for key in $CONFIG_KEYS; do
        value=$(extract_value "$NINJA_CONFIG" "$key")
        if is_real_value "$value"; then
            set_saved "$key" "$value"
        fi
    done
fi

# 2. Check legacy config locations
for legacy_config in "$HOME/.config/ninja/config.env" "$HOME/.ninja/config.env" "$HOME/.ninja-config.env"; do
    if [[ -f "$legacy_config" ]]; then
        info "Found legacy config: $legacy_config"

        for key in $CONFIG_KEYS; do
            current=$(get_saved "$key")
            if [[ -z "$current" ]]; then
                value=$(extract_value "$legacy_config" "$key")
                if is_real_value "$value"; then
                    set_saved "$key" "$value"
                    success "Migrated $key from $legacy_config"
                fi
            fi
        done

        # Backup legacy config
        cp "$legacy_config" "$BACKUP_DIR/$(basename "$legacy_config").legacy"
    fi
done

# 3. Check environment variables
for key in $CONFIG_KEYS; do
    current=$(get_saved "$key")
    if [[ -z "$current" ]]; then
        # Indirect variable expansion
        value="${!key:-}"
        if is_real_value "$value"; then
            set_saved "$key" "$value"
            success "Found $key in environment"
        fi
    fi
done

# 4. Check shell rc files for exported variables
for rc_file in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile" "$HOME/.bash_profile"; do
    if [[ -f "$rc_file" ]]; then
        for key in $CONFIG_KEYS; do
            current=$(get_saved "$key")
            if [[ -z "$current" ]]; then
                value=$(extract_value "$rc_file" "$key")
                if is_real_value "$value"; then
                    set_saved "$key" "$value"
                    info "Found $key in $rc_file"
                fi
            fi
        done
    fi
done

# 5. Migrate old variable names to new ones
# OPENAI_API_KEY -> OPENROUTER_API_KEY (if OpenRouter not set)
openrouter_key=$(get_saved "OPENROUTER_API_KEY")
openai_key=$(get_saved "OPENAI_API_KEY")
if [[ -z "$openrouter_key" ]] && [[ -n "$openai_key" ]]; then
    # Check if it's actually an OpenRouter key (starts with sk-or-)
    if [[ "$openai_key" == sk-or-* ]]; then
        set_saved "OPENROUTER_API_KEY" "$openai_key"
        success "Migrated OPENAI_API_KEY to OPENROUTER_API_KEY"
    fi
fi

# OPENROUTER_MODEL or OPENAI_MODEL -> NINJA_MODEL
ninja_model=$(get_saved "NINJA_MODEL")
if [[ -z "$ninja_model" ]]; then
    for old_key in "OPENROUTER_MODEL" "OPENAI_MODEL"; do
        old_value=$(extract_value "$NINJA_CONFIG" "$old_key" 2>/dev/null || echo "")
        if [[ -z "$old_value" ]] && [[ -f "$BACKUP_CONFIG" ]]; then
            old_value=$(extract_value "$BACKUP_CONFIG" "$old_key" || echo "")
        fi
        if is_real_value "$old_value"; then
            set_saved "NINJA_MODEL" "$old_value"
            success "Migrated $old_key to NINJA_MODEL"
            break
        fi
    done
fi

# Summary of found values
echo ""
info "Configuration migration summary:"
found_count=0
for key in OPENROUTER_API_KEY SERPER_API_KEY PERPLEXITY_API_KEY ANTHROPIC_API_KEY ZHIPU_API_KEY; do
    value=$(get_saved "$key")
    if [[ -n "$value" ]]; then
        len=${#value}
        success "✓ $key ($len chars)"
        found_count=$((found_count + 1))
    fi
done

for key in NINJA_MODEL NINJA_SEARCH_PROVIDER NINJA_CODE_BIN NINJA_MODEL_QUICK NINJA_MODEL_SEQUENTIAL NINJA_MODEL_PARALLEL; do
    value=$(get_saved "$key")
    if [[ -n "$value" ]]; then
        success "✓ $key = $value"
        found_count=$((found_count + 1))
    fi
done

if [[ $found_count -eq 0 ]]; then
    warn "No existing configuration found - will start fresh"
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

# Verify correct binaries are being used and update command aliases
info "Verifying binary locations..."
for cmd in ninja-coder ninja-researcher ninja-secretary ninja-resources ninja-prompts ninja-config ninja-daemon; do
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
# STEP 3: Write migrated configuration
# ============================================================================
echo ""
info "Writing migrated configuration..."

# Create new config with all migrated values
cat > "$NINJA_CONFIG" << EOF
# =============================================================================
# Ninja MCP Configuration - Centralized
# =============================================================================
# This file is the single source of truth for all Ninja MCP settings.
# All MCP servers read from this file.
#
# Last updated: $(date)
# =============================================================================

# -----------------------------------------------------------------------------
# API Keys
# -----------------------------------------------------------------------------
EOF

# Write API keys
for key in OPENROUTER_API_KEY SERPER_API_KEY PERPLEXITY_API_KEY ANTHROPIC_API_KEY ZHIPU_API_KEY; do
    value=$(get_saved "$key")
    if [[ -n "$value" ]]; then
        echo "$key=$value" >> "$NINJA_CONFIG"
    else
        echo "# $key=" >> "$NINJA_CONFIG"
    fi
done

cat >> "$NINJA_CONFIG" << 'EOF'

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
EOF

# Write model settings with defaults
ninja_model=$(get_saved "NINJA_MODEL")
if [[ -n "$ninja_model" ]]; then
    echo "NINJA_MODEL=$ninja_model" >> "$NINJA_CONFIG"
else
    echo "# NINJA_MODEL=anthropic/claude-sonnet-4" >> "$NINJA_CONFIG"
fi

for module in CODER RESEARCHER SECRETARY RESOURCES PROMPTS; do
    key="NINJA_${module}_MODEL"
    value=$(get_saved "$key")
    if [[ -n "$value" ]]; then
        echo "$key=$value" >> "$NINJA_CONFIG"
    fi
done

cat >> "$NINJA_CONFIG" << 'EOF'

# -----------------------------------------------------------------------------
# Task-Based Models (for different task types)
# -----------------------------------------------------------------------------
EOF

# Write task-based models
quick_model=$(get_saved "NINJA_MODEL_QUICK")
if [[ -n "$quick_model" ]]; then
    echo "NINJA_MODEL_QUICK=$quick_model" >> "$NINJA_CONFIG"
else
    echo "# NINJA_MODEL_QUICK=anthropic/claude-haiku-4.5" >> "$NINJA_CONFIG"
fi

sequential_model=$(get_saved "NINJA_MODEL_SEQUENTIAL")
if [[ -n "$sequential_model" ]]; then
    echo "NINJA_MODEL_SEQUENTIAL=$sequential_model" >> "$NINJA_CONFIG"
else
    echo "# NINJA_MODEL_SEQUENTIAL=anthropic/claude-sonnet-4" >> "$NINJA_CONFIG"
fi

parallel_model=$(get_saved "NINJA_MODEL_PARALLEL")
if [[ -n "$parallel_model" ]]; then
    echo "NINJA_MODEL_PARALLEL=$parallel_model" >> "$NINJA_CONFIG"
else
    echo "# NINJA_MODEL_PARALLEL=anthropic/claude-haiku-4.5" >> "$NINJA_CONFIG"
fi

# Write model preferences
prefer_cost=$(get_saved "NINJA_PREFER_COST")
if [[ -n "$prefer_cost" ]]; then
    echo "NINJA_PREFER_COST=$prefer_cost" >> "$NINJA_CONFIG"
fi

prefer_quality=$(get_saved "NINJA_PREFER_QUALITY")
if [[ -n "$prefer_quality" ]]; then
    echo "NINJA_PREFER_QUALITY=$prefer_quality" >> "$NINJA_CONFIG"
fi

cat >> "$NINJA_CONFIG" << 'EOF'

# -----------------------------------------------------------------------------
# Providers & Tools
# -----------------------------------------------------------------------------
EOF

# Write provider settings
search_provider=$(get_saved "NINJA_SEARCH_PROVIDER")
if [[ -n "$search_provider" ]]; then
    echo "NINJA_SEARCH_PROVIDER=$search_provider" >> "$NINJA_CONFIG"
else
    echo "NINJA_SEARCH_PROVIDER=duckduckgo" >> "$NINJA_CONFIG"
fi

code_bin=$(get_saved "NINJA_CODE_BIN")
if [[ -n "$code_bin" ]]; then
    echo "NINJA_CODE_BIN=$code_bin" >> "$NINJA_CONFIG"
else
    # Auto-detect code CLI (priority: opencode > claude > aider)
    if command -v opencode &> /dev/null; then
        echo "NINJA_CODE_BIN=$(command -v opencode)" >> "$NINJA_CONFIG"
        info "Auto-detected opencode"
    elif command -v claude &> /dev/null; then
        echo "NINJA_CODE_BIN=$(command -v claude)" >> "$NINJA_CONFIG"
        info "Auto-detected claude (Claude Code)"
    elif command -v aider &> /dev/null; then
        echo "NINJA_CODE_BIN=aider" >> "$NINJA_CONFIG"
        info "Auto-detected aider"
    else
        echo "NINJA_CODE_BIN=aider" >> "$NINJA_CONFIG"
    fi
fi

base_url=$(get_saved "OPENAI_BASE_URL")
if [[ -n "$base_url" ]]; then
    echo "OPENAI_BASE_URL=$base_url" >> "$NINJA_CONFIG"
else
    echo "OPENAI_BASE_URL=https://openrouter.ai/api/v1" >> "$NINJA_CONFIG"
fi

disable_daemon=$(get_saved "OPENCODE_DISABLE_DAEMON")
if [[ -n "$disable_daemon" ]]; then
    echo "OPENCODE_DISABLE_DAEMON=$disable_daemon" >> "$NINJA_CONFIG"
fi

cat >> "$NINJA_CONFIG" << 'EOF'

# -----------------------------------------------------------------------------
# Daemon Ports
# -----------------------------------------------------------------------------
EOF

# Configure daemon ports
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

    # Use saved port if exists, otherwise find free port
    saved_port=$(get_saved "$env_key")
    if [[ -n "$saved_port" ]]; then
        port="$saved_port"
        success "Restored $env_key=$port"
    else
        port=$(find_free_port "$default_port")
        if [ "$port" != "$default_port" ]; then
            warn "$module: port $default_port busy, using $port"
        fi
    fi
    echo "$env_key=$port" >> "$NINJA_CONFIG"
done

success "Configuration migrated to $NINJA_CONFIG"

# Export keys for current session
for key in OPENROUTER_API_KEY SERPER_API_KEY PERPLEXITY_API_KEY ANTHROPIC_API_KEY ZHIPU_API_KEY; do
    value=$(get_saved "$key")
    if [[ -n "$value" ]]; then
        export "$key=$value"
    fi
done

# ============================================================================
# STEP 4: Restart HTTP MCP servers with new code
# ============================================================================
echo ""
info "Restarting HTTP MCP servers with new code..."

if [[ -f "$SCRIPT_DIR/scripts/post-install.sh" ]]; then
    bash "$SCRIPT_DIR/scripts/post-install.sh"
else
    # Kill old servers
    pkill -f "ninja_coder.server" 2>/dev/null || true
    pkill -f "ninja_researcher.server" 2>/dev/null || true
    pkill -f "ninja_secretary.server" 2>/dev/null || true
    pkill -f "ninja_prompts.server" 2>/dev/null || true
    sleep 2

    # Start new servers (only if in dev directory)
    if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
        cd "$SCRIPT_DIR"
        nohup uv run python -m ninja_coder.server --http --port 8100 > /tmp/ninja-coder.log 2>&1 &
        nohup uv run python -m ninja_researcher.server --http --port 8101 > /tmp/ninja-researcher.log 2>&1 &
        nohup uv run python -m ninja_secretary.server --http --port 8102 > /tmp/ninja-secretary.log 2>&1 &
        nohup uv run python -m ninja_prompts.server --http --port 8107 > /tmp/ninja-prompts.log 2>&1 &
        sleep 3
        success "HTTP MCP servers restarted from local code"
    fi
fi

# ============================================================================
# STEP 5: Start daemons (optional)
# ============================================================================
echo ""
info "Starting ninja daemons..."

if command -v ninja-daemon &> /dev/null; then
    if ninja-daemon start 2>&1 | grep -q "✓\|already running"; then
        success "All daemons started"
    else
        warn "Some daemons may have failed to start"
        info "Check daemon status with: ninja-daemon status"
    fi
else
    info "Ninja daemons not available (using HTTP servers only)"
fi

# ============================================================================
# STEP 6: Re-register Claude Code MCP servers
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
            echo "NINJA_MODEL=anthropic/claude-sonnet-4" >> "$NINJA_CONFIG"
            success "Set NINJA_MODEL=anthropic/claude-sonnet-4 in $NINJA_CONFIG"
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
# STEP 7: Verify installation
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
echo -e "${BOLD}Configuration:${NC}"
if [[ $found_count -gt 0 ]]; then
    echo -e "  ${GREEN}✓ Migrated $found_count settings from old configs${NC}"
    echo -e "  ${GREEN}✓ Backup saved to: $BACKUP_ARCHIVE${NC}"
else
    echo -e "  ${YELLOW}⚠ No previous config found - using defaults${NC}"
fi
echo -e "  ${BLUE}➜ Config file: $NINJA_CONFIG${NC}"

echo ""
echo -e "${BOLD}Next steps:${NC}"
if [[ $found_count -eq 0 ]]; then
    echo "  ninja-config configure       # Full interactive setup"
    echo "  ninja-config configure --quick  # Quick API key + operator setup"
fi
echo "  ninja-config doctor          # Verify configuration"
echo "  claude mcp list              # Check MCP servers"
echo ""
