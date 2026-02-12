# Configuration Architecture Design

**Date:** 2026-02-12
**Status:** Design Phase
**Approved:** Pending User Review

---

## Executive Summary

Complete redesign of ninja configuration system with:
- ✅ **JSON** hierarchical config format
- ✅ **Automatic migration** from old .env
- ✅ **SQLite credential storage** with encryption
- ✅ **OpenCode integration** via `OPENCODE_CONFIG` env var
- ✅ **Component-first** architecture
- ✅ **Deprecate** old .env format

---

## Architecture Overview

### File Structure

```
~/.ninja/
├── config.json           # Hierarchical configuration (non-sensitive)
├── credentials.db        # Encrypted credentials (SQLite)
├── config.backup/        # Automatic backups
│   ├── config.json.20260212_014500
│   └── credentials.db.20260212_014500
└── migrations/           # Migration logs
    └── 20260212_from_env.log
```

### Legacy Files (to be migrated & deprecated)

```
~/.ninja-mcp.env         # OLD - Will be migrated automatically
~/.claude.json           # Keep for Claude Code MCP config
```

---

## 1. Configuration File Format

### `~/.ninja/config.json` Structure

```json
{
  "version": "2.0.0",
  "last_updated": "2026-02-12T01:45:00Z",

  "components": {
    "coder": {
      "operator": "opencode",
      "operator_settings": {
        "opencode": {
          "provider": "anthropic",
          "provider_routing": {
            "order": ["anthropic", "openrouter"],
            "allow_fallbacks": true
          },
          "custom_models": [],
          "experimental_models": false
        }
      },
      "models": {
        "default": "anthropic/claude-sonnet-4-5",
        "quick": "anthropic/claude-haiku-4-5",
        "heavy": "anthropic/claude-opus-4",
        "parallel": "anthropic/claude-haiku-4-5"
      }
    },

    "researcher": {
      "operator": "perplexity",
      "models": {
        "default": "sonar-pro"
      },
      "search_provider": "perplexity"
    },

    "secretary": {
      "operator": "opencode",
      "operator_settings": {
        "opencode": {
          "provider": "google"
        }
      },
      "models": {
        "default": "google/gemini-2.0-flash"
      }
    }
  },

  "daemon": {
    "enabled": true,
    "ports": {
      "coder": 8100,
      "researcher": 8101,
      "secretary": 8102,
      "prompts": 8107
    }
  },

  "preferences": {
    "cost_vs_quality": "balanced",
    "auto_update": true,
    "telemetry": false
  }
}
```

### Key Design Decisions

1. **Component-First Hierarchy**
   - Top level: `components` object with coder/researcher/secretary
   - Each component has its own operator and settings
   - Complete isolation between components

2. **Operator-Specific Settings**
   - Nested under `operator_settings[operator_name]`
   - Different operators have different schemas
   - Validated by Pydantic models

3. **No Credentials in JSON**
   - All API keys stored in SQLite
   - JSON contains only non-sensitive config
   - Credentials referenced by name

---

## 2. Credential Storage (SQLite)

### Database Schema

```sql
-- ~/.ninja/credentials.db

CREATE TABLE credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,           -- e.g., 'OPENROUTER_API_KEY'
    value BLOB NOT NULL,                 -- Encrypted value
    provider TEXT,                       -- e.g., 'openrouter', 'anthropic'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    metadata TEXT                        -- JSON metadata
);

CREATE INDEX idx_credentials_name ON credentials(name);
CREATE INDEX idx_credentials_provider ON credentials(provider);

-- Encryption metadata
CREATE TABLE encryption_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Only one row
    key_derivation TEXT NOT NULL,           -- 'pbkdf2', 'scrypt', etc.
    salt BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Encryption Strategy

**Algorithm:** AES-256-GCM
**Key Derivation:** PBKDF2-HMAC-SHA256 (100,000 iterations)
**Master Key Source:** Machine-specific key + user password (optional)

```python
# Pseudo-code
def derive_master_key() -> bytes:
    """Derive encryption key from machine ID + optional password."""
    machine_id = get_machine_id()  # CPU serial, MAC address hash, etc.
    salt = get_or_create_salt()

    # Optional: Prompt for password on first run
    password = os.getenv("NINJA_CREDENTIAL_PASSWORD", "")

    key_material = f"{machine_id}:{password}".encode()

    return pbkdf2_hmac(
        'sha256',
        key_material,
        salt,
        iterations=100_000,
        dklen=32
    )

