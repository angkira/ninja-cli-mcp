# Testing Guide

## Test Categories

ninja-cli-mcp uses pytest markers to organize tests into different categories:

### 🔹 Unit Tests (`@pytest.mark.unit`)
Fast, isolated tests with no external dependencies.
```bash
uv run pytest -m unit
```

### 💨 Smoke Tests
Quick sanity checks included in unit tests. Run automatically in CI.
```bash
uv run pytest tests/test_smoke.py
```

### 🔌 Integration Tests (`@pytest.mark.integration`)
Tests that require external services (OpenRouter API, etc).
```bash
# Requires OPENROUTER_API_KEY
uv run pytest -m integration
```

### 🤖 Agent Tests (`@pytest.mark.agent`)
Tests that require AI CLI tools (aider, claude, etc) to be installed.
```bash
# Requires aider or claude installed
uv run pytest -m agent
```

### 🚀 E2E Tests (`@pytest.mark.e2e`)
Full end-to-end workflow tests. Slow and require full setup.
```bash
# Requires API keys and AI CLI
uv run pytest -m e2e
```

### 🐌 Slow Tests (`@pytest.mark.slow`)
Tests that take >30 seconds.
```bash
uv run pytest -m "not slow"  # Skip slow tests
uv run pytest -m slow        # Only slow tests
```

## Running Tests Locally

### Quick verification (< 1 minute)
```bash
uv run pytest tests/test_smoke.py
```

### Full local test suite
```bash
# Install dev dependencies
uv sync

# Run all unit tests
uv run pytest -m unit -v

# Run with coverage
uv run pytest -m unit --cov=ninja_cli_mcp --cov-report=html
```

### Integration tests (requires API key)
```bash
export OPENROUTER_API_KEY="your-key-here"
uv run pytest -m integration -v
```

### E2E tests (requires everything)
```bash
# Install aider
pip install aider-chat

# Set API key
export OPENROUTER_API_KEY="your-key-here"

# Run E2E
uv run pytest -m e2e -v
```

## CI/CD Pipeline

GitHub Actions runs:
1. **Lint & Type Check** - ruff, mypy
2. **Smoke Tests** - Fast sanity checks
3. **Unit Tests** - All unit tests
4. **Integration Tests** - Only on `main` branch pushes
5. **Build** - Package build verification

E2E and agent tests are **not run in CI** due to requirements and cost.

## Writing Tests

### Use appropriate markers
```python
import pytest

@pytest.mark.unit
def test_something_fast():
    """Unit tests are fast and isolated."""
    assert True

@pytest.mark.integration
def test_with_api():
    """Integration tests may call external APIs."""
    if not os.getenv("API_KEY"):
        pytest.skip("API_KEY not set")
    # ...

@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.agent
def test_full_workflow():
    """E2E tests verify complete workflows."""
    # ...
```

### Skip when dependencies unavailable
```python
@pytest.mark.integration
def test_requires_api():
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    # ...

@pytest.mark.agent
def test_requires_aider():
    result = subprocess.run(["which", "aider"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("aider not installed")
    # ...
```

## Test Organization

```
tests/
├── test_smoke.py              # Smoke tests (marked as unit)
├── test_*.py                  # Unit tests
├── test_integration_*.py      # Integration tests
├── test_e2e.py                # E2E tests
└── conftest.py                # Shared fixtures
```

## Performance Guidelines

- **Unit tests**: < 100ms each
- **Smoke tests**: < 1s total
- **Integration tests**: < 10s each
- **E2E tests**: Can be slow (mark with `@pytest.mark.slow`)
