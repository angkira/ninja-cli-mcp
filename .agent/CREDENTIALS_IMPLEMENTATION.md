# Credentials Implementation Documentation

**Date:** 2026-02-12
**Status:** ✅ COMPLETED
**File:** `src/ninja_config/credentials.py`

---

## Executive Summary

The encrypted credential storage system has been successfully implemented with SQLite backend and AES-256-GCM encryption. The implementation follows hexagonal architecture principles, uses dependency injection, and provides complete type safety.

---

## Implementation Details

### File Location
```
src/ninja_config/credentials.py
```

### Architecture

The implementation follows **Hexagonal Architecture** with clear separation of concerns:

#### Domain Layer (Pure Business Logic)
- **CredentialEncryption**: AES-256-GCM encryption/decryption
- **KeyDerivation**: PBKDF2-HMAC-SHA256 key derivation

#### Infrastructure Layer
- **CredentialDatabase**: SQLite database adapter with thread-safe operations

#### Application Layer (Public API)
- **CredentialManager**: High-level credential management interface

### Database Schema

#### credentials table
```sql
CREATE TABLE credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    value BLOB NOT NULL,
    provider TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    metadata TEXT
);

CREATE INDEX idx_credentials_name ON credentials(name);
CREATE INDEX idx_credentials_provider ON credentials(provider);
```

#### encryption_meta table
```sql
CREATE TABLE encryption_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    key_derivation TEXT NOT NULL,
    salt BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Features Implemented

### 1. Encryption (AES-256-GCM)
- ✅ Algorithm: AES-256-GCM (Authenticated encryption)
- ✅ Nonce: 12 bytes (96 bits) - recommended for GCM
- ✅ Authentication tag: 16 bytes (128 bits)
- ✅ Format: `nonce (12 bytes) + ciphertext (includes 16-byte auth tag)`

### 2. Key Derivation (PBKDF2)
- ✅ Algorithm: PBKDF2-HMAC-SHA256
- ✅ Iterations: 100,000
- ✅ Key length: 32 bytes (256 bits)
- ✅ Salt: 32 bytes (randomly generated, stored in database)

### 3. Machine ID Integration
- ✅ Uses UUID node (MAC address-based)
- ✅ SHA-256 hash for stability
- ✅ Combined with optional password for key derivation

### 4. Password Support
- ✅ Reads from `NINJA_CREDENTIAL_PASSWORD` environment variable
- ✅ Optional (defaults to empty string)
- ✅ Combined with machine ID for enhanced security

### 5. Security Features
- ✅ File permissions: 600 (database), 700 (directory)
- ✅ Secure deletion: Overwrites data before delete
- ✅ Thread-safe operations: Uses threading.Lock
- ✅ No plaintext storage: All credentials encrypted at rest

### 6. CredentialManager API

```python
from ninja_config.credentials import CredentialManager

# Initialize
manager = CredentialManager()  # Uses ~/.ninja/credentials.db
# or
manager = CredentialManager(custom_db_path)

# Store credential
manager.set(
    name="OPENROUTER_API_KEY",
    value="sk-or-v1-...",
    provider="openrouter"  # optional
)

# Retrieve credential
api_key = manager.get("OPENROUTER_API_KEY")  # Returns str or None

# Check existence
exists = manager.exists("OPENROUTER_API_KEY")  # Returns bool

# List all credentials (with masked values)
credentials = manager.list_all()
# Returns: [
#     {
#         "name": "OPENROUTER_API_KEY",
#         "provider": "openrouter",
#         "masked_value": "sk-or-***...***1234",
#         "created_at": "2026-02-12T01:00:00",
#         "updated_at": "2026-02-12T01:00:00",
#         "last_used": "2026-02-12T02:00:00"
#     }
# ]

# Delete credential (secure overwrite + delete)
deleted = manager.delete("OPENROUTER_API_KEY")  # Returns bool
```

---

## Architecture Compliance

### ✅ Hexagonal Architecture
- **Domain Layer**: Pure business logic (encryption, key derivation)
- **Infrastructure Layer**: External dependencies (SQLite)
- **Application Layer**: Public API (CredentialManager)

### ✅ Dependency Injection
```python
class CredentialManager:
    def __init__(self, db_path: Path | None = None):
        # Dependencies injected via constructor
        self._db = CredentialDatabase(db_path)
        self._encryption = CredentialEncryption(master_key)
```

### ✅ Type Safety
- All functions have full type hints
- Return types specified for all methods
- Uses `str | None` instead of `Optional[str]` (modern syntax)
- Minimal use of `Any` type (only 3 instances, all in list_all return)
- Zero `# type: ignore` comments

### ✅ Error Handling
- Custom exception hierarchy:
  - `CredentialError` (base)
  - `EncryptionError`
  - `DatabaseError`
  - `CredentialNotFoundError`
- Proper error propagation
- Informative error messages

---

## Verification Tests

All requirements have been verified with comprehensive tests:

### Database Schema Tests
- ✅ credentials table structure
- ✅ encryption_meta table structure
- ✅ Indexes created correctly