def encrypt_credential(plaintext: str) -> bytes:
    """Encrypt credential with AES-256-GCM."""
    key = derive_master_key()
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
    return cipher.nonce + tag + ciphertext

def decrypt_credential(ciphertext: bytes) -> str:
    """Decrypt credential."""
    key = derive_master_key()
    nonce = ciphertext[:16]
    tag = ciphertext[16:32]
    encrypted = ciphertext[32:]

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(encrypted, tag)
    return plaintext.decode()
```

### Credential Manager API

```python
from ninja_config.credentials import CredentialManager

# Usage
cred_manager = CredentialManager()

# Store credential
cred_manager.set("OPENROUTER_API_KEY", "sk-or-...", provider="openrouter")

# Retrieve credential
api_key = cred_manager.get("OPENROUTER_API_KEY")

# Delete credential
cred_manager.delete("OPENROUTER_API_KEY")

# List all credentials (masked)
creds = cred_manager.list_all()
# Returns: [{"name": "OPENROUTER_API_KEY", "provider": "openrouter", "masked_value": "sk-or-***...***1234"}]
```

---

## 3. Pydantic Schema Definitions

### `src/ninja_config/config_schema.py`

```python
from pydantic import BaseModel, Field, validator
from typing import Literal, Optional, Dict, List
from datetime import datetime

# ============================================================================
# Operator Settings
# ============================================================================

class OpenCodeProviderRouting(BaseModel):
    """OpenCode provider routing configuration."""
    order: List[str] = Field(
        default=["anthropic"],
        description="Provider preference order"
    )
    allow_fallbacks: bool = Field(
        default=True,
        description="Allow fallback to other providers"
    )

class OpenCodeOperatorSettings(BaseModel):
    """OpenCode-specific operator settings."""
    provider: str = Field(
        default="anthropic",
        description="Primary provider to use"
    )
    provider_routing: Optional[OpenCodeProviderRouting] = None
    custom_models: List[str] = Field(
        default_factory=list,
        description="Custom model IDs to add"
    )
    experimental_models: bool = Field(
        default=False,
        description="Enable experimental models"
    )

class AiderOperatorSettings(BaseModel):
    """Aider-specific operator settings."""
    edit_format: Literal["diff", "whole", "udiff"] = "diff"
    auto_commits: bool = True
    dirty_commits: bool = True

class GeminiOperatorSettings(BaseModel):
    """Gemini CLI operator settings."""
    # Gemini has minimal settings
    pass

class ClaudeCodeOperatorSettings(BaseModel):
    """Claude Code operator settings."""
    # Claude Code has minimal settings
    pass

# Union of all operator settings
OperatorSettings = (
    OpenCodeOperatorSettings |
    AiderOperatorSettings |
    GeminiOperatorSettings |
    ClaudeCodeOperatorSettings
)

# ============================================================================
# Component Configuration
# ============================================================================

class ModelConfiguration(BaseModel):
    """Model configuration for a component."""
    default: str = Field(description="Default model for standard tasks")
    quick: Optional[str] = Field(None, description="Fast model for simple tasks")
    heavy: Optional[str] = Field(None, description="Powerful model for complex tasks")
    parallel: Optional[str] = Field(None, description="Model for parallel tasks")

class ComponentConfig(BaseModel):
    """Configuration for a single component (coder, researcher, secretary)."""
    operator: Literal["opencode", "aider", "claude", "gemini"] = Field(
        description="Operator to use for this component"
    )
    operator_settings: Dict[str, OperatorSettings] = Field(
        default_factory=dict,
        description="Operator-specific settings, keyed by operator name"
    )
    models: ModelConfiguration = Field(
        description="Model configuration"
    )

    # Component-specific fields
    search_provider: Optional[Literal["duckduckgo", "serper", "perplexity"]] = None

# ============================================================================
# Daemon Configuration
# ============================================================================

