#!/usr/bin/env bash
#
# dev.sh - Development workflow script
#
# Runs linting, type checking, and tests.
#
# Usage:
#   ./scripts/dev.sh          # Run all checks
#   ./scripts/dev.sh lint     # Run linter only
#   ./scripts/dev.sh typecheck # Run type checker only
#   ./scripts/dev.sh test     # Run tests only
#   ./scripts/dev.sh format   # Format code
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

cd "$PROJECT_ROOT"

# Ensure uv environment is set up
if [[ ! -d ".venv" ]]; then
    info "Virtual environment not found, running install..."
    ./scripts/install.sh
fi

run_lint() {
    info "Running ruff linter..."
    if uv run ruff check src/ tests/; then
        success "Linting passed"
        return 0
    else
        error "Linting failed"
        return 1
    fi
}

run_format() {
    info "Formatting code with ruff..."
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/ || true
    success "Code formatted"
}

run_typecheck() {
    info "Running type checker (mypy)..."
    if uv run mypy src/; then
        success "Type checking passed"
        return 0
    else
        warn "Type checking found issues"
        return 1
    fi
}

run_tests() {
    info "Running tests with pytest..."
    if uv run pytest tests/ -v --tb=short; then
        success "All tests passed"
        return 0
    else
        error "Some tests failed"
        return 1
    fi
}

run_all() {
    local failed=0

    echo ""
    echo "=========================================="
    echo "  Running Development Checks"
    echo "=========================================="
    echo ""

    run_lint || failed=1
    echo ""

    run_typecheck || failed=1
    echo ""

    run_tests || failed=1
    echo ""

    echo "=========================================="
    if [[ $failed -eq 0 ]]; then
        success "All checks passed!"
    else
        error "Some checks failed"
    fi
    echo "=========================================="
    echo ""

    return $failed
}

# Parse command
COMMAND="${1:-all}"

case "$COMMAND" in
    lint)
        run_lint
        ;;
    format)
        run_format
        ;;
    typecheck|type)
        run_typecheck
        ;;
    test|tests)
        run_tests
        ;;
    all|"")
        run_all
        ;;
    help|--help|-h)
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  lint       Run ruff linter"
        echo "  format     Format code with ruff"
        echo "  typecheck  Run mypy type checker"
        echo "  test       Run pytest tests"
        echo "  all        Run all checks (default)"
        echo "  help       Show this help message"
        ;;
    *)
        error "Unknown command: $COMMAND"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac
