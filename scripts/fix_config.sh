#!/usr/bin/env bash
#
# fix_config.sh - Fix corrupted configuration file
#
# This script helps users fix their config file if it was created with
# the buggy installer that captured ANSI codes in the API key.
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

CHECK="✓"
CROSS="✗"

CONFIG_FILE="$HOME/.ninja-cli-mcp.env"

echo -e "${BLUE}🔧 Ninja CLI MCP Config Fixer${NC}"
echo ""

# Check if config file exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo -e "${YELLOW}No config file found at: $CONFIG_FILE${NC}"
    echo ""
    echo "Run the installer first:"
    echo "  ./scripts/install_interactive.sh"
    exit 1
fi

echo "Found config file: $CONFIG_FILE"
echo ""

# Read current API key
source "$CONFIG_FILE"
CURRENT_KEY="${OPENROUTER_API_KEY:-}"

if [[ -z "$CURRENT_KEY" ]]; then
    echo -e "${YELLOW}No API key found in config${NC}"
    echo "Please run the installer to set up your API key."
    exit 1
fi

echo "Current API key length: ${#CURRENT_KEY} characters"
echo ""

# Check for ANSI codes
HAS_ANSI=false
if [[ "$CURRENT_KEY" =~ \[ ]] || [[ "$CURRENT_KEY" =~ $'\033' ]]; then
    HAS_ANSI=true
fi

if [[ $HAS_ANSI == true ]]; then
    echo -e "${RED}${CROSS} API key contains ANSI escape codes or invalid characters!${NC}"
    echo ""
    echo "This will cause all API calls to fail."
    echo ""

    # Try to extract the actual key
    # Remove everything before 'sk-'
    CLEANED_KEY=$(echo "$CURRENT_KEY" | grep -oP 'sk-[a-zA-Z0-9\-]+' | head -1)

    if [[ -n "$CLEANED_KEY" ]]; then
        echo -e "${GREEN}Found potential valid key: ${CLEANED_KEY:0:10}...${CLEANED_KEY: -4}${NC}"
        echo ""
        echo -n "Would you like to use this cleaned key? [y/N] "
        read -r response

        if [[ "$response" =~ ^[Yy]$ ]]; then
            API_KEY="$CLEANED_KEY"
        else
            echo ""
            echo "Please enter your OpenRouter API key:"
            echo -n "> "
            read -s API_KEY
            echo ""
        fi
    else
        echo "Could not extract valid key from config."
        echo ""
        echo "Please enter your OpenRouter API key:"
        echo -n "> "
        read -s API_KEY
        echo ""
    fi

    # Validate the new key
    if [[ ${#API_KEY} -lt 20 ]]; then
        echo -e "${RED}${CROSS} API key seems too short${NC}"
        exit 1
    fi

    if [[ ${#API_KEY} -gt 100 ]]; then
        echo -e "${RED}${CROSS} API key seems too long${NC}"
        exit 1
    fi

    if [[ "$API_KEY" =~ \[ ]] || [[ "$API_KEY" =~ $'\033' ]]; then
        echo -e "${RED}${CROSS} New API key still contains invalid characters${NC}"
        exit 1
    fi

    # Backup old config
    cp "$CONFIG_FILE" "${CONFIG_FILE}.bak"
    echo -e "${GREEN}${CHECK} Backed up old config to ${CONFIG_FILE}.bak${NC}"

    # Write new config
    cat > "$CONFIG_FILE" << EOF
# ninja-cli-mcp Configuration
# Fixed on $(date)

# OpenRouter API Key
export OPENROUTER_API_KEY='$API_KEY'

# Model Selection
export NINJA_MODEL='${NINJA_MODEL:-anthropic/claude-haiku-4.5}'

# AI Code CLI Binary
export NINJA_CODE_BIN='${NINJA_CODE_BIN:-ninja-code}'

# Optional: Timeout in seconds
# export NINJA_TIMEOUT_SEC=600
EOF

    chmod 600 "$CONFIG_FILE"

    echo -e "${GREEN}${CHECK} Configuration fixed!${NC}"
    echo ""
    echo "New config saved to: $CONFIG_FILE"
    echo "API key: ${API_KEY:0:8}...${API_KEY: -4}"
    echo ""
    echo "To apply the changes, run:"
    echo "  source $CONFIG_FILE"

else
    echo -e "${GREEN}${CHECK} API key looks valid!${NC}"
    echo ""
    echo "Key format: ${CURRENT_KEY:0:8}...${CURRENT_KEY: -4}"
    echo ""

    # Test the key format
    if [[ ! "$CURRENT_KEY" =~ ^sk- ]]; then
        echo -e "${YELLOW}Warning: API key doesn't start with 'sk-'${NC}"
        echo "This might not be a valid OpenRouter key."
    fi

    if [[ ${#CURRENT_KEY} -gt 80 ]]; then
        echo -e "${YELLOW}Warning: API key is longer than expected (${#CURRENT_KEY} chars)${NC}"
        echo "Double-check that it's correct."
    fi
fi

echo ""
echo -e "${BLUE}To test your configuration:${NC}"
echo "  1. Source the config: source $CONFIG_FILE"
echo "  2. Test OpenRouter connection:"
echo "     curl -H \"Authorization: Bearer \$OPENROUTER_API_KEY\" \\"
echo "          https://openrouter.ai/api/v1/models | jq '.data[0]'"
echo ""
