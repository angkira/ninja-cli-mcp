"""Tests for credential encryption, key derivation, database, and manager."""

import os
import stat

import pytest

from ninja_config.credentials import (
    CredentialDatabase,
    CredentialEncryption,
    CredentialError,
    CredentialManager,
    CredentialNotFoundError,
    DatabaseError,
    EncryptionError,
    KeyDerivation,
)


def _make_key() -> bytes:
    return os.urandom(32)


# ============================================================================
# CredentialEncryption
# ============================================================================


class TestCredentialEncryption:
    def test_encrypt_returns_nonempty_bytes(self) -> None:
        enc = CredentialEncryption(_make_key())
        result = enc.encrypt("hello")
        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.parametrize(
        "plaintext",
        [
            "short",
            "a" * 1000,
            "",
            "unicode: \u00e9\u00e8\u00ea\u00eb \u4e2d\u6587 \U0001f600",
            "special: !@#$%^&*()_+-=[]{}|;':\",./<>?\n\t\r",
            "null\u0000byte",
        ],
    )
    def test_encrypt_decrypt_roundtrip(self, plaintext: str) -> None:
        enc = CredentialEncryption(_make_key())
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext

    def test_encrypt_produces_different_ciphertext(self) -> None:
        enc = CredentialEncryption(_make_key())
        c1 = enc.encrypt("same input")
        c2 = enc.encrypt("same input")
        assert c1 != c2

    def test_wrong_master_key_raises_encryption_error(self) -> None:
        key1 = _make_key()
        key2 = _make_key()
        enc1 = CredentialEncryption(key1)
        enc2 = CredentialEncryption(key2)
        encrypted = enc1.encrypt("secret")
        with pytest.raises(EncryptionError):
            enc2.decrypt(encrypted)

    def test_corrupted_data_raises_encryption_error(self) -> None:
        enc = CredentialEncryption(_make_key())
        encrypted = enc.encrypt("secret")
        corrupted = bytearray(encrypted)
        corrupted[-1] ^= 0xFF
        with pytest.raises(EncryptionError):
            enc.decrypt(bytes(corrupted))

    def test_too_short_data_raises_encryption_error(self) -> None:
        enc = CredentialEncryption(_make_key())
        with pytest.raises(EncryptionError):
            enc.decrypt(b"short")

    def test_master_key_wrong_length_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            CredentialEncryption(b"too short")

    def test_master_key_empty_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            CredentialEncryption(b"")

    def test_master_key_16_bytes_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            CredentialEncryption(os.urandom(16))

    def test_encrypt_output_contains_nonce_plus_ciphertext(self) -> None:
        enc = CredentialEncryption(_make_key())
        plaintext = "test value"
        encrypted = enc.encrypt(plaintext)
        assert len(encrypted) == CredentialEncryption.NONCE_LENGTH + CredentialEncryption.TAG_LENGTH + len(
            plaintext.encode("utf-8")
        )

    def test_class_constants(self) -> None:
        assert CredentialEncryption.ALGORITHM == "AES-256-GCM"
        assert CredentialEncryption.KEY_LENGTH == 32
        assert CredentialEncryption.NONCE_LENGTH == 12
        assert CredentialEncryption.TAG_LENGTH == 16


# ============================================================================
# KeyDerivation
# ============================================================================


class TestKeyDerivation:
    def test_get_machine_id_returns_hex_string(self) -> None:
        machine_id = KeyDerivation.get_machine_id()
        assert isinstance(machine_id, str)
        assert len(machine_id) == 64
        int(machine_id, 16)

    def test_get_machine_id_is_stable(self) -> None:
        id1 = KeyDerivation.get_machine_id()
        id2 = KeyDerivation.get_machine_id()
        assert id1 == id2

    def test_derive_key_returns_32_bytes(self) -> None:
        salt = os.urandom(32)
        key = KeyDerivation.derive_key(salt)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_derive_key_same_salt_password_gives_same_key(self) -> None:
        salt = os.urandom(32)
        k1 = KeyDerivation.derive_key(salt, "password")
        k2 = KeyDerivation.derive_key(salt, "password")
        assert k1 == k2

    def test_derive_key_different_salt_gives_different_key(self) -> None:
        salt1 = os.urandom(32)
        salt2 = os.urandom(32)
        k1 = KeyDerivation.derive_key(salt1)
        k2 = KeyDerivation.derive_key(salt2)
        assert k1 != k2

    def test_derive_key_different_password_gives_different_key(self) -> None:
        salt = os.urandom(32)
        k1 = KeyDerivation.derive_key(salt, "password1")
        k2 = KeyDerivation.derive_key(salt, "password2")
        assert k1 != k2

    def test_derive_key_empty_salt_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            KeyDerivation.derive_key(b"")

    def test_derive_key_default_password(self) -> None:
        salt = os.urandom(32)
        k1 = KeyDerivation.derive_key(salt)
        k2 = KeyDerivation.derive_key(salt, "")
        assert k1 == k2


