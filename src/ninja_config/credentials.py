"""
Encrypted credential storage system using SQLite with AES-256-GCM encryption.

This module provides secure credential management with:
- AES-256-GCM encryption for credential values
- PBKDF2-HMAC-SHA256 key derivation (100,000 iterations)
- Machine-specific master key generation
- SQLite database for credential storage
- Thread-safe operations
- Secure credential deletion (overwrites before delete)

Architecture:
- Domain Layer: Credential encryption/decryption logic
- Infrastructure Layer: SQLite database adapter
- Ports: CredentialManager interface for external use
"""

import hashlib
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialError(Exception):
    """Base exception for credential-related errors."""

    pass


class EncryptionError(CredentialError):
    """Raised when encryption or decryption fails."""

    pass


class DatabaseError(CredentialError):
    """Raised when database operations fail."""

    pass


class CredentialNotFoundError(CredentialError):
    """Raised when a credential is not found."""

    pass


# ============================================================================
# Domain Layer: Encryption Logic
# ============================================================================


class CredentialEncryption:
    """
    Handles encryption and decryption of credential values using AES-256-GCM.

    This is pure domain logic with no infrastructure dependencies.
    """

    ALGORITHM = "AES-256-GCM"
    KEY_DERIVATION = "PBKDF2-HMAC-SHA256"
    ITERATIONS = 100_000
    KEY_LENGTH = 32  # 256 bits
    NONCE_LENGTH = 12  # 96 bits (recommended for GCM)
    TAG_LENGTH = 16  # 128 bits

    def __init__(self, master_key: bytes) -> None:
        """
        Initialize encryption with master key.

        Args:
            master_key: 32-byte master encryption key

        Raises:
            ValueError: If master key is not 32 bytes
        """
        if len(master_key) != self.KEY_LENGTH:
            raise ValueError(f"Master key must be {self.KEY_LENGTH} bytes")
        self._master_key = master_key

    def encrypt(self, plaintext: str) -> bytes:
        """
        Encrypt plaintext credential value.

        Args:
            plaintext: The credential value to encrypt

        Returns:
            Encrypted data as bytes (nonce + tag + ciphertext)

        Raises:
            EncryptionError: If encryption fails
        """
        try:
            aesgcm = AESGCM(self._master_key)
            nonce = os.urandom(self.NONCE_LENGTH)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

            # Format: nonce (12 bytes) + ciphertext (includes 16-byte auth tag)
            return nonce + ciphertext

        except Exception as e:
            raise EncryptionError(f"Failed to encrypt credential: {e}") from e

    def decrypt(self, encrypted_data: bytes) -> str:
        """
        Decrypt encrypted credential value.

        Args:
            encrypted_data: Encrypted data (nonce + tag + ciphertext)

        Returns:
            Decrypted plaintext credential value

        Raises:
            EncryptionError: If decryption fails (wrong key, corrupted data, etc.)
        """
        try:
            if len(encrypted_data) < self.NONCE_LENGTH + self.TAG_LENGTH:
                raise EncryptionError("Encrypted data is too short")

            nonce = encrypted_data[: self.NONCE_LENGTH]
            ciphertext = encrypted_data[self.NONCE_LENGTH :]

            aesgcm = AESGCM(self._master_key)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)

            return plaintext_bytes.decode("utf-8")

        except Exception as e:
            raise EncryptionError(f"Failed to decrypt credential: {e}") from e


# ============================================================================
# Domain Layer: Key Derivation
# ============================================================================