class DaemonConfig(BaseModel):
    """Daemon configuration."""
    enabled: bool = True
    ports: Dict[str, int] = Field(
        default={
            "coder": 8100,
            "researcher": 8101,
            "secretary": 8102,
            "prompts": 8107
        }
    )

# ============================================================================
# Preferences
# ============================================================================

class Preferences(BaseModel):
    """User preferences."""
    cost_vs_quality: Literal["cost", "balanced", "quality"] = "balanced"
    auto_update: bool = True
    telemetry: bool = False

# ============================================================================
# Root Configuration
# ============================================================================

class NinjaConfig(BaseModel):
    """Root configuration schema."""
    version: str = Field(default="2.0.0", description="Config schema version")
    last_updated: datetime = Field(default_factory=datetime.now)

    components: Dict[str, ComponentConfig] = Field(
        description="Component configurations"
    )
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    preferences: Preferences = Field(default_factory=Preferences)

    @validator("version")
    def validate_version(cls, v):
        """Ensure version is supported."""
        supported = ["2.0.0"]
        if v not in supported:
            raise ValueError(f"Unsupported config version: {v}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "version": "2.0.0",
                "components": {
                    "coder": {
                        "operator": "opencode",
                        "operator_settings": {
                            "opencode": {
                                "provider": "anthropic",
                                "provider_routing": {
                                    "order": ["anthropic", "openrouter"],
                                    "allow_fallbacks": True
                                }
                            }
                        },
                        "models": {
                            "default": "anthropic/claude-sonnet-4-5",
                            "quick": "anthropic/claude-haiku-4-5"
                        }
                    }
                }
            }
        }
```

---

## 4. OpenCode Integration

### Environment Variable Setup

When ninja starts or runs commands, set:

```bash
export OPENCODE_CONFIG="$HOME/.ninja/config.json"
export OPENCODE_CONFIG_DIR="$HOME/.ninja"
```

This points OpenCode to use our unified config file.

### Config Transformation

Since OpenCode expects a specific format, we'll transform our config:

```python
# src/ninja_config/opencode_integration.py

def generate_opencode_config(ninja_config: NinjaConfig) -> dict:
    """Generate OpenCode-compatible config from ninja config."""
    coder = ninja_config.components.get("coder")
    if not coder or coder.operator != "opencode":
        return {}

    settings = coder.operator_settings.get("opencode", {})

    opencode_config = {
        "models": {},
        "defaultProvider": settings.get("provider", "anthropic"),
    }

    # Add provider routing if configured
    if routing := settings.get("provider_routing"):
        opencode_config["providerRouting"] = {
            "order": routing.order,
            "allowFallbacks": routing.allow_fallbacks
        }

    # Add custom models
    for model_name in settings.get("custom_models", []):
        opencode_config["models"][model_name] = {}

    return opencode_config

def write_opencode_config(ninja_config: NinjaConfig):
    """Write OpenCode config to ~/.ninja/config.json."""
    config = generate_opencode_config(ninja_config)
    config_path = Path.home() / ".ninja" / "config.json"

    with config_path.open("w") as f:
        json.dump(config, f, indent=2)
```

---

## 5. Migration Strategy

### Automatic Migration on First Run

```python
# src/ninja_config/config_migrator.py

from pathlib import Path
import json
import shutil
from datetime import datetime

