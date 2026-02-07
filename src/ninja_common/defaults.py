"""
Central configuration defaults for Ninja MCP.

This is the SINGLE SOURCE OF TRUTH for all default values.
Do not hardcode defaults elsewhere - import from here.
"""

# =============================================================================
# MODEL DEFAULTS
# =============================================================================

# Default model for code generation tasks
DEFAULT_CODER_MODEL = "opencode/glm-4.7-free"

# Fallback models if primary is unavailable (in order of preference)
FALLBACK_CODER_MODELS = [
    "openrouter/anthropic/claude-haiku-4.5",
    "openrouter/anthropic/claude-3-5-haiku-20241022",
    "openrouter/anthropic/claude-sonnet-4-20250514",
    "openrouter/openai/gpt-4o-mini",
    "opencode/gpt-5-nano",
    "google/gemini-2.5-flash",
]

# Recommended models for different use cases
RECOMMENDED_MODELS = {
    # Free models (work out of box)
    "opencode/glm-4.7-free": "GLM-4.7 Free - works out of box, fast and capable",
    "opencode/gpt-5-nano": "GPT-5 Nano - free OpenCode model",
    "google/gemini-2.5-flash": "Gemini 2.5 Flash - free with GEMINI_API_KEY",
    # Claude models (Anthropic via OpenRouter)
    "openrouter/anthropic/claude-haiku-4.5": "Claude Haiku 4.5 - fast and capable",
    "openrouter/anthropic/claude-sonnet-4-20250514": "Claude Sonnet 4 - excellent for complex code",
    "openrouter/anthropic/claude-opus-4": "Claude Opus 4 - most capable",
    # GPT models (OpenAI via OpenRouter)
    "openrouter/openai/gpt-4o": "GPT-4o - OpenAI's flagship model",
    "openrouter/openai/gpt-4o-mini": "GPT-4o Mini - fast and cheap",
    # Qwen 2.5 models (via OpenRouter)
    "openrouter/qwen/qwen-2.5-coder-32b-instruct": "Qwen 2.5 Coder 32B - large coding model",
    # Qwen 3 models (via OpenRouter) - Latest generation
    "openrouter/qwen/qwen3-235b-a22b": "Qwen3 235B - most powerful Qwen model",
    "openrouter/qwen/qwen3-32b": "Qwen3 32B - balanced performance",
    "openrouter/qwen/qwen3-30b-a3b": "Qwen3 30B A3B - efficient MoE model",
    "openrouter/qwen/qwen3-14b": "Qwen3 14B - good balance of speed/quality",
    "openrouter/qwen/qwen3-8b": "Qwen3 8B - fast and capable",
    "openrouter/qwen/qwen3-4b": "Qwen3 4B - lightweight and fast",
    "openrouter/qwen/qwen3-1.7b": "Qwen3 1.7B - ultra-fast for simple tasks",
    # DeepSeek models (via OpenRouter)
    "openrouter/deepseek/deepseek-chat": "DeepSeek Chat - general purpose",
    "openrouter/deepseek/deepseek-coder": "DeepSeek Coder - specialized for code",
    # Google models (via OpenRouter)
    "openrouter/google/gemini-3-flash": "Gemini 3 Flash - latest fast model (78% SWE-bench)",
    "openrouter/google/gemini-3-pro": "Gemini 3 Pro - most capable Google model",
    "openrouter/google/gemini-2.5-flash": "Gemini 2.5 Flash - fast and efficient",
    "openrouter/google/gemini-2.5-pro": "Gemini 2.5 Pro - advanced reasoning",
    # Meta models (via OpenRouter)
    "openrouter/meta-llama/llama-3.1-70b-instruct": "Llama 3.1 70B - Meta's open model",
    "openrouter/meta-llama/llama-3.3-70b-instruct": "Llama 3.3 70B - latest Llama",
    # Z.ai models (via OpenCode native or Coding Plan API)
    "zai-coding-plan/glm-4.7": "GLM-4.7 - complex multi-step tasks with Coding Plan API",
    "zai-coding-plan/glm-4.6v": "GLM-4.6V - high concurrency parallel tasks",
    "zai/glm-4.7": "GLM-4.7 - fast and capable (native z.ai)",
    "zai/glm-4.0": "GLM-4.0 - fast and cost-effective",
}