class KeyDerivation:
    """
    Derives encryption keys from machine ID and optional password.

    This is pure domain logic with no infrastructure dependencies.
    """

    @staticmethod
    def get_machine_id() -> str:
        """
        Generate a stable machine-specific identifier.

        Uses a combination of:
        - Node ID (MAC address-based UUID)
        - Platform-specific identifiers

        Returns:
            Machine identifier as hex string

        Note:
            This is not cryptographically secure for authentication,
            but sufficient for deriving a machine-specific key.
        """
        # Use UUID node (based on MAC address)
        node = uuid.getnode()

        # Create a stable identifier
        machine_data = f"{node}".encode()
        return hashlib.sha256(machine_data).hexdigest()

    @staticmethod
    def derive_key(salt: bytes, password: str = "") -> bytes:
        """
        Derive encryption key using PBKDF2-HMAC-SHA256.

        Args:
            salt: Cryptographic salt (should be random and stored)
            password: Optional user password (from NINJA_CREDENTIAL_PASSWORD env var)

        Returns:
            32-byte encryption key

        Raises:
            ValueError: If salt is empty
        """
        if not salt:
            raise ValueError("Salt cannot be empty")

        machine_id = KeyDerivation.get_machine_id()
        key_material = f"{machine_id}:{password}".encode()

        return hashlib.pbkdf2_hmac(
            "sha256",
            key_material,
            salt,
            iterations=CredentialEncryption.ITERATIONS,
            dklen=CredentialEncryption.KEY_LENGTH,
        )


# ============================================================================
# Infrastructure Layer: SQLite Database Adapter
# ============================================================================


