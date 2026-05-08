"""
Tests for ninja_common.config_manager — Phase 1.2 (export_env) and
Phase 1.3 (auto-migration from ~/.ninja-mcp.env to SecretStore).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import ninja_common.config_manager as cm_module
from ninja_common.config_manager import ConfigManager
from ninja_config.secrets_store import SecretStoreUnavailable


if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class InMemoryStore:
    """Minimal in-memory SecretStore for tests — satisfies SecretStore protocol."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self.available = True

    def get(self, name: str) -> str | None:
        return self._data.get(name)

    def set(self, name: str, value: str) -> None:
        if not self.available:
            raise SecretStoreUnavailable("store unavailable")
        self._data[name] = value

    def delete(self, name: str) -> None:
        self._data.pop(name, None)

    def list_names(self) -> list[str]:
        return sorted(self._data.keys())

    def backend_name(self) -> str:
        return "in-memory-test-store"


def _write_env(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o600)


@pytest.fixture(autouse=True)
def reset_migration_guard():
    """Reset the module-level migration guard before every test."""
    cm_module._migration_done = False
    yield
    cm_module._migration_done = False


@pytest.fixture()
def fake_store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture()
def patch_default_store(fake_store: InMemoryStore):
    """Patch default_store() at the canonical location in ninja_config.secrets_store.

    Both _maybe_migrate and export_env import default_store from
    ninja_config.secrets_store via a deferred 'from ... import default_store'.
    Patching the function on the source module is the correct interception point.
    """
    with patch("ninja_config.secrets_store.default_store", return_value=fake_store):
        yield fake_store


# ---------------------------------------------------------------------------
# Phase 1.3 — Auto-migration
# ---------------------------------------------------------------------------


class TestMigrationNoEnvFile:
    """No .env file → no-op, no error."""

    def test_no_env_file_no_error(self, tmp_path: Path, patch_default_store) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        assert not env_path.exists()
        # Should not raise
        ConfigManager(config_file=str(env_path))
        assert not env_path.exists()

    def test_no_env_file_store_untouched(
        self, tmp_path: Path, patch_default_store: InMemoryStore
    ) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        ConfigManager(config_file=str(env_path))
        assert patch_default_store._data == {}


class TestMigrationMixedKeys:
    """
    .env with mixed (secret + non-secret) keys → secrets moved to store,
    non-secrets preserved verbatim, backup created.
    """

    ENV_CONTENT = (
        "# My config\n"
        "OPENROUTER_API_KEY=sk-or-v1-abc123\n"
        "NINJA_CODE_BIN=/usr/bin/opencode\n"
        "export ANTHROPIC_API_KEY=sk-ant-xyz789\n"
        "# trailing comment\n"
        "NINJA_USE_DIALOGUE_MODE=true\n"
    )

    def test_secrets_stored_in_store(
        self, tmp_path: Path, patch_default_store: InMemoryStore
    ) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, self.ENV_CONTENT)

        ConfigManager(config_file=str(env_path))

        assert patch_default_store.get("OPENROUTER_API_KEY") == "sk-or-v1-abc123"
        assert patch_default_store.get("ANTHROPIC_API_KEY") == "sk-ant-xyz789"

    def test_non_secrets_preserved_in_env(
        self, tmp_path: Path, patch_default_store: InMemoryStore
    ) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, self.ENV_CONTENT)

        ConfigManager(config_file=str(env_path))

        remaining = env_path.read_text()
        assert "NINJA_CODE_BIN=/usr/bin/opencode" in remaining
        assert "NINJA_USE_DIALOGUE_MODE=true" in remaining
        # Secrets must be removed
        assert "OPENROUTER_API_KEY" not in remaining
        assert "ANTHROPIC_API_KEY" not in remaining

    def test_comments_and_blank_lines_preserved(
        self, tmp_path: Path, patch_default_store: InMemoryStore
    ) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, self.ENV_CONTENT)

        ConfigManager(config_file=str(env_path))

        remaining = env_path.read_text()
        assert "# My config" in remaining
        assert "# trailing comment" in remaining

    def test_backup_created(self, tmp_path: Path, patch_default_store: InMemoryStore) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, self.ENV_CONTENT)

        ConfigManager(config_file=str(env_path))

        backup = tmp_path / ".ninja-mcp.env.pre-migration.bak"
        assert backup.exists()
        assert backup.read_text() == self.ENV_CONTENT

    def test_notice_printed_to_stderr(
        self,
        tmp_path: Path,
        patch_default_store: InMemoryStore,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, self.ENV_CONTENT)

        ConfigManager(config_file=str(env_path))

        _, err = capsys.readouterr()
        assert "[ninja-mcp] migrated 2 API keys to" in err
        assert "in-memory-test-store" in err
        assert ".pre-migration.bak" in err


class TestMigrationBackupIdempotent:
    """Backup already exists → not overwritten."""

    ENV_CONTENT = "OPENROUTER_API_KEY=sk-or-v1-new\nNINJA_CODE_BIN=foo\n"
    ORIGINAL_BACKUP = "OPENROUTER_API_KEY=sk-or-v1-original\n"

    def test_existing_backup_not_overwritten(
        self, tmp_path: Path, patch_default_store: InMemoryStore
    ) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        backup_path = tmp_path / ".ninja-mcp.env.pre-migration.bak"
        _write_env(env_path, self.ENV_CONTENT)
        backup_path.write_text(self.ORIGINAL_BACKUP)

        ConfigManager(config_file=str(env_path))

        assert backup_path.read_text() == self.ORIGINAL_BACKUP