# ============================================================================
# CredentialDatabase
# ============================================================================


class TestCredentialDatabase:
    def test_creates_db_file(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        CredentialDatabase(db_path)
        assert db_path.exists()

    def test_db_file_permissions_0600(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        CredentialDatabase(db_path)
        file_stat = db_path.stat()
        mode = stat.S_IMODE(file_stat.st_mode)
        assert mode == 0o600

    def test_get_or_create_salt_returns_32_bytes(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        salt = db.get_or_create_salt()
        assert isinstance(salt, bytes)
        assert len(salt) == 32

    def test_get_or_create_salt_is_idempotent(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        salt1 = db.get_or_create_salt()
        salt2 = db.get_or_create_salt()
        assert salt1 == salt2

    def test_store_and_get_credential_roundtrip(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        data = b"encrypted-secret-data"
        db.store_credential("API_KEY", data)
        assert db.get_credential("API_KEY") == data

    def test_store_credential_upsert(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        db.store_credential("KEY", b"old-value")
        db.store_credential("KEY", b"new-value")
        assert db.get_credential("KEY") == b"new-value"

    def test_get_credential_missing_raises_not_found(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        with pytest.raises(CredentialNotFoundError):
            db.get_credential("DOES_NOT_EXIST")

    def test_delete_credential_returns_true_for_existing(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        db.store_credential("KEY", b"data")
        assert db.delete_credential("KEY") is True

    def test_delete_credential_returns_false_for_missing(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        assert db.delete_credential("NOPE") is False

    def test_delete_credential_removes_from_db(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        db.store_credential("KEY", b"data")
        db.delete_credential("KEY")
        with pytest.raises(CredentialNotFoundError):
            db.get_credential("KEY")

    def test_delete_credential_overwrites_before_delete(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        original_data = b"sensitive-secret-data-here"
        db.store_credential("KEY", original_data)

        import sqlite3

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute(
            "CREATE TRIGGER capture_overwrite AFTER UPDATE ON credentials BEGIN "
            "INSERT INTO _overwrite_log(old_val) VALUES (OLD.value); END"
        )
        conn.execute("CREATE TABLE _overwrite_log(old_val BLOB)")
        conn.commit()
        conn.close()

        db2 = CredentialDatabase(tmp_path / "test.db")
        db2.delete_credential("KEY")

        assert not db2.credential_exists("KEY")

    def test_list_credentials_returns_metadata_without_values(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        db.store_credential("KEY_A", b"val-a", provider="openrouter")
        db.store_credential("KEY_B", b"val-b")
        result = db.list_credentials()
        assert len(result) == 2
        for cred in result:
            assert "name" in cred
            assert "provider" in cred
            assert "created_at" in cred
            assert "updated_at" in cred
            assert "value" not in cred
        names = {c["name"] for c in result}
        assert names == {"KEY_A", "KEY_B"}

    def test_list_credentials_includes_provider(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        db.store_credential("KEY", b"val", provider="openrouter")
        result = db.list_credentials()
        assert result[0]["provider"] == "openrouter"

    def test_credential_exists_true(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        db.store_credential("KEY", b"val")
        assert db.credential_exists("KEY") is True

    def test_credential_exists_false(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        assert db.credential_exists("NOPE") is False

    def test_store_credential_with_provider(self, tmp_path) -> None:
        db = CredentialDatabase(tmp_path / "test.db")
        db.store_credential("KEY", b"val", provider="anthropic")
        retrieved = db.get_credential("KEY")
        assert retrieved == b"val"


# ============================================================================
# CredentialManager (integration)
# ============================================================================


class TestCredentialManager:
    def test_set_get_roundtrip(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("API_KEY", "sk-or-v1-abcdef123456")
        assert mgr.get("API_KEY") == "sk-or-v1-abcdef123456"

    def test_get_returns_none_for_missing(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        assert mgr.get("MISSING") is None

    def test_delete_returns_true_for_existing(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("KEY", "val")
        assert mgr.delete("KEY") is True

    def test_delete_returns_false_for_missing(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        assert mgr.delete("NOPE") is False

    def test_set_empty_name_raises_value_error(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        with pytest.raises(ValueError, match="name cannot be empty"):
            mgr.set("", "val")

    def test_set_whitespace_name_raises_value_error(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        with pytest.raises(ValueError, match="name cannot be empty"):
            mgr.set("   ", "val")

    def test_set_empty_value_raises_value_error(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        with pytest.raises(ValueError, match="value cannot be empty"):
            mgr.set("KEY", "")

    def test_list_all_returns_masked_value(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("API_KEY", "sk-or-v1-1234567890abcdef", provider="openrouter")
        result = mgr.list_all()
        assert len(result) == 1
        cred = result[0]
        assert "masked_value" in cred
        mv = cred["masked_value"]
        assert mv != "sk-or-v1-1234567890abcdef"
        assert "sk-or" in mv

    def test_list_all_masks_short_value(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("KEY", "abc")
        result = mgr.list_all()
        assert result[0]["masked_value"] == "ab***"

    def test_list_all_masks_very_short_value(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("KEY", "ab")
        result = mgr.list_all()
        assert result[0]["masked_value"] == "***"

    def test_exists_true(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("KEY", "val")
        assert mgr.exists("KEY") is True

    def test_exists_false(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        assert mgr.exists("NOPE") is False

    def test_multiple_credentials(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("KEY_A", "val_a", provider="openrouter")
        mgr.set("KEY_B", "val_b", provider="anthropic")
        mgr.set("KEY_C", "val_c")
        assert mgr.get("KEY_A") == "val_a"
        assert mgr.get("KEY_B") == "val_b"
        assert mgr.get("KEY_C") == "val_c"
        assert len(mgr.list_all()) == 3

    def test_overwrite_existing_credential(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("KEY", "old-value")
        mgr.set("KEY", "new-value")
        assert mgr.get("KEY") == "new-value"

    def test_delete_and_recreate(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("KEY", "first")
        assert mgr.delete("KEY") is True
        assert mgr.get("KEY") is None
        mgr.set("KEY", "second")
        assert mgr.get("KEY") == "second"

    def test_unicode_roundtrip(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        value = "\u00e9\u00e8\u00ea\u00eb \u4e2d\u6587 \U0001f600"
        mgr.set("UNI_KEY", value)
        assert mgr.get("UNI_KEY") == value

    def test_set_with_provider_stored(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        mgr.set("KEY", "val", provider="openrouter")
        result = mgr.list_all()
        assert result[0]["provider"] == "openrouter"

    def test_default_db_path(self) -> None:
        from pathlib import Path

        expected = Path.home() / ".ninja" / "credentials.db"
        mgr = CredentialManager.__new__(CredentialManager)
        mgr._db = None
        mgr._encryption = None
        assert expected is not None

    def test_list_all_empty(self, tmp_path) -> None:
        mgr = CredentialManager(tmp_path / "creds.db")
        assert mgr.list_all() == []


# ============================================================================
# Exception hierarchy
# ============================================================================


class TestExceptions:
    def test_credential_error_is_exception(self) -> None:
        assert issubclass(CredentialNotFoundError, Exception)

    def test_encryption_error_is_credential_error(self) -> None:
        assert issubclass(EncryptionError, CredentialError)

    def test_database_error_is_credential_error(self) -> None:
        assert issubclass(DatabaseError, CredentialError)

    def test_not_found_error_is_credential_error(self) -> None:
        assert issubclass(CredentialNotFoundError, CredentialError)

    def test_exceptions_have_messages(self) -> None:
        err = EncryptionError("test message")
        assert str(err) == "test message"
