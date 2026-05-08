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
from typing import Protocol, runtime_checkable

import keyring
import keyring.backends.fail

from ninja_config.credentials import CredentialManager


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

KNOWN_SECRET_NAMES: frozenset[str] = frozenset(
    {
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
)

_KEYRING_SERVICE = "ninja-mcp"

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


def _get_credential_manager() -> CredentialManager:
    """Return (or create) the process-lifetime CredentialManager instance.

    Password resolution order:
    1. ``NINJA_CREDENTIAL_PASSWORD`` environment variable (set externally or by daemon)
    2. Interactive ``getpass`` prompt when stdin is a TTY
    3. Raises ``SecretStoreUnavailable`` if neither is possible (headless/CI)
    """
    global _credential_manager
    if _credential_manager is not None:
        return _credential_manager

    if os.getenv("NINJA_CREDENTIAL_PASSWORD") is not None:
        # Env var already set; CredentialManager reads it internally.
        _credential_manager = CredentialManager()
        return _credential_manager

    if not sys.stdin.isatty():
        raise SecretStoreUnavailable(
            "EncryptedFileBackend requires NINJA_CREDENTIAL_PASSWORD env var "
            "on non-interactive (daemon/CI) processes."
        )

    # Interactive: prompt once and inject into env for CredentialManager.
    password = getpass.getpass("ninja-mcp encrypted store password: ")
    os.environ["NINJA_CREDENTIAL_PASSWORD"] = password
    _credential_manager = CredentialManager()
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

    encrypted = EncryptedFileBackend()
    if _keyring_is_functional():
        _default_store = ChainBackend([KeyringBackend(), encrypted])
    else:
        _default_store = ChainBackend([encrypted])

    return _default_store
