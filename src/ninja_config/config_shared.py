"""
Shared definitions for installer and configurator.

Single source of truth for API key metadata, tool detection,
IDE detection, and config section structure. Used by both
tui_installer.py and interactive_configurator.py.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ninja_common.defaults import (
    DEFAULT_MODEL_PARALLEL,
    DEFAULT_MODEL_QUICK,
    DEFAULT_MODEL_SEQUENTIAL,
    DEFAULT_PORTS,
    PROVIDER_MODELS,
)


@dataclass(frozen=True)
class APIKeyDef:
    env_var: str
    display_name: str
    url: str
    module: str
    description: str


API_KEYS: list[APIKeyDef] = [
    APIKeyDef("OPENROUTER_API_KEY", "OpenRouter", "https://openrouter.ai/keys", "coder", "For Aider and general AI access"),
    APIKeyDef("ANTHROPIC_API_KEY", "Anthropic", "https://console.anthropic.com/settings/keys", "coder", "For Claude models (OpenCode)"),
    APIKeyDef("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys", "coder", "For GPT models (OpenCode)"),
    APIKeyDef("GOOGLE_API_KEY", "Google", "https://aistudio.google.com/app/apikey", "coder", "For Gemini models (OpenCode/Gemini CLI)"),
    APIKeyDef("AZURE_OPENAI_API_KEY", "Azure OpenAI", "https://portal.azure.com", "coder", "For Azure-hosted OpenAI models"),
    APIKeyDef("OLLAMA_API_KEY", "Ollama", "http://localhost:11434", "coder", "For local Ollama models (optional)"),
    APIKeyDef("LMSTUDIO_API_KEY", "LM Studio", "http://localhost:1234", "coder", "For local LM Studio models (optional)"),
    APIKeyDef("ZAI_API_KEY", "Z.ai / Zhipu AI", "https://open.bigmodel.cn/usercenter/apikeys", "coder", "For GLM models via z.ai"),
    APIKeyDef("GROQ_API_KEY", "Groq", "https://console.groq.com/keys", "coder", "For Groq models"),
    APIKeyDef("DEEPSEEK_API_KEY", "DeepSeek", "https://platform.deepseek.com/api_keys", "coder", "For DeepSeek models"),
    APIKeyDef("MISTRAL_API_KEY", "Mistral", "https://console.mistral.ai/api-keys", "coder", "For Mistral models"),
    APIKeyDef("PERPLEXITY_API_KEY", "Perplexity", "https://www.perplexity.ai/settings/api", "researcher", "For AI-powered research search"),
    APIKeyDef("SERPER_API_KEY", "Serper", "https://serper.dev", "researcher", "For Google search integration"),
]

CODER_API_KEYS = [k for k in API_KEYS if k.module == "coder"]
RESEARCHER_API_KEYS = [k for k in API_KEYS if k.module == "researcher"]


@dataclass(frozen=True)
class OperatorDef:
    id: str
    display_name: str
    description: str
    providers: tuple[str, ...]


OPERATORS: list[OperatorDef] = [
    OperatorDef("opencode", "OpenCode", "Multi-provider CLI (75+ LLMs)", ("anthropic", "google", "openai", "github-copilot", "openrouter", "zai")),
    OperatorDef("aider", "Aider", "OpenRouter-based CLI", ("openrouter",)),
    OperatorDef("claude", "Claude Code", "Anthropic's official CLI", ("anthropic",)),
    OperatorDef("gemini", "Gemini CLI", "Google native CLI", ("google",)),
    OperatorDef("cursor", "Cursor", "AI code editor", ("openai", "anthropic")),
]

OPERATOR_MAP: dict[str, OperatorDef] = {op.id: op for op in OPERATORS}

PROVIDER_KEY_URLS: dict[str, str] = {
    "anthropic": "https://console.anthropic.com/settings/keys",
    "google": "https://aistudio.google.com/app/apikey",
    "openai": "https://platform.openai.com/api-keys",
    "openrouter": "https://openrouter.ai/keys",
    "github-copilot": "https://github.com/settings/copilot",
    "zai": "https://open.bigmodel.cn/usercenter/apikeys",
}

TASK_MODEL_DEFAULTS: list[tuple[str, str, str, str]] = [
    ("NINJA_MODEL_QUICK", "Quick Tasks", "Fast simple tasks", DEFAULT_MODEL_QUICK),
    ("NINJA_MODEL_SEQUENTIAL", "Sequential Tasks", "Complex multi-step tasks", DEFAULT_MODEL_SEQUENTIAL),
    ("NINJA_MODEL_PARALLEL", "Parallel Tasks", "High concurrency parallel tasks", DEFAULT_MODEL_PARALLEL),
]


def get_fallback_models(provider: str | None = None) -> list[tuple[str, str, str]]:
    if provider and provider in PROVIDER_MODELS:
        return list(PROVIDER_MODELS[provider])
    return list(PROVIDER_MODELS.get("openrouter", []))


def detect_tools() -> dict[str, str]:
    tools: dict[str, str] = {}
    for name in ("aider", "opencode", "gemini", "claude", "cursor"):
        path = shutil.which(name)
        if path:
            tools[name] = path
    return tools


@dataclass(frozen=True)
class IDEDef:
    id: str
    display_name: str
    config_paths: tuple[Path, ...]


IDES: list[IDEDef] = [
    IDEDef("claude", "Claude Code", (
        Path.home() / ".config" / "claude" / "mcp.json",
        Path.home() / ".claude.json",
    )),
    IDEDef("opencode", "OpenCode", (
        Path.home() / ".opencode.json",
        Path.home() / ".config" / "opencode" / ".opencode.json",
    )),
    IDEDef("vscode", "VS Code", (
        Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json",
        Path.home() / ".config" / "Code" / "User" / "settings.json",
    )),
    IDEDef("zed", "Zed", (
        Path.home() / ".config" / "zed" / "settings.json",
    )),
]


def detect_ides() -> dict[str, str]:
    configs: dict[str, str] = {}
    for ide in IDES:
        for p in ide.config_paths:
            if p.exists():
                configs[ide.id] = str(p)
                break
    return configs


def mask_key(value: str) -> str:
    if not value:
        return "*** NOT SET ***"
    if len(value) < 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def check_python() -> bool:
    return sys.version_info >= (3, 11)


def check_uv() -> bool:
    return shutil.which("uv") is not None


def install_uv() -> bool:
    result = subprocess.run(
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        shell=True, capture_output=True, text=True, check=False,
    )
    if result.returncode == 0:
        local_bin = Path.home() / ".local" / "bin"
        import os
        os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"
        return True
    return False


def register_claude_mcp() -> int:
    if not shutil.which("claude"):
        return 0
    count = 0
    for server, command in MCP_SERVER_COMMANDS.items():
        subprocess.run(
            ["claude", "mcp", "remove", server, "-s", "user"],
            capture_output=True, check=False,
        )
        result = subprocess.run(
            ["claude", "mcp", "add", "--scope", "user", "--transport", "stdio", server, "--", *command],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            count += 1
    return count


DAEMON_CONFIG: dict[str, str] = {
    "NINJA_ENABLE_DAEMON": "true",
    **{f"NINJA_{name.upper()}_PORT": str(port) for name, port in DEFAULT_PORTS.items()},
}


MCP_SERVER_COMMANDS: dict[str, list[str]] = {
    "ninja-coder": ["ninja-mcp", "daemon", "connect", "coder"],
    "ninja-researcher": ["ninja-researcher"],
    "ninja-secretary": ["ninja-secretary"],
}


def save_secret(env_var: str, value: str) -> None:
    """Store an API key securely via SecretStore (keyring or AES-256-GCM encrypted file).

    Falls back to ConfigManager (plaintext .env) only if the secret store is
    completely unavailable (no keyring daemon AND no encryption password).
    """
    if not value:
        return

    try:
        from ninja_config.secrets_store import SecretStoreUnavailable, default_store

        store = default_store()
        store.set(env_var, value)
        return
    except SecretStoreUnavailable:
        pass
    except Exception:
        pass

    from ninja_common.config_manager import ConfigManager

    ConfigManager().set(env_var, value)


def get_secret(env_var: str) -> str | None:
    """Retrieve a secret: SecretStore > env var > plaintext .env."""
    try:
        from ninja_config.secrets_store import default_store

        store = default_store()
        val = store.get(env_var)
        if val:
            return val
    except Exception:
        pass

    import os

    env_val = os.environ.get(env_var)
    if env_val:
        return env_val

    from ninja_common.config_manager import ConfigManager

    return ConfigManager().get(env_var)
