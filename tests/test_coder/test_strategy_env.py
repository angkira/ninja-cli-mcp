"""Child-process env for coding CLIs: our key if present, else operator auth."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ninja_coder.strategies.base import subprocess_env


if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_strips_inherited_provider_keys(monkeypatch: MonkeyPatch) -> None:
    """A stale host API key must not leak into the child environment."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "stale-host-key")
    monkeypatch.setenv("OPENAI_API_KEY", "stale-host-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stale-host-key")

    env = subprocess_env()

    assert "OPENROUTER_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env


def test_injects_our_key_when_present() -> None:
    env = subprocess_env(api_key="sk-or-ours")
    assert env["OPENROUTER_API_KEY"] == "sk-or-ours"
    assert env["OPENAI_API_KEY"] == "sk-or-ours"


def test_no_key_defers_to_operator_auth() -> None:
    env = subprocess_env(api_key="")
    assert "OPENROUTER_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env


def test_extra_values_applied() -> None:
    env = subprocess_env(api_key="k", extra={"XDG_CONFIG_HOME": "/tmp/x"})
    assert env["XDG_CONFIG_HOME"] == "/tmp/x"
