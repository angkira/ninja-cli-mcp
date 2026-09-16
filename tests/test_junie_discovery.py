"""Dynamic Junie catalogue tests (CLI probe → settings.json → static fallback).

Discovery method: ``junie`` has no ``models`` subcommand; an invalid
``--model`` value makes it print ``Available models:`` rows to stderr
(local validation, no task run, no subscription spend).
"""

from __future__ import annotations

import subprocess

import pytest

import ninja_common.junie_discovery as jd
from ninja_common.junie_discovery import (
    discover_junie_models,
    get_junie_catalog,
    get_junie_default_effort,
    parse_junie_available_models,
    read_junie_settings_models,
)


PROBE_STDERR = (
    "Junie failed with the message: Invalid model: __ninja_list_probe__\n"
    "Available models:\n"
    "- Qwen/Qwen3.6-27B-FP8\n"
    "- claude-opus-4-6\n"
    "- deepseek-v4-flash\n"
    "- grok-4.6\n"
    "- sonnet\n"
)

PROBE_IDS = [
    "Qwen/Qwen3.6-27B-FP8",
    "claude-opus-4-6",
    "deepseek-v4-flash",
    "grok-4.6",
    "sonnet",
]


@pytest.fixture(autouse=True)
def _clear_caches():
    jd.clear_junie_catalog_cache()
    yield
    jd.clear_junie_catalog_cache()


def _result(stdout: str = "", stderr: str = "", returncode: int = 1):
    class _R:
        pass

    r = _R()
    r.stdout = stdout
    r.stderr = stderr
    r.returncode = returncode
    return r


# ── parser ────────────────────────────────────────────────────────────────


def test_parse_available_models_keeps_slash_ids() -> None:
    assert parse_junie_available_models(f"Starting…\n{PROBE_STDERR}") == PROBE_IDS


def test_parse_without_section_returns_empty() -> None:
    assert parse_junie_available_models("Starting…\nall good\n") == []
    assert parse_junie_available_models("") == []


def test_parse_deduplicates() -> None:
    text = "Available models:\n- grok-4.6\n- grok-4.6\n- sonnet\n"
    assert parse_junie_available_models(text) == ["grok-4.6", "sonnet"]


# ── CLI probe ─────────────────────────────────────────────────────────────


def test_run_cli_parses_stderr_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jd.shutil, "which", lambda _n: "/usr/bin/junie")
    monkeypatch.setattr(
        jd.subprocess, "run", lambda *a, **k: _result(stdout="Starting…", stderr=PROBE_STDERR)
    )
    assert jd._run_junie_models_cli() == PROBE_IDS


def test_run_cli_uses_stdin_devnull(monkeypatch: pytest.MonkeyPatch) -> None:
    """The probe must never block on stdin (bare ``junie models`` hangs)."""
    monkeypatch.setattr(jd.shutil, "which", lambda _n: "/usr/bin/junie")
    seen: dict = {}

    def _fake_run(*a, **k):
        seen.update(k)
        return _result(stderr=PROBE_STDERR)

    monkeypatch.setattr(jd.subprocess, "run", _fake_run)
    jd._run_junie_models_cli()
    assert seen.get("stdin") is subprocess.DEVNULL


def test_run_cli_no_binary_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jd.shutil, "which", lambda _n: None)
    monkeypatch.setattr(jd, "_which_junie", lambda: None)
    assert jd._run_junie_models_cli() == []


def test_run_cli_timeout_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jd, "_which_junie", lambda: "/usr/bin/junie")

    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="junie", timeout=15)

    monkeypatch.setattr(jd.subprocess, "run", _boom)
    assert jd._run_junie_models_cli() == []


def test_run_cli_unparsable_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jd, "_which_junie", lambda: "/usr/bin/junie")
    monkeypatch.setattr(jd.subprocess, "run", lambda *a, **k: _result(stderr="ok\n"))
    assert jd._run_junie_models_cli() == []


# ── settings.json ─────────────────────────────────────────────────────────


def test_settings_models_reads_json_string_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    """Junie writes effortPerModel as a JSON-encoded *string*."""
    monkeypatch.setattr(
        jd,
        "_read_junie_settings",
        lambda: {
            "effortPerModel": '{"grok-4.6":"low","deepseek-v4-flash":"high"}',
            "modelForLaunch": "gemini-3.8-flash",
        },
    )
    assert read_junie_settings_models() == ["grok-4.6", "deepseek-v4-flash", "gemini-3.8-flash"]


def test_settings_models_accepts_plain_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jd, "_read_junie_settings", lambda: {"effortPerModel": {"a-model": "low"}})
    assert read_junie_settings_models() == ["a-model"]


