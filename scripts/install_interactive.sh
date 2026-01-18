#!/usr/bin/env bash
#
# install_interactive.sh - Multi-module interactive installer for ninja-mcp
#
# Usage: ./scripts/install_interactive.sh
#

set -euo pipefail

# Colors and formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Unicode characters
CHECK="✓"
CROSS="✗"
ARROW="→"
BULLET="•"

# Helper functions
print_header() {
    echo ""
    echo -e "${BOLD}${MAGENTA}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
    echo -e "${BOLD}${MAGENTA}║${NC}              ${CYAN}${BOLD}🥷 NINJA MCP INSTALLER${NC}                ${BOLD}${MAGENTA}║${NC}"
    echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
    echo -e "${BOLD}${MAGENTA}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

info() {
    echo -e "${BLUE}${BULLET}${NC} $1"
}

success() {
    echo -e "${GREEN}${CHECK}${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

error() {
    echo -e "${RED}${CROSS}${NC} $1"
    exit 1
}

step() {
    echo ""
    echo -e "${BOLD}${CYAN}${ARROW} $1${NC}"
    echo -e "${DIM}─────────────────────────────────────────────────────────${NC}"
}

prompt() {
    echo -ne "${CYAN}?${NC} ${BOLD}$1${NC} "
}

prompt_secret() {
    echo -ne "${CYAN}?${NC} ${BOLD}$1${NC} " >&2
    read -s value
    echo "" >&2
    echo "$value"
}

confirm() {
    local prompt="$1"
    local default="${2:-N}"  # Default to N if not specified

    if [[ "$default" == "Y" ]]; then
        echo -ne "${CYAN}?${NC} ${BOLD}${prompt}${NC} ${DIM}[Y/n]${NC} " >&2
    else
        echo -ne "${CYAN}?${NC} ${BOLD}${prompt}${NC} ${DIM}[y/N]${NC} " >&2
    fi

    read -r response

    # If empty, use default
    if [[ -z "$response" ]]; then
        [[ "$default" == "Y" ]]
    else
        [[ "$response" =~ ^[Yy]$ ]]
    fi
}

# Validate model exists in OpenRouter
validate_openrouter_model() {
    local model_name="$1"
    local api_key="$2"

    if [[ -z "$api_key" ]]; then
        warn "Cannot validate model (no API key yet)"
        return 0  # Accept without validation
    fi

    # Query OpenRouter models API
    local response
    response=$(curl -s https://openrouter.ai/api/v1/models \
        -H "Authorization: Bearer $api_key" \
        -H "Content-Type: application/json" 2>/dev/null)

    if echo "$response" | grep -q "\"id\".*\"$model_name\""; then
        return 0  # Model found
    else
        return 1  # Model not found
    fi
}

# Portable alternative to mapfile (bash 3.2+ compatible)
# Usage: read_array ARRAY_NAME < <(command)
read_array() {
    local array_name=$1
    local -a lines
    while IFS= read -r line; do
        lines+=("$line")
    done
    eval "$array_name=(\"\${lines[@]}\")"
}

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Source shared Claude config utilities
source "$SCRIPT_DIR/lib/claude_config.sh"

# Configuration file
CONFIG_FILE="$HOME/.ninja-mcp.env"

# Print header
clear
print_header

echo -e "${DIM}Welcome! This installer will help you set up Ninja MCP modules:${NC}"
echo -e "${DIM}  • Coder - AI code execution via aider${NC}"
echo -e "${DIM}  • Researcher - Web search & reports generation${NC}"
echo -e "${DIM}  • Secretary - Documentation & codebase exploration${NC}"
echo ""

# Step 1: Module selection
step "Step 1: Select modules to install"

echo ""
echo -e "${DIM}Select which modules you want to install:${NC}"
echo ""

INSTALL_CODER=true
INSTALL_RESEARCHER=true
INSTALL_SECRETARY=true

echo -e "  ${BOLD}1.${NC} Coder ${DIM}(AI code execution - recommended)${NC}"
if confirm "Install Coder module?" "Y"; then
    INSTALL_CODER=true
    success "Coder module selected"
else
    INSTALL_CODER=false
    info "Coder module skipped"
fi

echo ""
echo -e "  ${BOLD}2.${NC} Researcher ${DIM}(Web search & reports)${NC}"
if confirm "Install Researcher module?" "Y"; then
    INSTALL_RESEARCHER=true
    success "Researcher module selected"
else
    INSTALL_RESEARCHER=false
    info "Researcher module skipped"
fi

echo ""
echo -e "  ${BOLD}3.${NC} Secretary ${DIM}(Documentation & codebase exploration)${NC}"
if confirm "Install Secretary module?" "Y"; then
    INSTALL_SECRETARY=true
    success "Secretary module selected"
else
    INSTALL_SECRETARY=false
    info "Secretary module skipped"
fi

echo ""
echo -e "${BOLD}Selected modules:${NC}"
[[ "$INSTALL_CODER" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Coder"
[[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Researcher"
[[ "$INSTALL_SECRETARY" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Secretary"

# Step 2: Check dependencies
step "Step 2: Checking dependencies"

# Check Python
info "Checking Python version..."

PYTHON_CMD=""
PYTHON_VERSION=""

if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
    PYTHON_VERSION=$(python3.12 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
    PYTHON_VERSION=$(python3.11 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if [[ "$PYTHON_MAJOR" -ge 3 ]] && [[ "$PYTHON_MINOR" -ge 11 ]]; then
        PYTHON_CMD="python3"
    fi
fi

if [[ -z "$PYTHON_CMD" ]]; then
    error "Python 3.11+ is required"
fi

success "Python $PYTHON_VERSION"

# Check uv
info "Checking for uv package manager..."
if command -v uv &> /dev/null; then
    UV_VERSION=$(uv --version 2>/dev/null | head -n1 | cut -d' ' -f2)
    success "uv $UV_VERSION"
else
    warn "uv not found"
    if confirm "Would you like to install uv now?"; then
        info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
        if command -v uv &> /dev/null; then
            success "uv installed successfully"
        else
            error "Failed to install uv"
        fi
    else
        error "uv is required. Install from: https://docs.astral.sh/uv/"
    fi
fi

# Step 3: Install dependencies
step "Step 3: Installing dependencies"

export UV_PYTHON="$PYTHON_CMD"

# Build extras list based on selected modules
# Build uv sync command with separate --extra flags (uv doesn't accept comma-separated extras)
SYNC_CMD="uv sync --python \"$PYTHON_CMD\""
EXTRAS_LIST=()
[[ "$INSTALL_CODER" == "true" ]] && EXTRAS_LIST+=("coder") && SYNC_CMD="$SYNC_CMD --extra coder"
[[ "$INSTALL_RESEARCHER" == "true" ]] && EXTRAS_LIST+=("researcher") && SYNC_CMD="$SYNC_CMD --extra researcher"
[[ "$INSTALL_SECRETARY" == "true" ]] && EXTRAS_LIST+=("secretary") && SYNC_CMD="$SYNC_CMD --extra secretary"

if [[ ${#EXTRAS_LIST[@]} -gt 0 ]]; then
    EXTRAS_DISPLAY=$(IFS=,; echo "${EXTRAS_LIST[*]}")
    info "Installing modules: $EXTRAS_DISPLAY"
    eval "$SYNC_CMD" 2>&1 | grep -v "already satisfied" || true
    success "Modules installed"
else
    info "Installing base dependencies only"
    eval "$SYNC_CMD" 2>&1 | grep -v "already satisfied" || true
    success "Base dependencies installed"
fi

# Step 4: Configure API keys
step "Step 4: Configuring API keys"

echo ""
echo -e "${DIM}Configure API keys for the selected modules:${NC}"
echo ""

# OpenRouter API key (for Coder)
OPENROUTER_KEY=""
if [[ "$INSTALL_CODER" == "true" ]]; then
    echo -e "${BOLD}OpenRouter API Key${NC} ${DIM}(required for Coder)${NC}"
    echo -e "${DIM}Get your key from: ${CYAN}https://openrouter.ai/keys${NC}"
    echo ""
    
    EXISTING_KEY="${OPENROUTER_API_KEY:-${OPENAI_API_KEY:-}}"
    if [[ -n "$EXISTING_KEY" ]]; then
        MASKED_KEY="${EXISTING_KEY:0:8}...${EXISTING_KEY: -4}"
        info "Found existing API key: $MASKED_KEY"
        if confirm "Use existing key?"; then
            OPENROUTER_KEY="$EXISTING_KEY"
            success "Using existing OpenRouter key"
        else
            OPENROUTER_KEY=$(prompt_secret "Enter OpenRouter API key:")
        fi
    else
        OPENROUTER_KEY=$(prompt_secret "Enter OpenRouter API key:")
    fi
fi

# Search engine selection (for Researcher)
SEARCH_PROVIDER="duckduckgo"
SERPER_KEY=""
PERPLEXITY_KEY=""
if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
    echo ""
    echo -e "${BOLD}Search Engine Selection${NC} ${DIM}(for Researcher module)${NC}"
    echo -e "${DIM}Choose your preferred search provider:${NC}"
    echo ""
    echo -e "  ${BOLD}1.${NC} DuckDuckGo ${DIM}(free, no API key required)${NC}"
    echo -e "  ${BOLD}2.${NC} Serper.dev ${DIM}(Google Search, requires API key)${NC}"
    echo -e "  ${BOLD}3.${NC} Perplexity AI ${DIM}(AI-powered search, requires API key)${NC}"
    echo ""

    prompt "Search provider [1-3] (default: 1):"
    read -r search_choice
    search_choice="${search_choice:-1}"

    case "$search_choice" in
        1)
            SEARCH_PROVIDER="duckduckgo"
            success "Selected: DuckDuckGo (free)"
            ;;
        2)
            SEARCH_PROVIDER="serper"
            echo ""
            echo -e "${BOLD}Serper.dev API Key${NC}"
            echo -e "${DIM}Get your key from: ${CYAN}https://serper.dev${NC}"
            echo -e "${DIM}Free tier: 2,500 searches/month${NC}"
            echo ""

            EXISTING_SERPER="${SERPER_API_KEY:-}"
            if [[ -n "$EXISTING_SERPER" ]]; then
                MASKED_SERPER="${EXISTING_SERPER:0:8}...${EXISTING_SERPER: -4}"
                info "Found existing Serper key: $MASKED_SERPER"
                if confirm "Use existing key?"; then
                    SERPER_KEY="$EXISTING_SERPER"
                    success "Using existing Serper key"
                else
                    SERPER_KEY=$(prompt_secret "Enter Serper API key:")
                    success "Serper key configured"
                fi
            else
                SERPER_KEY=$(prompt_secret "Enter Serper API key:")
                success "Serper key configured"
            fi
            ;;
        3)
            SEARCH_PROVIDER="perplexity"
            echo ""
            echo -e "${BOLD}Perplexity AI API Key${NC}"
            echo -e "${DIM}Get your key from: ${CYAN}https://www.perplexity.ai/settings/api${NC}"
            echo ""

            EXISTING_PERPLEXITY="${PERPLEXITY_API_KEY:-}"
            if [[ -n "$EXISTING_PERPLEXITY" ]]; then
                MASKED_PERPLEXITY="${EXISTING_PERPLEXITY:0:8}...${EXISTING_PERPLEXITY: -4}"
                info "Found existing Perplexity key: $MASKED_PERPLEXITY"
                if confirm "Use existing key?"; then
                    PERPLEXITY_KEY="$EXISTING_PERPLEXITY"
                    success "Using existing Perplexity key"
                else
                    PERPLEXITY_KEY=$(prompt_secret "Enter Perplexity API key:")
                    success "Perplexity key configured"
                fi
            else
                PERPLEXITY_KEY=$(prompt_secret "Enter Perplexity API key:")
                success "Perplexity key configured"
            fi
            ;;
        *)
            warn "Invalid choice, defaulting to DuckDuckGo"
            SEARCH_PROVIDER="duckduckgo"
            ;;
    esac
fi

# Step 5: Model selection
step "Step 5: Selecting AI models"

echo ""
echo -e "${DIM}Choose models for each module:${NC}"
echo ""

# Coder model
CODER_MODEL=""
if [[ "$INSTALL_CODER" == "true" ]]; then
    echo -e "${BOLD}Coder Module Model:${NC}"
    echo -e "${DIM}Fetching top coding models from LiveBench...${NC}"

    # Fetch recommendations dynamically
    CODER_MODELS_JSON=$($PYTHON_CMD "$SCRIPT_DIR/get_recommended_models.py" coder 2>/dev/null)

    if [[ -n "$CODER_MODELS_JSON" ]] && echo "$CODER_MODELS_JSON" | grep -q "name"; then
        # Parse JSON and display options (using portable read_array instead of mapfile)
        read_array MODEL_NAMES < <(echo "$CODER_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(m['name']) for m in data[:7]]")
        read_array MODEL_TIERS < <(echo "$CODER_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(m.get('tier', '')) for m in data[:7]]")
        read_array MODEL_PRICES < <(echo "$CODER_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(f\"\${m['price']:.2f}/1M\") for m in data[:7]]")
        read_array MODEL_SPEEDS < <(echo "$CODER_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(m['speed']) for m in data[:7]]")

        echo ""
        for i in "${!MODEL_NAMES[@]}"; do
            idx=$((i+1))
            model_name="${MODEL_NAMES[$i]}"
            tier="${MODEL_TIERS[$i]}"
            price="${MODEL_PRICES[$i]}"
            speed="${MODEL_SPEEDS[$i]}"
            echo -e "  ${BOLD}${idx}.${NC} ${model_name} ${DIM}${tier} | ${price} | ${speed}${NC}"
        done
    else
        # Fallback to hardcoded list
        MODEL_NAMES=("qwen/qwen-2.5-coder-32b-instruct" "anthropic/claude-sonnet-4" "google/gemini-2.0-flash-exp" "anthropic/claude-haiku-4.5-20250929" "openai/gpt-4o" "deepseek/deepseek-chat" "openai/gpt-4o-mini")
        echo ""
        echo -e "  ${BOLD}1.${NC} qwen/qwen-2.5-coder-32b-instruct ${DIM}💰 Budget | \$0.30/1M | 🚀 Fast${NC}"
        echo -e "  ${BOLD}2.${NC} anthropic/claude-sonnet-4 ${DIM}🎯 Quality | \$3.00/1M | ⚖️ Balanced${NC}"
        echo -e "  ${BOLD}3.${NC} google/gemini-2.0-flash-exp ${DIM}⚡ Speed | \$0.08/1M | ⚡ Very Fast${NC}"
        echo -e "  ${BOLD}4.${NC} anthropic/claude-haiku-4.5-20250929 ${DIM}🏆 Recommended | \$0.15/1M | ⚡ Very Fast${NC}"
        echo -e "  ${BOLD}5.${NC} openai/gpt-4o ${DIM}⚖️ Balanced | \$3.00/1M | ⚖️ Balanced${NC}"
        echo -e "  ${BOLD}6.${NC} deepseek/deepseek-chat ${DIM}💰 Budget | \$0.14/1M | 🚀 Fast${NC}"
        echo -e "  ${BOLD}7.${NC} openai/gpt-4o-mini ${DIM}⚡ Speed | \$0.15/1M | ⚡ Very Fast${NC}"
    fi

    echo ""
    echo -e "${DIM}Enter a number (1-${#MODEL_NAMES[@]}) or paste a model name (e.g., anthropic/claude-opus-4)${NC}"

    # Loop until valid model is selected
    while true; do
        prompt "Model choice (default: 1):"
        read -r model_choice
        model_choice=${model_choice:-1}  # Default to 1 if empty

        # Check if input is a number
        if [[ "$model_choice" =~ ^[0-9]+$ ]]; then
            # It's a number - validate range
            idx=$((model_choice-1))
            if [[ "$idx" -ge 0 ]] && [[ "$idx" -lt "${#MODEL_NAMES[@]}" ]]; then
                CODER_MODEL="${MODEL_NAMES[$idx]}"
                break
            else
                error "Invalid choice. Please enter 1-${#MODEL_NAMES[@]} or a model name."
            fi
        else
            # It's a model name - validate with OpenRouter
            info "Validating model: $model_choice"
            if validate_openrouter_model "$model_choice" "$OPENROUTER_KEY"; then
                CODER_MODEL="$model_choice"
                success "Model validated"
                break
            else
                error "Model '$model_choice' not found in OpenRouter"
                echo -e "${DIM}Check available models at: ${CYAN}https://openrouter.ai/models${NC}"
            fi
        fi
    done

    success "Coder model: $CODER_MODEL"
fi

# Researcher model
RESEARCHER_MODEL=""
if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
    echo ""
    echo -e "${BOLD}Researcher Module Model:${NC}"
    echo -e "${DIM}Fetching top research models...${NC}"

    # Fetch recommendations
    RESEARCHER_MODELS_JSON=$($PYTHON_CMD "$SCRIPT_DIR/get_recommended_models.py" researcher 2>/dev/null)

    if [[ -n "$RESEARCHER_MODELS_JSON" ]] && echo "$RESEARCHER_MODELS_JSON" | grep -q "name"; then
        read_array MODEL_NAMES < <(echo "$RESEARCHER_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(m['name']) for m in data[:5]]")
        read_array MODEL_TIERS < <(echo "$RESEARCHER_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(m.get('tier', '')) for m in data[:5]]")
        read_array MODEL_PRICES < <(echo "$RESEARCHER_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(f\"\${m['price']:.2f}/1M\") for m in data[:5]]")

        echo ""
        for i in "${!MODEL_NAMES[@]}"; do
            idx=$((i+1))
            echo -e "  ${BOLD}${idx}.${NC} ${MODEL_NAMES[$i]} ${DIM}${MODEL_TIERS[$i]} | ${MODEL_PRICES[$i]}${NC}"
        done
    else
        MODEL_NAMES=("anthropic/claude-sonnet-4" "openai/gpt-4o" "google/gemini-2.0-flash-exp" "anthropic/claude-sonnet-3.5" "deepseek/deepseek-chat")
        echo ""
        echo -e "  ${BOLD}1.${NC} anthropic/claude-sonnet-4 ${DIM}🏆 Recommended | \$3.00/1M${NC}"
        echo -e "  ${BOLD}2.${NC} openai/gpt-4o ${DIM}⚖️ Balanced | \$3.00/1M${NC}"
        echo -e "  ${BOLD}3.${NC} google/gemini-2.0-flash-exp ${DIM}⚡ Speed | \$0.08/1M${NC}"
        echo -e "  ${BOLD}4.${NC} anthropic/claude-sonnet-3.5 ${DIM}🎯 Quality | \$3.00/1M${NC}"
        echo -e "  ${BOLD}5.${NC} deepseek/deepseek-chat ${DIM}💰 Budget | \$0.14/1M${NC}"
    fi

    echo ""
    echo -e "${DIM}Enter a number (1-${#MODEL_NAMES[@]}) or paste a model name (e.g., anthropic/claude-opus-4)${NC}"

    # Loop until valid model is selected
    while true; do
        prompt "Model choice (default: 1):"
        read -r model_choice
        model_choice=${model_choice:-1}  # Default to 1 if empty

        # Check if input is a number
        if [[ "$model_choice" =~ ^[0-9]+$ ]]; then
            # It's a number - validate range
            idx=$((model_choice-1))
            if [[ "$idx" -ge 0 ]] && [[ "$idx" -lt "${#MODEL_NAMES[@]}" ]]; then
                RESEARCHER_MODEL="${MODEL_NAMES[$idx]}"
                break
            else
                error "Invalid choice. Please enter 1-${#MODEL_NAMES[@]} or a model name."
            fi
        else
            # It's a model name - validate with OpenRouter
            info "Validating model: $model_choice"
            if validate_openrouter_model "$model_choice" "$OPENROUTER_KEY"; then
                RESEARCHER_MODEL="$model_choice"
                success "Model validated"
                break
            else
                error "Model '$model_choice' not found in OpenRouter"
                echo -e "${DIM}Check available models at: ${CYAN}https://openrouter.ai/models${NC}"
            fi
        fi
    done

    success "Researcher model: $RESEARCHER_MODEL"
fi

# Secretary model
SECRETARY_MODEL=""
if [[ "$INSTALL_SECRETARY" == "true" ]]; then
    echo ""
    echo -e "${BOLD}Secretary Module Model:${NC}"
    echo -e "${DIM}Fetching fast summary models...${NC}"

    # Fetch recommendations
    SECRETARY_MODELS_JSON=$($PYTHON_CMD "$SCRIPT_DIR/get_recommended_models.py" secretary 2>/dev/null)

    if [[ -n "$SECRETARY_MODELS_JSON" ]] && echo "$SECRETARY_MODELS_JSON" | grep -q "name"; then
        read_array MODEL_NAMES < <(echo "$SECRETARY_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(m['name']) for m in data[:5]]")
        read_array MODEL_TIERS < <(echo "$SECRETARY_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(m.get('tier', '')) for m in data[:5]]")
        read_array MODEL_PRICES < <(echo "$SECRETARY_MODELS_JSON" | $PYTHON_CMD -c "import sys, json; data=json.load(sys.stdin); [print(f\"\${m['price']:.2f}/1M\") for m in data[:5]]")

        echo ""
        for i in "${!MODEL_NAMES[@]}"; do
            idx=$((i+1))
            echo -e "  ${BOLD}${idx}.${NC} ${MODEL_NAMES[$i]} ${DIM}${MODEL_TIERS[$i]} | ${MODEL_PRICES[$i]}${NC}"
        done
    else
        MODEL_NAMES=("google/gemini-2.0-flash-exp" "anthropic/claude-haiku-4.5-20250929" "openai/gpt-4o-mini" "qwen/qwen-2.5-coder-32b-instruct" "deepseek/deepseek-chat")
        echo ""
        echo -e "  ${BOLD}1.${NC} google/gemini-2.0-flash-exp ${DIM}🏆 Recommended | \$0.08/1M | ⚡ Very Fast${NC}"
        echo -e "  ${BOLD}2.${NC} anthropic/claude-haiku-4.5-20250929 ${DIM}⚡ Speed | \$0.15/1M | ⚡ Very Fast${NC}"
        echo -e "  ${BOLD}3.${NC} openai/gpt-4o-mini ${DIM}💰 Budget | \$0.15/1M | ⚡ Very Fast${NC}"
        echo -e "  ${BOLD}4.${NC} qwen/qwen-2.5-coder-32b-instruct ${DIM}⚖️ Balanced | \$0.30/1M | 🚀 Fast${NC}"
        echo -e "  ${BOLD}5.${NC} deepseek/deepseek-chat ${DIM}💰 Budget | \$0.14/1M | 🚀 Fast${NC}"
    fi

    echo ""
    echo -e "${DIM}Enter a number (1-${#MODEL_NAMES[@]}) or paste a model name (e.g., google/gemini-exp-1206)${NC}"

    # Loop until valid model is selected
    while true; do
        prompt "Model choice (default: 1):"
        read -r model_choice
        model_choice=${model_choice:-1}  # Default to 1 if empty

        # Check if input is a number
        if [[ "$model_choice" =~ ^[0-9]+$ ]]; then
            # It's a number - validate range
            idx=$((model_choice-1))
            if [[ "$idx" -ge 0 ]] && [[ "$idx" -lt "${#MODEL_NAMES[@]}" ]]; then
                SECRETARY_MODEL="${MODEL_NAMES[$idx]}"
                break
            else
                error "Invalid choice. Please enter 1-${#MODEL_NAMES[@]} or a model name."
            fi
        else
            # It's a model name - validate with OpenRouter
            info "Validating model: $model_choice"
            if validate_openrouter_model "$model_choice" "$OPENROUTER_KEY"; then
                SECRETARY_MODEL="$model_choice"
                success "Model validated"
                break
            else
                error "Model '$model_choice' not found in OpenRouter"
                echo -e "${DIM}Check available models at: ${CYAN}https://openrouter.ai/models${NC}"
            fi
        fi
    done

    success "Secretary model: $SECRETARY_MODEL"
fi

# Step 6: AI Code CLI (for Coder module)
NINJA_CODE_BIN=""
if [[ "$INSTALL_CODER" == "true" ]]; then
    step "Step 6: Configuring AI Code CLI (for Coder)"
    
    echo ""
    echo -e "${DIM}Scanning for AI code assistants...${NC}"
    echo ""
    
    DETECTED_CLIS=()
    
    # Check for aider
    if command -v aider &> /dev/null; then
        AIDER_PATH=$(command -v aider)
        DETECTED_CLIS+=("aider|$AIDER_PATH")
        info "Found: aider at $AIDER_PATH"
    fi
    
    # Check for cursor
    if command -v cursor &> /dev/null; then
        CURSOR_PATH=$(command -v cursor)
        if [[ "$CURSOR_PATH" == *".cursor"* ]] || cursor --version 2>&1 | grep -iq "cursor"; then
            DETECTED_CLIS+=("cursor|$CURSOR_PATH")
            info "Found: cursor at $CURSOR_PATH"
        fi
    fi

    # Check for opencode
    if command -v opencode &> /dev/null; then
        OPENCODE_PATH=$(command -v opencode)
        DETECTED_CLIS+=("opencode|$OPENCODE_PATH")
        info "Found: opencode at $OPENCODE_PATH"
    fi

    echo ""
    
    if [[ ${#DETECTED_CLIS[@]} -gt 0 ]]; then
        success "Found ${#DETECTED_CLIS[@]} AI code assistant(s)"
        echo ""
        echo -e "${DIM}Select an AI code assistant:${NC}"
        echo ""
        
        idx=1
        for cli_entry in "${DETECTED_CLIS[@]}"; do
            cli_name=$(echo "$cli_entry" | cut -d'|' -f1)
            cli_path=$(echo "$cli_entry" | cut -d'|' -f2)
            echo -e "  ${BOLD}${idx}.${NC} ${cli_name} ${DIM}(${cli_path})${NC}"
            ((idx++))
        done
        echo -e "  ${BOLD}${idx}.${NC} Enter custom path"
        echo ""
        
        prompt "Enter choice [1-${idx}] (default: 1):"
        read -r cli_choice
        cli_choice="${cli_choice:-1}"
        
        if [[ "$cli_choice" -ge 1 ]] && [[ "$cli_choice" -lt "$idx" ]]; then
            selected_entry="${DETECTED_CLIS[$((cli_choice-1))]}"
            NINJA_CODE_BIN=$(echo "$selected_entry" | cut -d'|' -f2)
            success "Selected: $NINJA_CODE_BIN"
        else
            prompt "Enter path to AI code CLI:"
            read -r NINJA_CODE_BIN
        fi
    else
        warn "No AI code assistants detected"
        echo ""
        echo -e "${DIM}Aider is the recommended AI coding assistant for Ninja Coder.${NC}"
        echo -e "${DIM}It integrates with OpenRouter and supports multiple AI models.${NC}"
        echo ""

        if confirm "Install aider-chat now?"; then
            info "Installing aider-chat via uv..."
            if uv tool install aider-chat 2>&1 | grep -v "already satisfied"; then
                success "Aider installed successfully"

                # Check if aider is in PATH
                if command -v aider &> /dev/null; then
                    NINJA_CODE_BIN=$(command -v aider)
                    success "Found aider at: $NINJA_CODE_BIN"
                else
                    # Try common uv tool install location
                    if [[ -f "$HOME/.local/bin/aider" ]]; then
                        NINJA_CODE_BIN="$HOME/.local/bin/aider"
                        success "Found aider at: $NINJA_CODE_BIN"
                    else
                        NINJA_CODE_BIN="aider"
                        warn "Aider installed but not in PATH. Using 'aider' (may need to add to PATH)"
                    fi
                fi
            else
                error "Failed to install aider. Please install manually: uv tool install aider-chat"
            fi
        else
            info "Skipping aider installation"
            echo ""
            prompt "Enter path to AI code CLI (or press Enter for 'aider'):"
            read -r NINJA_CODE_BIN
            NINJA_CODE_BIN="${NINJA_CODE_BIN:-aider}"
        fi
    fi
fi

# Step 7: Daemon configuration
step "Step 7: Daemon configuration"

echo ""
ENABLE_DAEMON=false
if confirm "Run modules as daemons (background processes)?"; then
    ENABLE_DAEMON=true
    success "Daemon mode enabled"
else
    info "Daemon mode disabled (will run in foreground)"
fi

# Step 8: Save configuration
step "Step 8: Saving configuration"

echo ""
info "Creating configuration file at: $CONFIG_FILE"

cat > "$CONFIG_FILE" << EOF
# Ninja MCP Configuration
# Generated on $(date)

# ============================================================================
# Common Configuration
# ============================================================================

# OpenRouter API Key (for Coder and Researcher)
export OPENROUTER_API_KEY='$OPENROUTER_KEY'

EOF

if [[ "$INSTALL_CODER" == "true" ]]; then
    cat >> "$CONFIG_FILE" << EOF
# ============================================================================
# Coder Module
# ============================================================================

# Coder model
export NINJA_CODER_MODEL='$CODER_MODEL'

# AI Code CLI binary
export NINJA_CODE_BIN='$NINJA_CODE_BIN'

# Coder timeout (seconds)
export NINJA_CODER_TIMEOUT=600

EOF
fi

if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
    cat >> "$CONFIG_FILE" << EOF
# ============================================================================
# Researcher Module
# ============================================================================

# Researcher model
export NINJA_RESEARCHER_MODEL='$RESEARCHER_MODEL'

# Search provider (duckduckgo, serper, perplexity)
export NINJA_SEARCH_PROVIDER='$SEARCH_PROVIDER'

# Serper.dev API key (for Google Search)
export SERPER_API_KEY='$SERPER_KEY'

# Perplexity AI API key (for AI-powered search)
export PERPLEXITY_API_KEY='$PERPLEXITY_KEY'

# Max sources per research
export NINJA_RESEARCHER_MAX_SOURCES=20

# Parallel research agents
export NINJA_RESEARCHER_PARALLEL_AGENTS=4

EOF
fi

if [[ "$INSTALL_SECRETARY" == "true" ]]; then
    cat >> "$CONFIG_FILE" << EOF
# ============================================================================
# Secretary Module
# ============================================================================

# Secretary model
export NINJA_SECRETARY_MODEL='$SECRETARY_MODEL'

# Max file size to analyze (bytes)
export NINJA_SECRETARY_MAX_FILE_SIZE=1048576

# Cache directory
export NINJA_SECRETARY_CACHE_DIR=~/.cache/ninja-secretary

EOF
fi

chmod 600 "$CONFIG_FILE"
success "Configuration saved"

# Step 9: IDE Integration
step "Step 9: IDE Integration"

echo ""
echo -e "${DIM}Checking for supported IDEs...${NC}"
echo ""

CLAUDE_INSTALLED=false
if command -v claude &> /dev/null; then
    success "Claude Code CLI found"
    CLAUDE_INSTALLED=true
fi

VSCODE_INSTALLED=false
if command -v code &> /dev/null; then
    success "VS Code found"
    VSCODE_INSTALLED=true
fi

ZED_INSTALLED=false
if command -v zed &> /dev/null || [[ -d "$HOME/.config/zed" ]]; then
    success "Zed found"
    ZED_INSTALLED=true
fi

OPENCODE_INSTALLED=false
if command -v opencode &> /dev/null || [[ -f "$HOME/.opencode.json" ]] || [[ -f "$HOME/.config/opencode/.opencode.json" ]]; then
    success "OpenCode found"
    OPENCODE_INSTALLED=true
fi

echo ""
echo -e "${BOLD}Register with IDEs:${NC}"
echo ""

# Claude Code
if [[ "$CLAUDE_INSTALLED" == "true" ]]; then
    if confirm "Register modules with Claude Code?"; then
        info "Registering with Claude Code..."

        # Detect and initialize Claude Code config location
        CLAUDE_MCP_CONFIG=$(detect_claude_mcp_config)
        info "Using config: $CLAUDE_MCP_CONFIG"
        init_claude_mcp_config "$CLAUDE_MCP_CONFIG"

        # Check if migration is needed
        check_config_migration

        if [[ -f "$CLAUDE_MCP_CONFIG" ]]; then
            info "Backing up existing Claude config..."
            cp "$CLAUDE_MCP_CONFIG" "$CLAUDE_MCP_CONFIG.backup.$(date +%s)"
        fi
        
        # Build MCP config
        cat > "$CLAUDE_MCP_CONFIG" << 'EOF'
{
  "mcpServers": {
EOF
        
        if [[ "$INSTALL_CODER" == "true" ]]; then
            cat >> "$CLAUDE_MCP_CONFIG" << 'EOF'
    "ninja-coder": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_coder.server"]
    },
EOF
        fi
        
        if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
            cat >> "$CLAUDE_MCP_CONFIG" << 'EOF'
    "ninja-researcher": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_researcher.server"]
    },
EOF
        fi
        
        if [[ "$INSTALL_SECRETARY" == "true" ]]; then
            cat >> "$CLAUDE_MCP_CONFIG" << 'EOF'
    "ninja-secretary": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_secretary.server"]
    },
EOF
        fi
        
        # Remove trailing comma and close JSON
        cat >> "$CLAUDE_MCP_CONFIG" << 'EOF'
  }
}
EOF
        
        # Fix trailing comma issue
        sed -i.tmp 's/},$/}/g' "$CLAUDE_MCP_CONFIG" 2>/dev/null || sed -i '' 's/},$/}/g' "$CLAUDE_MCP_CONFIG" 2>/dev/null || true
        rm -f "$CLAUDE_MCP_CONFIG.tmp"
        
        success "Registered with Claude Code"
    fi
fi

# VS Code
if [[ "$VSCODE_INSTALLED" == "true" ]]; then
    if confirm "Register modules with VS Code (GitHub Copilot)?"; then
        info "Configuring VS Code native MCP for Copilot..."

        # Create global MCP config
        VSCODE_MCP_DIR="$HOME/.vscode/mcp"
        mkdir -p "$VSCODE_MCP_DIR"
        VSCODE_MCP_CONFIG="$VSCODE_MCP_DIR/mcp.json"

        if [[ -f "$VSCODE_MCP_CONFIG" ]]; then
            info "Backing up existing MCP config..."
            cp "$VSCODE_MCP_CONFIG" "$VSCODE_MCP_CONFIG.backup"
        fi

        # Build MCP config
        cat > "$VSCODE_MCP_CONFIG" << 'EOF'
{
  "inputs": [],
  "servers": {
EOF

        FIRST_ENTRY=true

        if [[ "$INSTALL_CODER" == "true" ]]; then
            [[ "$FIRST_ENTRY" == "false" ]] && echo "," >> "$VSCODE_MCP_CONFIG"
            cat >> "$VSCODE_MCP_CONFIG" << EOF
    "ninja-coder": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "$PROJECT_ROOT", "run", "python", "-m", "ninja_coder.server"],
      "env": {
        "OPENROUTER_API_KEY": "$OPENROUTER_KEY",
        "NINJA_CODER_MODEL": "$CODER_MODEL",
        "NINJA_CODE_BIN": "$NINJA_CODE_BIN"
      }
    }
EOF
            FIRST_ENTRY=false
        fi

        if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
            [[ "$FIRST_ENTRY" == "false" ]] && echo "," >> "$VSCODE_MCP_CONFIG"
            cat >> "$VSCODE_MCP_CONFIG" << EOF
    "ninja-researcher": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "$PROJECT_ROOT", "run", "python", "-m", "ninja_researcher.server"],
      "env": {
        "OPENROUTER_API_KEY": "$OPENROUTER_KEY",
        "NINJA_RESEARCHER_MODEL": "$RESEARCHER_MODEL"$([ -n "$SERPER_KEY" ] && echo ",
        \"SERPER_API_KEY\": \"$SERPER_KEY\"" || echo "")
      }
    }
EOF
            FIRST_ENTRY=false
        fi

        if [[ "$INSTALL_SECRETARY" == "true" ]]; then
            [[ "$FIRST_ENTRY" == "false" ]] && echo "," >> "$VSCODE_MCP_CONFIG"
            cat >> "$VSCODE_MCP_CONFIG" << EOF
    "ninja-secretary": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "$PROJECT_ROOT", "run", "python", "-m", "ninja_secretary.server"],
      "env": {
        "OPENROUTER_API_KEY": "$OPENROUTER_KEY",
        "NINJA_SECRETARY_MODEL": "$SECRETARY_MODEL"
      }
    }
EOF
            FIRST_ENTRY=false
        fi

        echo "" >> "$VSCODE_MCP_CONFIG"
        echo "  }" >> "$VSCODE_MCP_CONFIG"
        echo "}" >> "$VSCODE_MCP_CONFIG"

        success "Registered with VS Code (Copilot)"
        echo ""
        info "How to use in VS Code:"
        echo -e "${DIM}  1. Open Copilot Chat${NC}"
        echo -e "${DIM}  2. Use @agent to activate agent mode${NC}"
        echo -e "${DIM}  3. MCP tools will be available in context${NC}"
    fi
fi

# Zed
if [[ "$ZED_INSTALLED" == "true" ]]; then
    if confirm "Register modules with Zed editor?"; then
        info "Registering with Zed..."

        ZED_CONFIG="$HOME/.config/zed/settings.json"

        if [[ ! -f "$ZED_CONFIG" ]]; then
            info "Creating Zed settings file..."
            mkdir -p "$HOME/.config/zed"
            echo "{}" > "$ZED_CONFIG"
        fi

        # Backup existing config
        cp "$ZED_CONFIG" "$ZED_CONFIG.backup"

        # Read existing config and merge
        TEMP_CONFIG=$(mktemp)

        # Use Python to merge JSON (safer than jq)
        cat > "$TEMP_CONFIG" << 'PYTHON_SCRIPT'
import json
import sys

# Read existing config
try:
    with open(sys.argv[1], 'r') as f:
        config = json.load(f)
except:
    config = {}

# Ensure context_servers exists
if 'context_servers' not in config:
    config['context_servers'] = {}

# Add ninja servers
PYTHON_SCRIPT

        if [[ "$INSTALL_CODER" == "true" ]]; then
            cat >> "$TEMP_CONFIG" << PYTHON_SCRIPT
config['context_servers']['ninja-coder'] = {
    "command": "uv",
    "args": ["--directory", "$PROJECT_ROOT", "run", "python", "-m", "ninja_coder.server"],
    "env": {
        "OPENROUTER_API_KEY": "$OPENROUTER_KEY",
        "NINJA_CODER_MODEL": "$CODER_MODEL",
        "NINJA_CODE_BIN": "$NINJA_CODE_BIN"
    }
}
PYTHON_SCRIPT
        fi

        if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
            cat >> "$TEMP_CONFIG" << PYTHON_SCRIPT
config['context_servers']['ninja-researcher'] = {
    "command": "uv",
    "args": ["--directory", "$PROJECT_ROOT", "run", "python", "-m", "ninja_researcher.server"],
    "env": {
        "OPENROUTER_API_KEY": "$OPENROUTER_KEY",
        "NINJA_RESEARCHER_MODEL": "$RESEARCHER_MODEL"$([ -n "$SERPER_KEY" ] && echo ",
        \"SERPER_API_KEY\": \"$SERPER_KEY\"" || echo "")
    }
}
PYTHON_SCRIPT
        fi

        if [[ "$INSTALL_SECRETARY" == "true" ]]; then
            cat >> "$TEMP_CONFIG" << PYTHON_SCRIPT
config['context_servers']['ninja-secretary'] = {
    "command": "uv",
    "args": ["--directory", "$PROJECT_ROOT", "run", "python", "-m", "ninja_secretary.server"],
    "env": {
        "OPENROUTER_API_KEY": "$OPENROUTER_KEY",
        "NINJA_SECRETARY_MODEL": "$SECRETARY_MODEL"
    }
}
PYTHON_SCRIPT
        fi

        cat >> "$TEMP_CONFIG" << 'PYTHON_SCRIPT'

# Write updated config
with open(sys.argv[1], 'w') as f:
    json.dump(config, f, indent=2)
PYTHON_SCRIPT

        $PYTHON_CMD "$TEMP_CONFIG" "$ZED_CONFIG"
        rm "$TEMP_CONFIG"

        success "Registered with Zed"
        info "Restart Zed to apply changes"
    fi
fi

# OpenCode
if [[ "$OPENCODE_INSTALLED" == "true" ]]; then
    if confirm "Register modules with OpenCode?"; then
        info "Registering with OpenCode..."

        # Detect OpenCode config location
        OPENCODE_CONFIG="$HOME/.opencode.json"
        [[ ! -f "$OPENCODE_CONFIG" ]] && OPENCODE_CONFIG="$HOME/.config/opencode/.opencode.json"

        # Create config directory if needed
        mkdir -p "$(dirname "$OPENCODE_CONFIG")"

        # Initialize config file if it doesn't exist
        if [[ ! -f "$OPENCODE_CONFIG" ]]; then
            info "Creating OpenCode config file..."
            echo '{}' > "$OPENCODE_CONFIG"
        fi

        info "Using config: $OPENCODE_CONFIG"

        # Backup existing config
        cp "$OPENCODE_CONFIG" "$OPENCODE_CONFIG.backup.$(date +%s)"

        # IMPORTANT: Manual registration required
        warn "⚠  IMPORTANT: Manual registration required"
        echo ""
        echo "OpenCode CLI does not support non-interactive MCP registration."
        echo "You must complete setup by running:"
        echo -e "  ${CYAN}opencode mcp add${NC}"
        echo ""
        echo "This will open an interactive interface where you can:"
        echo "  1. Select '\''Global'\' location (recommended)"
        echo "  2. Add each MCP server (ninja-coder, ninja-researcher, ninja-secretary)"
        echo "  3. Exit when done"
        echo ""
        echo "For detailed instructions, see:"
        echo -e "  ${CYAN}docs/OPENCODE_INTEGRATION.md${NC}"


        # Use Python to build MCP config (safer than manual JSON manipulation)
        TEMP_CONFIG=$(mktemp)
        cat > "$TEMP_CONFIG" << 'PYTHON_SCRIPT'
import json
import sys

# Read existing config
try:
    with open(sys.argv[1], 'r') as f:
        config = json.load(f)
except:
    config = {}

# Ensure mcpServers exists
if 'mcpServers' not in config:
    config['mcpServers'] = {}
PYTHON_SCRIPT

        # Add selected modules
        if [[ "$INSTALL_CODER" == "true" ]]; then
            cat >> "$TEMP_CONFIG" << PYTHON_SCRIPT
config['mcpServers']['ninja-coder'] = {
    "type": "stdio",
    "command": "uv",
    "args": ["--directory", "$PROJECT_ROOT", "run", "ninja-coder"],
    "env": [
        "OPENROUTER_API_KEY=$OPENROUTER_KEY",
        "NINJA_CODER_MODEL=$CODER_MODEL",
        "NINJA_CODE_BIN=$NINJA_CODE_BIN"
    ],
    "disabled": False
}
PYTHON_SCRIPT
        fi

        if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
            cat >> "$TEMP_CONFIG" << PYTHON_SCRIPT
config['mcpServers']['ninja-researcher'] = {
    "type": "stdio",
    "command": "uv",
    "args": ["--directory", "$PROJECT_ROOT", "run", "ninja-researcher"],
    "env": [
        "OPENROUTER_API_KEY=$OPENROUTER_KEY",
        "NINJA_RESEARCHER_MODEL=$RESEARCHER_MODEL"
    ],
    "disabled": False
}
PYTHON_SCRIPT
        fi

        if [[ "$INSTALL_SECRETARY" == "true" ]]; then
            cat >> "$TEMP_CONFIG" << PYTHON_SCRIPT
config['mcpServers']['ninja-secretary'] = {
    "type": "stdio",
    "command": "uv",
    "args": ["--directory", "$PROJECT_ROOT", "run", "ninja-secretary"],
    "env": [
        "NINJA_SECRETARY_MODEL=$SECRETARY_MODEL"
    ],
    "disabled": False
}
PYTHON_SCRIPT
        fi

        cat >> "$TEMP_CONFIG" << 'PYTHON_SCRIPT'

# Write updated config
with open(sys.argv[1], 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
PYTHON_SCRIPT

        $PYTHON_CMD "$TEMP_CONFIG" "$OPENCODE_CONFIG"
        rm "$TEMP_CONFIG"

        info "Run 'opencode mcp list' to verify"
    fi
fi

# Step 10: Final summary
echo ""
echo -e "${BOLD}${MAGENTA}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
echo -e "${BOLD}${MAGENTA}║${NC}            ${GREEN}${BOLD}${CHECK} Installation Complete!${NC}                 ${BOLD}${MAGENTA}║${NC}"
echo -e "${BOLD}${MAGENTA}║                                                          ║${NC}"
echo -e "${BOLD}${MAGENTA}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}Installed Modules:${NC}"
[[ "$INSTALL_CODER" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Coder - AI code execution"
[[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Researcher - Web search & reports"
[[ "$INSTALL_SECRETARY" == "true" ]] && echo -e "  ${GREEN}${CHECK}${NC} Secretary - Documentation & codebase"
echo ""

echo -e "${BOLD}Configuration:${NC}"
echo -e "  ${BULLET} Config file: ${DIM}$CONFIG_FILE${NC}"
[[ -n "$CODER_MODEL" ]] && echo -e "  ${BULLET} Coder model: ${CYAN}$CODER_MODEL${NC}"
[[ -n "$RESEARCHER_MODEL" ]] && echo -e "  ${BULLET} Researcher model: ${CYAN}$RESEARCHER_MODEL${NC}"
[[ -n "$SECRETARY_MODEL" ]] && echo -e "  ${BULLET} Secretary model: ${CYAN}$SECRETARY_MODEL${NC}"
[[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "  ${BULLET} Search provider: ${CYAN}$SEARCH_PROVIDER${NC}"
[[ -n "$SERPER_KEY" ]] && echo -e "  ${BULLET} Serper.dev: ${GREEN}Configured${NC}"
[[ -n "$PERPLEXITY_KEY" ]] && echo -e "  ${BULLET} Perplexity AI: ${GREEN}Configured${NC}"
echo ""

# Show which editors were configured
EDITORS_CONFIGURED=()
# Check both possible Claude config locations
DETECTED_CLAUDE_CONFIG=$(detect_claude_mcp_config)
[[ -f "$DETECTED_CLAUDE_CONFIG" ]] && grep -q '"mcpServers"' "$DETECTED_CLAUDE_CONFIG" 2>/dev/null && EDITORS_CONFIGURED+=("Claude Code")
[[ -f "$HOME/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json" ]] || [[ -f "$HOME/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json" ]] && EDITORS_CONFIGURED+=("VS Code (Cline)")
[[ -f "$HOME/.config/zed/settings.json.backup" ]] && EDITORS_CONFIGURED+=("Zed")
[[ -f "$HOME/.opencode.json" ]] || [[ -f "$HOME/.config/opencode/.opencode.json" ]] && EDITORS_CONFIGURED+=("OpenCode")

if [[ ${#EDITORS_CONFIGURED[@]} -gt 0 ]]; then
    echo -e "${BOLD}Editors Configured:${NC}"
    for editor in "${EDITORS_CONFIGURED[@]}"; do
        echo -e "  ${GREEN}${CHECK}${NC} $editor"
    done
    echo ""
fi

echo -e "${BOLD}Next Steps:${NC}"
echo ""
echo -e "  ${BOLD}1.${NC} Load configuration:"
echo -e "     ${DIM}source $CONFIG_FILE${NC}"
echo ""

if [[ "$ENABLE_DAEMON" == "true" ]]; then
    echo -e "  ${BOLD}2.${NC} Start daemons:"
    [[ "$INSTALL_CODER" == "true" ]] && echo -e "     ${DIM}ninja-daemon start coder${NC}"
    [[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "     ${DIM}ninja-daemon start researcher${NC}"
    [[ "$INSTALL_SECRETARY" == "true" ]] && echo -e "     ${DIM}ninja-daemon start secretary${NC}"
    echo ""
    echo -e "  ${BOLD}3.${NC} Check daemon status:"
    echo -e "     ${DIM}ninja-daemon status${NC}"
else
    echo -e "  ${BOLD}2.${NC} Run servers directly:"
    [[ "$INSTALL_CODER" == "true" ]] && echo -e "     ${DIM}ninja-coder${NC}"
    [[ "$INSTALL_RESEARCHER" == "true" ]] && echo -e "     ${DIM}ninja-researcher${NC}"
    [[ "$INSTALL_SECRETARY" == "true" ]] && echo -e "     ${DIM}ninja-secretary${NC}"
fi

echo ""
echo -e "  ${BOLD}3.${NC} Test the installation:"
if [[ "$INSTALL_RESEARCHER" == "true" ]]; then
    echo -e "     ${DIM}# Test researcher${NC}"
    echo -e "     ${DIM}source $CONFIG_FILE${NC}"
    echo -e "     ${DIM}ninja-researcher${NC}"
    echo -e "     ${DIM}# Then in Claude/IDE: researcher_web_search({\"query\": \"test\"})${NC}"
fi
echo ""

echo -e "${DIM}For more information, see: ${CYAN}README.md${NC}"
echo ""
echo -e "${GREEN}Happy coding! 🥷${NC}"
echo ""
