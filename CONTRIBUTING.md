# Contributing to ninja-cli-mcp

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing.

## Code of Conduct

This project adheres to the Contributor Covenant Code of Conduct. By participating, you are expected to uphold this code. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.

## Getting Started

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Git

### Local Development Setup

1. **Fork the repository** on GitHub

2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR_USERNAME/ninja-cli-mcp.git
   cd ninja-cli-mcp
   ```

3. **Create a virtual environment and install dependencies**
   ```bash
   uv sync --all-extras
   ```

4. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for formatting and linting:

```bash
# Format code
uv run ruff format src/ tests/

# Check formatting
uv run ruff check src/ tests/
```

### Type Checking

We use [mypy](https://mypy.readthedocs.io/) for static type checking:

```bash
uv run mypy src/
```

### Testing

All code changes should include tests:

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_tools.py -v

# Run with coverage
uv run pytest tests/ --cov=ninja_cli_mcp
```

### Before Submitting

Run the full validation pipeline:

```bash
# Format
uv run ruff format src/ tests/

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/

# Test
uv run pytest tests/ -v
```

Or use a script:
```bash
./scripts/dev.sh
```

## Commit Guidelines

Follow conventional commits format:

- `feat:` A new feature
- `fix:` A bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring without changing functionality
- `perf:` Performance improvements
- `test:` Adding or updating tests
- `ci:` CI/CD configuration changes
- `chore:` Dependency updates, etc.

Examples:
```
feat: add parallel plan execution with configurable fanout
fix: handle timeout gracefully in async subprocess execution
docs: improve README with better examples
test: add comprehensive tests for plan isolation
```

## Types of Contributions

### Reporting Bugs

- Use the **Bug Report** issue template
- Describe the problem clearly
- Include steps to reproduce
- Provide Python version and OS
- Attach logs or screenshots if relevant

### Suggesting Features

- Use the **Feature Request** issue template
- Explain the motivation
- Describe the proposed solution
- Consider alternative approaches

### Improving Documentation

- Fix typos or clarify confusing sections
- Add examples or tutorials
- Improve docstrings in code
- Add inline comments for complex logic

### Submitting Code Changes

1. **Start with an issue** (or create one) to discuss the change
2. **Implement your change** with tests
3. **Ensure all checks pass**:
   - Formatting (ruff format)
   - Linting (ruff check)
   - Type checking (mypy)
   - Tests (pytest)
4. **Create a Pull Request** with:
   - Clear title and description
   - Reference to related issue
   - Screenshots if relevant (UI changes)
   - List of changes

## Pull Request Process

1. **Update documentation** if needed
2. **Add tests** for new functionality
3. **Update CHANGELOG.md** with your changes
4. **Ensure CI passes** (tests, linting, type checking)
5. **Respond to review feedback** promptly
6. **Squash commits** if requested for clean history

## Architecture Guidelines

### Key Principles

1. **Separation of concerns**: MCP server should not read/write project files directly
2. **Subprocess isolation**: Each task runs in its own subprocess
3. **Scope enforcement**: Use `allowed_globs` and `deny_globs` for access control
4. **Result abstraction**: Return summaries, not raw file contents to the planner

### Module Organization

- `server.py`: MCP server and tool definitions
- `tools.py`: Tool implementations
- `ninja_driver.py`: Subprocess management and execution
- `models.py`: Pydantic data models
- `logging_utils.py`: Logging and metrics
- `path_utils.py`: Path validation and manipulation

## Performance Considerations

- Minimize file I/O in the MCP server
- Use async/await for I/O operations
- Implement proper cleanup for subprocess resources
- Consider memory usage for large instruction documents

## Documentation

- Keep README.md up to date
- Document public APIs with docstrings
- Include type hints in all code
- Add comments for complex logic

## Versioning

We follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

Update version in `pyproject.toml` when releasing.

## Questions?

- Open a **Discussion** on GitHub
- Check existing issues and PRs
- Review documentation and docstrings
- Ask in comments on relevant PRs/issues

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to ninja-cli-mcp! 🚀