def test_settings_models_missing_file_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jd, "_read_junie_settings", lambda: {})
    assert read_junie_settings_models() == []


def test_default_effort_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        jd,
        "_read_junie_settings",
        lambda: {"effortPerModel": '{"Grok-4.6":"low","bad-model":"ultra"}'},
    )
    assert get_junie_default_effort("grok-4.6") == "low"
    assert get_junie_default_effort("bad-model") is None
    assert get_junie_default_effort("unknown") is None
    assert get_junie_default_effort(None) is None


# ── priority: CLI > settings > static ─────────────────────────────────────


def test_cli_beats_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jd, "_run_junie_models_cli", lambda **k: ["cli-model"])
    monkeypatch.setattr(jd, "read_junie_settings_models", lambda: ["settings-model"])
    ids = discover_junie_models()
    assert ids[0] == "cli-model"
    assert "settings-model" in ids  # settings-only ids are appended, CLI wins order
    assert "deepseek-v4-flash" in ids  # static last-resort tail


def test_empty_cli_falls_back_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jd, "_run_junie_models_cli", lambda **k: [])
    monkeypatch.setattr(jd, "read_junie_settings_models", lambda: ["settings-model"])
    ids = discover_junie_models()
    assert ids[0] == "settings-model"
    assert "deepseek-v4-flash" in ids


