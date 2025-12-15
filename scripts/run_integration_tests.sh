#!/usr/bin/env bash
#
# run_integration_tests.sh - Run integration tests with Claude Code
#
# These tests make real API calls but are designed to use minimal tokens.
#
# Usage: ./scripts/run_integration_tests.sh
#

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo ""
echo -e "${BOLD}${CYAN}🧪 ninja-cli-mcp Integration Tests${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo ""

# Check for API key
if [[ -z "${OPENROUTER_API_KEY:-}" ]] && [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo -e "${YELLOW}⚠${NC}  No API key found!"
    echo ""
    echo "Integration tests require an OpenRouter API key."
    echo "Set one of these environment variables:"
    echo "  • OPENROUTER_API_KEY"
    echo "  • OPENAI_API_KEY"
    echo ""
    echo "Example:"
    echo "  export OPENROUTER_API_KEY='your-key-here'"
    echo "  ./scripts/run_integration_tests.sh"
    echo ""
    exit 1
fi

# Show configuration
echo -e "${BOLD}Configuration:${NC}"
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    MASKED="${OPENROUTER_API_KEY:0:8}...${OPENROUTER_API_KEY: -4}"
    echo -e "  ${BLUE}•${NC} API Key:    ${MASKED}"
fi
MODEL="${NINJA_MODEL:-anthropic/claude-sonnet-4}"
echo -e "  ${BLUE}•${NC} Model:      ${CYAN}${MODEL}${NC}"
echo ""

# Warning about costs
echo -e "${YELLOW}⚠${NC}  ${BOLD}Cost Warning:${NC}"
echo "  These tests make real API calls but use minimal tokens."
echo "  Estimated cost: ${BOLD}\$0.01 - \$0.05${NC} for the full suite."
echo ""

read -p "Continue? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo -e "${BOLD}Running integration tests...${NC}"
echo ""

# Set environment variable to enable integration tests
export RUN_INTEGRATION_TESTS=1

# Run integration tests
if uv run pytest tests/test_integration_claude.py -v --tb=short -m "not slow"; then
    echo ""
    echo -e "${GREEN}✓${NC} ${BOLD}Fast integration tests passed!${NC}"
    echo ""

    # Ask about slow tests
    echo -e "${BOLD}Slow tests:${NC}"
    echo "  Some tests make network requests (e.g., fetching pricing from OpenRouter)."
    echo "  These take longer but don't use API credits."
    echo ""

    read -p "Run slow tests too? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo -e "${BOLD}Running slow tests...${NC}"
        echo ""

        if uv run pytest tests/test_integration_claude.py -v --tb=short -m "slow"; then
            echo ""
            echo -e "${GREEN}✓${NC} ${BOLD}All integration tests passed!${NC}"
        else
            echo ""
            echo -e "${RED}✗${NC} Some slow tests failed"
            exit 1
        fi
    fi

    echo ""
    echo -e "${BOLD}Test Summary:${NC}"
    echo ""

    # Check if metrics were created
    if [[ -d "/tmp/test_project" ]]; then
        METRICS_DIR="/tmp/test_project/.ninja-cli-mcp/metrics"
        if [[ -f "$METRICS_DIR/tasks.csv" ]]; then
            echo -e "  ${GREEN}✓${NC} Metrics tracking verified"

            # Show token/cost summary
            echo ""
            echo -e "${BOLD}Token Usage:${NC}"
            uv run python -c "
import csv
from pathlib import Path

metrics_file = Path('$METRICS_DIR/tasks.csv')
if metrics_file.exists():
    with open(metrics_file) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        if rows:
            total_tokens = sum(int(r.get('total_tokens', 0)) for r in rows)
            total_cost = sum(float(r.get('total_cost', 0)) for r in rows)

            print(f'  Total tokens: {total_tokens:,}')
            print(f'  Total cost:   \${total_cost:.4f}')
        else:
            print('  No tasks recorded')
" 2>/dev/null || echo "  Metrics file empty"
        fi
    fi

    echo ""
    echo -e "${GREEN}✓${NC} ${BOLD}Integration tests complete!${NC}"
    echo ""

else
    echo ""
    echo -e "${RED}✗${NC} Integration tests failed"
    echo ""
    echo "Common issues:"
    echo "  • Invalid API key"
    echo "  • Network connectivity problems"
    echo "  • API rate limits reached"
    echo ""
    exit 1
fi
