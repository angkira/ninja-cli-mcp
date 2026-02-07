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
    "anthropic/claude-sonnet-4-20250514",
    "openai/gpt-4o-mini",
]

# Recommended models for different use cases
RECOMMENDED_MODELS = {
    # Claude models (Anthropic via OpenRouter)
    "anthropic/claude-haiku-4.5": "Claude Haiku 4.5 - fast and capable",
    "anthropic/claude-sonnet-4-20250514": "Claude Sonnet 4 - excellent for complex code",
    "anthropic/claude-opus-4": "Claude Opus 4 - most capable",
    # GPT models (OpenAI via OpenRouter)
    "openai/gpt-4o": "GPT-4o - OpenAI's flagship model",
    "openai/gpt-4o-mini": "GPT-4o Mini - fast and cheap",
    # Qwen 2.5 models (via OpenRouter)
    "qwen/qwen-2.5-coder-32b-instruct": "Qwen 2.5 Coder 32B - large coding model",
    # Qwen 3 models (via OpenRouter) - Latest generation
    "qwen/qwen3-235b-a22b": "Qwen3 235B - most powerful Qwen model",
    "qwen/qwen3-32b": "Qwen3 32B - balanced performance",
    "qwen/qwen3-30b-a3b": "Qwen3 30B A3B - efficient MoE model",
    "qwen/qwen3-14b": "Qwen3 14B - good balance of speed/quality",
    "qwen/qwen3-8b": "Qwen3 8B - fast and capable",
    "qwen/qwen3-4b": "Qwen3 4B - lightweight and fast",
    "qwen/qwen3-1.7b": "Qwen3 1.7B - ultra-fast for simple tasks",
    # DeepSeek models (via OpenRouter)
    "deepseek/deepseek-chat": "DeepSeek Chat - general purpose",
    "deepseek/deepseek-coder": "DeepSeek Coder - specialized for code",
    # Google models (via OpenRouter)
    "google/gemini-3-flash": "Gemini 3 Flash - latest fast model (78% SWE-bench)",
    "google/gemini-3-pro": "Gemini 3 Pro - most capable Google model",
    "google/gemini-2.5-flash": "Gemini 2.5 Flash - fast and efficient",
    "google/gemini-2.5-pro": "Gemini 2.5 Pro - advanced reasoning",
    # Meta models (via OpenRouter)
    "meta-llama/llama-3.1-70b-instruct": "Llama 3.1 70B - Meta's open model",
    "meta-llama/llama-3.3-70b-instruct": "Llama 3.3 70B - latest Llama",
    # Z.ai models (via OpenCode native)
    "glm-4.7": "GLM-4.7 - complex multi-step tasks with Coding Plan API",
    "glm-4.6v": "GLM-4.6V - high concurrency parallel tasks",
    "glm-4.0": "GLM-4.0 - fast and cost-effective",
}

# =============================================================================
# TASK-BASED MODEL DEFAULTS
# =============================================================================

# Default models for different task types
DEFAULT_MODEL_QUICK = "anthropic/claude-haiku-4.5"  # Fast simple tasks
DEFAULT_MODEL_SEQUENTIAL = "anthropic/claude-haiku-4.5"  # Complex multi-step tasks
DEFAULT_MODEL_PARALLEL = "anthropic/claude-haiku-4.5"  # High-concurrency parallel tasks

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
    ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Fast & cost-effective"),
    ("anthropic/claude-opus-4", "Claude Opus 4", "Most powerful"),
    ("anthropic/claude-sonnet-4-20250514", "Claude Sonnet 4", "Latest balanced model"),
    ("anthropic/claude-3-7-sonnet-latest", "Claude 3.7 Sonnet", "Previous gen balanced"),
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
    ("glm-4.7", "GLM-4.7", "Complex multi-step tasks - supports Coding Plan API"),
    ("glm-4.6v", "GLM-4.6V", "High concurrency (20 parallel) - best for parallel tasks"),
    ("glm-4.0", "GLM-4.0", "Fast and cost-effective - quick tasks"),
]

