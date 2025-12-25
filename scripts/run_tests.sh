#!/usr/bin/env bash
#
# run_tests.sh - Test runner for Ninja MCP modules
#
# Usage:
#   ./scripts/run_tests.sh                # Run all tests
#   ./scripts/run_tests.sh researcher     # Run researcher tests only
#   ./scripts/run_tests.sh secretary      # Run secretary tests only
#   ./scripts/run_tests.sh --unit         # Run unit tests only
#   ./scripts/run_tests.sh --integration  # Run integration tests only
#   ./scripts/run_tests.sh --fast         # Skip slow tests
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
MODULE=""
TEST_TYPE=""
MARKERS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        researcher|secretary|coder)
            MODULE="$1"
            shift
            ;;
        --unit)
            MARKERS="-m unit"
            shift
            ;;
        --integration)
            MARKERS="-m integration"
            shift
            ;;
        --fast)
            MARKERS="-m 'not slow'"
            shift
            ;;
        --slow)
            MARKERS="-m slow"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [MODULE] [OPTIONS]"
            echo ""
            echo "Modules:"
            echo "  researcher    Test researcher module only"
            echo "  secretary     Test secretary module only"
            echo "  coder         Test coder module only"
            echo ""
            echo "Options:"
            echo "  --unit          Run unit tests only"
            echo "  --integration   Run integration tests only"
            echo "  --fast          Skip slow tests"
            echo "  --slow          Run only slow tests"
            echo "  --help          Show this help"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Print header
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║                                                          ║${NC}"
echo -e "${BOLD}${CYAN}║${NC}            ${GREEN}${BOLD}🧪 Ninja MCP Test Suite${NC}                ${BOLD}${CYAN}║${NC}"
echo -e "${BOLD}${CYAN}║                                                          ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest not found${NC}"
    echo -e "${YELLOW}Install with: uv sync --extra dev${NC}"
    exit 1
fi

# Load environment variables if available
if [[ -f "$HOME/.ninja-mcp.env" ]]; then
    echo -e "${BLUE}→ Loading configuration from ~/.ninja-mcp.env${NC}"
    source "$HOME/.ninja-mcp.env"
fi

# Determine which tests to run
TEST_PATH="tests/"
if [[ -n "$MODULE" ]]; then
    TEST_PATH="tests/test_${MODULE}/"
    echo -e "${BLUE}→ Running ${BOLD}${MODULE}${NC}${BLUE} module tests${NC}"
else
    echo -e "${BLUE}→ Running ${BOLD}all${NC}${BLUE} module tests${NC}"
fi

if [[ -n "$MARKERS" ]]; then
    echo -e "${BLUE}→ Test filter: ${BOLD}${MARKERS}${NC}"
fi

echo ""

# Run pytest
PYTEST_ARGS=(
    "$TEST_PATH"
    "-v"
    "--tb=short"
    "--color=yes"
)

# Add markers if specified
if [[ -n "$MARKERS" ]]; then
    PYTEST_ARGS+=($MARKERS)
fi

# Add coverage if running all tests
if [[ -z "$MODULE" ]] && [[ -z "$MARKERS" ]]; then
    PYTEST_ARGS+=(
        "--cov=src"
        "--cov-report=term-missing"
        "--cov-report=html"
    )
    echo -e "${YELLOW}→ Coverage reporting enabled${NC}"
    echo ""
fi

# Run tests
echo -e "${BOLD}Running tests...${NC}"
echo ""

if pytest "${PYTEST_ARGS[@]}"; then
    echo ""
    echo -e "${GREEN}${BOLD}✓ All tests passed!${NC}"

    # Show coverage report location if generated
    if [[ -z "$MODULE" ]] && [[ -z "$MARKERS" ]]; then
        echo ""
        echo -e "${BLUE}→ Coverage report: ${CYAN}htmlcov/index.html${NC}"
    fi

    exit 0
else
    echo ""
    echo -e "${RED}${BOLD}✗ Some tests failed${NC}"
    exit 1
fi
