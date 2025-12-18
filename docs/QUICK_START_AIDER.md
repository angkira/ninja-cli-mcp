# Quick Start: Using ninja-cli-mcp with Aider

This guide will get you up and running with ninja-cli-mcp + Aider + OpenRouter in under 5 minutes.

## Prerequisites

- Python 3.11+
- Git
- OpenRouter API key ([get one here](https://openrouter.ai/))

## Installation (1 minute)

```bash
# Clone the repository
git clone https://github.com/angkira/ninja-cli-mcp.git
cd ninja-cli-mcp

# Install dependencies including Aider
uv sync --extra aider

# Configure with OpenRouter API key
cat > ~/.ninja-cli-mcp.env << EOF
export OPENROUTER_API_KEY='your-openrouter-api-key-here'
export NINJA_MODEL='qwen/qwen3-coder-30b-a3b-instruct'
export NINJA_CODE_BIN='aider'
export NINJA_TIMEOUT_SEC=300
EOF

# Load configuration
source ~/.ninja-cli-mcp.env
```

## Test It (1 minute)

```bash
# Create a test repository
mkdir /tmp/test_repo && cd /tmp/test_repo
git init && git config user.email "you@example.com" && git config user.name "Your Name"

# Create a simple Python file
echo 'def hello():
    print("Hello")' > test.py
git add test.py && git commit -m "Initial commit"

# Use ninja-cli-mcp to add a docstring
cd ~/ninja-cli-mcp
uv run python -m ninja_cli_mcp.cli quick-task \
  --repo-root /tmp/test_repo \
  --task "Add a docstring to the hello() function"

# Check the result
cat /tmp/test_repo/test.py
```

Expected output:
```python
def hello():
    """Print a greeting message."""
    print("Hello")
```

## Use with GitHub Copilot CLI (2 minutes)

```bash
# Install for GitHub Copilot CLI
cd ~/ninja-cli-mcp
bash scripts/install_copilot_cli_mcp.sh

# Restart your terminal or IDE

# In your project:
gh copilot

# Then use ninja-cli-mcp:
> Use ninja_quick_task to refactor the user authentication module
```

## Use with Claude Desktop

Add to Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "ninja-cli-mcp": {
      "command": "/path/to/ninja-cli-mcp/scripts/run_server.sh",
      "args": []
    }
  }
}
```

## Try Different Models

```bash
# Fast and capable (default)
export NINJA_MODEL='qwen/qwen3-coder-30b-a3b-instruct'

# Best quality
export NINJA_MODEL='anthropic/claude-sonnet-4'

# Fast OpenAI
export NINJA_MODEL='openai/gpt-4o'

# Cost-effective
export NINJA_MODEL='deepseek/deepseek-coder'
```

## Run Tests

```bash
cd ~/ninja-cli-mcp
bash scripts/test_aider_integration.sh
```

## Common Commands

### Quick Task
```bash
uv run python -m ninja_cli_mcp.cli quick-task \
  --repo-root /path/to/repo \
  --task "Your task description"
```

### Run Tests
```bash
uv run python -m ninja_cli_mcp.cli run-tests \
  --repo-root /path/to/repo \
  --commands "pytest tests/" "npm test"
```

### Show Configuration
```bash
source ~/.ninja-cli-mcp.env
uv run python -m ninja_cli_mcp.cli show-config
```

### List Available Models
```bash
uv run python -m ninja_cli_mcp.cli list-models
```

## Troubleshooting

### "Aider not found"
```bash
uv sync --extra aider
```

### "API key not set"
```bash
echo "export OPENROUTER_API_KEY='your-key'" >> ~/.ninja-cli-mcp.env
source ~/.ninja-cli-mcp.env
```

### "Task timed out"
```bash
echo "export NINJA_TIMEOUT_SEC=600" >> ~/.ninja-cli-mcp.env
```

## What Just Happened?

1. **ninja-cli-mcp** is an MCP server that delegates code tasks
2. **Aider** is the coding agent that actually edits your code
3. **OpenRouter** provides access to 200+ AI models
4. **Your chosen model** (Qwen, Claude, GPT, etc.) does the thinking

This architecture keeps your main AI assistant (GitHub Copilot, Claude Desktop, etc.) separate from the code executor, providing better security and flexibility.

## Next Steps

- Read [CODING_AGENT_CLI_OPTIONS.md](CODING_AGENT_CLI_OPTIONS.md) for alternative CLIs
- Check [AIDER_INTEGRATION_COMPLETE.md](AIDER_INTEGRATION_COMPLETE.md) for detailed info
- See [TROUBLESHOOTING_ABORT_ERROR.md](TROUBLESHOOTING_ABORT_ERROR.md) if issues arise

## Support

- Issues: https://github.com/angkira/ninja-cli-mcp/issues
- Aider docs: https://aider.chat/docs/
- OpenRouter: https://openrouter.ai/

**Happy coding!** 🚀
