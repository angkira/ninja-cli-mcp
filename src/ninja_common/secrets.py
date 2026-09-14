"""Cross-platform secret accessor backed by the encrypted store.

Runtime modules (ninja_coder, ninja_researcher, ninja_secretary) use this to
read/write API keys without pulling any TUI/config dependencies. The heavy
secret store (``ninja_config.secrets_store``) is imported lazily so importing
``ninja_common`` stays cheap and layering stays one-directional at import time.

Storage is AES-256-GCM (see ``ninja_config.credentials``); the store password is
held in process memory only (prompted / inherited via fd / systemd credential).
Secrets are never written to ``~/.ninja-mcp.env`` or exported into ``os.environ``.
"""

from __future__ import annotations

import os
from typing import Final


#: Env var names that hold secrets (mirrored by ninja_config.config_shared).
KNOWN_SECRET_NAMES: Final[frozenset[str]] = frozenset(
    {
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "PERPLEXITY_API_KEY",
        "ZAI_API_KEY",
        "GROQ_API_KEY",
        "DEEPSEEK_API_KEY",
        "MISTRAL_API_KEY",
        "GOOGLE_API_KEY",
        "SERPER_API_KEY",
    }
)


def is_secret(name: str) -> bool:
    """Return True when ``name`` is a known secret key."""
    return name in KNOWN_SECRET_NAMES


def get_secret(name: str) -> str | None:
    """Return a secret from the encrypted store.

    Resolution: encrypted store first; a pre-existing (read-only) environment
    variable is honoured only as a last resort for CI/headless use. Ninja never
    writes secrets into the environment itself.
    """
    try:
        from ninja_config.secrets_store import default_store

        value = default_store().get(name)
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(name) or None


def set_secret(name: str, value: str) -> None:
    """Store ``name`` in the encrypted store (never in env/config)."""
    from ninja_config.secrets_store import default_store

    default_store().set(name, value)


def delete_secret(name: str) -> None:
    """Remove ``name`` from every secret backend."""
    from ninja_config.secrets_store import default_store

    default_store().delete(name)
