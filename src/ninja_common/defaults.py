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
    "resources": 8106,
    "prompts": 8107,
}

# =============================================================================
# BINARY DEFAULTS
# =============================================================================

DEFAULT_CODE_BIN = "aider"

# =============================================================================
# SAFETY DEFAULTS
# =============================================================================

# Safety mode for git-based protection against file overwrites
# - "auto": Automatically commit uncommitted changes before running tasks (default)
# - "strict": Refuse to run with uncommitted changes
# - "warn": Warn but allow execution
# - "off": Disable all safety checks (not recommended)
DEFAULT_SAFETY_MODE = "auto"

# Whether to create safety tags for recovery
DEFAULT_CREATE_SAFETY_TAGS = True

# =============================================================================
# MODEL DATABASE FOR INTELLIGENT SELECTION
# =============================================================================

MODEL_DATABASE = {
    # Z.ai models (via OpenCode with native support)
    "glm-4.6v": {
        "provider": "z.ai",
        "best_for": ["parallel"],
        "concurrent_limit": 20,
        "cost": "low",
        "livebench_score": None,  # Not yet benchmarked
        "supports_coding_plan_api": False,
    },
    "glm-4.7": {
        "provider": "z.ai",
        "best_for": ["sequential"],
        "concurrent_limit": 5,
        "cost": "medium",
        "livebench_score": 84.9,
        "supports_coding_plan_api": True,
    },
    "glm-4.0": {
        "provider": "z.ai",
        "best_for": ["quick"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 75.0,
        "supports_coding_plan_api": False,
    },
    # OpenRouter models (via Aider)
    "anthropic/claude-sonnet-4": {
        "provider": "openrouter",
        "best_for": ["sequential", "quick"],
        "concurrent_limit": 5,
        "cost": "high",
        "livebench_score": 88.0,
        "supports_coding_plan_api": False,
    },
    "anthropic/claude-haiku-4.5": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 82.0,
        "supports_coding_plan_api": False,
    },
    "anthropic/claude-opus-4": {
        "provider": "openrouter",
        "best_for": ["sequential"],
        "concurrent_limit": 3,
        "cost": "very_high",
        "livebench_score": 91.0,
        "supports_coding_plan_api": False,
    },
}
