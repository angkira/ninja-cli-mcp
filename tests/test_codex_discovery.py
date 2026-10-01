"""Dynamic Codex catalogue tests (config.toml → binary metadata → sqlite history → static fallback).

Tests cover:
- TOML configuration parsing and fallback regex parser
- Binary embedded JSON metadata scanning
- SQLite history extraction from ~/.codex/state_5.sqlite
- Model priority ranking (current -> gpt-6 -> gpt-5.6 -> other -> static fallback)
- In-process TTL cache
- Integration with operator_models, model_selector, model_cache, and model_autocomplete
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

import pytest

import ninja_common.codex_discovery as cd
from ninja_common.codex_discovery import (
    _parse_toml_fallback,
    clear_codex_catalog_cache,
    codex_display_name,
    discover_codex_models,
    get_codex_catalog,
    parse_codex_binary_metadata,
    read_codex_binary_models,
    read_codex_config_current_model,
    read_codex_config_models,
    read_codex_sqlite_models,
)
from ninja_common.defaults import CODEX_MODELS


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_codex_catalog_cache()
    from ninja_config.ui.model_cache import clear_model_cache

    clear_model_cache()
    yield
    clear_codex_catalog_cache()
    clear_model_cache()


# ── TOML parsing & fallback ───────────────────────────────────────────────


def test_parse_toml_fallback_extracts_all_sections() -> None:
    content = """
    # Top-level settings
    model = "gpt-6-luna"
    temperature = 0.7

    [tui.model_availability_nux]
    "gpt-6-sol" = "2026-03-01T00:00:00Z"
    gpt-6.1-sol = "2026-03-15T00:00:00Z"

    [notice.model_migrations]
    gpt-5-legacy = "gpt-6-luna"
    "gpt-5.6-old" = "gpt-6-sol"
    """
    data = _parse_toml_fallback(content)
    assert data.get("model") == "gpt-6-luna"
    assert "gpt-6-sol" in data.get("tui", {}).get("model_availability_nux", {})
    assert "gpt-6.1-sol" in data.get("tui", {}).get("model_availability_nux", {})
    assert data.get("notice", {}).get("model_migrations", {}).get("gpt-5-legacy") == "gpt-6-luna"


def test_parse_toml_fallback_empty_or_comment_only() -> None:
    data = _parse_toml_fallback("# Only comments\n\n   # another comment\n")
    assert data == {}


def test_read_codex_config_reads_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        model = "gpt-6-astra"

        [tui.model_availability_nux]
        gpt-6-sol = "2026-04-01"
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(cd.Path, "home", lambda: tmp_path)
    # Put config in tmp_path/.codex/config.toml
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(cfg.read_text(encoding="utf-8"), encoding="utf-8")

    assert read_codex_config_current_model() == "gpt-6-astra"
    discovered = read_codex_config_models()
    assert "gpt-6-astra" in discovered
    assert "gpt-6-sol" in discovered


def test_read_codex_config_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cd.Path, "home", lambda: tmp_path)
    assert read_codex_config_current_model() is None
    assert read_codex_config_models() == []


# ── Binary scanning ───────────────────────────────────────────────────────


def test_parse_codex_binary_metadata_extracts_models() -> None:
    model1 = {
        "slug": "gpt-6-test-model",
        "display_name": "GPT-6 Test Model",
        "description": "High performance test model",
    }
    model2 = {
        "slug": "gpt-6.1-sol-mini",
        "display_name": "GPT-6.1 Sol Mini",
        "description": "Compact sol model",
    }
    raw = b"\x00\x01padding" + json.dumps(model1).encode("utf-8") + b"\xff\xfe"
    raw += b"more padding" + json.dumps(model2).encode("utf-8") + b"\x00"

    results = parse_codex_binary_metadata(raw)
    slugs = [r[0] for r in results]
    assert "gpt-6-test-model" in slugs
    assert "gpt-6.1-sol-mini" in slugs

    entry1 = next(r for r in results if r[0] == "gpt-6-test-model")
    assert entry1[1] == "GPT-6 Test Model"
    assert entry1[2] == "High performance test model"


def test_parse_codex_binary_metadata_skips_invalid_json() -> None:
    raw = b"random binary without slug patterns \x00\x01\xff"
    results = parse_codex_binary_metadata(raw)
    assert results == []


def test_read_codex_binary_models_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cd, "_which_codex", lambda *a, **k: None)
    assert read_codex_binary_models() == []


def test_read_codex_binary_models_from_mock_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_bin = tmp_path / "codex"
    payload = json.dumps(
        {"slug": "gpt-6-mock", "display_name": "Mock 6", "description": "Mock desc"}
    ).encode("utf-8")
    fake_bin.write_bytes(b"\x00" * 32 + payload + b"\x00" * 32)

    monkeypatch.setattr(cd, "_which_codex", lambda *a, **k: str(fake_bin))
    results = read_codex_binary_models()
    assert len(results) == 1
    assert results[0] == ("gpt-6-mock", "Mock 6", "Mock desc")


# ── SQLite history reading ────────────────────────────────────────────────


def test_read_codex_sqlite_models(tmp_path: Path) -> None:
    db_file = tmp_path / "state_5.sqlite"
    conn = sqlite3.connect(str(db_file))
    try:
        conn.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, model TEXT)")
        conn.execute("INSERT INTO threads VALUES ('t1', 'gpt-6-sol')")
        conn.execute("INSERT INTO threads VALUES ('t2', 'gpt-5.6-luna')")
        conn.execute("INSERT INTO threads VALUES ('t3', 'gpt-6-sol')")  # duplicate
        conn.execute("INSERT INTO threads VALUES ('t4', '__internal__')")  # should filter
        conn.execute("INSERT INTO threads VALUES ('t5', '')")  # should filter
        conn.commit()
    finally:
        conn.close()

    models = read_codex_sqlite_models(db_path=db_file)
    assert "gpt-6-sol" in models
    assert "gpt-5.6-luna" in models
    assert "__internal__" not in models
    assert "" not in models


def test_read_codex_sqlite_models_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.sqlite"
    assert read_codex_sqlite_models(db_path=missing) == []


# ── Priority & ranking ────────────────────────────────────────────────────


def test_discover_codex_models_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. current model is gpt-6-luna
    monkeypatch.setattr(cd, "read_codex_config_current_model", lambda: "gpt-6-luna")
    monkeypatch.setattr(cd, "read_codex_config_models", lambda: ["gpt-6-luna", "gpt-5-older"])
    monkeypatch.setattr(
        cd,
        "read_codex_binary_models",
        lambda: [
            ("gpt-6.1-sol", "GPT-6.1 Sol", "Workhorse"),
            ("gpt-5.6-sol", "GPT-5.6 Sol", "Older"),
        ],
    )
    monkeypatch.setattr(cd, "read_codex_sqlite_models", lambda **k: ["gpt-6-astra"])

    triples = discover_codex_models()
    ids = [t[0] for t in triples]

    # Current model from config.toml MUST be first
    assert ids[0] == "gpt-6-luna"

    # All gpt-6 family models should come before gpt-5.6 and gpt-5
    idx_6_sol = ids.index("gpt-6.1-sol")
    idx_6_astra = ids.index("gpt-6-astra")
    idx_5_6_sol = ids.index("gpt-5.6-sol")
    idx_5_older = ids.index("gpt-5-older")

    assert idx_6_sol < idx_5_6_sol
    assert idx_6_astra < idx_5_6_sol
    assert idx_5_6_sol < idx_5_older


def test_empty_sources_fall_back_to_static(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cd, "read_codex_config_current_model", lambda: None)
    monkeypatch.setattr(cd, "read_codex_config_models", lambda: [])
    monkeypatch.setattr(cd, "read_codex_binary_models", lambda: [])
    monkeypatch.setattr(cd, "read_codex_sqlite_models", lambda **k: [])

    triples = discover_codex_models()
    static_ids = [t[0] for t in CODEX_MODELS]
    discovered_ids = [t[0] for t in triples]

    for sid in static_ids:
        assert sid in discovered_ids


def test_codex_display_name_helper() -> None:
    assert codex_display_name("gpt-6-luna") == "GPT-6-Luna"
    assert codex_display_name("gpt-6.1-sol") == "GPT-6.1-Sol"
    assert codex_display_name("custom-model-fast") == "Custom-Model-Fast"


# ── TTL Cache ─────────────────────────────────────────────────────────────


def test_catalog_cached_with_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _mock_discover():
        calls["n"] += 1
        return [("gpt-6-luna", "GPT-6 Luna", "Fast")]

    monkeypatch.setattr(cd, "discover_codex_models", _mock_discover)
    res1 = get_codex_catalog()
    res2 = get_codex_catalog()
    assert res1 == res2
    assert calls["n"] == 1


def test_catalog_refetch_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _mock_discover():
        calls["n"] += 1
        return [("gpt-6-luna", "GPT-6 Luna", "Fast")]

    monkeypatch.setattr(cd, "discover_codex_models", _mock_discover)
    get_codex_catalog(ttl=300.0)
    get_codex_catalog(ttl=0.0)
    assert calls["n"] == 2


# ── Model Selector wiring ─────────────────────────────────────────────────


def test_model_selector_loads_codex_dynamically(monkeypatch: pytest.MonkeyPatch) -> None:
    import ninja_config.model_selector as ms

    test_triples = [
        ("gpt-6-luna", "GPT-6 Luna", "Fast cost-efficient model"),
        ("gpt-6.1-sol", "GPT-6.1 Sol", "Workhorse model"),
    ]
    monkeypatch.setattr(ms, "discover_codex_models", lambda: test_triples)
    monkeypatch.setattr(cd, "read_codex_config_current_model", lambda: "gpt-6-luna")

    models = ms._get_codex_models()
    assert [m.id for m in models] == ["gpt-6-luna", "gpt-6.1-sol"]
    assert models[0].recommended is True
    assert models[1].recommended is False
    assert all(m.provider == "codex" for m in models)


# ── UI Model Cache & Autocomplete ─────────────────────────────────────────


def test_cached_get_codex_models_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    from ninja_config.model_selector import Model
    from ninja_config.ui import model_cache
    from ninja_config.ui.model_cache import cached_get_codex_models, clear_model_cache

    calls = {"n": 0}

    def _mock_get():
        calls["n"] += 1
        return [Model(id="gpt-6-luna", name="Luna", description="", provider="codex")]

    monkeypatch.setattr(model_cache, "_get_codex_models", _mock_get)
    clear_model_cache()
    try:
        first = cached_get_codex_models()
        second = cached_get_codex_models()
        assert calls["n"] == 1
        assert [m.id for m in first] == [m.id for m in second]
        assert first[0].id == "gpt-6-luna"
    finally:
        clear_model_cache()


def test_resolve_search_models_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    from ninja_config.model_selector import Model
    from ninja_config.ui import model_autocomplete as ma

    mock_models = [Model(id="gpt-6-luna", name="Luna", description="", provider="codex")]
    monkeypatch.setattr(ma, "cached_get_codex_models", lambda: mock_models)

    assert ma.resolve_search_models("codex", "codex") == mock_models


def test_guess_provider_classifies_dynamic_codex_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from ninja_config.model_selector import Model
    from ninja_config.ui import model_autocomplete as ma

    monkeypatch.setattr(
        ma,
        "cached_get_codex_models",
        lambda: [Model(id="gpt-6-custom-discovered", name="x", description="", provider="codex")],
    )
    assert ma.guess_provider("gpt-6-custom-discovered", operator="codex") == "codex"


# ── Operator Model Routing ────────────────────────────────────────────────


def test_operator_compatibility_dynamic_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    from ninja_common.operator_models import is_model_compatible, resolve_operator_model

    monkeypatch.setattr(
        cd, "get_codex_catalog", lambda **k: ["gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"]
    )

    assert is_model_compatible("gpt-6-luna", "codex") is True
    assert is_model_compatible("gpt-6.1-sol", "codex") is True
    assert is_model_compatible("codex/gpt-6-luna", "codex") is True
    assert is_model_compatible("openai/gpt-6-astra", "codex") is True
    assert is_model_compatible("unknown-claude-model", "codex") is False

    assert resolve_operator_model("codex/gpt-6-luna", "codex") == "gpt-6-luna"
    assert resolve_operator_model("gpt-6.1-sol", "codex") == "gpt-6.1-sol"
