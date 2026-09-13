# Ninja MCP - Modern task automation
# Install just: curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Default recipe (show help)
default:
    @just --list

# ============================================================================
# Installation & Setup
# ============================================================================

# Interactive installation (recommended)
install:
    @./scripts/install_interactive.sh

# Install for development (editable mode)
install-dev:
    @echo "📦 Installing for development..."
    uv sync --all-extras
    @echo "✓ Development installation complete"
    @echo ""
    @echo "Next steps:"
    @echo "  just setup-ide    # Configure IDE integration"
    @echo "  just test         # Run tests"

# Install as global tool (production)
install-global:
    @echo "📦 Installing globally with uv tool..."
    uv tool install --force --editable .
    @echo "✓ Global installation complete"
    @echo ""
    @echo "Commands available:"
    @echo "  ninja-coder      # Code assistant MCP server"
    @echo "  ninja-researcher # Research MCP server"
    @echo "  ninja-secretary  # Secretary MCP server"
    @echo "  ninja-daemon     # Daemon manager"
    @echo "  ninja-config     # Configuration manager"

# Uninstall global tool
uninstall-global:
    @echo "🗑️  Uninstalling global tool..."
    uv tool uninstall ninja-mcp || true
    @echo "✓ Uninstalled"

# ============================================================================
# IDE Integration
# ============================================================================

# Setup IDE integration (auto-detect)
setup-ide:
    @./scripts/install_ide_integrations.sh

# Setup Claude Code MCP integration
setup-claude-code:
    @./scripts/install_claude_code_mcp.sh --all

# Setup VS Code Cline integration
setup-vscode:
    @./scripts/install_vscode_mcp.sh --all

# Setup Zed editor integration
setup-zed:
    @./scripts/install_zed_mcp.sh --all

# ============================================================================
# Development
# ============================================================================

# Run all tests
test:
    @echo "🧪 Running tests..."
    uv run pytest

# Run tests with coverage
test-coverage:
    @echo "🧪 Running tests with coverage..."
    uv run pytest --cov=src --cov-report=html --cov-report=term

# Run specific test file
test-file FILE:
    @echo "🧪 Running {{FILE}}..."
    uv run pytest {{FILE}} -v

# Run linting
lint:
    @echo "🔍 Running linter..."
    uv run ruff check src/

# Run linting with auto-fix
lint-fix:
    @echo "🔧 Running linter with auto-fix..."
    uv run ruff check --fix src/

# Format code
format:
    @echo "✨ Formatting code..."
    uv run ruff format src/

# Type checking
typecheck:
    @echo "🔍 Running type checker..."
    uv run mypy src/

# Run all checks (lint, format, typecheck)
check: lint format typecheck
    @echo "✓ All checks passed"

# ============================================================================
# Daemon Management
# ============================================================================

# Start all daemons
daemon-start:
    @echo "🚀 Starting all daemons..."
    uv run ninja-daemon start

# Stop all daemons
daemon-stop:
    @echo "🛑 Stopping all daemons..."
    uv run ninja-daemon stop

# Restart all daemons
daemon-restart:
    @echo "🔄 Restarting all daemons..."
    uv run ninja-daemon restart

# Show daemon status
daemon-status:
    @echo "📊 Daemon status:"
    @uv run ninja-daemon status | python3 -m json.tool

# View daemon logs
daemon-logs MODULE="coder":
    @echo "📋 Viewing logs for {{MODULE}}..."
    @tail -f ~/.cache/ninja-mcp/logs/{{MODULE}}.log

# ============================================================================
# Running Servers
# ============================================================================

# Run coder server (stdio mode)
run-coder:
    uv run ninja-coder

# Run researcher server (stdio mode)
run-researcher:
    uv run ninja-researcher

# Run secretary server (stdio mode)
run-secretary:
    uv run ninja-secretary

# Run coder in HTTP mode for testing
run-coder-http PORT="8100":
    uv run python -m ninja_coder.server --http --port {{PORT}}

# Run researcher in HTTP mode for testing
run-researcher-http PORT="8101":
    uv run python -m ninja_researcher.server --http --port {{PORT}}

# Run secretary in HTTP mode for testing
run-secretary-http PORT="8102":
    uv run python -m ninja_secretary.server --http --port {{PORT}}

# ============================================================================
# Building & Packaging
# ============================================================================

# Build package
build:
    @echo "📦 Building package..."
    uv build
    @echo "✓ Build complete: dist/"

# Build and publish to PyPI (test)
publish-test: build
    @echo "📤 Publishing to TestPyPI..."
    uv publish --index-url https://test.pypi.org/legacy/

# Build and publish to PyPI (production)
publish: build
    @echo "📤 Publishing to PyPI..."
    @echo "⚠️  This will publish to production PyPI!"
    @echo "Press Ctrl+C to cancel, or Enter to continue..."
    @read
    uv publish

