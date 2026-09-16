"""Operator ↔ model compatibility (single source of truth).

A *model operator* is a coding CLI (``opencode``, ``aider``, ``codex``,
``junie``, ``claude``, ``agy``). Native operators only accept a fixed set of
model ids (e.g. Codex's flat ``gpt-5.6-luna``); passing an OpenRouter-style id
to them makes the CLI fail. These helpers let every layer (runtime model
selection, config autocomplete, text tasks) agree on what a given operator can
run, so a model can never leak across operators.
"""

from __future__ import annotations

import os

from ninja_common.defaults import (
    CLAUDE_CODE_MODELS,
    CODEX_MODELS,
    JUNIE_EFFORT_LEVELS,
    JUNIE_MODEL_ALIASES,
    JUNIE_MODELS,
    OPERATOR_DEFAULT_MODELS,
)
from ninja_common.junie_discovery import get_junie_catalog


#: Operators whose model ids are fully determined by a static catalogue.
#: ``junie`` keeps its static entry as the last-resort fallback, but at
#: runtime its catalogue is dynamic (``junie --model`` probe → settings.json
#: → static; see ``ninja_common.junie_discovery``). Compatibility and
#: validation for junie consult the cached dynamic catalogue.
OPERATOR_NATIVE_MODELS: dict[str, frozenset[str]] = {
    "codex": frozenset(mid for mid, _n, _d in CODEX_MODELS),
    "junie": frozenset(mid for mid, _n, _d in JUNIE_MODELS),
    "claude": frozenset(mid for mid, _n, _d in CLAUDE_CODE_MODELS),
}

#: Operators that accept ``provider/model`` ids dynamically (opencode: any
#: provider it knows; aider: OpenRouter-style ``provider/model``; agy: any id
#: from its own dynamic catalogue).
DYNAMIC_OPERATORS: frozenset[str] = frozenset({"opencode", "aider", "agy"})

#: Binary-name substrings mapped to their operator id. Order matters: the
#: first match wins (checked against the lowercased binary name).
_BIN_MARKERS: tuple[tuple[str, str], ...] = (
    ("aider", "aider"),
    ("opencode", "opencode"),
    ("agy", "agy"),
    ("claude", "claude"),
    ("junie", "junie"),
    ("codex", "codex"),
)


def operator_from_bin(bin_path: str | None) -> str | None:
    """Map a binary path/name to a known operator id.

    Args:
        bin_path: ``NINJA_CODE_BIN`` value — a bare id or an absolute path.

    Returns:
        Operator id (e.g. ``"codex"``) or ``None`` if unrecognised.
    """
    value = (bin_path or "").strip().lower()
    if not value:
        return None
    for marker, operator in _BIN_MARKERS:
        if marker in value:
            return operator
    return None


def operator_default_model(operator: str | None) -> str | None:
    """Return the default model id for an operator, if known.

    Args:
        operator: Operator id (e.g. ``"codex"``).

    Returns:
        Default model id, or ``None`` for unknown operators.
    """
    return OPERATOR_DEFAULT_MODELS.get((operator or "").lower())


def is_model_compatible(model: str, operator: str | None) -> bool:
    """Return whether ``model`` can be run by ``operator``.

    Unknown operators and empty models are treated as compatible (no opinion).

    Args:
        model: Model id (e.g. ``"gpt-5.6-luna"`` or ``"openrouter/…"``).
        operator: Operator id, or ``None``.

    Returns:
        True if the operator can run the model.
    """
    if not model or not operator:
        return True
    op = operator.lower()
    if op == "opencode":
        return True
    if op == "aider":
        # Aider is OpenRouter-backed: it needs ``provider/model`` ids and
        # cannot run another operator's flat id (e.g. codex's gpt-5.6-luna).
        return "/" in model
    if op == "agy":
        # Antigravity models are flat ids (gemini-3.8-flash-medium,
        # claude-sonnet-4-6, …) or the "default" sentinel; a provider-prefixed
        # id (e.g. openrouter/…) belongs to another operator and must be
        # replaced by agy's default.
        return "/" not in model
    if op in ("codex", "claude"):
        native = OPERATOR_NATIVE_MODELS.get(op)
        if native is None:
            return True
        return model in native
    if op == "junie":
        try:
            catalog = get_junie_catalog()
        except Exception:
            catalog = [mid for mid, _n, _d in JUNIE_MODELS]
        normalized = normalize_junie_model(model)
        lowered = normalized.lower()
        return any(known.lower() == lowered for known in catalog)
    native = OPERATOR_NATIVE_MODELS.get(op)
    if native is None:
        return True
    return model in native


