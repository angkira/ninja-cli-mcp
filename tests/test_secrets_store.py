"""
Tests for ninja_config.secrets_store — SecretStore backends.

Integration test for EncryptedFileBackend is deliberately skipped;
CredentialManager is covered by its own test suite.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import keyring.backends.fail
import pytest

import ninja_config.secrets_store as store_module
from ninja_config.secrets_store import (
    KNOWN_SECRET_NAMES,
    ChainBackend,
    EncryptedFileBackend,
    KeyringBackend,
    SecretStore,
    SecretStoreUnavailable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeBackend:
    """Simple in-memory backend for testing ChainBackend composition."""

    def __init__(self, name: str, data: dict[str, str] | None = None) -> None:
        self._name = name
        self._data: dict[str, str] = data or {}
        self.available = True

    def get(self, name: str) -> str | None:
        return self._data.get(name)

    def set(self, name: str, value: str) -> None:
        if not self.available:
            raise SecretStoreUnavailable(f"{self._name} unavailable")
        self._data[name] = value

    def delete(self, name: str) -> None:
        self._data.pop(name, None)

    def list_names(self) -> list[str]:
        if not self.available:
            return []
        return sorted(self._data.keys())

    def backend_name(self) -> str:
        return self._name


# ---------------------------------------------------------------------------
# KNOWN_SECRET_NAMES
# ---------------------------------------------------------------------------


def test_known_secret_names_is_frozenset() -> None:
    assert isinstance(KNOWN_SECRET_NAMES, frozenset)


def test_known_secret_names_contains_expected_keys() -> None:
    expected = {
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "PERPLEXITY_API_KEY",
        "ZAI_API_KEY",
        "GROQ_API_KEY",
        "DEEPSEEK_API_KEY",
        "MISTRAL_API_KEY",
        "GOOGLE_API_KEY",
    }
    assert expected == KNOWN_SECRET_NAMES


# ---------------------------------------------------------------------------
# SecretStore Protocol
# ---------------------------------------------------------------------------


def test_fake_backend_satisfies_protocol() -> None:
    fb = FakeBackend("test")
    assert isinstance(fb, SecretStore)


# ---------------------------------------------------------------------------
# KeyringBackend
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_keyring():
    """Patch the keyring module used inside secrets_store."""
    with patch.object(store_module, "keyring") as mock_kr:
        # make get_keyring return a dummy so backend_name works
        dummy_kr = MagicMock()
        dummy_kr.__class__.__name__ = "SecretService"
        mock_kr.get_keyring.return_value = dummy_kr
        mock_kr.errors = MagicMock()
        mock_kr.errors.PasswordDeleteError = Exception
        yield mock_kr


def test_keyring_backend_get_returns_value(mock_keyring) -> None:
    mock_keyring.get_password.return_value = "sk-test-123"
    backend = KeyringBackend()
    result = backend.get("OPENAI_API_KEY")
    assert result == "sk-test-123"
    mock_keyring.get_password.assert_called_once_with("ninja-mcp", "OPENAI_API_KEY")


def test_keyring_backend_get_returns_none_when_missing(mock_keyring) -> None:
    mock_keyring.get_password.return_value = None
    backend = KeyringBackend()
    assert backend.get("OPENAI_API_KEY") is None


def test_keyring_backend_set(mock_keyring) -> None:
    backend = KeyringBackend()
    backend.set("OPENAI_API_KEY", "sk-abc")
    mock_keyring.set_password.assert_called_once_with("ninja-mcp", "OPENAI_API_KEY", "sk-abc")


def test_keyring_backend_delete(mock_keyring) -> None:
    backend = KeyringBackend()
    backend.delete("OPENAI_API_KEY")
    mock_keyring.delete_password.assert_called_once_with("ninja-mcp", "OPENAI_API_KEY")


def test_keyring_backend_delete_ignores_missing(mock_keyring) -> None:
    mock_keyring.delete_password.side_effect = mock_keyring.errors.PasswordDeleteError
    backend = KeyringBackend()
    # Must not raise
    backend.delete("OPENAI_API_KEY")


def test_keyring_backend_list_names_returns_present(mock_keyring) -> None:
    # Only OPENAI_API_KEY and GROQ_API_KEY are "in" the keyring
    def _get_password(service, name):
        if name in ("OPENAI_API_KEY", "GROQ_API_KEY"):
            return "some-value"
        return None

    mock_keyring.get_password.side_effect = _get_password
    backend = KeyringBackend()
    names = backend.list_names()
    assert set(names) == {"OPENAI_API_KEY", "GROQ_API_KEY"}


def test_keyring_backend_list_names_empty_when_none_present(mock_keyring) -> None:
    mock_keyring.get_password.return_value = None
    backend = KeyringBackend()
    assert backend.list_names() == []


def test_keyring_backend_backend_name(mock_keyring) -> None:
    backend = KeyringBackend()
    name = backend.backend_name()
    assert "OS keyring" in name
    assert "SecretService" in name


# ---------------------------------------------------------------------------
# ChainBackend
# ---------------------------------------------------------------------------


def test_chain_get_returns_first_hit() -> None:
    a = FakeBackend("a", {"K1": "from-a"})
    b = FakeBackend("b", {"K1": "from-b", "K2": "from-b"})
    chain = ChainBackend([a, b])  # type: ignore[arg-type]
    assert chain.get("K1") == "from-a"
    assert chain.get("K2") == "from-b"
    assert chain.get("K3") is None


def test_chain_get_falls_through_empty_first_backend() -> None:
    a = FakeBackend("a", {})
    b = FakeBackend("b", {"K1": "from-b"})
    chain = ChainBackend([a, b])  # type: ignore[arg-type]
    assert chain.get("K1") == "from-b"


def test_chain_set_goes_to_first_backend() -> None:
    a = FakeBackend("a")
    b = FakeBackend("b")
    chain = ChainBackend([a, b])  # type: ignore[arg-type]
    chain.set("K1", "value")
    assert a.get("K1") == "value"
    assert b.get("K1") is None


def test_chain_delete_removes_from_all_backends() -> None:
    a = FakeBackend("a", {"K1": "val"})
    b = FakeBackend("b", {"K1": "val"})
    chain = ChainBackend([a, b])  # type: ignore[arg-type]
    chain.delete("K1")
    assert a.get("K1") is None
    assert b.get("K1") is None


def test_chain_list_names_unions_backends() -> None:
    a = FakeBackend("a", {"K1": "v", "K2": "v"})
    b = FakeBackend("b", {"K2": "v", "K3": "v"})
    chain = ChainBackend([a, b])  # type: ignore[arg-type]
    assert set(chain.list_names()) == {"K1", "K2", "K3"}


def test_chain_backend_name_returns_first_usable() -> None:
    a = FakeBackend("primary-backend")
    b = FakeBackend("fallback-backend")
    chain = ChainBackend([a, b])  # type: ignore[arg-type]
    assert chain.backend_name() == "primary-backend"


# ---------------------------------------------------------------------------
# default_store
# ---------------------------------------------------------------------------


def test_default_store_returns_encrypted_only_when_keyring_is_fail_keyring() -> None:
    """When keyring is fail.Keyring, default_store should use encrypted file only."""
    # Reset module singleton so factory runs fresh
    store_module._default_store = None

    fake_fail_kr = keyring.backends.fail.Keyring()

    with patch.object(store_module, "keyring") as mock_kr:
        mock_kr.get_keyring.return_value = fake_fail_kr
        mock_kr.backends = MagicMock()
        mock_kr.backends.fail = MagicMock()
        mock_kr.backends.fail.Keyring = keyring.backends.fail.Keyring

        result = store_module.default_store()

    assert isinstance(result, ChainBackend)
    # The chain should contain only EncryptedFileBackend (no KeyringBackend)
    backends = result._backends
    assert all(isinstance(b, EncryptedFileBackend) for b in backends)
    assert len(backends) == 1

    # Reset after test to avoid singleton bleed
    store_module._default_store = None


def test_default_store_includes_keyring_when_functional() -> None:
    """When keyring is functional, default_store should include KeyringBackend first."""
    store_module._default_store = None

    # Use a non-fail keyring class
    functional_kr = MagicMock()
    functional_kr.__class__ = type("SecretService", (), {})

    with patch.object(store_module, "keyring") as mock_kr:
        mock_kr.get_keyring.return_value = functional_kr
        mock_kr.backends = MagicMock()
        mock_kr.backends.fail = MagicMock()
        mock_kr.backends.fail.Keyring = keyring.backends.fail.Keyring

        result = store_module.default_store()

    assert isinstance(result, ChainBackend)
    backends = result._backends
    assert isinstance(backends[0], KeyringBackend)
    assert isinstance(backends[1], EncryptedFileBackend)

    store_module._default_store = None


@pytest.mark.skip(reason="EncryptedFileBackend integration covered by CredentialManager tests")
def test_encrypted_file_backend_integration() -> None:
    """Skipped — CredentialManager has its own test suite."""
