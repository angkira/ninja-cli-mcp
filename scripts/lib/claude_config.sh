#!/usr/bin/env bash
#
# claude_config.sh - Shared utilities for Claude Code MCP configuration
#
# Functions for detecting and managing Claude Code configuration files

# Detect Claude Code MCP config location
# Returns the path to the appropriate config file based on platform
detect_claude_mcp_config() {
    local claude_config=""

    # Try new location first (Claude Code 1.0+)
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS
        claude_config="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    elif [[ "$(uname)" == "Linux" ]]; then
        # Linux
        claude_config="$HOME/.config/Claude/claude_desktop_config.json"
    fi

    # If new location doesn't exist, try legacy location
    if [[ ! -f "$claude_config" ]]; then
        # Legacy location
        if [[ -d "$HOME/.claude" ]]; then
            claude_config="$HOME/.claude/config.json"
        else
            # Default to new location for creation
            if [[ "$(uname)" == "Darwin" ]]; then
                claude_config="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
            else
                claude_config="$HOME/.config/Claude/claude_desktop_config.json"
            fi
        fi
    fi

    echo "$claude_config"
}

# Initialize Claude Code MCP config if it doesn't exist
# Args:
#   $1 - Path to config file
init_claude_mcp_config() {
    local config_file="$1"
    local config_dir=$(dirname "$config_file")

    # Create directory if needed
    if [[ ! -d "$config_dir" ]]; then
        mkdir -p "$config_dir"
    fi

    # Create minimal config if file doesn't exist
    if [[ ! -f "$config_file" ]]; then
        cat > "$config_file" << 'EOF'
{
  "mcpServers": {}
}
EOF
        chmod 600 "$config_file"
    fi
}

# Check if config migration from old location is needed
# Offers to migrate config from ~/.claude/config.json to new location
check_config_migration() {
    local old_config="$HOME/.claude/config.json"
    local new_config=$(detect_claude_mcp_config)

    # Skip if old config doesn't exist or new config already exists
    if [[ ! -f "$old_config" ]] || [[ -f "$new_config" ]]; then
        return 0
    fi

    # Skip if they're the same file
    if [[ "$old_config" == "$new_config" ]]; then
        return 0
    fi

    echo ""
    echo -e "${YELLOW}[MIGRATION]${NC} Found legacy Claude config at: $old_config"
    echo -e "${YELLOW}[MIGRATION]${NC} New location is: $new_config"
    echo ""

    read -p "Would you like to migrate the config? [Y/n] " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        # Create directory for new config
        local new_dir=$(dirname "$new_config")
        mkdir -p "$new_dir"

        # Copy config
        cp "$old_config" "$new_config"
        chmod 600 "$new_config"

        echo -e "${GREEN}[OK]${NC} Config migrated to: $new_config"
        echo -e "${BLUE}[INFO]${NC} Old config preserved at: $old_config"
        echo ""
    fi
}