# Create a new release (interactive)
release VERSION:
    @echo "🚀 Creating release v{{VERSION}}..."
    @echo ""
    @echo "This will:"
    @echo "  1. Update version in pyproject.toml"
    @echo "  2. Update CHANGELOG.md"
    @echo "  3. Commit changes"
    @echo "  4. Create and push git tag"
    @echo ""
    @echo "Press Ctrl+C to cancel, or Enter to continue..."
    @read
    @# Update version
    @sed -i 's/^version = ".*"/version = "{{VERSION}}"/' pyproject.toml
    @echo "✓ Updated version in pyproject.toml"
    @# Prompt for changelog
    @echo ""
    @echo "Please update CHANGELOG.md with release notes for v{{VERSION}}"
    @echo "Press Enter when done..."
    @read
    @# Commit
    git add pyproject.toml CHANGELOG.md
    git commit -m "Bump version to {{VERSION}}"
    @# Tag
    git tag -a v{{VERSION}} -m "Release v{{VERSION}}"
    @echo ""
    @echo "✓ Created tag v{{VERSION}}"
    @echo ""
    @echo "To complete the release, push:"
    @echo "  git push origin main v{{VERSION}}"
    @echo ""
    @echo "This will trigger GitHub Actions to build and publish."

# Quick release (assumes changelog is ready)
release-quick VERSION:
    @echo "🚀 Quick release v{{VERSION}}..."
    @sed -i 's/^version = ".*"/version = "{{VERSION}}"/' pyproject.toml
    git add pyproject.toml CHANGELOG.md
    git commit -m "Bump version to {{VERSION}}"
    git tag -a v{{VERSION}} -m "Release v{{VERSION}}"
    git push origin main v{{VERSION}}
    @echo "✓ Release v{{VERSION}} pushed!"
    @echo "Monitor: https://github.com/angkira/ninja-mcp/actions"

# Local release flow: bump, gate, build, tag, publish to PyPI (scripts/release.sh)
release-local VERSION:
    ./scripts/release.sh {{VERSION}}

# Dry-run the local release flow without mutating anything
release-dry-run VERSION:
    ./scripts/release.sh {{VERSION}} --dry-run

# Bump, gate, build, commit and tag without PyPI publish
release-tag-only VERSION:
    ./scripts/release.sh {{VERSION}} --skip-publish

# Publish the current version to PyPI (local) using the all-projects token
publish-local:
    ./scripts/release.sh $(grep '^version' pyproject.toml | head -1 | cut -d'"' -f2) --skip-tests --yes

# Build Homebrew formula
build-homebrew:
    @echo "🍺 Building Homebrew formula..."
    @./scripts/packaging/build-homebrew.sh

# Build Debian package
build-deb:
    @echo "📦 Building Debian package..."
    @./scripts/packaging/build-deb.sh

# Build all packages
build-all: build build-homebrew build-deb
    @echo "✓ All packages built"

# ============================================================================
# Cleaning
# ============================================================================

# Clean build artifacts
clean:
    @echo "🧹 Cleaning build artifacts..."
    rm -rf dist/ build/ *.egg-info .pytest_cache .coverage htmlcov/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    @echo "✓ Cleaned"

# Clean all (including venv and cache)
clean-all: clean
    @echo "🧹 Cleaning all..."
    rm -rf .venv/ .uv-cache/
    rm -rf ~/.cache/ninja-mcp/
    @echo "✓ Deep cleaned"

# ============================================================================
# Documentation
# ============================================================================

# Generate API documentation
docs:
    @echo "📚 Generating documentation..."
    @echo "TODO: Setup sphinx or mkdocs"

# Serve documentation locally
docs-serve:
    @echo "📚 Serving documentation..."
    @echo "TODO: Setup docs server"

# ============================================================================
# Configuration
# ============================================================================

# Run configuration wizard
config:
    uv run ninja-config

# Show current configuration
config-show:
    @echo "📋 Current configuration:"
    @cat ~/.ninja-mcp.env 2>/dev/null || echo "No config file found"

# Validate MCP configuration
validate-mcp:
    @echo "✓ Validating MCP configuration..."
    @bash -c 'source scripts/lib/claude_config.sh && CONFIG=$$(detect_claude_mcp_config) && echo "Using config: $$CONFIG" && python3 -m json.tool "$$CONFIG" > /dev/null && echo "✓ Valid JSON" || echo "✗ Invalid JSON"'

# ============================================================================
# Utilities
# ============================================================================

# Show version information
version:
    @echo "Ninja MCP Version Information:"
    @grep '^version' pyproject.toml | head -1
    @echo ""
    @echo "Installed tools:"
    @uv tool list 2>/dev/null | grep ninja || echo "Not installed as tool"

# Check system requirements
check-requirements:
    @echo "🔍 Checking system requirements..."
    @echo -n "Python: " && python3 --version || echo "✗ Python 3.11+ required"
    @echo -n "uv: " && uv --version || echo "✗ uv required"
    @echo -n "Git: " && git --version || echo "✗ Git required"
    @echo -n "Claude Code: " && claude --version 2>/dev/null || echo "⚠ Optional"
    @echo ""
    @echo "Environment variables:"
    @echo -n "OPENROUTER_API_KEY: " && [[ -n "${OPENROUTER_API_KEY:-}" ]] && echo "✓ Set" || echo "✗ Not set"

# Benchmark tools
benchmark:
    @echo "⚡ Running benchmarks..."
    @echo "TODO: Implement benchmarks"

# ============================================================================
# Examples & Demo
# ============================================================================

# Run interactive demo
demo:
    @echo "🎬 Running interactive demo..."
    @./scripts/demo.sh

# Show example configurations
examples:
    @echo "📋 Example configurations:"
    @echo ""
    @echo "Claude Code (global install):"
    @cat examples/mcp-config-template.json
    @echo ""
    @echo "Local development:"
    @cat examples/mcp-config-local-dev.json
