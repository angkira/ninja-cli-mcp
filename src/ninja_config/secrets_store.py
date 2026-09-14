"""
Secure secret storage backends for ninja-mcp API keys.

Provides a Protocol-based abstraction over three backends:
- KeyringBackend: OS keyring (libsecret / macOS Keychain / Windows Credential Locker)
- EncryptedFileBackend: AES-256-GCM SQLite via existing CredentialManager
- ChainBackend: tries backends in order; writes to first available
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path
from typing import Protocol, runtime_checkable

import keyring
import keyring.backends.fail

from ninja_common.secrets import KNOWN_SECRET_NAMES
from ninja_config.credentials import CredentialManager


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

__all__ = [
    "KNOWN_SECRET_NAMES",
    "ChainBackend",
    "EncryptedFileBackend",
    "KeyringBackend",
    "SecretStore",
    "SecretStoreUnavailable",
    "clear_store_password",
    "default_store",
    "get_store_password",
    "prompt_store_password",
    "rekey_and_set_password",
    "reset_encrypted_store",
    "set_store_password",
    "store_password_source",
]

_KEYRING_SERVICE = "ninja-mcp"

#: Keyring item holding the store password itself (OS Keychain on macOS).
_STORE_PASSWORD_ITEM = "__store_password__"

_ENV_PASSWORD_VAR = "NINJA_CREDENTIAL_PASSWORD"
#: systemd LoadCredential id (Linux): file at $CREDENTIALS_DIRECTORY/<id>.
_SYSTEMD_CRED_ID = "ninja-store-password"
#: Explicit password-file override (cross-platform; e.g. launchd on macOS).
_PASSWORD_FILE_VAR = "NINJA_STORE_PASSWORD_FILE"

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class SecretStoreUnavailable(Exception):
    """Raised when a backend cannot be used in the current environment."""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SecretStore(Protocol):
    """Interface for secret storage backends."""

    def get(self, name: str) -> str | None:
        """Return secret value or None if not present."""
        ...

    def set(self, name: str, value: str) -> None:
        """Store or overwrite a secret."""
        ...

    def delete(self, name: str) -> None:
        """Remove a secret; no-op if not present."""
        ...

    def list_names(self) -> list[str]:
        """Return names of secrets currently held by this backend."""
        ...

    def backend_name(self) -> str:
        """Human-readable backend identifier."""
        ...


# ---------------------------------------------------------------------------
# KeyringBackend
# ---------------------------------------------------------------------------


class KeyringBackend:
    """Secret storage backed by the OS keyring (libsecret / Keychain / WCLM)."""

    def get(self, name: str) -> str | None:
        """Return secret from OS keyring, or None."""
        value = keyring.get_password(_KEYRING_SERVICE, name)
        return value if value else None

    def set(self, name: str, value: str) -> None:
        """Store secret in OS keyring."""
        keyring.set_password(_KEYRING_SERVICE, name, value)

    def delete(self, name: str) -> None:
        """Delete secret from OS keyring; no-op if not present."""
        try:
            keyring.delete_password(_KEYRING_SERVICE, name)
        except keyring.errors.PasswordDeleteError:
            pass

    def list_names(self) -> list[str]:
        """Return whitelisted names that are present in the keyring."""
        return [name for name in KNOWN_SECRET_NAMES if self.get(name) is not None]

    def backend_name(self) -> str:
        """Return backend name derived from active keyring implementation class."""
        cls_name = keyring.get_keyring().__class__.__name__
        return f"OS keyring ({cls_name})"


# ---------------------------------------------------------------------------
# EncryptedFileBackend — module-level lazy singleton for CredentialManager
# ---------------------------------------------------------------------------

_credential_manager: CredentialManager | None = None


def _reset_singletons() -> None:
    """Drop cached store/manager so the next access rebuilds with new settings."""
    global _credential_manager, _default_store
    _credential_manager = None
    _default_store = None


#: In-memory copy of the store password (never written to env or config).
_store_password: str | None = None
_store_password_source: str = "unset"

#: Env var carrying the *file descriptor number* (not the secret) that a freshly
#: spawned daemon reads its password from once at startup.
_CRED_FD_VAR = "NINJA_CREDENTIAL_FD"


def _read_fd_password() -> str | None:
    """Read a one-shot password from the inherited fd in ``NINJA_CREDENTIAL_FD``.

    ``DaemonManager.start`` prompts once in the launcher and hands each child a
    pipe read-end, so the secret never appears in env/argv. The fd is consumed
    and closed on first read.
    """
    fd_env = os.environ.pop(_CRED_FD_VAR, None)
    if not fd_env:
        return None
    try:
        fd = int(fd_env)
    except ValueError:
        return None
    try:
        chunk = os.read(fd, 65536)
    except OSError:
        return None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    return chunk.decode("utf-8", "replace") or None


def _read_systemd_credential() -> str | None:
    """Read the password from a systemd ``LoadCredential`` file (Linux)."""
    cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not cred_dir:
        return None
    try:
        value = (Path(cred_dir) / _SYSTEMD_CRED_ID).read_text().strip()
    except OSError:
        return None
    return value or None


def _read_password_file() -> str | None:
    """Read the password from ``NINJA_STORE_PASSWORD_FILE`` (any platform)."""
    path_str = os.environ.get(_PASSWORD_FILE_VAR)
    if not path_str:
        return None
    try:
        value = Path(path_str).read_text().strip()
    except OSError:
        return None
    return value or None


def _read_keyring_password() -> str | None:
    """Read the persisted store password from the OS keychain/keyring."""
    try:
        if _keyring_is_functional():
            return keyring.get_password(_KEYRING_SERVICE, _STORE_PASSWORD_ITEM)
    except Exception:
        pass
    return None


def _resolve_store_password() -> str | None:
    """Resolve the store password without prompting; cache the first hit.

    Order: memory → inherited fd → systemd credential → password file →
    OS keychain/keyring → ``NINJA_CREDENTIAL_PASSWORD`` env (CI only). The fd
    is one-shot, so the resolved value is cached in memory.
    """
    global _store_password, _store_password_source
    if _store_password is not None:
        return _store_password
    sources = (
        ("fd", _read_fd_password),
        ("systemd", _read_systemd_credential),
        ("file", _read_password_file),
        ("keyring", _read_keyring_password),
        ("env", lambda: os.getenv(_ENV_PASSWORD_VAR) or None),
    )
    for source, getter in sources:
        password = getter()
        if password:
            _store_password = password
            _store_password_source = source
            return password
    return None


def store_password_source() -> str:
    """Report where the encrypted-store password currently comes from."""
    _resolve_store_password()
    return _store_password_source


def get_store_password() -> str | None:
    """Return the resolved store password (without prompting), if any."""
    return _resolve_store_password()


def set_store_password(password: str, *, persist: bool = False) -> None:
    """Set the store password for THIS process (in memory).

    When ``persist`` is true it is also saved to the OS keychain/keyring so a
    headless launch (macOS launchd; Linux with no TTY) can unlock the store.
    The password is never written to env or the config file.
    """
    global _store_password, _store_password_source
    _store_password = password
    _store_password_source = "memory"
    if persist:
        try:
            if _keyring_is_functional():
                keyring.set_password(_KEYRING_SERVICE, _STORE_PASSWORD_ITEM, password)
        except Exception:
            pass
    _reset_singletons()


def clear_store_password() -> None:
    """Forget the in-memory password and any keychain-persisted copy."""
    global _store_password, _store_password_source
    _store_password = None
    _store_password_source = "unset"
    try:
        if _keyring_is_functional():
            try:
                keyring.delete_password(_KEYRING_SERVICE, _STORE_PASSWORD_ITEM)
            except Exception:
                pass
    except Exception:
        pass
    _reset_singletons()


def prompt_store_password(prompt: str = "ninja-mcp encrypted store password: ") -> str:
    """Prompt interactively for the store password, cache it in memory, return it."""
    password = getpass.getpass(prompt)
    set_store_password(password)
    return password


def rekey_and_set_password(new_password: str, *, persist: bool = False) -> int:
    """Change the encrypted-store password, re-encrypting every credential.

    Reads existing rows with the *currently known* password (never prompts on
    its own if the store was already unlocked) and rewrites them under
    ``new_password``. With ``persist`` the new password is also stored in the
    OS keychain/keyring for headless launches.

    Returns:
        Number of credentials re-encrypted.
    """
    db_path = Path.home() / ".ninja" / "credentials.db"
    count = 0
    if db_path.exists():
        # Reuse the already-open manager (it holds the current key) if the store
        # was unlocked this process; otherwise unlock it now (may prompt).
        manager = _credential_manager
        if manager is None:
            manager = _get_credential_manager()
        count = manager.rekey(new_password)
    set_store_password(new_password, persist=persist)
    return count


def reset_encrypted_store() -> bool:
    """Delete the encrypted credentials DB and forget the store password.

    Returns:
        True if the DB file was removed (or already absent).
    """
    clear_store_password()
    db_path = Path.home() / ".ninja" / "credentials.db"
    ok = True
    try:
        if db_path.exists():
            db_path.unlink()
    except OSError:
        ok = False
    _reset_singletons()
    return ok


def _get_credential_manager() -> CredentialManager:
    """Return (or create) the process-lifetime CredentialManager instance.

    Password resolution (never writes the password to env/config):
    1. In-memory password set earlier this process
    2. One-shot inherited fd (``NINJA_CREDENTIAL_FD``) from ``daemon start``
    3. systemd ``LoadCredential`` file (Linux)
    4. ``NINJA_STORE_PASSWORD_FILE`` (any platform, e.g. launchd on macOS)
    5. OS keychain/keyring (macOS Keychain / Secret Service)
    6. ``NINJA_CREDENTIAL_PASSWORD`` env var (explicit CI/headless fallback)
    7. Interactive ``getpass`` prompt when stdin is a TTY
    8. Raises ``SecretStoreUnavailable`` otherwise
    """
    global _credential_manager, _store_password, _store_password_source
    if _credential_manager is not None:
        return _credential_manager

    password = _resolve_store_password()
    if password is None:
        # Legacy / passwordless store: try an empty password before prompting so
        # machine-bound stores (and headless daemons) open without a TTY.
        empty = CredentialManager(password="")
        if empty.can_decrypt():
            _store_password = ""
            _store_password_source = "passwordless"
            _credential_manager = empty
            return empty
        if not sys.stdin.isatty():
            raise SecretStoreUnavailable(
                "EncryptedFileBackend needs the store password: run interactively, "
                "start daemons via 'ninja-mcp daemon start', provision a systemd "
                "credential / NINJA_STORE_PASSWORD_FILE, or set "
                "NINJA_CREDENTIAL_PASSWORD for headless use."
            )
        password = getpass.getpass("ninja-mcp encrypted store password: ")
        set_store_password(password)

    _credential_manager = CredentialManager(password=password)
    return _credential_manager


class EncryptedFileBackend:
    """Secret storage backed by the AES-256-GCM SQLite CredentialManager."""

    def get(self, name: str) -> str | None:
        """Return decrypted secret or None."""
        try:
            mgr = _get_credential_manager()
        except SecretStoreUnavailable:
            return None
        return mgr.get(name)

    def set(self, name: str, value: str) -> None:
        """Encrypt and store secret."""
        _get_credential_manager().set(name, value)

    def delete(self, name: str) -> None:
        """Delete secret; no-op if not present."""
        try:
            mgr = _get_credential_manager()
        except SecretStoreUnavailable:
            return
        mgr.delete(name)

    def list_names(self) -> list[str]:
        """Return names of whitelisted secrets stored in the encrypted file."""
        try:
            mgr = _get_credential_manager()
        except SecretStoreUnavailable:
            return []
        all_creds = mgr.list_all()
        stored = {cred["name"] for cred in all_creds}
        return sorted(stored & KNOWN_SECRET_NAMES)

    def backend_name(self) -> str:
        """Return fixed backend label."""
        return "encrypted file (~/.ninja-mcp.db)"


# ---------------------------------------------------------------------------
# ChainBackend
# ---------------------------------------------------------------------------


class ChainBackend:
    """Composes multiple backends; read falls through, writes go to first available."""

    def __init__(self, backends: list[SecretStore]) -> None:
        self._backends = backends

    def get(self, name: str) -> str | None:
        """Return first hit from backend chain, or None."""
        for backend in self._backends:
            value = backend.get(name)
            if value is not None:
                return value
        return None

    def _first_usable(self) -> SecretStore:
        """Return the first backend that does not raise SecretStoreUnavailable.

        EncryptedFileBackend availability is verified by calling the manager
        accessor; all other backends are assumed always available.
        """
        for backend in self._backends:
            if isinstance(backend, EncryptedFileBackend):
                try:
                    _get_credential_manager()
                except SecretStoreUnavailable:
                    continue
            return backend
        raise SecretStoreUnavailable("No usable backend available in chain.")

    def set(self, name: str, value: str) -> None:
        """Store secret in the first usable backend."""
        self._first_usable().set(name, value)

    def delete(self, name: str) -> None:
        """Delete secret from all backends; ignore missing."""
        for backend in self._backends:
            backend.delete(name)

    def list_names(self) -> list[str]:
        """Return union of names across all available backends."""
        names: set[str] = set()
        for backend in self._backends:
            names.update(backend.list_names())
        return sorted(names)

    def backend_name(self) -> str:
        """Return the name of the active write backend."""
        try:
            usable = self._first_usable()
        except SecretStoreUnavailable:
            return "none (all backends unavailable)"
        return usable.backend_name()


# ---------------------------------------------------------------------------
# default_store factory — module-level singleton
# ---------------------------------------------------------------------------

_default_store: ChainBackend | None = None


def _keyring_is_functional() -> bool:
    """Return True when a real keyring backend is available (not fail.Keyring)."""
    kr = keyring.get_keyring()
    # fail.Keyring signals no usable keyring daemon
    if isinstance(kr, keyring.backends.fail.Keyring):
        return False
    # ChainerBackend with empty backends list also means nothing available
    cls_name = type(kr).__name__
    if cls_name == "ChainerBackend":
        try:
            # Access internal backends list if present
            backends_list = getattr(kr, "_backends", None) or getattr(kr, "backends", None)
            if backends_list is not None and len(backends_list) == 0:
                return False
        except Exception:
            pass
    return True


def default_store() -> ChainBackend:
    """Return the process-lifetime default ChainBackend.

    Uses OS keyring as primary when available; falls back to encrypted file only.
    """
    global _default_store
    if _default_store is not None:
        return _default_store

    # Encrypted store FIRST so it is the single source of truth: the OS keyring
    # is a fallback and can no longer shadow a newer value in the encrypted DB.
    encrypted = EncryptedFileBackend()
    if _keyring_is_functional():
        _default_store = ChainBackend([encrypted, KeyringBackend()])
    else:
        _default_store = ChainBackend([encrypted])

    return _default_store