class TestMigrationStoreUnavailable:
    """SecretStore.set raises SecretStoreUnavailable → .env left untouched."""

    ENV_CONTENT = "OPENROUTER_API_KEY=sk-or-v1-abc\nNINJA_CODE_BIN=bar\n"

    def test_env_left_untouched(self, tmp_path: Path) -> None:
        unavailable_store = InMemoryStore()
        unavailable_store.available = False

        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, self.ENV_CONTENT)
        original_content = env_path.read_text()

        with patch("ninja_config.secrets_store.default_store", return_value=unavailable_store):
            ConfigManager(config_file=str(env_path))

        assert env_path.read_text() == original_content

    def test_no_backup_created_on_abort(self, tmp_path: Path) -> None:
        unavailable_store = InMemoryStore()
        unavailable_store.available = False

        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, self.ENV_CONTENT)

        with patch("ninja_config.secrets_store.default_store", return_value=unavailable_store):
            ConfigManager(config_file=str(env_path))

        backup = tmp_path / ".ninja-mcp.env.pre-migration.bak"
        assert not backup.exists()


class TestMigrationGuard:
    """Second ConfigManager() instance → migration does NOT run again."""

    ENV_CONTENT = "OPENROUTER_API_KEY=sk-or-v1-once\n"

    def test_migration_runs_only_once(
        self, tmp_path: Path, patch_default_store: InMemoryStore
    ) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, self.ENV_CONTENT)

        # First instantiation — migrates.
        ConfigManager(config_file=str(env_path))
        assert patch_default_store.get("OPENROUTER_API_KEY") == "sk-or-v1-once"

        # Tamper with the store to detect a second migration attempt.
        patch_default_store._data["OPENROUTER_API_KEY"] = "tampered"

        # Restore env file with a different secret value to prove it won't be re-read.
        _write_env(env_path, "OPENROUTER_API_KEY=sk-or-v1-second\n")

        # Second instantiation — guard must prevent migration.
        ConfigManager(config_file=str(env_path))

        # Value must still be "tampered", not the new "sk-or-v1-second".
        assert patch_default_store.get("OPENROUTER_API_KEY") == "tampered"


class TestMigrationOnlyNonEmptyValues:
    """Lines with empty values are not migrated."""

    ENV_CONTENT = "OPENROUTER_API_KEY=\nNINJA_CODE_BIN=foo\n"

    def test_empty_secret_not_migrated(
        self, tmp_path: Path, patch_default_store: InMemoryStore
    ) -> None:
        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, self.ENV_CONTENT)

        ConfigManager(config_file=str(env_path))

        # No secrets were non-empty, so no migration occurs.
        assert patch_default_store._data == {}
        # .env is untouched
        assert env_path.read_text() == self.ENV_CONTENT


# ---------------------------------------------------------------------------
# Phase 1.2 — export_env() resolution chain
# ---------------------------------------------------------------------------


class TestExportEnvResolutionChain:
    """Resolution chain for KNOWN_SECRET_NAMES in export_env()."""

    def _make_manager(self, tmp_path: Path, content: str) -> ConfigManager:
        """Return a ConfigManager pointing to a temp .env without triggering migration."""
        env_path = tmp_path / ".ninja-mcp.env"
        _write_env(env_path, content)
        # Guard already set (autouse fixture resets per test); mark done before
        # constructing so migration is skipped — we test export_env separately.
        cm_module._migration_done = True
        return ConfigManager(config_file=str(env_path))

    def test_store_wins_over_env_and_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When secret is in store AND env AND .env, store value wins."""
        store = InMemoryStore()
        store._data["OPENROUTER_API_KEY"] = "from-store"
        monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")

        mgr = self._make_manager(tmp_path, "OPENROUTER_API_KEY=from-file\n")

        with patch("ninja_config.secrets_store.default_store", return_value=store):
            # Clear env first so export_env sets it
            monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
            mgr.export_env()

        assert os.environ["OPENROUTER_API_KEY"] == "from-store"

    def test_env_wins_when_store_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When secret not in store but IS in env, env value wins."""
        store = InMemoryStore()  # empty
        monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")

        mgr = self._make_manager(tmp_path, "OPENROUTER_API_KEY=from-file\n")

        with patch("ninja_config.secrets_store.default_store", return_value=store):
            mgr.export_env()

        assert os.environ["OPENROUTER_API_KEY"] == "from-env"

    def test_file_wins_when_store_and_env_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When secret not in store, not in env, .env value is used."""
        store = InMemoryStore()  # empty
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        mgr = self._make_manager(tmp_path, "OPENROUTER_API_KEY=from-file\n")

        with patch("ninja_config.secrets_store.default_store", return_value=store):
            mgr.export_env()

        assert os.environ["OPENROUTER_API_KEY"] == "from-file"

    def test_non_secret_injected_only_if_not_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-secret keys from .env are NOT injected if already in os.environ."""
        store = InMemoryStore()
        monkeypatch.setenv("NINJA_CODE_BIN", "already-set")

        mgr = self._make_manager(tmp_path, "NINJA_CODE_BIN=from-file\n")

        with patch("ninja_config.secrets_store.default_store", return_value=store):
            mgr.export_env()

        assert os.environ["NINJA_CODE_BIN"] == "already-set"

    def test_non_secret_injected_when_not_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-secret keys from .env are injected when absent from os.environ."""
        store = InMemoryStore()
        monkeypatch.delenv("NINJA_CODE_BIN", raising=False)

        mgr = self._make_manager(tmp_path, "NINJA_CODE_BIN=/usr/bin/opencode\n")

        with patch("ninja_config.secrets_store.default_store", return_value=store):
            mgr.export_env()

        assert os.environ["NINJA_CODE_BIN"] == "/usr/bin/opencode"
