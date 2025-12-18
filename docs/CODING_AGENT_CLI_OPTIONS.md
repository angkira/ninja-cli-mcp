# Coding Agent CLI Options for ninja-cli-mcp

## Overview

The ninja-cli-mcp server delegates code execution to AI coding agent CLIs. These CLIs must support:
- OpenRouter API (for model flexibility)
- File editing capabilities
- Command-line interface
- Automated workflows

## Recommended Options

### 1. **Aider** (RECOMMENDED)

**Pros:**
- ✅ Native OpenRouter support
- ✅ Mature, actively maintained
- ✅ Python-based (easy integration)
- ✅ Extensive documentation
- ✅ Git integration built-in
- ✅ Works with any OpenAI-compatible API
- ✅ Can be installed via pip

**Installation:**
```bash
pip install aider-chat
```

**Configuration:**
```bash
export OPENROUTER_API_KEY='your-key'
aider --model openrouter/anthropic/claude-sonnet-4
```

**Integration with ninja-cli-mcp:**
```bash
export NINJA_CODE_BIN='aider'
export OPENROUTER_API_KEY='your-key'
export NINJA_MODEL='anthropic/claude-sonnet-4'
```

**Repository:** https://github.com/paul-gauthier/aider
**Documentation:** https://aider.chat/docs/

---

### 2. **Qwen Code CLI** (Official)

**Pros:**
- ✅ Fork of Gemini CLI optimized for code
- ✅ Native OpenRouter support
- ✅ Free tier: 2000 requests/day
- ✅ Optimized for Qwen3-Coder models
- ✅ TypeScript/Node.js based

**Installation:**
```bash
npm install -g @qwen-code/qwen-code
```

**Configuration:**
```bash
export OPENAI_API_KEY='your-openrouter-key'
export OPENAI_BASE_URL='https://openrouter.ai/api/v1'
export OPENAI_MODEL='qwen/qwen3-coder'
qwen --version
```

**Integration with ninja-cli-mcp:**
```bash
export NINJA_CODE_BIN='qwen'
export OPENROUTER_API_KEY='your-key'
export NINJA_MODEL='qwen/qwen3-coder'
```

**Repository:** https://github.com/QwenLM/qwen-code
**Documentation:** https://www.datacamp.com/tutorial/qwen-code

---

### 3. **Gemini CLI with OpenRouter Fork**

**Pros:**
- ✅ Multiple community forks with OpenRouter support
- ✅ Based on Google's Gemini CLI
- ✅ TypeScript/Node.js based

**Installation:**
```bash
npm install -g @chameleon-nexus-tech/gemini-cli-openrouter
# OR
npm install -g @shrwnsan/gemini-cli-openrouter
```

**Configuration:**
```bash
export AI_ENGINE='openrouter'
export AI_API_KEY='your-openrouter-key'
export AI_MODEL='anthropic/claude-sonnet-4'
export GEMINI_API_KEY='any-value'  # Required but not used
gemini --version
```

**Integration with ninja-cli-mcp:**
```bash
export NINJA_CODE_BIN='gemini'
export OPENROUTER_API_KEY='your-key'
export NINJA_MODEL='anthropic/claude-sonnet-4'
```

**Repositories:**
- https://github.com/shrwnsan/gemini-cli-openrouter
- https://github.com/chameleon-nexus-tech/gemini-cli-openrouter

---

## Comparison Table

| Feature | Aider | Qwen Code CLI | Gemini CLI OpenRouter |
|---------|-------|---------------|----------------------|
| **Language** | Python | TypeScript/Node.js | TypeScript/Node.js |
| **Installation** | pip | npm | npm |
| **OpenRouter Support** | Native | Native | Fork-based |
| **Maturity** | Very High | High | Medium |
| **Community** | Large | Growing | Small |
| **Documentation** | Excellent | Good | Fair |
| **Git Integration** | Built-in | Yes | Yes |
| **Model Support** | Any OpenRouter | Optimized for Qwen | Any OpenRouter |
| **Free Tier** | N/A (uses your API) | 2000 req/day | N/A |

---

## Implementation Plan for ninja-cli-mcp

### Option A: Bundle Aider (RECOMMENDED)

Add aider as a Python dependency:

**pyproject.toml:**
```toml
[project]
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0.0",
    "anyio>=4.0.0",
    "aider-chat>=0.60.0",  # Add this
]
```

**Default Configuration:**
```bash
# Auto-detect or default to aider
export NINJA_CODE_BIN="${NINJA_CODE_BIN:-aider}"
```

### Option B: Install Qwen Code CLI

Add installation script:

**scripts/install_qwen_cli.sh:**
```bash
#!/usr/bin/env bash
# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo "Error: npm is required to install Qwen Code CLI"
    exit 1
fi

# Install Qwen Code CLI globally
npm install -g @qwen-code/qwen-code

# Verify installation
if command -v qwen &> /dev/null; then
    echo "Qwen Code CLI installed successfully"
    qwen --version
else
    echo "Error: Qwen Code CLI installation failed"
    exit 1
fi
```

### Option C: Support Multiple CLIs (BEST)

Detect and use any available CLI:

**scripts/detect_coding_cli.sh:**
```bash
#!/usr/bin/env bash
# Detect available coding agent CLI

if command -v aider &> /dev/null; then
    echo "aider"
elif command -v qwen &> /dev/null; then
    echo "qwen"
elif command -v gemini &> /dev/null; then
    echo "gemini"
elif command -v claude &> /dev/null; then
    echo "claude"
else
    echo ""
fi
```

---

## Recommendation

**Use Aider as the default** because:

1. ✅ **Easy Integration**: Python package, installed via pip/uv
2. ✅ **Mature**: Battle-tested, large community
3. ✅ **Best Documentation**: Extensive docs and examples
4. ✅ **OpenRouter Native**: No fork needed
5. ✅ **Flexible**: Works with any model via OpenRouter

**Fallback to Qwen Code CLI** if:
- User prefers Node.js ecosystem
- Optimizing for Qwen models specifically
- Want free tier benefits

---

## Next Steps

1. Update `pyproject.toml` to include `aider-chat` as dependency
2. Update installation scripts to install Aider by default
3. Update `NINJA_CODE_BIN` default from `ninja-code` to `aider`
4. Add CLI detection script for flexibility
5. Update documentation with new default
6. Update `.ninja-cli-mcp.env` template

---

## References

- Aider: https://aider.chat/
- Qwen Code CLI: https://github.com/QwenLM/qwen-code
- OpenRouter: https://openrouter.ai/
- Gemini CLI OpenRouter fork: https://github.com/shrwnsan/gemini-cli-openrouter