class ConfigMigrator:
    """Migrate old .env config to new JSON + SQLite format."""

    def __init__(self):
        self.old_env_path = Path.home() / ".ninja-mcp.env"
        self.new_config_dir = Path.home() / ".ninja"
        self.new_config_path = self.new_config_dir / "config.json"
        self.credentials_db = self.new_config_dir / "credentials.db"

    def needs_migration(self) -> bool:
        """Check if migration is needed."""
        return (
            self.old_env_path.exists() and
            not self.new_config_path.exists()
        )

    def migrate(self) -> dict:
        """Perform migration."""
        print("🔄 Migrating configuration to new format...")

        # 1. Backup old config
        backup_path = self._backup_old_config()
        print(f"   ✓ Backed up old config to {backup_path}")

        # 2. Parse old env file
        old_config = self._parse_old_env()
        print(f"   ✓ Parsed {len(old_config)} settings from old config")

        # 3. Extract credentials
        credentials = self._extract_credentials(old_config)
        print(f"   ✓ Extracted {len(credentials)} API keys")

        # 4. Build new config structure
        new_config = self._build_new_config(old_config)
        print(f"   ✓ Built new configuration structure")

        # 5. Save credentials to SQLite
        self._save_credentials(credentials)
        print(f"   ✓ Saved credentials to encrypted database")

        # 6. Save new config to JSON
        self._save_config(new_config)
        print(f"   ✓ Saved configuration to {self.new_config_path}")

        # 7. Mark old config as migrated
        self._mark_migrated()

        print("\n✅ Migration completed successfully!")
        print(f"   Old config: {self.old_env_path} (backed up)")
        print(f"   New config: {self.new_config_path}")
        print(f"   Credentials: {self.credentials_db}")

        return {
            "old_config": str(self.old_env_path),
            "new_config": str(self.new_config_path),
            "backup": str(backup_path),
            "credentials_count": len(credentials)
        }

    def _backup_old_config(self) -> Path:
        """Backup old env file."""
        backup_dir = self.new_config_dir / "config.backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"ninja-mcp.env.{timestamp}"

        shutil.copy2(self.old_env_path, backup_path)
        return backup_path

    def _parse_old_env(self) -> dict:
        """Parse old .env file."""
        config = {}
        with self.old_env_path.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Parse both "export KEY=value" and "KEY=value"
                if "=" in line:
                    line = line.replace("export ", "", 1)
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip().strip("'\"")

        return config

    def _extract_credentials(self, old_config: dict) -> dict:
        """Extract API keys and credentials."""
        credentials = {}
        for key, value in old_config.items():
            if "API_KEY" in key or "KEY" in key or "PASSWORD" in key:
                credentials[key] = value
        return credentials

    def _build_new_config(self, old_config: dict) -> NinjaConfig:
        """Build new config from old settings."""
        components = {}

        # Coder component
        coder_operator = old_config.get("NINJA_CODE_BIN", "opencode")
        coder_provider = old_config.get("NINJA_CODER_PROVIDER", "anthropic")

        components["coder"] = ComponentConfig(
            operator=coder_operator,
            operator_settings={
                coder_operator: OpenCodeOperatorSettings(
                    provider=coder_provider
                ) if coder_operator == "opencode" else {}
            },
            models=ModelConfiguration(
                default=old_config.get("NINJA_CODER_MODEL", "anthropic/claude-sonnet-4-5"),
                quick=old_config.get("NINJA_MODEL_QUICK"),
                heavy=old_config.get("NINJA_MODEL_SEQUENTIAL"),
                parallel=old_config.get("NINJA_MODEL_PARALLEL")
            )
        )

        # Researcher component
        components["researcher"] = ComponentConfig(
            operator="perplexity",
            models=ModelConfiguration(
                default=old_config.get("NINJA_RESEARCHER_MODEL", "sonar-pro")
            ),
            search_provider=old_config.get("NINJA_SEARCH_PROVIDER", "duckduckgo")
        )

        # Secretary component
        components["secretary"] = ComponentConfig(
            operator=old_config.get("NINJA_SECRETARY_OPERATOR", "opencode"),
            models=ModelConfiguration(
                default=old_config.get("NINJA_SECRETARY_MODEL", "google/gemini-2.0-flash")
            )
        )

        # Build root config
        return NinjaConfig(
            components=components,
            daemon=DaemonConfig(
                enabled=old_config.get("NINJA_ENABLE_DAEMON", "true").lower() == "true",
                ports={
                    "coder": int(old_config.get("NINJA_CODER_PORT", 8100)),
                    "researcher": int(old_config.get("NINJA_RESEARCHER_PORT", 8101)),
                    "secretary": int(old_config.get("NINJA_SECRETARY_PORT", 8102)),
                    "prompts": int(old_config.get("NINJA_PROMPTS_PORT", 8107))
                }
            )
        )

    def _save_credentials(self, credentials: dict):
        """Save credentials to SQLite."""
        from ninja_config.credentials import CredentialManager

        cred_manager = CredentialManager()
        for name, value in credentials.items():
            provider = self._guess_provider(name)
            cred_manager.set(name, value, provider=provider)

    def _guess_provider(self, key_name: str) -> str:
        """Guess provider from key name."""
        if "OPENROUTER" in key_name:
            return "openrouter"
        elif "ANTHROPIC" in key_name:
            return "anthropic"
        elif "OPENAI" in key_name:
            return "openai"
        elif "GOOGLE" in key_name or "GEMINI" in key_name:
            return "google"
        elif "PERPLEXITY" in key_name:
            return "perplexity"
        elif "SERPER" in key_name:
            return "serper"
        elif "ZHIPU" in key_name:
            return "zai"
        return "unknown"

    def _save_config(self, config: NinjaConfig):
        """Save new config to JSON."""
        self.new_config_dir.mkdir(parents=True, exist_ok=True)

        with self.new_config_path.open("w") as f:
            json.dump(
                config.model_dump(),
                f,
                indent=2,
                default=str
            )

    def _mark_migrated(self):
        """Mark old config as migrated."""
        migrated_marker = self.old_env_path.with_suffix(".env.migrated")
        self.old_env_path.rename(migrated_marker)