def resolve_operator_model(model: str | None, operator: str | None) -> str:
    """Return a model the operator can actually run.

    Pins ``model`` when it is compatible; otherwise falls back to the
    operator's default model, and finally to ``model`` unchanged.
    Junie ids are normalized first (provider-prefix strip + alias map),
    so ``junie/deepseek-v4-flash`` pins instead of falling back.

    Args:
        model: Preferred model id (may belong to another operator).
        operator: Operator id, or ``None``.

    Returns:
        A compatible model id (or the original when nothing better is known).
    """
    if (operator or "").lower() == "junie" and model:
        normalized = normalize_junie_model(model)
        if is_model_compatible(normalized, operator):
            return normalized
    if is_model_compatible(model or "", operator):
        return str(model)
    return operator_default_model(operator) or str(model or "")


def normalize_junie_model(model: str | None) -> str:
    """Normalize a Junie model id without validating it (never raises).

    Legacy short aliases resolve first (``grok`` → ``grok-4.6``, back-compat
    even though the CLI also lists a literal ``grok``). Otherwise an exact
    (case-insensitive) match against the dynamic catalogue wins — this
    preserves slash-qualified ids the CLI reports (e.g.
    ``Qwen/Qwen3.6-27B-FP8``) — then a ``provider/`` prefix is stripped
    (``openai/gpt-5.6-luna`` → ``gpt-5.6-luna``) and case is canonicalized
    against the known catalogue (dynamic first, static as back-compat).

    Args:
        model: Raw model id (may be provider-qualified or an alias).

    Returns:
        Normalized model id, or ``""`` for empty input.
    """
    raw = (model or "").strip()
    if not raw:
        return ""
    try:
        catalog = get_junie_catalog()
    except Exception:
        catalog = [mid for mid, _n, _d in JUNIE_MODELS]
    # Legacy short aliases win (back-compat: ``grok`` → ``grok-4.6`` even
    # though the CLI also lists a literal ``grok`` model).
    candidate = raw.split("/")[-1].strip() or raw
    lowered = candidate.lower()
    alias = JUNIE_MODEL_ALIASES.get(lowered)
    if alias:
        return alias
    lowered_raw = raw.lower()
    for known in catalog:
        if known.lower() == lowered_raw:
            return known
    for known in catalog:
        if known.lower() == lowered:
            return known
    for mid, _name, _desc in JUNIE_MODELS:
        if mid.lower() == lowered:
            return mid
    return candidate


def resolve_junie_model(model: str | None) -> str:
    """Normalize a Junie model id and validate it loudly.

    Validation runs against the dynamic catalogue (CLI probe →
    settings.json → static fallback) plus the legacy alias map; when no
    binary/settings are available the static catalogue applies as before.

    Args:
        model: Raw model id (may be provider-qualified or an alias).
            Empty/``None`` resolves to the Junie default model.

    Returns:
        Canonical Junie model id for ``--model``.

    Raises:
        ValueError: If the normalized id is not a known Junie model.
    """
    normalized = normalize_junie_model(model)
    if not normalized:
        normalized = normalize_junie_model(operator_default_model("junie") or "")
    try:
        valid = get_junie_catalog()
    except Exception:
        valid = [mid for mid, _n, _d in JUNIE_MODELS]
    if not any(normalized.lower() == known.lower() for known in valid):
        raise ValueError(
            f"Unknown Junie model {model!r} (normalized to {normalized!r}). "
            f"Valid Junie models: {', '.join(valid)}"
        )
    return normalized


def resolve_junie_effort(explicit: str | None = None, task_type: str | None = None) -> str | None:
    """Resolve the Junie ``--effort`` level (``low`` | ``medium`` | ``high``).

    Precedence: explicit per-call value → per-task-type env
    (``NINJA_JUNIE_EFFORT_QUICK/SEQUENTIAL/PARALLEL``) → global
    ``NINJA_JUNIE_EFFORT`` → ``None`` (flag omitted, CLI decides).

    Args:
        explicit: Per-call override (e.g. from ``additional_flags``).
        task_type: Task type (``quick``/``sequential``/``parallel``,
            ``*_plan`` suffixes accepted).

    Returns:
        Validated effort level, or ``None`` when unset.

    Raises:
        ValueError: If a set value is not a valid effort level.
    """
    raw: str | None = (explicit or "").strip() or None
    if raw is None and task_type:
        base = task_type.removesuffix("_plan").upper()
        raw = (os.environ.get(f"NINJA_JUNIE_EFFORT_{base}") or "").strip() or None
    if raw is None:
        raw = (os.environ.get("NINJA_JUNIE_EFFORT") or "").strip() or None
    if raw is None:
        return None
    value = raw.lower()
    if value not in JUNIE_EFFORT_LEVELS:
        raise ValueError(
            f"Invalid Junie effort {raw!r}. Expected one of: {', '.join(JUNIE_EFFORT_LEVELS)}"
        )
    return value