# =============================================================================
# TASK-BASED MODEL DEFAULTS
# =============================================================================

# Default models for different task types
DEFAULT_MODEL_QUICK = "opencode/glm-4.7-free"
DEFAULT_MODEL_SEQUENTIAL = "zai-coding-plan/glm-4.7"
DEFAULT_MODEL_PARALLEL = "opencode/glm-4.7-free"

# =============================================================================
# OPENCODE PROVIDERS
# =============================================================================

OPENCODE_PROVIDERS = [
    ("anthropic", "Anthropic", "Claude models - native API"),
    ("google", "Google", "Gemini models - native API"),
    ("openai", "OpenAI", "GPT models - native API"),
    ("github-copilot", "GitHub Copilot", "Via GitHub OAuth"),
    ("openrouter", "OpenRouter", "Multi-provider API - Qwen3, DeepSeek, Llama, etc."),
    ("zai", "Z.ai / Zhipu AI", "GLM models - native Coding Plan API support"),
]

# =============================================================================
# CLAUDE CODE MODELS (Anthropic native)
# =============================================================================

CLAUDE_CODE_MODELS = [
    ("claude-haiku-4", "Claude Haiku 4", "Fast & cost-effective"),
    ("claude-opus-4", "Claude Opus 4", "Most powerful Claude model"),
    ("claude-sonnet-4", "Claude Sonnet 4", "Latest Claude - Balanced performance"),
]

# =============================================================================
# ANTHROPIC MODELS (Native API)
# =============================================================================

ANTHROPIC_MODELS = [
    ("openrouter/anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Fast & cost-effective"),
    ("openrouter/anthropic/claude-opus-4", "Claude Opus 4", "Most powerful"),
    ("openrouter/anthropic/claude-sonnet-4-20250514", "Claude Sonnet 4", "Latest balanced model"),
    ("openrouter/anthropic/claude-3-7-sonnet-latest", "Claude 3.7 Sonnet", "Previous gen balanced"),
]

# =============================================================================
# GOOGLE MODELS (Native API via Gemini CLI)
# =============================================================================