```

### Migration Flow

```
User runs: ninja-config <any command>
  ↓
Check: Does ~/.ninja/config.json exist?
  ├─ NO → Check if migration needed
  │         ├─ YES → Auto-migrate
  │         └─ NO → Show setup wizard
  └─ YES → Load config normally
```

---

## 6. Implementation Files

### New Files to Create

```
src/ninja_config/
├── config_schema.py              # Pydantic schemas (NEW)
├── credentials.py                # Credential manager with SQLite + encryption (NEW)
├── config_loader.py              # Unified config loader (NEW)
├── config_migrator.py            # Migration from .env (NEW)
├── opencode_integration.py       # OpenCode config sync (NEW)
├── ui/                           # Split UI into modules (NEW)
│   ├── __init__.py
│   ├── base.py                   # Shared UI components
│   ├── main_menu.py              # Main menu
│   ├── component_setup.py        # Component setup flows
│   ├── operator_config.py        # Operator settings
│   └── model_selector.py         # Model selection
└── ...existing files...
```

### Files to Refactor

```
src/ninja_config/
├── interactive_configurator.py   # REFACTOR → Split into ui/* modules
├── model_selector.py             # REFACTOR → Extract UI to ui/model_selector.py
└── config_manager.py             # REFACTOR → Deprecate, use config_loader.py
```

---

## 7. CLI Commands

### New Commands

```bash
# Automatic migration happens on any command if needed
ninja-config configure          # Opens TUI (migrates first if needed)

# Manual migration (if user wants control)
ninja-config migrate            # Migrate old .env to new format
ninja-config migrate --dry-run  # Preview migration

# Credential management
ninja-config credentials list          # List all credentials (masked)
ninja-config credentials set <name>    # Set a credential
ninja-config credentials delete <name> # Delete a credential

# Config validation
ninja-config validate           # Validate current config
ninja-config doctor             # Diagnose config issues
```

---

## 8. Security Considerations

### Credential Protection

1. **Encryption at Rest** - All credentials encrypted in SQLite with AES-256-GCM
2. **Machine-Specific Keys** - Encryption key derived from machine ID
3. **Optional Password** - User can set `NINJA_CREDENTIAL_PASSWORD` for extra security
4. **No Plaintext** - Never store credentials in plaintext files
5. **Secure Deletion** - Overwrite credential data before deleting

### Permission Model

```bash
chmod 700 ~/.ninja                    # Only user can access
chmod 600 ~/.ninja/config.json        # Only user can read/write
chmod 600 ~/.ninja/credentials.db     # Only user can read/write
```

---

## Next Steps

1. ✅ User approval of architecture
2. ⏳ Implement Pydantic schemas
3. ⏳ Implement credential manager (SQLite + encryption)
4. ⏳ Implement config loader
5. ⏳ Implement migrator
6. ⏳ Refactor UI components
7. ⏳ Add OpenCode integration
8. ⏳ Write tests
9. ⏳ Update documentation

---

## Questions Resolved

1. ✅ **Config Format**: JSON
2. ✅ **Migration**: Automatic on first run
3. ✅ **OpenCode Sync**: Via `OPENCODE_CONFIG` env var pointing to our config
4. ✅ **Backwards Compat**: Deprecate .env after migration
5. ✅ **Credentials**: SQLite with AES-256 encryption

