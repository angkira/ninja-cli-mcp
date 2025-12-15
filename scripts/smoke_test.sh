#!/usr/bin/env bash
#
# smoke_test.sh - Basic smoke test for ninja-cli-mcp
#
# Creates a temporary test repository and verifies basic functionality:
# - Server module can be imported
# - Quick task tool can be invoked
# - Logs are created correctly
#
# Usage: ./scripts/smoke_test.sh
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
    echo -e "${GREEN}[PASS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    FAILED=1
}

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

FAILED=0

echo ""
echo "=========================================="
echo "  ninja-cli-mcp Smoke Test"
echo "=========================================="
echo ""

# Create temporary test directory
TEST_DIR=$(mktemp -d)
trap "rm -rf $TEST_DIR" EXIT

info "Created temporary test directory: $TEST_DIR"

# Initialize a simple test repo
mkdir -p "$TEST_DIR/src"
echo 'print("Hello World")' > "$TEST_DIR/src/main.py"
echo '# Test Project' > "$TEST_DIR/README.md"

info "Initialized test repository with sample files"

# Test 1: Module import
info "Test 1: Checking module imports..."
if uv run python -c "from ninja_cli_mcp import server, tools, models; print('Imports OK')" 2>/dev/null; then
    success "Module imports work correctly"
else
    fail "Module imports failed"
fi

# Test 2: Model validation
info "Test 2: Checking Pydantic models..."
if uv run python -c "
from ninja_cli_mcp.models import QuickTaskRequest, PlanStep, TestPlan
req = QuickTaskRequest(task='test', repo_root='/tmp')
step = PlanStep(id='1', title='Test', task='Do something')
print('Models OK')
" 2>/dev/null; then
    success "Pydantic models validate correctly"
else
    fail "Pydantic model validation failed"
fi

# Test 3: Path utilities
info "Test 3: Checking path utilities..."
if uv run python -c "
from ninja_cli_mcp.path_utils import validate_repo_root, safe_resolve, is_path_within
import tempfile
import os

# Test with real temp directory
with tempfile.TemporaryDirectory() as d:
    path = validate_repo_root(d)
    assert path.exists(), 'Path should exist'
    assert is_path_within(os.path.join(d, 'subdir'), d), 'Should be within'
    assert not is_path_within('/etc/passwd', d), 'Should not be within'

print('Path utils OK')
" 2>/dev/null; then
    success "Path utilities work correctly"
else
    fail "Path utilities test failed"
fi

# Test 4: Logging utilities
info "Test 4: Checking logging utilities..."
if uv run python -c "
from ninja_cli_mcp.logging_utils import setup_logging, create_task_logger
import tempfile

setup_logging()

with tempfile.TemporaryDirectory() as d:
    logger = create_task_logger(d, 'test-step')
    logger.info('Test message')
    logger.set_metadata('test_key', 'test_value')
    log_path = logger.save()

    assert log_path.endswith('.log'), 'Should create log file'

print('Logging OK')
" 2>/dev/null; then
    success "Logging utilities work correctly"
else
    fail "Logging utilities test failed"
fi

# Test 5: Ninja driver instruction building
info "Test 5: Checking Ninja driver instruction builder..."
if uv run python -c "
from ninja_cli_mcp.ninja_driver import InstructionBuilder, NinjaConfig, RECOMMENDED_MODELS
from ninja_cli_mcp.models import ExecutionMode, PlanStep

builder = InstructionBuilder('/tmp/test', ExecutionMode.QUICK)
instruction = builder.build_quick_task(
    task='Add a function',
    context_paths=['src/'],
    allowed_globs=['**/*.py'],
    deny_globs=['*.pyc'],
)

assert 'task' in instruction
assert instruction['repo_root'] == '/tmp/test'
assert 'instructions' in instruction
assert 'guarantees' in instruction

# Check model recommendations exist
assert len(RECOMMENDED_MODELS) > 0, 'Should have recommended models'

print('Instruction builder OK')
" 2>/dev/null; then
    success "Ninja driver instruction builder works correctly"
else
    fail "Ninja driver instruction builder test failed"
fi

# Test 6: CLI parser
info "Test 6: Checking CLI argument parser..."
if uv run python -c "
from ninja_cli_mcp.cli import build_parser

parser = build_parser()
args = parser.parse_args(['quick-task', '--repo-root', '/tmp', '--task', 'Test task'])
assert args.repo_root == '/tmp'
assert args.task == 'Test task'

args = parser.parse_args(['run-tests', '--repo-root', '/tmp', '--commands', 'pytest'])
assert args.repo_root == '/tmp'
assert 'pytest' in args.commands

# Test new commands
args = parser.parse_args(['list-models'])
assert args.command == 'list-models'

args = parser.parse_args(['show-config'])
assert args.command == 'show-config'

print('CLI parser OK')
" 2>/dev/null; then
    success "CLI argument parser works correctly"
else
    fail "CLI argument parser test failed"
fi

# Test 7: Tool executor initialization
info "Test 7: Checking tool executor initialization..."
if uv run python -c "
from ninja_cli_mcp.tools import ToolExecutor, get_executor, reset_executor

reset_executor()
executor = get_executor()
assert executor is not None
assert executor.driver is not None

print('Tool executor OK')
" 2>/dev/null; then
    success "Tool executor initializes correctly"
else
    fail "Tool executor initialization test failed"
fi

# Test 8: Internal directory creation
info "Test 8: Checking internal directory creation..."
if uv run python -c "
from ninja_cli_mcp.path_utils import ensure_internal_dirs
import tempfile
import os

with tempfile.TemporaryDirectory() as d:
    dirs = ensure_internal_dirs(d)
    assert os.path.isdir(dirs['logs']), 'logs dir should exist'
    assert os.path.isdir(dirs['tasks']), 'tasks dir should exist'
    assert os.path.isdir(dirs['metadata']), 'metadata dir should exist'

print('Internal dirs OK')
" 2>/dev/null; then
    success "Internal directories created correctly"
else
    fail "Internal directory creation test failed"
fi

# Test 9: Model configuration
info "Test 9: Checking model configuration..."
if uv run python -c "
from ninja_cli_mcp.ninja_driver import NinjaConfig, DEFAULT_MODEL, RECOMMENDED_MODELS

config = NinjaConfig()
assert config.model == DEFAULT_MODEL, 'Should use default model'

# Test with_model
new_config = config.with_model('openai/gpt-4o')
assert new_config.model == 'openai/gpt-4o', 'Should have new model'
assert config.model == DEFAULT_MODEL, 'Original should be unchanged'

print('Model config OK')
" 2>/dev/null; then
    success "Model configuration works correctly"
else
    fail "Model configuration test failed"
fi

echo ""
echo "=========================================="
if [[ $FAILED -eq 0 ]]; then
    success "All smoke tests passed!"
    echo ""
    echo "The ninja-cli-mcp package is ready to use."
    echo ""
    echo "Note: Full functionality requires:"
    echo "  1. OPENROUTER_API_KEY environment variable"
    echo "  2. AI Code CLI installed and accessible"
    echo ""
    echo "Supported models (set via NINJA_MODEL):"
    echo "  - anthropic/claude-sonnet-4 (default)"
    echo "  - openai/gpt-4o"
    echo "  - qwen/qwen3-coder"
    echo "  - deepseek/deepseek-coder"
    echo "  - And many more via OpenRouter"
    echo ""
else
    fail "Some smoke tests failed"
    echo ""
    echo "Please check the errors above and fix any issues."
    echo ""
fi
echo "=========================================="
echo ""

exit $FAILED