GOOGLE_MODELS = [
    ("gemini-3-flash", "Gemini 3 Flash", "Latest fast model - 78% SWE-bench"),
    ("gemini-3-pro", "Gemini 3 Pro", "Most capable - advanced math & coding"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash", "Fast and efficient"),
    ("gemini-2.5-pro", "Gemini 2.5 Pro", "Advanced reasoning"),
]

# =============================================================================
# OPENAI MODELS (Native API)
# =============================================================================

OPENAI_MODELS = [
    ("openai/gpt-4o", "GPT-4o", "Flagship multimodal"),
    ("openai/gpt-4o-mini", "GPT-4o Mini", "Fast and cheap"),
    ("openai/o1", "O1", "Reasoning model"),
    ("openai/o3-mini", "O3 Mini", "Latest reasoning"),
]

# =============================================================================
# GITHUB COPILOT MODELS (Via GitHub OAuth)
# =============================================================================

GITHUB_COPILOT_MODELS = [
    ("github-copilot/claude-sonnet-4.5", "Claude Sonnet 4.5", "Via Copilot"),
    ("github-copilot/gpt-4o", "GPT-4o", "Via Copilot"),
    ("github-copilot/gemini-3-pro", "Gemini 3 Pro", "Via Copilot"),
]

# =============================================================================
# PERPLEXITY MODELS (Researcher)
# =============================================================================

PERPLEXITY_MODELS = [
    ("sonar", "Sonar", "Fast search-focused model"),
    ("sonar-pro", "Sonar Pro", "Advanced search with better reasoning"),
    ("sonar-reasoning", "Sonar Reasoning", "Complex reasoning with search"),
]

# Valid Perplexity model IDs for validation
VALID_PERPLEXITY_MODELS = ["sonar", "sonar-pro", "sonar-reasoning"]

# =============================================================================
# Z.AI / ZHIPU MODELS
# =============================================================================

ZAI_MODELS = [
    ("zai-coding-plan/glm-4.7", "GLM-4.7", "Complex multi-step tasks - supports Coding Plan API"),
    (
        "zai-coding-plan/glm-4.6v",
        "GLM-4.6V",
        "High concurrency (20 parallel) - best for parallel tasks",
    ),
    ("zai/glm-4.0", "GLM-4.0", "Fast and cost-effective - quick tasks"),
]

# =============================================================================
# OPENROUTER MODELS (For Aider and OpenRouter API)
# =============================================================================

OPENROUTER_MODELS = [
    # Claude models (Anthropic)
    ("openrouter/anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Fast & cost-effective"),
    ("openrouter/anthropic/claude-opus-4", "Claude Opus 4", "Most powerful Claude model"),
    (
        "openrouter/anthropic/claude-sonnet-4-20250514",
        "Claude Sonnet 4",
        "Latest Claude - Balanced performance",
    ),
    # GPT models (OpenAI)
    ("openrouter/openai/gpt-4o", "GPT-4o", "OpenAI's flagship multimodal model"),
    ("openrouter/openai/gpt-4o-mini", "GPT-4o Mini", "Fast and cheap"),
    ("openrouter/openai/o1", "O1", "OpenAI reasoning model"),
    ("openrouter/openai/o3-mini", "O3 Mini", "Latest OpenAI reasoning model"),
    # Qwen 3 models (Latest generation)
    ("openrouter/qwen/qwen3-235b-a22b", "Qwen3 235B", "Most powerful Qwen - 235B MoE"),
    ("openrouter/qwen/qwen3-235b-a22b:free", "Qwen3 235B (Free)", "Most powerful Qwen - Free tier"),
    ("openrouter/qwen/qwen3-max", "Qwen3 Max", "Maximum capability Qwen3"),
    ("openrouter/qwen/qwen3-32b", "Qwen3 32B", "Balanced performance"),
    ("openrouter/qwen/qwen3-32b:free", "Qwen3 32B (Free)", "Balanced performance - Free tier"),
    ("openrouter/qwen/qwen3-30b-a3b", "Qwen3 30B A3B", "Efficient MoE model"),
    ("openrouter/qwen/qwen3-30b-a3b:free", "Qwen3 30B A3B (Free)", "Efficient MoE - Free tier"),
    ("openrouter/qwen/qwen3-14b", "Qwen3 14B", "Good balance of speed/quality"),
    ("openrouter/qwen/qwen3-14b:free", "Qwen3 14B (Free)", "Good balance - Free tier"),
    ("openrouter/qwen/qwen3-8b", "Qwen3 8B", "Fast and capable"),
    ("openrouter/qwen/qwen3-8b:free", "Qwen3 8B (Free)", "Fast and capable - Free tier"),
    ("openrouter/qwen/qwen3-4b", "Qwen3 4B", "Lightweight and fast"),
    ("openrouter/qwen/qwen3-4b:free", "Qwen3 4B (Free)", "Lightweight - Free tier"),
    ("openrouter/qwen/qwen3-1.7b:free", "Qwen3 1.7B (Free)", "Ultra-fast - Free tier"),
    # Qwen 3 Coder models (Specialized for code)
    ("openrouter/qwen/qwen3-coder-480b-a35b", "Qwen3 Coder 480B", "Most powerful coding model"),
    (
        "openrouter/qwen/qwen3-coder-480b-a35b:free",
        "Qwen3 Coder 480B (Free)",
        "Most powerful coder - Free tier",
    ),
    ("openrouter/qwen/qwen3-coder-32b", "Qwen3 Coder 32B", "Balanced coding model"),
    (
        "openrouter/qwen/qwen3-coder-32b:free",
        "Qwen3 Coder 32B (Free)",
        "Balanced coder - Free tier",
    ),
    ("openrouter/qwen/qwen3-coder-14b", "Qwen3 Coder 14B", "Fast coding model"),
    ("openrouter/qwen/qwen3-coder-8b", "Qwen3 Coder 8B", "Lightweight coding model"),
    # Qwen 3 Thinking/Reasoning models
    ("openrouter/qwen/qwen3-235b-a22b:thinking", "Qwen3 235B Thinking", "Deep reasoning mode"),
    ("openrouter/qwen/qwen3-32b:thinking", "Qwen3 32B Thinking", "Reasoning mode"),
    # Qwen 2.5 models
    ("openrouter/qwen/qwen-2.5-coder-32b-instruct", "Qwen 2.5 Coder 32B", "Large coding model"),
    (
        "openrouter/qwen/qwen-2.5-coder-32b-instruct:free",
        "Qwen 2.5 Coder 32B (Free)",
        "Large coding - Free tier",
    ),
    ("openrouter/qwen/qwen-2.5-72b-instruct", "Qwen 2.5 72B", "Large general model"),
    (
        "openrouter/qwen/qwen-2.5-72b-instruct:free",
        "Qwen 2.5 72B (Free)",
        "Large general - Free tier",
    ),
    # DeepSeek models
    ("openrouter/deepseek/deepseek-chat", "DeepSeek Chat", "General purpose chat"),
    (
        "openrouter/deepseek/deepseek-chat:free",
        "DeepSeek Chat (Free)",
        "General purpose - Free tier",
    ),
    ("openrouter/deepseek/deepseek-coder", "DeepSeek Coder", "Specialized for code"),
    ("openrouter/deepseek/deepseek-r1", "DeepSeek R1", "Reasoning model"),
    ("openrouter/deepseek/deepseek-r1:free", "DeepSeek R1 (Free)", "Reasoning - Free tier"),
    # Google models
    ("openrouter/google/gemini-3-flash", "Gemini 3 Flash", "Latest fast model - 78% SWE-bench"),
    ("openrouter/google/gemini-3-pro", "Gemini 3 Pro", "Most capable Google model"),
    ("openrouter/google/gemini-2.5-flash", "Gemini 2.5 Flash", "Fast and efficient"),
    ("openrouter/google/gemini-2.5-pro", "Gemini 2.5 Pro", "Advanced reasoning"),
    # Meta Llama models
    ("openrouter/meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B", "Latest Llama"),
    (
        "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        "Llama 3.3 70B (Free)",
        "Latest Llama - Free tier",
    ),
    ("openrouter/meta-llama/llama-3.1-70b-instruct", "Llama 3.1 70B", "Proven open model"),
    (
        "openrouter/meta-llama/llama-3.1-70b-instruct:free",
        "Llama 3.1 70B (Free)",
        "Proven open model - Free tier",
    ),
]

# Valid OpenRouter providers for model filtering
OPENROUTER_PROVIDERS = [
    "anthropic",
    "openai",
    "qwen",
    "deepseek",
    "google",
    "meta-llama",
    "mistralai",
    "cohere",
]

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
    "zai-coding-plan/glm-4.6v": {
        "provider": "z.ai",
        "best_for": ["parallel"],
        "concurrent_limit": 20,
        "cost": "low",
        "livebench_score": None,
        "supports_coding_plan_api": False,
    },
    "zai-coding-plan/glm-4.7": {
        "provider": "z.ai",
        "best_for": ["sequential"],
        "concurrent_limit": 5,
        "cost": "medium",
        "livebench_score": 84.9,
        "supports_coding_plan_api": True,
    },
    "zai/glm-4.0": {
        "provider": "z.ai",
        "best_for": ["quick"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 75.0,
        "supports_coding_plan_api": False,
    },
    # OpenRouter models (via Aider)
    "openrouter/anthropic/claude-sonnet-4-20250514": {
        "provider": "openrouter",
        "best_for": ["sequential", "quick"],
        "concurrent_limit": 5,
        "cost": "high",
        "livebench_score": 88.0,
        "supports_coding_plan_api": False,
    },
    "openrouter/anthropic/claude-haiku-4.5": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 82.0,
        "supports_coding_plan_api": False,
    },
    "openrouter/anthropic/claude-opus-4": {
        "provider": "openrouter",
        "best_for": ["sequential"],
        "concurrent_limit": 3,
        "cost": "very_high",
        "livebench_score": 91.0,
        "supports_coding_plan_api": False,
    },
    # Qwen 3 models (via OpenRouter)
    "openrouter/qwen/qwen3-235b-a22b": {
        "provider": "openrouter",
        "best_for": ["sequential"],
        "concurrent_limit": 3,
        "cost": "high",
        "livebench_score": 87.0,
        "supports_coding_plan_api": False,
    },
    "openrouter/qwen/qwen3-32b": {
        "provider": "openrouter",
        "best_for": ["sequential", "quick"],
        "concurrent_limit": 5,
        "cost": "medium",
        "livebench_score": 84.0,
        "supports_coding_plan_api": False,
    },
    "openrouter/qwen/qwen3-30b-a3b": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 8,
        "cost": "low",
        "livebench_score": 82.0,
        "supports_coding_plan_api": False,
    },
    "openrouter/qwen/qwen3-14b": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 78.0,
        "supports_coding_plan_api": False,
    },
    "openrouter/qwen/qwen3-8b": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 15,
        "cost": "very_low",
        "livebench_score": 74.0,
        "supports_coding_plan_api": False,
    },
    # DeepSeek models (via OpenRouter)
    "openrouter/deepseek/deepseek-r1": {
        "provider": "openrouter",
        "best_for": ["sequential", "reasoning"],
        "concurrent_limit": 5,
        "cost": "medium",
        "livebench_score": 86.0,
        "supports_coding_plan_api": False,
    },
    "openrouter/deepseek/deepseek-coder": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 80.0,
        "supports_coding_plan_api": False,
    },
    # Gemini models (via Gemini CLI or OpenRouter)
    "google/gemini-3-flash": {
        "provider": "google",
        "best_for": ["quick", "parallel", "coding"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 85.0,
        "swe_bench_score": 78.0,
        "supports_coding_plan_api": False,
        "operator": "gemini",
    },
    "google/gemini-3-pro": {
        "provider": "google",
        "best_for": ["sequential", "coding", "math"],
        "concurrent_limit": 5,
        "cost": "high",
        "livebench_score": 89.0,
        "supports_coding_plan_api": False,
        "operator": "gemini",
    },
    "google/gemini-2.5-flash": {
        "provider": "google",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 15,
        "cost": "very_low",
        "livebench_score": 80.0,
        "supports_coding_plan_api": False,
        "operator": "gemini",
    },
    "google/gemini-2.5-pro": {
        "provider": "google",
        "best_for": ["sequential", "reasoning"],
        "concurrent_limit": 5,
        "cost": "medium",
        "livebench_score": 86.0,
        "supports_coding_plan_api": False,
        "operator": "gemini",
    },
    # Claude Code models (native Anthropic via Claude CLI)
    "claude-sonnet-4": {
        "provider": "anthropic",
        "best_for": ["sequential", "quick"],
        "concurrent_limit": 5,
        "cost": "high",
        "livebench_score": 88.0,
        "supports_coding_plan_api": False,
        "operator": "claude",
    },
    "claude-opus-4": {
        "provider": "anthropic",
        "best_for": ["sequential"],
        "concurrent_limit": 3,
        "cost": "very_high",
        "livebench_score": 91.0,
        "supports_coding_plan_api": False,
        "operator": "claude",
    },
    "claude-haiku-4": {
        "provider": "anthropic",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 82.0,
        "supports_coding_plan_api": False,
        "operator": "claude",
    },
    # Perplexity models (for researcher)
    "sonar": {
        "provider": "perplexity",
        "best_for": ["search"],
        "concurrent_limit": 10,
        "cost": "low",
        "supports_search": True,
    },
    "sonar-pro": {
        "provider": "perplexity",
        "best_for": ["search", "reasoning"],
        "concurrent_limit": 5,
        "cost": "medium",
        "supports_search": True,
    },
    "sonar-reasoning": {
        "provider": "perplexity",
        "best_for": ["reasoning", "search"],
        "concurrent_limit": 3,
        "cost": "high",
        "supports_search": True,
    },
}


# =============================================================================
# MODEL PREFERENCES
# =============================================================================

# Cost vs Quality preference (default: balanced)
DEFAULT_PREFER_COST = False
DEFAULT_PREFER_QUALITY = False

# =============================================================================
# PROVIDER TO MODEL LIST MAPPING
# =============================================================================

# Maps OpenCode provider names to their available model lists
PROVIDER_MODELS = {
    "anthropic": ANTHROPIC_MODELS,
    "google": GOOGLE_MODELS,
    "openai": OPENAI_MODELS,
    "github-copilot": GITHUB_COPILOT_MODELS,
    "openrouter": OPENROUTER_MODELS,
    "zai": ZAI_MODELS,
}
