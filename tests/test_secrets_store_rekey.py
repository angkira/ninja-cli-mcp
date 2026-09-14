"""Encrypted-store password management: in-memory password, rekey + reset.

The password is never persisted to env/config; headless launches get it from a
systemd credential, an explicit password file, or the OS keychain. Tests run
against a temp HOME with the OS keyring disabled.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

import ninja_config.secrets_store as ss
from ninja_config.credentials import CredentialManager, EncryptionError


if TYPE_CHECKING:
    import pathlib

    from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: pathlib.Path, monkeypatch: MonkeyPatch):
    """Redirect HOME to a temp dir, disable keyring, and forget any password."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in (
        "NINJA_CREDENTIAL_PASSWORD",
        "NINJA_CREDENTIAL_FD",
        "CREDENTIALS_DIRECTORY",
        "NINJA_STORE_PASSWORD_FILE",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(ss, "_keyring_is_functional", lambda: False)
    ss.clear_store_password()
    yield tmp_path
    ss.clear_store_password()


def _seed_store(password: str) -> None:
    """Write a credential encrypted under ``password`` (simulating a prior run)."""
    ss.set_store_password(password)
    manager = CredentialManager(password=password)
    manager.set("OPENROUTER_API_KEY", "sk-or-secret")
    ss._credential_manager = manager
    ss._default_store = None


def test_password_never_written_to_env_or_config(_isolated_store: pathlib.Path) -> None:
    ss.rekey_and_set_password("mem-pass")
    assert "NINJA_CREDENTIAL_PASSWORD" not in os.environ
    from ninja_common.config_manager import ConfigManager

    assert not ConfigManager().get("NINJA_CREDENTIAL_PASSWORD")
    assert ss.store_password_source() == "memory"


def test_rekey_reencrypts_and_new_password_reads(_isolated_store: pathlib.Path) -> None:
    _seed_store("old-pass")
    assert ss.rekey_and_set_password("new-pass") == 1

    # Simulate a fresh process that re-supplies the new password.
    ss.clear_store_password()
    ss.set_store_password("new-pass")
    assert ss.EncryptedFileBackend().get("OPENROUTER_API_KEY") == "sk-or-secret"


def test_old_password_no_longer_decrypts(_isolated_store: pathlib.Path) -> None:
    _seed_store("old-pass")
    ss.rekey_and_set_password("new-pass")

    ss.clear_store_password()
    ss.set_store_password("old-pass")
    with pytest.raises(EncryptionError):
        ss._get_credential_manager().get("OPENROUTER_API_KEY")


def test_fd_password_one_shot(_isolated_store: pathlib.Path) -> None:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"fd-pass")
    os.close(write_fd)
    os.environ["NINJA_CREDENTIAL_FD"] = str(read_fd)
    assert ss._read_fd_password() == "fd-pass"
    assert "NINJA_CREDENTIAL_FD" not in os.environ
    assert ss._read_fd_password() is None


def test_manager_unlocks_from_inherited_fd(_isolated_store: pathlib.Path) -> None:
    _seed_store("fd-pass")
    ss.clear_store_password()  # forget memory, as a fresh daemon would

    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"fd-pass")
    os.close(write_fd)
    os.environ["NINJA_CREDENTIAL_FD"] = str(read_fd)

    assert "NINJA_CREDENTIAL_PASSWORD" not in os.environ
    assert ss.EncryptedFileBackend().get("OPENROUTER_API_KEY") == "sk-or-secret"


def test_systemd_credential_source(
    _isolated_store: pathlib.Path, monkeypatch: MonkeyPatch
) -> None:
    cred_dir = _isolated_store / "creds"
    cred_dir.mkdir()
    (cred_dir / "ninja-store-password").write_text("systemd-pass\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    assert ss.get_store_password() == "systemd-pass"
    assert ss.store_password_source() == "systemd"


def test_password_file_source(
    _isolated_store: pathlib.Path, monkeypatch: MonkeyPatch
) -> None:
    pw_file = _isolated_store / "pw.txt"
    pw_file.write_text("file-pass\n")
    monkeypatch.setenv("NINJA_STORE_PASSWORD_FILE", str(pw_file))
    assert ss.get_store_password() == "file-pass"
    assert ss.store_password_source() == "file"


def test_reset_removes_db_and_password(_isolated_store: pathlib.Path) -> None:
    _seed_store("old-pass")
    db = _isolated_store / ".ninja" / "credentials.db"
    assert db.exists()

    assert ss.reset_encrypted_store() is True
    assert not db.exists()
    assert ss.get_store_password() is None
    assert ss.store_password_source() == "unset"
