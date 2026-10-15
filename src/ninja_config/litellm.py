"""LiteLLM provider configuration for OpenCode v2.

OpenCode v2 reads ``opencode.jsonc`` (JSON with comments and trailing commas)
and configures custom providers under ``providers.<id>`` with ``package``,
``settings.baseURL`` and a ``models`` map. This module reads and writes that
block while preserving every other key in the file.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

# Provider id used in opencode.jsonc and as the model-id prefix (litellm/...).
LITELLM_PROVIDER_ID = "litellm"

#: OpenAI-compatible runtime package for LiteLLM proxies (OpenCode v2).
LITELLM_PACKAGE = "@opencode/ai/providers/openai-compatible"

#: Environment variables OpenCode v2 reads for the LiteLLM API key.
LITELLM_KEY_ENV = ["LITELLM_API_KEY", "LITE_LLM_KEY"]


def _opencode_config_path() -> Path:
    """Return the path to the global OpenCode v2 config file."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "opencode" / "opencode.jsonc"


def _strip_jsonc(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments and trailing commas outside strings."""
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _load(path: Path) -> dict[str, Any]:
    """Parse an OpenCode config file (JSONC). Missing or invalid files yield ``{}``."""
    if not path.exists():
        return {}
    try:
        data = json.loads(_strip_jsonc(path.read_text()))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Cannot parse %s: %s", path, e)
        return {}
    return data if isinstance(data, dict) else {}


def read_litellm_config() -> dict | None:
    """Read the current LiteLLM provider block from ``opencode.jsonc``.

    Returns:
        A dict with keys ``base_url``, ``api_key``, ``models`` (list of model
        ids) or ``None`` if no LiteLLM provider is configured.
    """
    path = _opencode_config_path()
    provider = _load(path).get("providers", {}).get(LITELLM_PROVIDER_ID)
    if not provider:
        return None

    settings = provider.get("settings", {})
    models = [
        model.get("modelID", model_id) if isinstance(model, dict) else model_id
        for model_id, model in (provider.get("models") or {}).items()
    ]
    return {
        "base_url": settings.get("baseURL", ""),
        "api_key": settings.get("apiKey", ""),
        "models": models,
    }


def write_litellm_config(base_url: str, api_key: str, models: list[str]) -> bool:
    """Write or update the LiteLLM provider block in ``opencode.jsonc``.

    Other providers, plugins and settings in the file are preserved. The
    API key is stored as ``settings.apiKey`` only when given; otherwise the
    provider reads it from the environment variables in ``env``.

    Args:
        base_url: Base URL of the LiteLLM proxy (e.g. ``http://host:4000/v1``).
        api_key: API key for the proxy (may be empty).
        models: Model ids served by the proxy (as configured in LiteLLM).

    Returns:
        True on success.
    """
    path = _opencode_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = _load(path)
    data.setdefault("$schema", "https://opencode.ai/config.json")
    providers = data.setdefault("providers", {})
    provider = providers.setdefault(LITELLM_PROVIDER_ID, {})
    provider.setdefault("name", "LiteLLM")
    provider["env"] = list(LITELLM_KEY_ENV)
    provider["package"] = LITELLM_PACKAGE

    settings = provider.setdefault("settings", {})
    settings["baseURL"] = base_url.rstrip("/") if base_url else ""
    if api_key:
        settings["apiKey"] = api_key
    else:
        settings.pop("apiKey", None)

    provider["models"] = {
        model_id: {"modelID": model_id, "name": model_id} for model_id in models if model_id
    }

    try:
        path.write_text(json.dumps(data, indent=2) + "\n")
        logger.info("Wrote litellm provider block to %s", path)
        return True
    except OSError as e:
        logger.error("Failed to write litellm config: %s", e)
        return False


def remove_litellm_config() -> bool:
    """Remove the LiteLLM provider block from ``opencode.jsonc``.

    Returns:
        True if the block was removed (or was not present).
    """
    path = _opencode_config_path()
    if not path.exists():
        return True
    data = _load(path)
    providers = data.get("providers", {})
    if LITELLM_PROVIDER_ID not in providers:
        return True
    providers.pop(LITELLM_PROVIDER_ID, None)
    try:
        path.write_text(json.dumps(data, indent=2) + "\n")
        return True
    except OSError as e:
        logger.error("Failed to remove litellm config: %s", e)
        return False


def is_litellm_configured() -> bool:
    """Return True when a LiteLLM provider block exists with a base URL."""
    cfg = read_litellm_config()
    return bool(cfg and cfg["base_url"])