class CredentialDatabase:
    """
    SQLite database adapter for credential storage.

    Thread-safe implementation with connection pooling per thread.
    """

    def __init__(self, db_path: Path) -> None:
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file

        Raises:
            DatabaseError: If database initialization fails
        """
        self.db_path = db_path
        self._thread_local = threading.local()
        self._lock = threading.Lock()

        # Ensure parent directory exists with secure permissions
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Initialize database schema
        self._initialize_schema()

        # Set secure file permissions (600)
        try:
            Path(db_path).chmod(0o600)
        except OSError as e:
            raise DatabaseError(f"Failed to set secure permissions on database: {e}") from e

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get thread-local database connection.

        Returns:
            SQLite connection for current thread
        """
        if not hasattr(self._thread_local, "connection"):
            self._thread_local.connection = sqlite3.connect(
                str(self.db_path), check_same_thread=False
            )
            self._thread_local.connection.row_factory = sqlite3.Row
        return self._thread_local.connection

    @contextmanager
    def _transaction(self):
        """
        Context manager for database transactions.

        Provides automatic commit/rollback and thread safety.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _initialize_schema(self) -> None:
        """
        Initialize database schema.

        Raises:
            DatabaseError: If schema initialization fails
        """
        try:
            with self._transaction() as conn:
                # Create credentials table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS credentials (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        value BLOB NOT NULL,
                        provider TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used TIMESTAMP,
                        metadata TEXT
                    )
                    """
                )

                # Create indexes
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_credentials_name ON credentials(name)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_credentials_provider "
                    "ON credentials(provider)"
                )

                # Create encryption metadata table
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS encryption_meta (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        key_derivation TEXT NOT NULL,
                        salt BLOB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to initialize database schema: {e}") from e

    def get_or_create_salt(self) -> bytes:
        """
        Get existing salt or create a new one.

        Returns:
            Cryptographic salt

        Raises:
            DatabaseError: If salt retrieval/creation fails
        """
        try:
            with self._transaction() as conn:
                # Try to get existing salt
                cursor = conn.execute("SELECT salt FROM encryption_meta WHERE id = 1")
                row = cursor.fetchone()

                if row:
                    return bytes(row["salt"])

                # Create new salt
                salt = os.urandom(32)
                conn.execute(
                    """
                    INSERT INTO encryption_meta (id, key_derivation, salt)
                    VALUES (1, ?, ?)
                    """,
                    (CredentialEncryption.KEY_DERIVATION, salt),
                )
                return salt

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get or create salt: {e}") from e

    def store_credential(
        self, name: str, encrypted_value: bytes, provider: str | None = None
    ) -> None:
        """
        Store or update encrypted credential.

        Args:
            name: Credential name (unique identifier)
            encrypted_value: Encrypted credential value
            provider: Optional provider name

        Raises:
            DatabaseError: If storage fails
        """
        try:
            with self._transaction() as conn:
                now = datetime.now().isoformat()
                conn.execute(
                    """
                    INSERT INTO credentials (name, value, provider, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        value = excluded.value,
                        provider = excluded.provider,
                        updated_at = excluded.updated_at
                    """,
                    (name, encrypted_value, provider, now, now),
                )

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to store credential '{name}': {e}") from e

    def get_credential(self, name: str) -> bytes:
        """
        Retrieve encrypted credential value.

        Args:
            name: Credential name

        Returns:
            Encrypted credential value

        Raises:
            CredentialNotFoundError: If credential doesn't exist
            DatabaseError: If retrieval fails
        """
        try:
            with self._transaction() as conn:
                cursor = conn.execute("SELECT value FROM credentials WHERE name = ?", (name,))
                row = cursor.fetchone()

                if not row:
                    raise CredentialNotFoundError(f"Credential '{name}' not found")

                # Update last_used timestamp
                conn.execute(
                    "UPDATE credentials SET last_used = ? WHERE name = ?",
                    (datetime.now().isoformat(), name),
                )

                return bytes(row["value"])

        except CredentialNotFoundError:
            raise
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to get credential '{name}': {e}") from e

    def delete_credential(self, name: str) -> bool:
        """
        Securely delete credential.

        Overwrites the encrypted value before deletion for security.

        Args:
            name: Credential name

        Returns:
            True if credential was deleted, False if it didn't exist

        Raises:
            DatabaseError: If deletion fails
        """
        try:
            with self._transaction() as conn:
                # First, overwrite with random data
                cursor = conn.execute("SELECT id, value FROM credentials WHERE name = ?", (name,))
                row = cursor.fetchone()

                if not row:
                    return False

                # Overwrite with random data of same length
                random_data = os.urandom(len(row["value"]))
                conn.execute(
                    "UPDATE credentials SET value = ? WHERE name = ?", (random_data, name)
                )

                # Now delete
                conn.execute("DELETE FROM credentials WHERE name = ?", (name,))

                return True

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to delete credential '{name}': {e}") from e

    def list_credentials(self) -> list[dict[str, Any]]:
        """
        List all credentials with metadata (values excluded).

        Returns:
            List of credential metadata dictionaries

        Raises:
            DatabaseError: If listing fails
        """
        try:
            with self._transaction() as conn:
                cursor = conn.execute(
                    """
                    SELECT name, provider, created_at, updated_at, last_used
                    FROM credentials
                    ORDER BY name
                    """
                )

                return [dict(row) for row in cursor.fetchall()]

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to list credentials: {e}") from e

    def credential_exists(self, name: str) -> bool:
        """
        Check if credential exists.

        Args:
            name: Credential name

        Returns:
            True if credential exists, False otherwise

        Raises:
            DatabaseError: If check fails
        """
        try:
            with self._transaction() as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) as count FROM credentials WHERE name = ?", (name,)
                )
                row = cursor.fetchone()
                return row["count"] > 0

        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to check credential existence: {e}") from e


# ============================================================================
# Application Layer: Credential Manager (Public API)
# ============================================================================


