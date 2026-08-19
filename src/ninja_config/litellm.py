"""LiteLLM provider configuration helpers.

LiteLLM is an OpenAI-compatible proxy. To use it as a model source for the
opencode strategy we register a custom provider block in the global
``opencode.json`` (``provider.litellm``) with a base URL, API key and the
models served by the proxy. Ninja itself then routes any ``litellm/<model>``
model id straight through to the opencode CLI.

The config path follows opencode's global config resolution:
``$XDG_CONFIG_HOME/opencode/opencode.json`` (default ``~/.config/opencode``).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)

# Provider id used in opencode.json and as the model-id prefix (litellm/...).
LITELLM_PROVIDER_ID = "litellm"

# Default config dir per opencode's own resolution rules.
def _opencode_config_path() -> Path:
    """Return the path to the global opencode config file."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        base = Path(config_home)
    else:
        base = Path.home() / ".config"
    return base / "opencode" / "opencode.json"


def read_litellm_config() -> dict | None:
    """Read the current litellm provider block from opencode.json.

    Returns:
        A dict with keys ``base_url``, ``api_key``, ``models`` (list of model
        ids) or ``None`` if no litellm provider is configured.
    """
    path = _opencode_config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Cannot parse %s: %s", path, e)
        return None

    provider = data.get("provider", {}).get(LITELLM_PROVIDER_ID)
    if not provider:
        return None

    options = provider.get("options", {})
    models = list(provider.get("models", {}).keys()) or []
    return {
        "base_url": options.get("baseURL", ""),
        "api_key": options.get("apiKey", ""),
        "models": models,
    }


def write_litellm_config(base_url: str, api_key: str, models: list[str]) -> bool:
    """Write or update the litellm provider block in opencode.json.

    Args:
        base_url: Base URL of the LiteLLM proxy (e.g. ``http://host:4000/v1``).
        api_key: API key for the proxy.
        models: Model ids served by the proxy (as configured in LiteLLM).

    Returns:
        True on success.
    """
    path = _opencode_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}

    provider = data.setdefault("provider", {}).setdefault(
        LITELLM_PROVIDER_ID,
        {
            "npm": "@ai-sdk/openai-compatible",
            "name": "LiteLLM",
        },
    )
    provider["options"] = {
        "baseURL": base_url.rstrip("/") if base_url else "",
        "apiKey": api_key,
    }
    provider["models"] = {
        model_id: {"name": model_id} for model_id in models if model_id
    }

    try:
        path.write_text(json.dumps(data, indent=2))
        logger.info("Wrote litellm provider block to %s", path)
        return True
    except OSError as e:
        logger.error("Failed to write litellm config: %s", e)
        return False


def remove_litellm_config() -> bool:
    """Remove the litellm provider block from opencode.json.

    Returns:
        True if the block was removed (or was not present).
    """
    path = _opencode_config_path()
    if not path.exists():
        return True
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return True
    if "litellm" not in data.get("provider", {}):
        return True
    data["provider"].pop("litellm", None)
    try:
        path.write_text(json.dumps(data, indent=2))
        return True
    except OSError as e:
        logger.error("Failed to remove litellm config: %s", e)
        return False


def is_litellm_configured() -> bool:
    """Return True when a litellm provider block exists with a base URL."""
    cfg = read_litellm_config()
    return bool(cfg and cfg["base_url"])
