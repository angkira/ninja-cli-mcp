"""Process-level TTL cache for provider/model discovery.

``ninja_config.model_selector`` shells out to ``opencode models`` (and friends)
on every call. The modern TUI used to call it synchronously for all five roles
in ``on_mount``, blocking the first frame for ~14s. This module memoizes both
discovery calls per process with a TTL so:

- one ``discover`` serves all five role pickers on tab open,
- repeated autocomplete keystrokes filter the cached model list in-memory
  instead of spawning a subprocess per keystroke,
- stale entries expire automatically (default TTL 300s).

Only stdlib + ``model_selector`` imports — safe to import from widgets.
"""

from __future__ import annotations

import threading
import time

from ninja_config.model_selector import (
    OPENCODE_PROVIDERS,
    Model,
    discover_opencode_providers,
    get_provider_models,
)


DISCOVER_TTL: float = 300.0
MODELS_TTL: float = 300.0

_discover_cache: tuple[float, list[tuple[str, str, str]]] | None = None
_models_cache: dict[tuple[str, str], tuple[float, list[Model]]] = {}
#: Serializes subprocess discovery so the five role pickers opening at once
#: trigger a single ``opencode models`` call instead of a thundering herd.
_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def cached_discover_providers(ttl: float = DISCOVER_TTL) -> list[tuple[str, str, str]]:
    """Return discovered ``(provider_id, display, desc)`` tuples, cached per process.

    Args:
        ttl: Cache lifetime in seconds.

    Returns:
        Provider list; static :data:`OPENCODE_PROVIDERS` fallback on failure
        (mirrors :func:`discover_opencode_providers` semantics).
    """
    global _discover_cache
    if _discover_cache is not None:
        stamped, providers = _discover_cache
        if _now() - stamped < ttl:
            return providers
    with _lock:  # Double-checked: one subprocess for concurrent pickers.
        if _discover_cache is not None:
            stamped, providers = _discover_cache
            if _now() - stamped < ttl:
                return providers
        try:
            providers = discover_opencode_providers()
        except Exception:
            providers = OPENCODE_PROVIDERS.copy()
        if not providers:
            providers = OPENCODE_PROVIDERS.copy()
        _discover_cache = (_now(), providers)
        return providers


def cached_get_provider_models(
    operator: str,
    provider: str,
    ttl: float = MODELS_TTL,
) -> list[Model]:
    """Return models for ``(operator, provider)``, cached per process.

    Args:
        operator: Operator id (e.g. ``"opencode"``).
        provider: Provider id (e.g. ``"openrouter"``).
        ttl: Cache lifetime in seconds.

    Returns:
        List of :class:`Model` (possibly empty — callers apply static fallbacks).
    """
    key = (operator, provider)
    hit = _models_cache.get(key)
    if hit is not None:
        stamped, models = hit
        if _now() - stamped < ttl:
            return models
    with _lock:  # Double-checked: one subprocess for concurrent pickers.
        hit = _models_cache.get(key)
        if hit is not None:
            stamped, models = hit
            if _now() - stamped < ttl:
                return models
        try:
            models = get_provider_models(operator, provider)
        except Exception:
            models = []
        _models_cache[key] = (_now(), models)
        return models


def filter_models(models: list[Model], query: str, limit: int = 30) -> list[Model]:
    """Case-insensitive substring filter over model id + name.

    Args:
        models: Full cached model list for a provider.
        query: User typed text (already ≥2 chars by contract).
        limit: Max results returned.

    Returns:
        Matching models, stable-sorted by model id.
    """
    needle = query.strip().lower()
    if not needle:
        return []
    matched = [m for m in models if needle in m.id.lower() or needle in m.name.lower()]
    matched.sort(key=lambda m: m.id.lower())
    return matched[:limit]


def clear_model_cache() -> None:
    """Drop all cached entries (tests / manual refresh)."""
    global _discover_cache
    _discover_cache = None
    _models_cache.clear()
