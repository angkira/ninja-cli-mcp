# CLI Strategy Architecture

## Overview

Ninja-coder now supports multiple CLI tools through a strategy pattern architecture. This allows seamless switching between different code generation tools (Aider, OpenCode, etc.) while maintaining a consistent interface.

## Architecture

### Strategy Pattern

The codebase uses the Strategy pattern to abstract CLI-specific logic:

```
NinjaDriver
    ├── CLIStrategy (Protocol)
    │   ├── AiderStrategy
    │   ├── OpenCodeStrategy
    │   └── GenericStrategy (fallback)
    └── ModelSelector
```

### Components

#### 1. CLIStrategy Protocol (`src/ninja_coder/strategies/base.py`)

Defines the interface all CLI strategies must implement:

```python
class CLIStrategy(Protocol):
    name: str
    capabilities: CLICapabilities

    def build_command(...) -> CLICommandResult
    def parse_output(...) -> ParsedResult
    def should_retry(...) -> bool
    def get_timeout(task_type: str) -> int
```

#### 2. Concrete Strategies

**AiderStrategy** (`src/ninja_coder/strategies/aider_strategy.py`):
- Supports OpenRouter models
- Provider preference via YAML settings
- 13 error detection patterns
- Retry logic for summarization failures

**OpenCodeStrategy** (`src/ninja_coder/strategies/opencode_strategy.py`):
- Native z.ai support
- Coding Plan API integration
- Optimized for parallel tasks
- Simpler error patterns

#### 3. Strategy Registry (`src/ninja_coder/strategies/registry.py`)

Automatically selects the appropriate strategy based on binary name:

```python
# Detects "aider" in binary name → AiderStrategy
# Detects "opencode" in binary name → OpenCodeStrategy
# Default → GenericStrategy
```

## Using Different CLI Tools

### Aider (Default)

```bash
NINJA_CODE_BIN=aider
NINJA_MODEL=anthropic/claude-haiku-4.5
NINJA_OPENROUTER_PROVIDERS=google-vertex  # Optional provider preference
```

### OpenCode with Z.ai

```bash
NINJA_CODE_BIN=opencode
NINJA_MODEL=glm-4.7
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
OPENAI_API_KEY=your-zai-key
```

## Provider Preferences (Aider)

For models available on multiple providers, you can specify preferences:

```bash
# Use Google Vertex for faster throughput (100 t/s vs 30 t/s)
export NINJA_OPENROUTER_PROVIDERS="google-vertex"

# Multiple providers with fallback
export NINJA_OPENROUTER_PROVIDERS="google-vertex,together"
```

This creates a YAML model settings file that Aider uses for routing.

## Error Handling

Each strategy implements its own error detection and retry logic:

- **AiderStrategy**: 13 error patterns for summarization failures, threading errors, etc.
- **OpenCodeStrategy**: Simpler patterns for API errors, rate limits, timeouts

Retryable errors trigger automatic retry (configurable via `NINJA_MAX_RETRIES`).

## Extending with New CLIs

To add support for a new CLI tool:

1. Create a new strategy class implementing `CLIStrategy`
2. Register it in `CLIStrategyRegistry._strategies`
3. Update detection logic in `get_strategy()`

Example:

```python
from ninja_coder.strategies.base import CLIStrategy, CLICapabilities

class MyCustomStrategy:
    def __init__(self, bin_path: str, config: NinjaConfig):
        self.bin_path = bin_path
        self.config = config
        self._capabilities = CLICapabilities(...)

    @property
    def name(self) -> str:
        return "mycli"

    def build_command(...) -> CLICommandResult:
        # CLI-specific command building
        ...

    # Implement other required methods
```

## Configuration Reference

### CLI Selection

- `NINJA_CODE_BIN`: Path to CLI binary (default: "aider")

### Aider-Specific

- `NINJA_AIDER_TIMEOUT`: Timeout in seconds (default: 300)
- `NINJA_OPENROUTER_PROVIDERS`: Comma-separated provider list

### OpenCode-Specific

- `NINJA_OPENCODE_TIMEOUT`: Timeout in seconds (default: 600)
- `NINJA_ZAI_CODING_PLAN`: Use Coding Plan API (auto/true/false, default: auto)

### Model Configuration

- `NINJA_MODEL`: Model to use (default: anthropic/claude-haiku-4.5)
- `OPENAI_BASE_URL`: API base URL
- `OPENAI_API_KEY`: API key

## Benefits

1. **Flexibility**: Easy switching between CLI tools
2. **Isolation**: CLI-specific logic is encapsulated
3. **Extensibility**: New CLIs can be added without modifying core code
4. **Testing**: Strategies can be tested independently
5. **Maintenance**: Easier to update CLI-specific behavior

## Backward Compatibility

The refactoring maintains full backward compatibility:
- Default behavior unchanged (`NINJA_CODE_BIN=aider`)
- Existing environment variables work as before
- All Aider error patterns preserved
- Retry logic maintained
