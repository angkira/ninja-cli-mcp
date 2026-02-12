# Configuration Refactoring Analysis

**Date:** 2026-02-12
**Status:** In Progress

## Investigation Results

### 1. Ninja-Coder Failed Tasks

**Findings:**
- Only 1 log entry found in recent logs (last 24h)
- No ERROR or WARNING level logs in the query results
- The single log shows: Driver initialized with `claude` CLI and `qwen/qwen3-coder` model
- **Conclusion:** No recent task failures detected. System appears stable.

---

## 2. Current Configuration Structure Analysis

### Configuration Files Map

```
src/ninja_config/
├── config_cli.py                    # CLI entry point (ninja-config command)
├── config_manager.py                # Low-level config file I/O
├── configurator.py                  # ? (need to read)
├── interactive_configurator.py      # Original basic TUI (NinjaConfigurator)
├── model_selector.py                # Operator/model detection & selection logic
├── tui_installer.py                 # Installation wizard
└── __init__.py

src/ninja_common/
├── config_cli.py                    # Duplicate? Or different purpose?
└── config_manager.py                # Shared config manager
```

### Current Configuration Flow Problems

#### Problem 1: Chaotic Entry Points
```
ninja-config configure
  ├─→ cmd_configure()
  └─→ run_power_configurator() in interactive_configurator.py
      └─→ PowerConfigurator class
          ├─ Main menu with 15+ options
          ├─ _configure_operators()
          ├─ _configure_models()
          ├─ _coder_setup_flow()  # "Recommended" flow
          └─ ... many more scattered options
```

**Issues:**
- Too many top-level menu items (15+)
- Multiple ways to configure the same thing
- No clear "recommended" path for new users
- Configuration concerns are mixed

#### Problem 2: Operator → Provider → Model Flow is Backwards

**Current flow** (in `_coder_setup_flow`):
```
1. Select Operator (opencode, aider, claude, gemini)
2. Select Provider (only for opencode: anthropic, google, openai, etc.)
3. Select Model (queries from operator/provider)
```

**User mental model should be:**
```
1. What component? (coder, researcher, secretary)
2. Which operator for this component? (opencode, aider, claude)
3. Which model for this operator?
4. (Optional) Operator settings (modes, provider routing, etc.)
```

#### Problem 3: Missing OpenCode Provider Configuration

