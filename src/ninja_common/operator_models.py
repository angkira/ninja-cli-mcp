"""Operator ↔ model compatibility (single source of truth).

A *model operator* is a coding CLI (``opencode``, ``aider``, ``codex``,
``junie``, ``claude``, ``gemini``). Native operators only accept a fixed set of
model ids (e.g. Codex's flat ``gpt-5.6-luna``); passing an OpenRouter-style id
to them makes the CLI fail. These helpers let every layer (runtime model
selection, config autocomplete, text tasks) agree on what a given operator can
run, so a model can never leak across operators.
"""

from __future__ import annotations

from ninja_common.defaults import (
    CLAUDE_CODE_MODELS,
    CODEX_MODELS,
    GOOGLE_MODELS,
    JUNIE_MODELS,
    OPERATOR_DEFAULT_MODELS,
)


#: Operators whose model ids are fully determined by a static catalogue.
OPERATOR_NATIVE_MODELS: dict[str, frozenset[str]] = {
    "codex": frozenset(mid for mid, _n, _d in CODEX_MODELS),
    "junie": frozenset(mid for mid, _n, _d in JUNIE_MODELS),
    "claude": frozenset(mid for mid, _n, _d in CLAUDE_CODE_MODELS),
    "gemini": frozenset(mid for mid, _n, _d in GOOGLE_MODELS),
}

#: Operators that accept ``provider/model`` ids dynamically (opencode: any
#: provider it knows; aider: OpenRouter-style ``provider/model``).
DYNAMIC_OPERATORS: frozenset[str] = frozenset({"opencode", "aider"})

#: Binary-name substrings mapped to their operator id. Order matters: the
#: first match wins (checked against the lowercased binary name).
_BIN_MARKERS: tuple[tuple[str, str], ...] = (
    ("aider", "aider"),
    ("opencode", "opencode"),
    ("gemini", "gemini"),
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
    native = OPERATOR_NATIVE_MODELS.get(op)
    if native is None:
        return True
    return model in native


def resolve_operator_model(model: str | None, operator: str | None) -> str:
    """Return a model the operator can actually run.

    Pins ``model`` when it is compatible; otherwise falls back to the
    operator's default model, and finally to ``model`` unchanged.

    Args:
        model: Preferred model id (may belong to another operator).
        operator: Operator id, or ``None``.

    Returns:
        A compatible model id (or the original when nothing better is known).
    """
    if is_model_compatible(model or "", operator):
        return str(model)
    return operator_default_model(operator) or str(model or "")
