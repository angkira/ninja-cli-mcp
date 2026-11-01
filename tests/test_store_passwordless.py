"""Regression tests: passwordless secret store must never get a bogus password.

A non-empty password prompted/forwarded for a passwordless store made
decryption fail, ``get_secret`` returned None and providers cached an empty key.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

import pytest

import ninja_config.secrets_store as store_module
from ninja_common import secrets as common_secrets
from ninja_common.daemon import DaemonManager
from ninja_config.credentials import CredentialManager, EncryptionError


if TYPE_CHECKING:
    from pathlib import Path


SECRET_NAME = "PERPLEXITY_API_KEY"
SECRET_VALUE = "pplx-test-value-not-real"


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated DB path with a clean in-process password/singleton state."""
    path = tmp_path / "credentials.db"
    monkeypatch.setenv("NINJA_CREDENTIALS_DB", str(path))
    for var in (
        "NINJA_CREDENTIAL_FD",
        "NINJA_CREDENTIAL_PASSWORD",
        "NINJA_STORE_PASSWORD_FILE",
        "CREDENTIALS_DIRECTORY",
        SECRET_NAME,
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(store_module, "_store_password", None)
    monkeypatch.setattr(store_module, "_store_password_source", "unset")
    monkeypatch.setattr(store_module, "_read_keyring_password", lambda: None)
    # Never touch the developer's real OS keyring from tests.
    monkeypatch.setattr(store_module, "_keyring_is_functional", lambda: False)
    store_module._reset_singletons()
    yield path
    store_module._reset_singletons()


def _make_store(path: Path, password: str) -> None:
    CredentialManager(db_path=path, password=password).set(SECRET_NAME, SECRET_VALUE)


def _manager(tmp_path: Path) -> DaemonManager:
    return DaemonManager(cache_dir=tmp_path / "cache")


def _set_tty(monkeypatch: pytest.MonkeyPatch, is_tty: bool) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: is_tty, raising=False)


def _forbid_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> str:
        raise AssertionError("must not prompt for a passwordless store")

    monkeypatch.setattr(store_module, "prompt_store_password", boom)


@pytest.mark.parametrize("interactive", [True, False])
def test_passwordless_store_never_prompts(db, tmp_path, monkeypatch, interactive):
    _make_store(db, "")
    _set_tty(monkeypatch, interactive)
    _forbid_prompt(monkeypatch)
    assert _manager(tmp_path)._unlock_store_once() == ""


def test_passwordless_store_ignores_stale_env_password(db, tmp_path, monkeypatch):
    _make_store(db, "")
    monkeypatch.setenv("NINJA_CREDENTIAL_PASSWORD", "stale-wrong")
    _set_tty(monkeypatch, False)
    assert _manager(tmp_path)._unlock_store_once() == ""


def test_protected_store_interactive_prompts(db, tmp_path, monkeypatch):
    _make_store(db, "s3cret")
    _set_tty(monkeypatch, True)
    monkeypatch.setattr(store_module, "prompt_store_password", lambda *a, **k: "s3cret")
    assert _manager(tmp_path)._unlock_store_once() == "s3cret"


def test_protected_store_headless_returns_none(db, tmp_path, monkeypatch):
    _make_store(db, "s3cret")
    _set_tty(monkeypatch, False)
    _forbid_prompt(monkeypatch)
    assert _manager(tmp_path)._unlock_store_once() is None


def test_protected_store_env_password_used(db, tmp_path, monkeypatch):
    _make_store(db, "s3cret")
    monkeypatch.setenv("NINJA_CREDENTIAL_PASSWORD", "s3cret")
    _set_tty(monkeypatch, False)
    assert _manager(tmp_path)._unlock_store_once() == "s3cret"


def test_no_db_returns_none(db, tmp_path):
    assert _manager(tmp_path)._unlock_store_once() is None


def test_fd_wrong_password_falls_back_to_passwordless(db, monkeypatch):
    _make_store(db, "")
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"bogus-password")
    os.close(write_fd)
    monkeypatch.setenv("NINJA_CREDENTIAL_FD", str(read_fd))
    mgr = store_module._get_credential_manager()
    assert mgr.get(SECRET_NAME) == SECRET_VALUE
    assert store_module.store_password_source() == "passwordless"


def test_fd_wrong_password_on_protected_store_is_not_success(db, monkeypatch):
    _make_store(db, "s3cret")
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"bogus-password")
    os.close(write_fd)
    monkeypatch.setenv("NINJA_CREDENTIAL_FD", str(read_fd))
    _set_tty(monkeypatch, False)
    with pytest.raises(EncryptionError):
        store_module.EncryptedFileBackend().get(SECRET_NAME)
    assert common_secrets.get_secret(SECRET_NAME) is None


def test_fd_correct_password_on_protected_store(db, monkeypatch):
    _make_store(db, "s3cret")
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"s3cret")
    os.close(write_fd)
    monkeypatch.setenv("NINJA_CREDENTIAL_FD", str(read_fd))
    assert store_module.EncryptedFileBackend().get(SECRET_NAME) == SECRET_VALUE


def test_empty_fd_value_is_ignored(db, monkeypatch):
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    monkeypatch.setenv("NINJA_CREDENTIAL_FD", str(read_fd))
    assert store_module._read_fd_password() is None


def test_get_secret_store_first_then_env(db, monkeypatch):
    _make_store(db, "")
    monkeypatch.setenv(SECRET_NAME, "from-env")
    assert common_secrets.get_secret(SECRET_NAME) == SECRET_VALUE
    store_module._reset_singletons()
    db.unlink()
    assert common_secrets.get_secret(SECRET_NAME) == "from-env"


def test_get_secret_none_when_nowhere(db):
    assert common_secrets.get_secret(SECRET_NAME) is None


def test_get_secret_logs_warning_without_value(db, monkeypatch, caplog):
    monkeypatch.setenv(SECRET_NAME, "env-secret-value")

    def boom() -> object:
        raise RuntimeError("decrypt failed for env-secret-value")

    monkeypatch.setattr(store_module, "default_store", boom)
    with caplog.at_level(logging.WARNING, logger="ninja_common.secrets"):
        assert common_secrets.get_secret(SECRET_NAME) == "env-secret-value"
    assert any(
        r.levelno == logging.WARNING and SECRET_NAME in r.getMessage() for r in caplog.records
    )
    assert "env-secret-value" not in caplog.text


def test_perplexity_reresolves_empty_key(monkeypatch):
    from ninja_researcher.search_providers import PerplexityProvider

    values = iter([None, "pplx-late-key"])
    monkeypatch.setattr(common_secrets, "get_secret", lambda _n: next(values))
    provider = PerplexityProvider()
    assert provider.api_key == ""
    assert provider.is_available() is True
    assert provider.api_key == "pplx-late-key"


def test_perplexity_still_unavailable_when_key_missing(monkeypatch):
    from ninja_researcher.search_providers import PerplexityProvider, ProviderError

    monkeypatch.setattr(common_secrets, "get_secret", lambda _n: None)
    provider = PerplexityProvider()
    assert provider.is_available() is False
    with pytest.raises(ProviderError):
        asyncio.run(provider.search("q"))
