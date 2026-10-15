"""Tests for the LiteLLM provider configuration helpers (OpenCode v2 opencode.jsonc)."""

from __future__ import annotations

import json

import pytest

from ninja_config import litellm as ll


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Point the OpenCode config home at a temp dir."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def _config_path(tmp_config):
    return tmp_config / "opencode" / "opencode.jsonc"


def test_write_and_read_roundtrip(tmp_config):
    assert ll.write_litellm_config(
        "http://localhost:4000/v1", "sk-test", ["gpt-4o", "deepseek-chat"]
    )
    cfg = ll.read_litellm_config()
    assert cfg is not None
    assert cfg["base_url"] == "http://localhost:4000/v1"
    assert cfg["api_key"] == "sk-test"
    assert cfg["models"] == ["gpt-4o", "deepseek-chat"]
    assert ll.is_litellm_configured()


def test_write_uses_v2_provider_shape(tmp_config):
    ll.write_litellm_config("http://h:1/v1", "", ["m"])
    data = json.loads(_config_path(tmp_config).read_text())
    provider = data["providers"]["litellm"]
    assert provider["package"] == ll.LITELLM_PACKAGE
    assert provider["settings"]["baseURL"] == "http://h:1/v1"
    assert provider["models"]["m"]["modelID"] == "m"
    assert provider["env"] == ["LITELLM_API_KEY", "LITE_LLM_KEY"]
    assert "npm" not in provider and "options" not in provider


def test_empty_api_key_is_not_stored(tmp_config):
    ll.write_litellm_config("http://h:1/v1", "", ["m"])
    data = json.loads(_config_path(tmp_config).read_text())
    assert "apiKey" not in data["providers"]["litellm"]["settings"]


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


def test_write_preserves_existing_v2_config(tmp_config):
    path = _config_path(tmp_config)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "plugins": ["/x/litellm-provider.js"],
                "mcp": {"servers": {"loki": {"type": "remote"}}},
                "providers": {"anthropic": {"package": "@opencode/ai/providers/anthropic"}},
            }
        )
    )
    ll.write_litellm_config("http://h:1/v1", "k", ["m"])
    data = json.loads(path.read_text())
    assert data["plugins"] == ["/x/litellm-provider.js"]
    assert data["mcp"]["servers"]["loki"]["type"] == "remote"
    assert "anthropic" in data["providers"]
    assert "litellm" in data["providers"]


def test_reads_jsonc_with_comments_and_trailing_commas(tmp_config):
    path = _config_path(tmp_config)
    path.parent.mkdir(parents=True)
    path.write_text(
        """{
  // user comment with a fake url: http://not-a-comment
  "$schema": "https://opencode.ai/config.json",
  "providers": {
    "litellm": {
      "settings": { "baseURL": "https://proxy.example/v1", }, /* block */
      "models": { "m1": { "modelID": "upstream-m1" }, },
    },
  },
}
"""
    )
    cfg = ll.read_litellm_config()
    assert cfg is not None
    assert cfg["base_url"] == "https://proxy.example/v1"
    assert cfg["models"] == ["upstream-m1"]


def test_remove_preserves_other_providers(tmp_config):
    path = _config_path(tmp_config)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "providers": {
                    "litellm": {"settings": {"baseURL": "x"}},
                    "anthropic": {"package": "p"},
                }
            }
        )
    )
    assert ll.remove_litellm_config()
    data = json.loads(path.read_text())
    assert "litellm" not in data["providers"]
    assert "anthropic" in data["providers"]
