"""Dynamic Codex model catalogue (config.toml first, binary second, sqlite third, static last).

Discovery sources for OpenAI Codex CLI:
1. ``~/.codex/config.toml``:
   - current model: ``model = "..."``
   - nux / availability: ``[tui.model_availability_nux]`` (keys)
   - migrations: ``[notice.model_migrations]`` (values)
2. ``codex`` binary:
   - Located via ``shutil.which("codex")`` and common system install paths.
   - Embedded model metadata JSON blocks containing ``slug``, ``display_name``,
     and ``description``.
3. ``~/.codex/state_5.sqlite``:
   - Historical model usage from ``SELECT DISTINCT model FROM threads``.
4. Static fallback:
   - :data:`ninja_common.defaults.CODEX_MODELS`.

Empty/missing sources are not errors — discovery aggregates and deduplicates
models, sorting them with the current configured model first, followed by
``gpt-6-*`` models, then previous generation models, and finally legacy/static ids.
Results are cached per process with a TTL (see :func:`get_codex_catalog`).
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
import time
from pathlib import Path


try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

from ninja_common.defaults import CODEX_MODELS


#: Process-level catalogue cache TTL (seconds; mirrors model_cache TTL 300s).
CODEX_CATALOG_TTL: float = 300.0

_catalog_cache: tuple[float, list[str]] | None = None
_catalog_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def _which_codex(binary: str | None = None) -> str | None:
    """Locate the ``codex`` binary (explicit path, PATH, or common install dirs)."""
    if binary:
        cand = Path(binary)
        try:
            if cand.is_file():
                return str(cand)
        except OSError:
            pass
    found = shutil.which("codex")
    if found:
        return found
    for directory in (
        Path.home() / ".local" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    ):
        candidate = directory / "codex"
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def _parse_toml_fallback(raw: str) -> dict:
    """Regex fallback to extract model metadata from config.toml when tomllib is absent."""
    data: dict = {}
    m = re.search(r'^\s*model\s*=\s*["\']([^"\']+)["\']', raw, re.MULTILINE)
    if m:
        data["model"] = m.group(1).strip()
    migrations_section = re.search(r"\[notice\.model_migrations\](.*?)(?:\[|\Z)", raw, re.DOTALL)
    if migrations_section:
        migrations = {}
        for line in migrations_section.group(1).splitlines():
            line_m = re.match(r'^\s*["\']?([^"\']+)["\']?\s*=\s*["\']([^"\']+)["\']', line)
            if line_m:
                migrations[line_m.group(1).strip()] = line_m.group(2).strip()
        data.setdefault("notice", {})["model_migrations"] = migrations
    nux_section = re.search(r"\[tui\.model_availability_nux\](.*?)(?:\[|\Z)", raw, re.DOTALL)
    if nux_section:
        nux = {}
        for line in nux_section.group(1).splitlines():
            line_m = re.match(r'^\s*["\']?([^"\']+)["\']?\s*=\s*(\S+)', line)
            if line_m:
                nux[line_m.group(1).strip()] = line_m.group(2).strip()
        data.setdefault("tui", {})["model_availability_nux"] = nux
    return data


def _read_codex_config(config_path: Path | None = None) -> dict:
    """Read ``~/.codex/config.toml`` (tolerates missing/corrupt files)."""
    target = config_path or (Path.home() / ".codex" / "config.toml")
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError:
        return {}
    if tomllib is not None:
        try:
            parsed = tomllib.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return _parse_toml_fallback(raw)


def read_codex_config_current_model(config_path: Path | None = None) -> str | None:
    """Return the current configured model from ``~/.codex/config.toml``, or None."""
    data = _read_codex_config(config_path=config_path)
    model = data.get("model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    return None


def read_codex_config_models(config_path: Path | None = None) -> list[str]:
    """Return model ids discovered in ``~/.codex/config.toml``.

    Sources (in priority order):
    - Current model: ``model = "..."``
    - NUX availability keys: ``[tui.model_availability_nux]``
    - Migrations targets (values): ``[notice.model_migrations]``

    Returns:
        Deduplicated list of model ids in order of appearance.
    """
    data = _read_codex_config(config_path=config_path)
    models: list[str] = []
    seen: set[str] = set()

    def _add(mid: object) -> None:
        if isinstance(mid, str):
            clean = mid.strip()
            if clean and clean not in seen and not clean.startswith("__"):
                seen.add(clean)
                models.append(clean)

    _add(data.get("model"))

    nux = data.get("tui", {}).get("model_availability_nux", {})
    if isinstance(nux, dict):
        for k in nux:
            _add(k)

    migrations = data.get("notice", {}).get("model_migrations", {})
    if isinstance(migrations, dict):
        for v in migrations.values():
            _add(v)

    return models


def parse_codex_binary_metadata(raw: bytes) -> list[tuple[str, str, str]]:
    """Parse embedded model JSON blocks from raw binary bytes.

    Looks for ``b'"slug":'`` patterns and extracts ``slug``, ``display_name``,
    and ``description``.

    Args:
        raw: Byte content of the codex binary or a binary slice.

    Returns:
        List of ``(slug, display_name, description)`` tuples, deduplicated.
    """
    results: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for match in re.finditer(rb"\"slug\":\s*\"([^\"]+)\"", raw):
        slug = match.group(1).decode("utf-8", errors="ignore").strip()
        if not slug or slug in seen or slug.startswith("__"):
            continue

        next_slug_pos = raw.find(b'"slug":', match.end())
        chunk_end = next_slug_pos if next_slug_pos != -1 else min(len(raw), match.start() + 4000)
        if chunk_end - match.start() > 4000:
            chunk_end = match.start() + 4000
        chunk_forward = raw[match.start() : chunk_end].decode("utf-8", errors="ignore")

        dn_match = re.search(
            r"\"display_name\":\s*\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"", chunk_forward
        )
        desc_match = re.search(
            r"\"description\":\s*\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"", chunk_forward
        )

        if not dn_match or not desc_match:
            prev_slug_pos = raw.rfind(b'"slug":', 0, match.start())
            chunk_start = max(0, match.start() - 500)
            if prev_slug_pos != -1 and prev_slug_pos >= chunk_start:
                chunk_start = prev_slug_pos + len(b'"slug":')
            chunk_backward = raw[chunk_start : match.start()].decode("utf-8", errors="ignore")
            if not dn_match:
                dn_match = re.search(
                    r"\"display_name\":\s*\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"", chunk_backward
                )
            if not desc_match:
                desc_match = re.search(
                    r"\"description\":\s*\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"", chunk_backward
                )

        dn = ""
        if dn_match:
            try:
                dn = json.loads('"' + dn_match.group(1) + '"')
            except Exception:
                dn = dn_match.group(1)
        desc = ""
        if desc_match:
            try:
                desc = json.loads('"' + desc_match.group(1) + '"')
            except Exception:
                desc = desc_match.group(1)

        seen.add(slug)
        results.append((slug, dn.strip(), desc.strip()))

    return results


def read_codex_binary_models(binary: str | None = None) -> list[tuple[str, str, str]]:
    """Extract embedded model metadata directly from the codex binary.

    Args:
        binary: Optional explicit path to the codex binary.

    Returns:
        List of ``(model_id, display_name, description)`` triples, or ``[]`` on failure.
    """
    codex_path = _which_codex(binary)
    if not codex_path:
        return []
    try:
        raw_bytes = Path(codex_path).read_bytes()
        return parse_codex_binary_metadata(raw_bytes)
    except (OSError, MemoryError):
        return []


def read_codex_sqlite_models(db_path: Path | None = None) -> list[str]:
    """Extract historical model IDs from ``~/.codex/state_5.sqlite``.

    Queries ``SELECT DISTINCT model FROM threads`` in read-only mode.

    Args:
        db_path: Optional explicit path to state_5.sqlite.

    Returns:
        List of distinct model IDs, or ``[]`` on missing file/query failure.
    """
    target = db_path or (Path.home() / ".codex" / "state_5.sqlite")
    try:
        if not target.is_file():
            return []
    except OSError:
        return []

    conn = None
    try:
        uri = f"file:{target.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    except Exception:
        try:
            conn = sqlite3.connect(str(target), timeout=2.0)
        except Exception:
            return []

    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT DISTINCT model FROM threads")
            rows = cursor.fetchall()
            models: list[str] = []
            for (m,) in rows:
                if isinstance(m, str):
                    cleaned = m.strip()
                    if cleaned and not cleaned.startswith("__") and cleaned not in models:
                        models.append(cleaned)
            return models
        finally:
            cursor.close()
    except Exception:
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def codex_display_name(model_id: str) -> str:
    """Derive a human-readable name for a Codex model id."""
    base = model_id.split("/")[-1].strip() or model_id
    parts = base.split("-")
    formatted: list[str] = []
    for p in parts:
        if p.lower().startswith("gpt"):
            formatted.append(p.upper())
        else:
            formatted.append(p.capitalize())
    return "-".join(formatted)


def _static_codex_ids() -> list[str]:
    return [mid for mid, _n, _d in CODEX_MODELS]


def discover_codex_models() -> list[tuple[str, str, str]]:
    """Discover Codex models: config.toml + binary + sqlite + static fallback.

    Sorts models by priority and relevance:
    1. Current model from ``config.toml`` (if any)
    2. ``gpt-6-*`` models (frontier/latest workhorses)
    3. ``gpt-5.6-*`` models
    4. ``gpt-5-*`` models
    5. Other ``gpt-*`` models
    6. All remaining discovered models

    Returns:
        List of ``(model_id, display_name, description)`` triples, deduplicated.
        Never empty while the static fallback exists.
    """
    current_model = read_codex_config_current_model()
    config_models = read_codex_config_models()
    bin_models = read_codex_binary_models()
    sqlite_models = read_codex_sqlite_models()

    metadata: dict[str, tuple[str, str]] = {}
    for mid, name, desc in CODEX_MODELS:
        metadata[mid] = (name, desc)

    for slug, dn, desc in bin_models:
        cur_name, cur_desc = metadata.get(slug, ("", ""))
        name = dn or cur_name or codex_display_name(slug)
        description = desc or cur_desc
        metadata[slug] = (name, description)

    for mid in config_models:
        if mid not in metadata:
            metadata[mid] = (codex_display_name(mid), "Configured in ~/.codex/config.toml")

    for mid in sqlite_models:
        if mid not in metadata:
            metadata[mid] = (codex_display_name(mid), "From ~/.codex history")

    seen: set[str] = set()
    ordered_ids: list[str] = []

    all_ids = (
        config_models + [m[0] for m in bin_models] + sqlite_models + [m[0] for m in CODEX_MODELS]
    )

    for mid in all_ids:
        clean = mid.strip()
        if clean and clean not in seen and not clean.startswith("__"):
            seen.add(clean)
            ordered_ids.append(clean)

    def _priority(mid: str) -> tuple[int, int]:
        low = mid.lower()
        if current_model and low == current_model.lower():
            return (0, 0)
        if low.startswith("gpt-6"):
            return (1, 0)
        if low.startswith("gpt-5.6"):
            return (2, 0)
        if low.startswith("gpt-5"):
            return (3, 0)
        if low.startswith("gpt"):
            return (4, 0)
        return (5, 0)

    ordered_ids.sort(key=_priority)

    triples: list[tuple[str, str, str]] = []
    for mid in ordered_ids:
        name, desc = metadata.get(mid, (codex_display_name(mid), ""))
        triples.append((mid, name, desc))

    return triples if triples else list(CODEX_MODELS)


def discover_codex_model_triples() -> list[tuple[str, str, str]]:
    """Alias to :func:`discover_codex_models` returning (id, name, desc) triples."""
    return discover_codex_models()


def get_codex_catalog(ttl: float = CODEX_CATALOG_TTL) -> list[str]:
    """Return the Codex model catalogue, cached per process with a TTL.

    Args:
        ttl: Cache lifetime in seconds.

    Returns:
        Model ids from :func:`discover_codex_models` (static fallback
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
            triples = discover_codex_models()
            ids = [t[0] for t in triples]
        except Exception:
            ids = _static_codex_ids()
        if not ids:
            ids = _static_codex_ids()
        _catalog_cache = (_now(), ids)
        return ids


def clear_codex_catalog_cache() -> None:
    """Drop the cached catalogue (tests / manual refresh)."""
    global _catalog_cache
    _catalog_cache = None
