"""
Central configuration defaults for Ninja MCP.

This is the SINGLE SOURCE OF TRUTH for all default values.
Do not hardcode defaults elsewhere - import from here.
"""

# =============================================================================
# MODEL DEFAULTS
# =============================================================================

# Default model for code generation tasks
DEFAULT_CODER_MODEL = "anthropic/claude-haiku-4.5"

# Fallback models if primary is unavailable (in order of preference)
FALLBACK_CODER_MODELS = [
    "anthropic/claude-3-5-haiku-20241022",
    "anthropic/claude-sonnet-4",
    "openai/gpt-4o-mini",
]

# Recommended models for different use cases
RECOMMENDED_MODELS = {
    # Claude models (Anthropic)
    "anthropic/claude-haiku-4.5": "Claude Haiku 4.5 - fast and capable",
    "anthropic/claude-sonnet-4": "Claude Sonnet 4 - excellent for complex code",
    "anthropic/claude-opus-4": "Claude Opus 4 - most capable",
    # GPT models (OpenAI)
    "openai/gpt-4o": "GPT-4o - OpenAI's flagship model",
    "openai/gpt-4o-mini": "GPT-4o Mini - fast and cheap",
    # Qwen models
    "qwen/qwen-2.5-coder-32b-instruct": "Qwen 2.5 Coder 32B - large coding model",
    # DeepSeek models
    "deepseek/deepseek-chat": "DeepSeek Chat - general purpose",
    # Google models
    "google/gemini-pro-1.5": "Gemini Pro 1.5 - Google's advanced model",
    # Meta models
    "meta-llama/llama-3.1-70b-instruct": "Llama 3.1 70B - Meta's open model",
}

# =============================================================================
# API DEFAULTS
# =============================================================================

DEFAULT_OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SEC = 600

# =============================================================================
# DAEMON DEFAULTS
# =============================================================================

DEFAULT_PORTS = {
    "coder": 8100,
    "researcher": 8101,
    "secretary": 8102,
}

# =============================================================================
# BINARY DEFAULTS
# =============================================================================

DEFAULT_CODE_BIN = "aider"
