"""Dynamic Pi model catalogue (CLI first, settings.json second, static last).

Discovery sources for Pi coding agent (pi.dev):
1. CLI discovery: ``pi --list-models``
   Outputs tabular format:
   ``provider    model                context  max-out  thinking  images``
2. ``~/.pi/agent/settings.json``:
   - ``defaultModel``, ``defaultProvider``
3. ``~/.pi/agent/models.json``:
   - custom defined models
4. Static fallback:
   - :data:`ninja_common.defaults.PI_MODELS`.

Empty/missing sources are not errors — discovery aggregates and deduplicates
models, sorting them with the current configured model first, followed by
the discovered CLI models, and finally static ids.
Results are cached per process with a TTL (see :func:`get_pi_catalog`).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from ninja_common.defaults import PI_MODELS


#: Probe timeout (seconds). The probe is local validation.
PI_DISCOVERY_TIMEOUT: float = 15.0

#: Process-level catalogue cache TTL (seconds; mirrors model_cache TTL 300s).
PI_CATALOG_TTL: float = 300.0

_catalog_cache: tuple[float, list[str]] | None = None
_catalog_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def _which_pi(binary: str | None = None) -> str | None:
    """Locate the ``pi`` binary (explicit path, PATH, or common install dirs)."""
    if binary:
        cand = Path(binary)
        try:
            if cand.is_file():
                return str(cand)
        except OSError:
            pass
    found = shutil.which("pi")
    if found:
        return found
    for directory in (
        Path.home() / ".nvm" / "versions" / "node",
        Path.home() / ".local" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ):
        if not directory.exists():
            continue
        if directory.name == "node":
            # Search nvm node versions
            for node_dir in directory.glob("*/bin/pi"):
                if node_dir.is_file():
                    return str(node_dir)
        else:
            candidate = directory / "pi"
            try:
                if candidate.is_file():
                    return str(candidate)
            except OSError:
                continue
    return None


def read_pi_settings_current_model() -> str | None:
    """Read the current defaultModel configured in ~/.pi/agent/settings.json."""
    settings_dir = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
    settings_file = settings_dir / "settings.json"
    if not settings_file.is_file():
        return None
    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        model = data.get("defaultModel")
        if isinstance(model, str) and model.strip():
            return model.strip()
    except Exception:
        pass
    return None


def parse_pi_list_models_output(text: str) -> list[tuple[str, str, str]]:
    """Parse ``pi --list-models`` output table into model triples.

    Args:
        text: Stdout from ``pi --list-models``.

    Returns:
        List of (model_id, display_name, description) tuples.
    """
    triples: list[tuple[str, str, str]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return triples

    # Check header
    header_idx = -1
    for i, line in enumerate(lines):
        lowered = line.lower()
        if "provider" in lowered and "model" in lowered:
            header_idx = i
            break

    if header_idx == -1:
        return triples

    seen_ids: set[str] = set()

    for line in lines[header_idx + 1 :]:
        parts = re.split(r"\s{2,}", line)
        if len(parts) < 2:
            parts = line.split()
        if len(parts) < 2:
            continue

        provider = parts[0].strip()
        model_name = parts[1].strip()
        context = parts[2].strip() if len(parts) > 2 else ""
        thinking = parts[4].strip() if len(parts) > 4 else ""

        model_id = model_name
        if model_id in seen_ids:
            continue
        seen_ids.add(model_id)

        display_name = model_name.replace("-", " ").title()
        desc_parts = [f"via {provider}"]
        if context:
            desc_parts.append(f"context: {context}")
        if thinking and thinking.lower() in ("yes", "true"):
            desc_parts.append("thinking: yes")
        desc = ", ".join(desc_parts)

        triples.append((model_id, display_name, desc))

    return triples


def _run_pi_models_cli(binary: str | None = None) -> list[tuple[str, str, str]]:
    """Run ``pi --list-models`` and parse discovered models."""
    pi_bin = _which_pi(binary)
    if not pi_bin:
        return []
    try:
        proc = subprocess.run(
            [pi_bin, "--list-models"],
            capture_output=True,
            text=True,
            timeout=PI_DISCOVERY_TIMEOUT,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            return parse_pi_list_models_output(proc.stdout)
    except Exception:
        pass
    return []


def discover_pi_model_triples(binary: str | None = None) -> list[tuple[str, str, str]]:
    """Discover Pi models from CLI probe, settings, and static fallback.

    Returns:
        List of (model_id, display_name, description) triples with current model first.
    """
    triples: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    # 1. Current model from settings.json
    current_model = read_pi_settings_current_model()

    # 2. Probe CLI
    cli_triples = _run_pi_models_cli(binary)
    for model_id, name, desc in cli_triples:
        if model_id.lower() not in seen:
            seen.add(model_id.lower())
            triples.append((model_id, name, desc))

    # 3. Static fallback
    for model_id, name, desc in PI_MODELS:
        if model_id.lower() not in seen:
            seen.add(model_id.lower())
            triples.append((model_id, name, desc))

    if current_model:
        # Move current model to front if present
        cur_low = current_model.lower()
        idx = next((i for i, (mid, _, _) in enumerate(triples) if mid.lower() == cur_low), None)
        if idx is not None and idx > 0:
            current_triple = triples.pop(idx)
            triples.insert(0, current_triple)
        elif idx is None:
            # Add at front
            disp = current_model.replace("-", " ").title()
            triples.insert(0, (current_model, disp, "Configured default model in settings.json"))

    return triples


def get_pi_catalog(binary: str | None = None, force_refresh: bool = False) -> list[str]:
    """Return model ids for Pi, cached with TTL.

    Args:
        binary: Optional binary path.
        force_refresh: Ignore cached catalogue if True.

    Returns:
        List of model ids.
    """
    global _catalog_cache
    now = _now()
    if not force_refresh and _catalog_cache is not None:
        ts, cached = _catalog_cache
        if now - ts < PI_CATALOG_TTL:
            return list(cached)

    with _catalog_lock:
        if not force_refresh and _catalog_cache is not None:
            ts, cached = _catalog_cache
            if now - ts < PI_CATALOG_TTL:
                return list(cached)

        triples = discover_pi_model_triples(binary)
        model_ids = [mid for mid, _n, _d in triples]
        _catalog_cache = (now, model_ids)
        return list(model_ids)


def clear_catalog_cache() -> None:
    """Clear process-level catalogue cache (for testing)."""
    global _catalog_cache
    with _catalog_lock:
        _catalog_cache = None