def test_empty_cli_and_settings_fall_back_to_static(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No binary + no settings → static catalogue, no error raised."""
    monkeypatch.setattr(jd, "_run_junie_models_cli", lambda **k: [])
    monkeypatch.setattr(jd, "read_junie_settings_models", lambda: [])
    from ninja_common.defaults import JUNIE_MODELS

    assert discover_junie_models() == [mid for mid, _n, _d in JUNIE_MODELS]


# ── TTL cache ─────────────────────────────────────────────────────────────


def test_catalog_cached_with_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _fake(**k):
        calls["n"] += 1
        return ["cli-model"]

    monkeypatch.setattr(jd, "_run_junie_models_cli", _fake)
    monkeypatch.setattr(jd, "read_junie_settings_models", lambda: [])
    assert get_junie_catalog() == get_junie_catalog()
    assert calls["n"] == 1


def test_catalog_refetch_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _fake(**k):
        calls["n"] += 1
        return ["cli-model"]

    monkeypatch.setattr(jd, "_run_junie_models_cli", _fake)
    monkeypatch.setattr(jd, "read_junie_settings_models", lambda: [])
    get_junie_catalog(ttl=300.0)
    get_junie_catalog(ttl=0.0)
    assert calls["n"] == 2


# ── model_selector wiring ─────────────────────────────────────────────────


def test_selector_discovers_dynamically(monkeypatch: pytest.MonkeyPatch) -> None:
    import ninja_config.model_selector as ms

    monkeypatch.setattr(
        "ninja_common.junie_discovery._run_junie_models_cli", lambda **k: list(PROBE_IDS)
    )
    monkeypatch.setattr("ninja_common.junie_discovery.read_junie_settings_models", lambda: [])
    from ninja_config.ui.model_cache import clear_model_cache

    clear_model_cache()
    try:
        triples = ms.discover_junie_models()
        # CLI order wins; static-only ids trail as last-resort fallback.
        assert [mid for mid, _n, _d in triples][: len(PROBE_IDS)] == PROBE_IDS
        models = ms._get_junie_models()
        assert [m.id for m in models][: len(PROBE_IDS)] == PROBE_IDS
        assert all(m.provider == "junie" for m in models)
        assert set(PROBE_IDS) <= {m.id for m in ms.get_provider_models("junie", "junie")}
    finally:
        clear_model_cache()


def test_selector_falls_back_to_static_without_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ninja_config.model_selector as ms
    from ninja_common.defaults import JUNIE_MODELS

    monkeypatch.setattr("ninja_common.junie_discovery._run_junie_models_cli", lambda **k: [])
    monkeypatch.setattr("ninja_common.junie_discovery.read_junie_settings_models", lambda: [])
    assert [m.id for m in ms._get_junie_models()] == [mid for mid, _n, _d in JUNIE_MODELS]


def test_run_junie_models_wrapper_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """``model_selector._run_junie_models`` mirrors the opencode probe style."""
    import ninja_config.model_selector as ms

    monkeypatch.setattr(
        "ninja_common.junie_discovery._run_junie_models_cli", lambda **k: list(PROBE_IDS)
    )
    assert ms._run_junie_models() == PROBE_IDS

    def _boom(**k):
        raise OSError("nope")

    monkeypatch.setattr("ninja_common.junie_discovery._run_junie_models_cli", _boom)
    assert ms._run_junie_models() == []


def test_cached_get_junie_models_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    import ninja_config.model_selector as ms
    from ninja_config.ui import model_cache
    from ninja_config.ui.model_cache import cached_get_junie_models, clear_model_cache

    calls = {"n": 0}
    real = ms._get_junie_models

    def _counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(model_cache, "_get_junie_models", _counting)
    monkeypatch.setattr(
        "ninja_common.junie_discovery._run_junie_models_cli", lambda **k: list(PROBE_IDS)
    )
    monkeypatch.setattr("ninja_common.junie_discovery.read_junie_settings_models", lambda: [])
    clear_model_cache()
    try:
        first = cached_get_junie_models()
        second = cached_get_junie_models()
        assert calls["n"] == 1
        assert [m.id for m in first] == [m.id for m in second]
        assert [m.id for m in first][: len(PROBE_IDS)] == PROBE_IDS
    finally:
        clear_model_cache()


# ── TUI search path ───────────────────────────────────────────────────────


def test_search_resolves_junie_dynamically(monkeypatch: pytest.MonkeyPatch) -> None:
    """The picker search path serves the dynamic catalogue, not statics."""
    from ninja_config.ui import model_autocomplete as ma

    sentinel = object()
    monkeypatch.setattr(ma, "cached_get_junie_models", lambda: sentinel)
    assert ma.resolve_search_models("junie", "junie") is sentinel


def test_search_non_junie_uses_provider_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from ninja_config.ui import model_autocomplete as ma

    def _boom() -> None:
        raise AssertionError("junie cache must not be used for opencode")

    monkeypatch.setattr(ma, "cached_get_junie_models", _boom)
    monkeypatch.setattr(ma, "cached_get_provider_models", lambda o, p: [f"{o}/{p}"])
    assert ma.resolve_search_models("opencode", "openrouter") == ["opencode/openrouter"]


def test_guess_provider_classifies_dynamic_junie_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ninja_config.model_selector import Model
    from ninja_config.ui import model_autocomplete as ma

    monkeypatch.setattr(
        ma,
        "cached_get_junie_models",
        lambda: [Model(id="claude-opus-4-6", name="x", description="", provider="junie")],
    )
    assert ma.guess_provider("claude-opus-4-6", operator="junie") == "junie"


# ── validation against the dynamic catalogue ──────────────────────────────


def _mock_catalog(monkeypatch: pytest.MonkeyPatch, ids: list[str]) -> None:
    monkeypatch.setattr(jd, "_run_junie_models_cli", lambda **k: list(ids))
    monkeypatch.setattr(jd, "read_junie_settings_models", lambda: [])


def test_resolve_accepts_cli_only_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from ninja_common.operator_models import resolve_junie_model

    _mock_catalog(monkeypatch, ["claude-opus-4-6", "deepseek-v4-flash"])
    assert resolve_junie_model("claude-opus-4-6") == "claude-opus-4-6"


def test_resolve_rejects_garbage_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    from ninja_common.operator_models import resolve_junie_model

    _mock_catalog(monkeypatch, ["deepseek-v4-flash"])
    with pytest.raises(ValueError, match="Unknown Junie model"):
        resolve_junie_model("openrouter/deepseek/deepseek-v4.1-flash")


def test_normalize_keeps_slash_id_and_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    from ninja_common.operator_models import normalize_junie_model

    _mock_catalog(monkeypatch, list(PROBE_IDS))
    assert normalize_junie_model("Qwen/Qwen3.6-27B-FP8") == "Qwen/Qwen3.6-27B-FP8"
    assert normalize_junie_model("grok") == "grok-4.6"
    assert normalize_junie_model("junie/deepseek-v4-flash") == "deepseek-v4-flash"


def test_compatible_uses_dynamic_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    from ninja_common.operator_models import is_model_compatible

    _mock_catalog(monkeypatch, ["claude-opus-4-6", "deepseek-v4-flash"])
    assert is_model_compatible("claude-opus-4-6", "junie") is True
    # Static ids stay valid (last-resort tail); a truly foreign id is rejected.
    assert is_model_compatible("gpt-5.6-luna", "junie") is True
    assert is_model_compatible("openrouter/deepseek/deepseek-v4.1-flash", "junie") is False


def test_compatible_static_fallback_without_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ninja_common.operator_models import is_model_compatible

    _mock_catalog(monkeypatch, [])
    # Empty CLI + empty settings → static catalogue via real discover path.
    assert is_model_compatible("deepseek-v4-flash", "junie") is True
    assert is_model_compatible("nope-1", "junie") is False
