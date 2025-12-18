#!/usr/bin/env bash
#
# test_aider_integration.sh - Test Aider integration with ninja-cli-mcp
#
# This script tests that Aider is properly integrated and working
# with OpenRouter API.

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "=========================================="
echo "  Test Aider Integration"
echo "=========================================="
echo ""

# Check if environment is configured
if [[ ! -f "$HOME/.ninja-cli-mcp.env" ]]; then
    error "Configuration file not found: $HOME/.ninja-cli-mcp.env"
    echo ""
    echo "Run the installation script first:"
    echo "  ./scripts/install_coding_cli.sh aider"
    exit 1
fi

# Load environment
source "$HOME/.ninja-cli-mcp.env"

# Check required variables
if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
    error "OPENROUTER_API_KEY is not set"
    exit 1
fi

if [[ -z "${NINJA_CODE_BIN:-}" ]]; then
    error "NINJA_CODE_BIN is not set"
    exit 1
fi

info "Configuration:"
echo "  NINJA_CODE_BIN: $NINJA_CODE_BIN"
echo "  NINJA_MODEL: ${NINJA_MODEL:-not set}"
echo "  API Key: ${OPENROUTER_API_KEY:0:10}...${OPENROUTER_API_KEY: -4}"
echo ""

# Check if Aider is available
info "Checking if Aider is available..."
cd "$PROJECT_ROOT"
if uv run aider --version &> /dev/null; then
    AIDER_VERSION=$(uv run aider --version 2>/dev/null | head -n1)
    success "Aider found: $AIDER_VERSION"
else
    error "Aider is not available"
    echo ""
    echo "Install Aider with:"
    echo "  uv sync --extra aider"
    exit 1
fi

# Create test repository
TEST_DIR="/tmp/test_ninja_aider_$(date +%s)"
info "Creating test repository: $TEST_DIR"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Initialize git repo
git init > /dev/null 2>&1
git config user.email "test@test.com"
git config user.name "Test User"

# Create test file
cat > calculator.py << 'EOF'
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
EOF

git add calculator.py
git commit -m "Initial commit" > /dev/null 2>&1

success "Test repository created"
echo ""

# Test 1: Add docstrings
info "Test 1: Adding docstrings to functions"
cd "$PROJECT_ROOT"
if timeout 60 uv run python -m ninja_cli_mcp.cli quick-task \
    --repo-root "$TEST_DIR" \
    --task "Add docstrings to all functions in calculator.py explaining what they do" \
    > /tmp/test_output1.txt 2>&1; then
    
    # Check if docstrings were added
    if grep -q '"""' "$TEST_DIR/calculator.py"; then
        success "Test 1 PASSED: Docstrings added"
        echo ""
        echo "Modified file:"
        cat "$TEST_DIR/calculator.py"
        echo ""
    else
        error "Test 1 FAILED: No docstrings found"
        cat /tmp/test_output1.txt
        exit 1
    fi
else
    error "Test 1 FAILED: Command failed"
    cat /tmp/test_output1.txt
    exit 1
fi

# Test 2: Add new function
info "Test 2: Adding a new multiply function"
if timeout 60 uv run python -m ninja_cli_mcp.cli quick-task \
    --repo-root "$TEST_DIR" \
    --task "Add a multiply(a, b) function to calculator.py that returns a * b with a proper docstring" \
    > /tmp/test_output2.txt 2>&1; then
    
    # Check if multiply function was added
    if grep -q "def multiply" "$TEST_DIR/calculator.py"; then
        success "Test 2 PASSED: multiply() function added"
        echo ""
        echo "Modified file:"
        cat "$TEST_DIR/calculator.py"
        echo ""
    else
        error "Test 2 FAILED: multiply() function not found"
        cat /tmp/test_output2.txt
        exit 1
    fi
else
    error "Test 2 FAILED: Command failed"
    cat /tmp/test_output2.txt
    exit 1
fi

# Test 3: Verify functionality
info "Test 3: Testing the modified code"
cd "$TEST_DIR"
if python -c "from calculator import add, subtract, multiply; assert add(2, 3) == 5; assert subtract(5, 3) == 2; assert multiply(4, 5) == 20; print('All tests passed')"; then
    success "Test 3 PASSED: Code works correctly"
    echo ""
else
    error "Test 3 FAILED: Code doesn't work"
    exit 1
fi

# Cleanup
info "Cleaning up test repository"
rm -rf "$TEST_DIR"
rm -f /tmp/test_output*.txt

echo ""
echo "=========================================="
echo "  All Tests Passed!"
echo "=========================================="
echo ""
echo "Aider is properly integrated with ninja-cli-mcp"
echo "and can execute code modification tasks via OpenRouter."
echo ""
