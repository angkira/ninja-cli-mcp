"""Tests for the inline API-key rows on the API Keys tab (no event loop)."""

from __future__ import annotations

from ninja_config.modern_tui import APIKeyRow


def _row(value: str = "sk-test-value") -> APIKeyRow:
    return APIKeyRow("OPENAI_API_KEY", "OpenAI", "coder", value)


def test_api_key_row_exposes_env_var_and_display_name() -> None:
    """The row carries the env var / display name the save handler needs."""
    row = _row()

    assert row.env_var == "OPENAI_API_KEY"
    assert row.display_name == "OpenAI"
    assert row.module == "coder"


def test_api_key_row_header_shows_name_and_masks_secret() -> None:
    """The row header names the provider but never leaks the raw key."""
    head = _row("sk-super-secret")._head_text()

    assert "OpenAI" in head
    assert "sk-super-secret" not in head


def test_api_key_row_header_marks_unset() -> None:
    """An empty value renders as 'not set' rather than a blank row."""
    assert "not set" in _row("")._head_text()
