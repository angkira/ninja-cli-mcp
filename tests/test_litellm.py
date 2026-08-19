"""Tests for the LiteLLM provider configuration helpers."""

from __future__ import annotations

import json

import pytest

from ninja_config import litellm as ll


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Point the litellm config path at a temp dir."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_write_and_read_roundtrip(tmp_config):
    assert ll.write_litellm_config("http://localhost:4000/v1", "sk-test", ["gpt-4o", "deepseek-chat"])
    cfg = ll.read_litellm_config()
    assert cfg is not None
    assert cfg["base_url"] == "http://localhost:4000/v1"
    assert cfg["api_key"] == "sk-test"
    assert cfg["models"] == ["gpt-4o", "deepseek-chat"]
    assert ll.is_litellm_configured()


def test_write_strips_trailing_slash(tmp_config):
    ll.write_litellm_config("http://host:4000/v1/", "k", ["m"])
    cfg = ll.read_litellm_config()
    assert cfg is not None
    assert cfg["base_url"] == "http://host:4000/v1"


def test_read_absent_returns_none(tmp_config):
    assert ll.read_litellm_config() is None
    assert not ll.is_litellm_configured()


def test_remove_litellm(tmp_config):
    ll.write_litellm_config("http://h:1/v1", "k", ["m"])
    assert ll.is_litellm_configured()
    assert ll.remove_litellm_config()
    assert not ll.is_litellm_configured()
    assert ll.read_litellm_config() is None


def test_write_preserves_existing_opencode_config(tmp_config):
    path = tmp_config / "opencode" / "opencode.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"experimental": {"x": 1}, "provider": {"anthropic": {"npm": "p"}}}))
    ll.write_litellm_config("http://h:1/v1", "k", ["m"])
    data = json.loads(path.read_text())
    assert data["experimental"]["x"] == 1
    assert "anthropic" in data["provider"]
    assert "litellm" in data["provider"]


def test_remove_litellm_preserves_other_providers(tmp_config):
    path = tmp_config / "opencode" / "opencode.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "provider": {
                    "litellm": {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": "x"}},
                    "anthropic": {"npm": "p"},
                }
            }
        )
    )
    assert ll.remove_litellm_config()
    data = json.loads(path.read_text())
    assert "litellm" not in data["provider"]
    assert "anthropic" in data["provider"]
