#!/usr/bin/env bash
#
# run_notebooks.sh - Launch Jupyter notebooks for model comparison
#
# Usage: ./scripts/run_notebooks.sh
#

set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NOTEBOOKS_DIR="$PROJECT_ROOT/notebooks"

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                          ║${NC}"
echo -e "${BLUE}║${NC}          ${GREEN}📊 Ninja CLI MCP - Jupyter Notebooks${NC}          ${BLUE}║${NC}"
echo -e "${BLUE}║                                                          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if notebooks directory exists
if [[ ! -d "$NOTEBOOKS_DIR" ]]; then
    echo -e "${YELLOW}⚠${NC}  Notebooks directory not found"
    exit 1
fi

# Check if Jupyter is installed
if ! command -v jupyter &> /dev/null; then
    echo -e "${YELLOW}⚠${NC}  Jupyter not found. Installing..."
    echo ""

    cd "$PROJECT_ROOT"

    # Try to install with uv
    if command -v uv &> /dev/null; then
        echo "Installing notebook dependencies with uv..."
        uv sync --extra notebooks
    else
        echo "Please install Jupyter manually:"
        echo "  uv sync --extra notebooks"
        echo "  # or"
        echo "  pip install jupyter matplotlib seaborn pandas"
        exit 1
    fi
fi

# Load environment if config exists
CONFIG_FILE="$HOME/.ninja-cli-mcp.env"
if [[ -f "$CONFIG_FILE" ]]; then
    echo -e "${GREEN}✓${NC} Loading configuration from: $CONFIG_FILE"
    source "$CONFIG_FILE"
else
    echo -e "${YELLOW}⚠${NC}  No config file found at: $CONFIG_FILE"
    echo "  Run ./scripts/install_interactive.sh first"
    echo ""
fi

# Check API key
if [[ -z "${OPENROUTER_API_KEY:-}" ]] && [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo -e "${YELLOW}⚠${NC}  Warning: No API key found"
    echo "  Some notebooks require OPENROUTER_API_KEY or OPENAI_API_KEY"
    echo "  Cost analysis notebook will still work (uses pricing API only)"
    echo ""
fi

# Launch Jupyter
echo ""
echo -e "${GREEN}🚀 Launching Jupyter Notebook...${NC}"
echo ""
echo "Available notebooks:"
echo "  📊 01_model_comparison.ipynb - Compare models on real tasks"
echo "  💰 02_cost_analysis.ipynb    - Deep cost analysis"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

cd "$NOTEBOOKS_DIR"
uv run jupyter notebook

echo ""
echo -e "${GREEN}✓${NC} Jupyter stopped"
echo ""
