"""Dynamic Junie model catalogue (CLI first, settings.json second, static last).

Discovery method (verified live, 2026-09-16): ``junie`` exposes **no**
``models`` subcommand (a bare ``junie models`` hangs waiting for a task on
stdin), but model validation prints the full catalogue to stderr::

    junie --model __ninja_list_probe__   # exit 1, ~1.3s, no task run
    # stderr: "Junie failed with the message: Invalid model: ...\nAvailable models:\n- <id>\n..."

That probe is local arg validation — no subscription spend — and is parsed by
:func:`parse_junie_available_models`. Priority of sources:

1. CLI probe (:func:`_run_junie_models_cli`),
2. ``~/.junie/settings.json`` (:func:`read_junie_settings_models` —
   ``effortPerModel`` keys + ``modelForLaunch``),
3. static :data:`ninja_common.defaults.JUNIE_MODELS` (last resort, e.g. no binary).

Empty CLI output is *not* an error — the next source is used instead.
Results are cached per process with a TTL (see :func:`get_junie_catalog`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

from ninja_common.defaults import JUNIE_EFFORT_LEVELS, JUNIE_MODELS


#: Sentinel model id that can never be valid; the CLI rejects it and prints
#: the catalogue. Must not look like a flag (``--help`` would also work today
#: but could be consumed as a real flag by a future CLI version).
JUNIE_MODEL_PROBE_SENTINEL = "__ninja_list_probe__"

#: Probe timeout (seconds). The probe is local validation (~1.3s observed).
JUNIE_DISCOVERY_TIMEOUT = 15.0

#: Process-level catalogue cache TTL (seconds; mirrors model_cache TTL 300s).
JUNIE_CATALOG_TTL = 300.0

_catalog_cache: tuple[float, list[str]] | None = None
_catalog_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def parse_junie_available_models(text: str) -> list[str]:
    """Parse ``Available models:`` ``- <id>`` rows from CLI output.

    Args:
        text: Combined stdout/stderr of the invalid-model probe.

    Returns:
        Model ids in listed order (slash-qualified ids like
        ``Qwen/Qwen3.6-27B-FP8`` kept as-is), deduplicated.
    """
    ids: list[str] = []
    seen: set[str] = set()
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if not in_section:
            if stripped.lower().startswith("available models"):
                in_section = True
            continue
        if stripped.startswith("- ") or stripped.startswith("-\t") or stripped.startswith("-"):
            model_id = stripped[1:].strip()
        else:
            continue
        if model_id and model_id not in seen:
            seen.add(model_id)
            ids.append(model_id)
    return ids


def _which_junie() -> str | None:
    """Locate the ``junie`` binary (PATH + common install dirs)."""
    found = shutil.which("junie")
    if found:
        return found
    for directory in (
        Path.home() / ".local" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ):
        candidate = directory / "junie"
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def _run_junie_models_cli(
    binary: str | None = None,
    timeout: float = JUNIE_DISCOVERY_TIMEOUT,
) -> list[str]:
    """Probe ``junie --model <sentinel>`` and return the listed model ids.

    Args:
        binary: Optional ``junie`` binary path; discovered when omitted.
        timeout: Subprocess timeout in seconds.

    Returns:
        Model ids from the CLI, or ``[]`` on any failure (no binary,
        timeout, unparsable output). Empty is not an error — callers fall
        back to the next source.
    """
    junie_path = binary or _which_junie()
    if not junie_path:
        return []
    try:
        result = subprocess.run(
            [junie_path, "--model", JUNIE_MODEL_PROBE_SENTINEL],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    return parse_junie_available_models(combined)


def _read_junie_settings() -> dict:
    """Read ``~/.junie/settings.json`` (tolerates missing/corrupt files)."""
    try:
        raw = (Path.home() / ".junie" / "settings.json").read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_junie_settings_models() -> list[str]:
    """Return model ids configured in ``~/.junie/settings.json``.

    Sources: ``effortPerModel`` keys (a dict, or — as Junie writes it — a
    JSON-encoded string holding a dict) plus ``modelForLaunch``.

    Returns:
        Model ids, deduplicated in first-seen order, or ``[]``.
    """
    data = _read_junie_settings()
    ids: list[str] = []
    seen: set[str] = set()

    def _add(model_id: object) -> None:
        if isinstance(model_id, str) and model_id.strip() and model_id not in seen:
            seen.add(model_id)
            ids.append(model_id)

    effort = data.get("effortPerModel")
    if isinstance(effort, str):
        try:
            effort = json.loads(effort)
        except (json.JSONDecodeError, ValueError):
            effort = None
    if isinstance(effort, dict):
        for key in effort:
            _add(key)
    _add(data.get("modelForLaunch"))
    return ids


def get_junie_default_effort(model: str | None) -> str | None:
    """Return the per-model default ``--effort`` from settings.json, if set.

    Args:
        model: Junie model id (matched case-insensitively).

    Returns:
        ``low`` | ``medium`` | ``high``, or ``None`` when unset/invalid.
    """
    if not (model or "").strip():
        return None
    data = _read_junie_settings()
    effort = data.get("effortPerModel")
    if isinstance(effort, str):
        try:
            effort = json.loads(effort)
        except (json.JSONDecodeError, ValueError):
            return None
    if not isinstance(effort, dict):
        return None
    wanted = model.strip().lower()  # type: ignore[union-attr]
    for key, value in effort.items():
        if isinstance(key, str) and key.lower() == wanted:
            level = str(value or "").strip().lower()
            return level if level in JUNIE_EFFORT_LEVELS else None
    return None


def _static_junie_ids() -> list[str]:
    return [mid for mid, _n, _d in JUNIE_MODELS]


def discover_junie_models() -> list[str]:
    """Discover Junie model ids: CLI probe → settings.json → static fallback.

    Returns:
        Model ids, deduplicated. Never empty while the static catalogue
        exists (static ids unknown to the CLI/settings are appended last so
        legacy aliases keep resolving).
    """
    cli_ids = _run_junie_models_cli()
    if cli_ids:
        ids = list(cli_ids)
        seen = set(ids)
        for model_id in read_junie_settings_models():
            if model_id not in seen:
                seen.add(model_id)
                ids.append(model_id)
        for model_id in _static_junie_ids():
            if model_id not in seen:
                seen.add(model_id)
                ids.append(model_id)
        return ids
    settings_ids = read_junie_settings_models()
    if settings_ids:
        seen = set(settings_ids)
        return settings_ids + [mid for mid in _static_junie_ids() if mid not in seen]
    return _static_junie_ids()


def get_junie_catalog(ttl: float = JUNIE_CATALOG_TTL) -> list[str]:
    """Return the Junie model catalogue, cached per process with a TTL.

    Args:
        ttl: Cache lifetime in seconds.

    Returns:
        Model ids from :func:`discover_junie_models` (static fallback
        included, so never empty in practice).
    """
    global _catalog_cache
    if _catalog_cache is not None:
        stamped, ids = _catalog_cache
        if _now() - stamped < ttl:
            return ids
    with _catalog_lock:
        if _catalog_cache is not None:
            stamped, ids = _catalog_cache
            if _now() - stamped < ttl:
                return ids
        try:
            ids = discover_junie_models()
        except Exception:
            ids = _static_junie_ids()
        if not ids:
            ids = _static_junie_ids()
        _catalog_cache = (_now(), ids)
        return ids


def clear_junie_catalog_cache() -> None:
    """Drop the cached catalogue (tests / manual refresh)."""
    global _catalog_cache
    _catalog_cache = None


def junie_display_name(model_id: str) -> str:
    """Derive a human-readable name for a discovered model id."""
    base = model_id.split("/")[-1].strip() or model_id
    return base.replace("-", " ").replace("_", " ").title()


def discover_junie_model_triples() -> list[tuple[str, str, str]]:
    """Discover ``(id, name, description)`` triples for Junie models.

    Static names/descriptions are kept where known; CLI- or settings-only
    ids get a derived display name. Order follows :func:`discover_junie_models`
    (CLI → settings → static).

    Returns:
        Model triples for pickers and selectors.
    """
    static_by_lower = {mid.lower(): (mid, name, desc) for mid, name, desc in JUNIE_MODELS}
    cli_ids = _run_junie_models_cli()
    settings_ids = read_junie_settings_models() if not cli_ids else []
    if cli_ids:
        ordered = list(cli_ids)
        seen = set(ordered)
        for model_id in read_junie_settings_models():
            if model_id not in seen:
                seen.add(model_id)
                ordered.append(model_id)
        sources = dict.fromkeys(cli_ids, "Discovered via Junie CLI")
        for model_id in ordered:
            sources.setdefault(model_id, "From ~/.junie/settings.json")
    elif settings_ids:
        ordered = list(settings_ids)
        sources = dict.fromkeys(settings_ids, "From ~/.junie/settings.json")
    else:
        ordered = []
        sources = {}
    seen = set(ordered)
    for mid in _static_junie_ids():
        if mid not in seen:
            seen.add(mid)
            ordered.append(mid)
            sources[mid] = "Junie model"
    triples: list[tuple[str, str, str]] = []
    for model_id in ordered:
        known = static_by_lower.get(model_id.lower())
        if known:
            triples.append(known)
        else:
            triples.append((model_id, junie_display_name(model_id), sources.get(model_id, "")))
    return triples
