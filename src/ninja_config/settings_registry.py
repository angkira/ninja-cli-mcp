"""
Human-readable registry of all tunable Ninja MCP runtime constants.

Every runtime knob that is read from the environment at runtime lives here with
a human label, description, default value and value type. The modern TUI and
any other config surface render these directly, so a new constant needs only
one entry in this file to appear as a human setting.

Types:
- ``str``: free text
- ``int``: integer
- ``bool``: yes/no (stored as "true"/"false")
- ``choice``: one of ``options`` (stored as the chosen value)
"""

from __future__ import annotations

from dataclasses import dataclass

from ninja_common.defaults import (
    DEFAULT_TIMEOUT_SEC,
    DEFAULT_WORKTREE_MAX_AGE_DAYS,
    DEFAULT_WORKTREE_MODE,
    DEFAULT_WORKTREE_PARALLEL,
    DEFAULT_WORKTREE_QUICK,
    DEFAULT_WORKTREE_SEQUENTIAL,
)


@dataclass(frozen=True)
class SettingDef:
    """Metadata for a single tunable runtime constant."""

    env_var: str
    label: str
    description: str
    default: str
    value_type: str = "str"
    options: tuple[str, ...] = ()


SETTINGS: list[SettingDef] = [
    # ── Models ───────────────────────────────────────────────────────────
    SettingDef("NINJA_CODER_MODEL", "Coder Model", "Main model for standard coding tasks", ""),
    SettingDef("NINJA_MODEL_QUICK", "Quick Model", "Fast model for simple tasks", "opencode/glm-4.7-free"),
    SettingDef("NINJA_MODEL_SEQUENTIAL", "Sequential Model", "Complex multi-step tasks model", "zai-coding-plan/glm-4.7"),
    SettingDef("NINJA_MODEL_PARALLEL", "Parallel Model", "High-concurrency parallel tasks model", "opencode/glm-4.7-free"),
    SettingDef("NINJA_SECRETARY_MODEL", "Secretary Model", "Model for documentation and analysis", "opencode/glm-4.7-free"),
    SettingDef("NINJA_RESEARCHER_MODEL", "Researcher Model", "Model for web research", "sonar-reasoning"),
    SettingDef("NINJA_RESOURCES_MODEL", "Resources Model", "Model for resource templates", ""),
    SettingDef("NINJA_PROMPTS_MODEL", "Prompts Model", "Model for prompt management", ""),
    SettingDef("NINJA_AGENT_MODEL", "Agent Model", "Model for agent orchestration", "opencode/glm-4.7-free"),
    # ── Operator / provider ──────────────────────────────────────────────
    SettingDef("NINJA_CODE_BIN", "Code Operator", "Which AI coding CLI to use (opencode, aider, claude, gemini, junie, ...)", "opencode"),
    SettingDef("NINJA_CODER_PROVIDER", "Coder Provider", "Default OpenCode provider", "openrouter"),
    SettingDef("NINJA_CODER_OPENCODE_PROVIDER", "OpenCode Provider", "Provider passed to the opencode strategy", "openrouter"),
    SettingDef("NINJA_SECRETARY_OPERATOR", "Secretary Operator", "Operator for the secretary module", "opencode"),
    SettingDef("NINJA_RESEARCHER_OPERATOR", "Researcher Operator", "Operator for the researcher module", "perplexity"),
    # ── Timeouts ─────────────────────────────────────────────────────────
    SettingDef("NINJA_TIMEOUT_SEC", "Task Timeout (s)", "Hard timeout for a single task execution", str(DEFAULT_TIMEOUT_SEC), "int"),
    SettingDef("NINJA_INACTIVITY_TIMEOUT", "Inactivity Timeout (s)", "Abort when no output for this long", "60", "int"),
    SettingDef("NINJA_OPENCODE_TIMEOUT", "OpenCode Timeout (s)", "Base timeout for the opencode strategy", "600", "int"),
    SettingDef("NINJA_OPENCODE_QUICK_TIMEOUT", "Quick Task Timeout (s)", "Max timeout for quick tasks", "600", "int"),
    SettingDef("NINJA_OPENCODE_SEQUENTIAL_TIMEOUT", "Sequential Timeout (s)", "Max timeout for sequential tasks", "900", "int"),
    SettingDef("NINJA_OPENCODE_PARALLEL_TIMEOUT", "Parallel Timeout (s)", "Max timeout for parallel tasks", "1200", "int"),
    SettingDef("NINJA_OPENCODE_SERVE_TIMEOUT", "Serve Task Timeout (s)", "Per-task timeout in the serve pool", "600", "int"),
    SettingDef("NINJA_AIDER_TIMEOUT", "Aider Timeout (s)", "Timeout for the Aider strategy", "300", "int"),
    SettingDef("NINJA_CLAUDE_TIMEOUT", "Claude Timeout (s)", "Timeout for the Claude strategy", "600", "int"),
    SettingDef("NINJA_GEMINI_TIMEOUT", "Gemini Timeout (s)", "Timeout for the Gemini strategy", "600", "int"),
    SettingDef("NINJA_JUNIE_TIMEOUT", "Junie Timeout (s)", "Timeout for the Junie strategy", "600", "int"),
    # ── Retries ──────────────────────────────────────────────────────────
    SettingDef("NINJA_MAX_RETRIES", "Max Retries", "Retry count for tool calls", "2", "int"),
    SettingDef("NINJA_RETRY_DELAY_SEC", "Retry Delay (s)", "Delay between retries", "5", "int"),
    # ── Safety / worktree ────────────────────────────────────────────────
    SettingDef(
        "NINJA_SAFETY_MODE",
        "Safety Mode",
        "Git-based protection against file overwrites",
        "auto",
        "choice",
        ("auto", "strict", "warn", "off"),
    ),
    SettingDef(
        "NINJA_WORKTREE_MODE",
        "Worktree Mode",
        "Global worktree isolation switch (off disables isolation for all task types)",
        DEFAULT_WORKTREE_MODE,
        "choice",
        ("on", "off"),
    ),
    SettingDef(
        "NINJA_WORKTREE_QUICK",
        "Worktree for Quick Tasks",
        "Worktree isolation for simple tasks: off = in-place + safety-commit (default); on = isolate; auto = follow global mode",
        DEFAULT_WORKTREE_QUICK,
        "choice",
        ("off", "on", "auto"),
    ),
    SettingDef(
        "NINJA_WORKTREE_SEQUENTIAL",
        "Worktree for Sequential Plans",
        "Worktree isolation for long multi-step sequential plans (default on; auto = follow global mode)",
        DEFAULT_WORKTREE_SEQUENTIAL,
        "choice",
        ("on", "off", "auto"),
    ),
    SettingDef(
        "NINJA_WORKTREE_PARALLEL",
        "Worktree for Parallel Plans",
        "Worktree isolation for parallel plans (default on; auto = follow global mode)",
        DEFAULT_WORKTREE_PARALLEL,
        "choice",
        ("on", "off", "auto"),
    ),
    SettingDef(
        "NINJA_WORKTREE_MAX_AGE_DAYS",
        "Worktree Max Age (days)",
        "Auto-prune isolation worktrees older than this (0 prunes everything older than now)",
        str(DEFAULT_WORKTREE_MAX_AGE_DAYS),
        "int",
    ),
    # ── Serve pool (opencode serve) ──────────────────────────────────────
    SettingDef(
        "NINJA_OPENCODE_SERVE_MODE",
        "Serve Mode",
        "Use the persistent opencode serve pool",
        "0",
        "choice",
        ("0", "1"),
    ),
    SettingDef("NINJA_OPENCODE_SERVE_PORT_START", "Serve Port Start", "First port in the serve pool range", "20000", "int"),
    SettingDef("NINJA_OPENCODE_SERVE_PORT_END", "Serve Port End", "Last port in the serve pool range", "21000", "int"),
    # ── Misc ─────────────────────────────────────────────────────────────
    SettingDef("NINJA_DEDUP_TTL", "Dedup TTL (s)", "Deduplication window for identical requests", "300", "int"),
    SettingDef("NINJA_OPENROUTER_PROVIDERS", "OpenRouter Providers", "Comma-separated provider order for fallback", ""),
    SettingDef("NINJA_SEARCH_PROVIDER", "Search Provider", "Web search backend", "duckduckgo", "choice", ("duckduckgo", "serper", "perplexity")),
    SettingDef("NINJA_ENABLE_DAEMON", "Enable Daemon", "Run MCP servers as background daemons", "true", "choice", ("true", "false")),
    SettingDef("NINJA_CODER_PORT", "Coder Port", "Daemon port for the coder server", "8100", "int"),
    SettingDef("NINJA_RESEARCHER_PORT", "Researcher Port", "Daemon port for the researcher server", "8101", "int"),
    SettingDef("NINJA_SECRETARY_PORT", "Secretary Port", "Daemon port for the secretary server", "8102", "int"),
    SettingDef("NINJA_AGENT_PORT", "Agent Port", "Daemon port for the agent orchestrator server", "8103", "int"),
    SettingDef(
        "NINJA_LITELLM_BASE_URL",
        "LiteLLM Base URL",
        "LiteLLM proxy base URL (also written to opencode.json)",
        "",
    ),
    SettingDef(
        "NINJA_LITELLM_API_KEY",
        "LiteLLM API Key",
        "API key for the LiteLLM proxy",
        "",
    ),
]


def setting_map() -> dict[str, SettingDef]:
    """Return a dict of env var → SettingDef."""
    return {s.env_var: s for s in SETTINGS}