# =============================================================================
# OPENROUTER MODELS (For Aider and OpenRouter API)
# =============================================================================

OPENROUTER_MODELS = [
    # Claude models (Anthropic)
    ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "Fast & cost-effective"),
    ("anthropic/claude-opus-4", "Claude Opus 4", "Most powerful Claude model"),
    (
        "anthropic/claude-sonnet-4-20250514",
        "Claude Sonnet 4",
        "Latest Claude - Balanced performance",
    ),
    # GPT models (OpenAI)
    ("openai/gpt-4o", "GPT-4o", "OpenAI's flagship multimodal model"),
    ("openai/gpt-4o-mini", "GPT-4o Mini", "Fast and cheap"),
    ("openai/o1", "O1", "OpenAI reasoning model"),
    ("openai/o3-mini", "O3 Mini", "Latest OpenAI reasoning model"),
    # Qwen 3 models (Latest generation)
    ("qwen/qwen3-235b-a22b", "Qwen3 235B", "Most powerful Qwen - 235B MoE"),
    ("qwen/qwen3-235b-a22b:free", "Qwen3 235B (Free)", "Most powerful Qwen - Free tier"),
    ("qwen/qwen3-max", "Qwen3 Max", "Maximum capability Qwen3"),
    ("qwen/qwen3-32b", "Qwen3 32B", "Balanced performance"),
    ("qwen/qwen3-32b:free", "Qwen3 32B (Free)", "Balanced performance - Free tier"),
    ("qwen/qwen3-30b-a3b", "Qwen3 30B A3B", "Efficient MoE model"),
    ("qwen/qwen3-30b-a3b:free", "Qwen3 30B A3B (Free)", "Efficient MoE - Free tier"),
    ("qwen/qwen3-14b", "Qwen3 14B", "Good balance of speed/quality"),
    ("qwen/qwen3-14b:free", "Qwen3 14B (Free)", "Good balance - Free tier"),
    ("qwen/qwen3-8b", "Qwen3 8B", "Fast and capable"),
    ("qwen/qwen3-8b:free", "Qwen3 8B (Free)", "Fast and capable - Free tier"),
    ("qwen/qwen3-4b", "Qwen3 4B", "Lightweight and fast"),
    ("qwen/qwen3-4b:free", "Qwen3 4B (Free)", "Lightweight - Free tier"),
    ("qwen/qwen3-1.7b:free", "Qwen3 1.7B (Free)", "Ultra-fast - Free tier"),
    # Qwen 3 Coder models (Specialized for code)
    ("qwen/qwen3-coder-480b-a35b", "Qwen3 Coder 480B", "Most powerful coding model"),
    (
        "qwen/qwen3-coder-480b-a35b:free",
        "Qwen3 Coder 480B (Free)",
        "Most powerful coder - Free tier",
    ),
    ("qwen/qwen3-coder-32b", "Qwen3 Coder 32B", "Balanced coding model"),
    ("qwen/qwen3-coder-32b:free", "Qwen3 Coder 32B (Free)", "Balanced coder - Free tier"),
    ("qwen/qwen3-coder-14b", "Qwen3 Coder 14B", "Fast coding model"),
    ("qwen/qwen3-coder-8b", "Qwen3 Coder 8B", "Lightweight coding model"),
    # Qwen 3 Thinking/Reasoning models
    ("qwen/qwen3-235b-a22b:thinking", "Qwen3 235B Thinking", "Deep reasoning mode"),
    ("qwen/qwen3-32b:thinking", "Qwen3 32B Thinking", "Reasoning mode"),
    # Qwen 2.5 models
    ("qwen/qwen-2.5-coder-32b-instruct", "Qwen 2.5 Coder 32B", "Large coding model"),
    (
        "qwen/qwen-2.5-coder-32b-instruct:free",
        "Qwen 2.5 Coder 32B (Free)",
        "Large coding - Free tier",
    ),
    ("qwen/qwen-2.5-72b-instruct", "Qwen 2.5 72B", "Large general model"),
    ("qwen/qwen-2.5-72b-instruct:free", "Qwen 2.5 72B (Free)", "Large general - Free tier"),
    # DeepSeek models
    ("deepseek/deepseek-chat", "DeepSeek Chat", "General purpose chat"),
    ("deepseek/deepseek-chat:free", "DeepSeek Chat (Free)", "General purpose - Free tier"),
    ("deepseek/deepseek-coder", "DeepSeek Coder", "Specialized for code"),
    ("deepseek/deepseek-r1", "DeepSeek R1", "Reasoning model"),
    ("deepseek/deepseek-r1:free", "DeepSeek R1 (Free)", "Reasoning - Free tier"),
    # Google models
    ("google/gemini-3-flash", "Gemini 3 Flash", "Latest fast model - 78% SWE-bench"),
    ("google/gemini-3-pro", "Gemini 3 Pro", "Most capable Google model"),
    ("google/gemini-2.5-flash", "Gemini 2.5 Flash", "Fast and efficient"),
    ("google/gemini-2.5-pro", "Gemini 2.5 Pro", "Advanced reasoning"),
    # Meta Llama models
    ("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B", "Latest Llama"),
    ("meta-llama/llama-3.3-70b-instruct:free", "Llama 3.3 70B (Free)", "Latest Llama - Free tier"),
    ("meta-llama/llama-3.1-70b-instruct", "Llama 3.1 70B", "Proven open model"),
    (
        "meta-llama/llama-3.1-70b-instruct:free",
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
    "anthropic/claude-sonnet-4-20250514": {
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
    # Qwen 3 models (via OpenRouter)
    "qwen/qwen3-235b-a22b": {
        "provider": "openrouter",
        "best_for": ["sequential"],
        "concurrent_limit": 3,
        "cost": "high",
        "livebench_score": 87.0,
        "supports_coding_plan_api": False,
    },
    "qwen/qwen3-32b": {
        "provider": "openrouter",
        "best_for": ["sequential", "quick"],
        "concurrent_limit": 5,
        "cost": "medium",
        "livebench_score": 84.0,
        "supports_coding_plan_api": False,
    },
    "qwen/qwen3-30b-a3b": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 8,
        "cost": "low",
        "livebench_score": 82.0,
        "supports_coding_plan_api": False,
    },
    "qwen/qwen3-14b": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 78.0,
        "supports_coding_plan_api": False,
    },
    "qwen/qwen3-8b": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 15,
        "cost": "very_low",
        "livebench_score": 74.0,
        "supports_coding_plan_api": False,
    },
    # DeepSeek models (via OpenRouter)
    "deepseek/deepseek-r1": {
        "provider": "openrouter",
        "best_for": ["sequential", "reasoning"],
        "concurrent_limit": 5,
        "cost": "medium",
        "livebench_score": 86.0,
        "supports_coding_plan_api": False,
    },
    "deepseek/deepseek-coder": {
        "provider": "openrouter",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 80.0,
        "supports_coding_plan_api": False,
    },
    # Gemini models (via Gemini CLI or OpenRouter)
    "gemini-3-flash": {
        "provider": "google",
        "best_for": ["quick", "parallel", "coding"],
        "concurrent_limit": 10,
        "cost": "low",
        "livebench_score": 85.0,
        "swe_bench_score": 78.0,
        "supports_coding_plan_api": False,
        "operator": "gemini",
    },
    "gemini-3-pro": {
        "provider": "google",
        "best_for": ["sequential", "coding", "math"],
        "concurrent_limit": 5,
        "cost": "high",
        "livebench_score": 89.0,
        "supports_coding_plan_api": False,
        "operator": "gemini",
    },
    "gemini-2.5-flash": {
        "provider": "google",
        "best_for": ["quick", "parallel"],
        "concurrent_limit": 15,
        "cost": "very_low",
        "livebench_score": 80.0,
        "supports_coding_plan_api": False,
        "operator": "gemini",
    },
    "gemini-2.5-pro": {
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