class CredentialManager:
    """
    Main credential management interface.

    Provides high-level API for storing, retrieving, and managing encrypted credentials.

    Usage:
        >>> manager = CredentialManager()
        >>> manager.set("OPENROUTER_API_KEY", "sk-or-...", provider="openrouter")
        >>> api_key = manager.get("OPENROUTER_API_KEY")
        >>> manager.delete("OPENROUTER_API_KEY")
        >>> credentials = manager.list_all()
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """
        Initialize credential manager.

        Args:
            db_path: Path to credentials database (defaults to ~/.ninja/credentials.db)

        Raises:
            DatabaseError: If database initialization fails
            EncryptionError: If encryption setup fails
        """
        if db_path is None:
            db_path = Path.home() / ".ninja" / "credentials.db"

        # Initialize database
        self._db = CredentialDatabase(db_path)

        # Initialize encryption
        password = os.getenv("NINJA_CREDENTIAL_PASSWORD", "")
        salt = self._db.get_or_create_salt()
        master_key = KeyDerivation.derive_key(salt, password)
        self._encryption = CredentialEncryption(master_key)

    def set(self, name: str, value: str, provider: str | None = None) -> None:
        """
        Store or update a credential.

        Args:
            name: Credential name (e.g., "OPENROUTER_API_KEY")
            value: Credential value (will be encrypted)
            provider: Optional provider name (e.g., "openrouter")

        Raises:
            EncryptionError: If encryption fails
            DatabaseError: If storage fails
            ValueError: If name or value is empty
        """
        if not name or not name.strip():
            raise ValueError("Credential name cannot be empty")

        if not value:
            raise ValueError("Credential value cannot be empty")

        encrypted_value = self._encryption.encrypt(value)
        self._db.store_credential(name.strip(), encrypted_value, provider)

    def get(self, name: str) -> str | None:
        """
        Retrieve a credential value.

        Args:
            name: Credential name

        Returns:
            Decrypted credential value, or None if not found

        Raises:
            EncryptionError: If decryption fails
            DatabaseError: If retrieval fails
        """
        try:
            encrypted_value = self._db.get_credential(name)
            return self._encryption.decrypt(encrypted_value)
        except CredentialNotFoundError:
            return None

    def delete(self, name: str) -> bool:
        """
        Delete a credential.

        Securely overwrites the encrypted value before deletion.

        Args:
            name: Credential name

        Returns:
            True if credential was deleted, False if it didn't exist

        Raises:
            DatabaseError: If deletion fails
        """
        return self._db.delete_credential(name)

    def list_all(self) -> list[dict[str, Any]]:
        """
        List all credentials with masked values.

        Returns:
            List of credential dictionaries with metadata and masked values
            Example: [
                {
                    "name": "OPENROUTER_API_KEY",
                    "provider": "openrouter",
                    "masked_value": "sk-or-***...***1234",
                    "created_at": "2026-02-12T01:00:00",
                    "updated_at": "2026-02-12T01:00:00",
                    "last_used": "2026-02-12T02:00:00"
                }
            ]

        Raises:
            DatabaseError: If listing fails
        """
        credentials = self._db.list_credentials()

        # Add masked values
        for cred in credentials:
            # Get actual value to create proper mask
            try:
                value = self.get(cred["name"])
                if value:
                    cred["masked_value"] = self._mask_value(value)
                else:
                    cred["masked_value"] = "***"
            except Exception:
                cred["masked_value"] = "***"

        return credentials

    def exists(self, name: str) -> bool:
        """
        Check if a credential exists.

        Args:
            name: Credential name

        Returns:
            True if credential exists, False otherwise

        Raises:
            DatabaseError: If check fails
        """
        return self._db.credential_exists(name)

    @staticmethod
    def _mask_value(value: str) -> str:
        """
        Create a masked version of a credential value.

        Shows first few and last few characters, masks the middle.

        Args:
            value: Credential value to mask

        Returns:
            Masked credential value

        Examples:
            "sk-or-v1-1234567890abcdef" -> "sk-or-***...***cdef"
            "short" -> "sh***"
        """
        if len(value) <= 8:
            # For short values, just show first 2 chars
            return f"{value[:2]}***" if len(value) > 2 else "***"

        # For longer values, show prefix and suffix
        prefix_len = min(6, len(value) // 3)
        suffix_len = min(4, len(value) // 4)

        prefix = value[:prefix_len]
        suffix = value[-suffix_len:]

        return f"{prefix}***...***{suffix}"