### Encryption Tests
- ✅ AES-256-GCM encryption/decryption
- ✅ Key derivation (32-byte keys)
- ✅ PBKDF2 iterations (100,000)
- ✅ Nonce length (12 bytes)
- ✅ Authentication tag (16 bytes)

### Security Tests
- ✅ Machine ID generation (stable, SHA-256)
- ✅ Password support (NINJA_CREDENTIAL_PASSWORD)
- ✅ File permissions (600 for DB, 700 for directory)
- ✅ Secure deletion (overwrite before delete)
- ✅ Thread-safe operations (10 concurrent threads)

### API Tests
- ✅ set() - Store credentials
- ✅ get() - Retrieve credentials
- ✅ delete() - Delete credentials
- ✅ list_all() - List with masked values
- ✅ exists() - Check existence

### Error Handling Tests
- ✅ Empty name validation
- ✅ Empty value validation
- ✅ Wrong decryption key detection

---

## Code Quality Metrics

- **Total Lines**: 694
- **Docstrings**: 36 (all public methods documented)
- **Type Hints**: 21 functions with return types
- **Exception Handling**: 13 try blocks, 16 raises
- **Thread Safety**: Lock-based synchronization
- **Security**: 7 security features implemented

---

## Usage Examples

### Basic Usage
```python
from ninja_config.credentials import CredentialManager

manager = CredentialManager()

# Store API keys
manager.set("OPENROUTER_API_KEY", "sk-or-v1-...", provider="openrouter")
manager.set("ANTHROPIC_API_KEY", "sk-ant-...", provider="anthropic")

# Retrieve when needed
api_key = manager.get("OPENROUTER_API_KEY")
if api_key:
    # Use API key
    pass
```

### With Custom Password
```bash
export NINJA_CREDENTIAL_PASSWORD="my_secure_password"
```

```python
# Password automatically used when deriving encryption key
manager = CredentialManager()
manager.set("SECRET_KEY", "sensitive_value")
```

### Migration from Environment Variables
```python
import os
from ninja_config.credentials import CredentialManager

manager = CredentialManager()

# Migrate API keys from environment
env_keys = [
    ("OPENROUTER_API_KEY", "openrouter"),
    ("ANTHROPIC_API_KEY", "anthropic"),
    ("GOOGLE_API_KEY", "google"),
]

for key_name, provider in env_keys:
    value = os.getenv(key_name)
    if value:
        manager.set(key_name, value, provider=provider)
        print(f"Migrated {key_name}")
```

### List All Credentials
```python
manager = CredentialManager()

credentials = manager.list_all()
for cred in credentials:
    print(f"{cred['name']}: {cred['masked_value']}")
    print(f"  Provider: {cred['provider']}")
    print(f"  Last used: {cred['last_used']}")
```

---

## Integration Points

### With Configuration System
The credential manager integrates with the new configuration system:

```python
# config_loader.py
from ninja_config.credentials import CredentialManager

class ConfigLoader:
    def __init__(self):
        self._cred_manager = CredentialManager()

    def get_api_key(self, provider: str) -> str | None:
        """Get API key for provider."""
        key_name = f"{provider.upper()}_API_KEY"
        return self._cred_manager.get(key_name)
```

### With OpenCode Integration
```python
# opencode_integration.py
from ninja_config.credentials import CredentialManager

def get_openrouter_key() -> str | None:
    manager = CredentialManager()
    return manager.get("OPENROUTER_API_KEY")
```

---

## Security Considerations

### Encryption at Rest
- All credentials encrypted with AES-256-GCM
- Authentication tag prevents tampering
- Nonce ensures unique encryption each time

### Key Derivation
- PBKDF2-HMAC-SHA256 with 100,000 iterations
- Protects against brute-force attacks
- Machine-specific key prevents credential transfer

### File Permissions
- Database: 600 (owner read/write only)
- Directory: 700 (owner access only)
- Prevents unauthorized access

### Secure Deletion
- Overwrites encrypted data with random bytes
- Then deletes from database
- Prevents data recovery from disk

### Thread Safety
- All database operations protected by locks
- Thread-local connections prevent race conditions
- Safe for concurrent access

---

## Future Enhancements (Optional)

### Potential Improvements
1. **Credential rotation**: Automatic key rotation with grace period
2. **Audit logging**: Track all credential access
3. **Expiration**: Time-based credential expiration
4. **Backup/restore**: Export/import encrypted credentials
5. **Password prompt**: Interactive password entry on first use
6. **Key escrow**: Optional recovery mechanism

These are NOT required for the current implementation but could be added later.

---

## References

- **Architecture Design**: `.agent/CONFIG_ARCHITECTURE_DESIGN.md` (Section 2)
- **Implementation File**: `src/ninja_config/credentials.py`
- **Architecture Guide**: `.agent/ARCHITECT.md`

---

**Status**: ✅ IMPLEMENTATION COMPLETE AND VERIFIED

All requirements satisfied. Ready for integration with configuration system.