From OpenCode docs (https://opencode.ai/docs/providers/#openrouter), OpenCode supports:

```json
{
  "models": {
    "moonshotai/kimi-k2": {
      "options": {
        "provider": {
          "order": ["baseten"],
          "allow_fallbacks": false
        }
      }
    }
  }
}
```

**Missing features:**
- Provider routing configuration
- Provider order preference
- Fallback settings
- Per-model provider customization

#### Problem 4: Operator Settings Are Scattered/Missing

Each operator has unique settings:

**OpenCode:**
- Provider routing (order, fallbacks)
- Model-specific options
- Custom model additions
- Authentication per provider

**Aider:**
- Edit format (`--edit-format`)
- Model parameters
- Auto-commits, git settings

**Claude Code:**
- Only works with Anthropic models
- Auth via `claude auth`
- No advanced settings needed

**Gemini CLI:**
- Google API key
- Model selection (limited)

**Current state:** Only basic operator selection exists. No operator-specific settings UI.

---

## 3. Current Configuration Data Model

### Environment Variables Structure

```bash
# API Keys (Global)
OPENROUTER_API_KEY
ANTHROPIC_API_KEY
OPENAI_API_KEY
GOOGLE_API_KEY
PERPLEXITY_API_KEY
SERPER_API_KEY
ZHIPU_API_KEY

# Coder Module
NINJA_CODE_BIN                  # operator binary path
NINJA_MODEL                     # generic model
NINJA_CODER_MODEL              # coder-specific model
NINJA_CODER_PROVIDER           # selected provider (for opencode)
NINJA_MODEL_QUICK              # quick task model
NINJA_MODEL_SEQUENTIAL         # heavy task model
NINJA_MODEL_PARALLEL           # parallel task model

# Researcher Module
NINJA_RESEARCHER_MODEL         # perplexity model
NINJA_SEARCH_PROVIDER          # duckduckgo, serper, perplexity

# Secretary Module
NINJA_SECRETARY_OPERATOR       # can use different operator
NINJA_SECRETARY_MODEL          # secretary model

# Daemon
NINJA_ENABLE_DAEMON
NINJA_CODER_PORT
NINJA_RESEARCHER_PORT
NINJA_SECRETARY_PORT
```

### Issues with Current Data Model

1. **Flat namespace** - All settings in one flat file
2. **No hierarchy** - Can't distinguish component → operator → model relationship
3. **No operator settings** - No place for operator-specific configs
4. **Redundancy** - Multiple `NINJA_MODEL*` variables
5. **No validation** - No schema for valid combinations

---

## 4. Desired Configuration Architecture

### Proposed Hierarchical Structure

```yaml
# Component-first approach
components:
  coder:
    operator: opencode
    operator_settings:
      provider: anthropic
      provider_routing:
        order: [anthropic, openrouter]
        allow_fallbacks: true
      custom_models:
        - my-model/custom
    models:
      default: anthropic/claude-sonnet-4-5
      quick: anthropic/claude-haiku-4-5
      heavy: anthropic/claude-opus-4

  researcher:
    operator: perplexity
    models:
      default: sonar-pro

  secretary:
    operator: opencode
    operator_settings:
      provider: google
    models:
      default: google/gemini-2.0-flash

# Global API keys (unchanged)
api_keys:
  openrouter: sk-or-...
  anthropic: sk-ant-...
  google: ...
```

### Benefits

1. **Clear hierarchy** - Component → Operator → Settings → Models
2. **Component isolation** - Each component can use different operator
3. **Operator flexibility** - Operator-specific settings supported
4. **Model strategies** - Different models for different task types
5. **Extensible** - Easy to add new components/operators

---

## 5. UI/UX Flow Redesign

### Proposed Main Menu

```
🥷 NINJA CONFIGURATION MANAGER

Current Configuration:
  Coder:      opencode → anthropic → claude-sonnet-4-5
  Researcher: perplexity → sonar-pro
  Secretary:  opencode → google → gemini-2.0-flash

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Setup & Quick Start
  ├─ 🎯 Coder Setup        Configure coding assistant
  ├─ 🔍 Researcher Setup   Configure research engine
  ├─ 📋 Secretary Setup    Configure secretary

  API Keys & Authentication
  ├─ 🔑 API Key Management
  └─ 🌐 OpenCode Providers

  Advanced
  ├─ ⚙️  System Settings
  ├─ 📊 Performance Tuning
  └─ 🗑️  Reset Configuration

  📋 Configuration Overview
  🚪 Exit
```

### Component Setup Flow (Example: Coder)

```
🎯 CODER SETUP

Step 1: Select Operator
  ► OpenCode        Multi-provider CLI (75+ models)
    Aider           OpenRouter-based CLI
    Claude Code     Anthropic's official CLI
    Gemini CLI      Google native CLI

Step 2: Configure Operator (OpenCode)
  Provider:     ► Anthropic
  Provider Routing:
    Order:      [anthropic, openrouter]
    Fallbacks:  ✓ Enabled

Step 3: Select Models
  Default Model:  ► anthropic/claude-sonnet-4-5
  Quick Tasks:    ► anthropic/claude-haiku-4-5
  Heavy Tasks:    ► anthropic/claude-opus-4

✅ CODER SETUP COMPLETE
```

---

## 6. OpenCode Modes & Provider Settings

### From OpenCode Documentation

**Provider Routing:**
```json
{
  "provider": {
    "order": ["baseten", "anthropic"],
    "allow_fallbacks": true
  }
}
```

**Custom Models:**
```json
{
  "models": {
    "my-custom-model": {
      "options": {...}
    }
  }
}
```

### Required UI Components

1. **Provider Order Selector**
   - Multi-select list
   - Drag-to-reorder
   - Shows available providers

2. **Fallback Toggle**
   - Enable/disable fallbacks
   - Explanation text

3. **Custom Model Entry**
   - Model name input
   - Provider selection
   - Options (JSON editor?)

---

## 7. Implementation Challenges

### Challenge 1: Configuration File Format

**Options:**
- Keep `.env` format (flat) + add hierarchy via naming
- Switch to JSON/YAML (hierarchical)
- Hybrid: `.env` for backwards compat + `.ninja-config.json` for new structure

**Recommendation:** Hybrid approach
- Keep `~/.ninja-mcp.env` for backwards compatibility
- Add `~/.ninja-mcp.json` for hierarchical config
- ConfigManager reads both, JSON takes precedence

### Challenge 2: Backwards Compatibility

**Existing configs:**
```bash
NINJA_CODE_BIN=opencode
NINJA_CODER_MODEL=anthropic/claude-sonnet-4-5
```

**Migration strategy:**
```python
def migrate_config():
    """Migrate flat .env to hierarchical .json"""
    env_config = read_env()

    components = {
        "coder": {
            "operator": env_config.get("NINJA_CODE_BIN", "opencode"),
            "models": {
                "default": env_config.get("NINJA_CODER_MODEL"),
                "quick": env_config.get("NINJA_MODEL_QUICK"),
                "heavy": env_config.get("NINJA_MODEL_SEQUENTIAL"),
            }
        }
    }

    write_json(components)
```

### Challenge 3: OpenCode Config Integration

OpenCode uses `~/.local/share/opencode/opencode.json` for its config.

**Options:**
1. Read OpenCode config, show in UI (read-only)
2. Write to OpenCode config from UI
3. Keep separate, document manual sync

**Recommendation:** Option 2 - Write to OpenCode config
- Ninja UI becomes source of truth
- Writes to both `~/.ninja-mcp.json` AND `~/.local/share/opencode/opencode.json`
- Keeps configs in sync

---

## 8. Files to Refactor

### Files to Consolidate

1. **`interactive_configurator.py`** (1800+ lines)
   - Split into modules:
     - `ui_main_menu.py` - Main menu
     - `ui_component_setup.py` - Component setup flows
     - `ui_operator_config.py` - Operator-specific settings
     - `ui_model_selector.py` - Model selection UI

2. **`model_selector.py`**
   - Keep operator/model detection logic
   - Extract UI code to `ui_model_selector.py`

3. **`config_manager.py`**
   - Add JSON config support
   - Add migration utilities
   - Keep env file support

### New Files to Create

1. **`config_schema.py`** - Pydantic models for config validation
2. **`config_migrator.py`** - Migrate old configs to new format
3. **`opencode_integration.py`** - Read/write OpenCode configs
4. **`ui_base.py`** - Shared UI components (InquirerPy wrappers)

---

## Next Steps

1. ✅ Complete this analysis
2. ⏳ Create Pydantic schemas for new config structure
3. ⏳ Implement hierarchical ConfigManager
4. ⏳ Build migration utilities
5. ⏳ Refactor UI components
6. ⏳ Add OpenCode provider settings UI
7. ⏳ Test migration with existing configs
8. ⏳ Update documentation

---

## Questions for User

1. **JSON vs YAML?** Which format for hierarchical config?
2. **Migration timing?** Automatic on first run, or manual command?
3. **OpenCode sync?** Should we write to OpenCode's config file?
4. **Backwards compat?** Keep reading .env forever, or deprecate after migration?

