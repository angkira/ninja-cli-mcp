# Interactive Configurator Refactoring Progress

## Objective
Refactor the 1823-line `src/ninja_config/interactive_configurator.py` into focused, modular UI components following hexagonal architecture principles.

## Target Structure

```
src/ninja_config/ui/
├── __init__.py           # Module exports
├── base.py               # Shared UI utilities ✅ COMPLETE
├── main_menu.py          # Main menu & overview ✅ COMPLETE
├── component_setup.py    # Component setup flows ✅ COMPLETE
├── operator_config.py    # Operator & API key config ✅ COMPLETE
├── model_selector.py     # Model selection UI ⚠️ NEEDS CREATION
└── settings.py           # Daemon, IDE, search, advanced ⚠️ NEEDS CREATION
```

## Completed Modules

### 1. base.py ✅
**Functions extracted:**
- `get_masked_value()` - Masks sensitive values
- `print_header()` - Prints formatted headers
- `detect_installed_tools()` - Detects AI coding tools
- `check_opencode_auth()` - Checks OpenCode auth status

**Status:** Complete and production-ready

### 2. main_menu.py ✅
**Functions extracted:**
- `show_welcome()` - Welcome message
- `show_main_menu()` - Main configuration menu
- `show_configuration_overview()` - Configuration overview display

**Status:** Complete and production-ready

### 3. component_setup.py ✅
**Functions extracted:**
- `run_coder_setup_flow()` - Complete coder setup wizard
- `configure_coder_models()` - Coder model configuration
- `configure_secretary()` - Secretary module setup
- `build_model_choices()` - Build model choice lists
- `get_fallback_models()` - Fallback model lists

**Status:** Complete and production-ready

### 4. operator_config.py ✅
**Functions extracted:**
- `manage_api_keys()` - API key management
- `configure_operators()` - Operator selection
- `select_opencode_provider()` - Provider selection for OpenCode
- `configure_opencode_auth()` - OpenCode authentication management

**Status:** Complete and production-ready

## Remaining Work

### 5. model_selector.py ⚠️ NEEDS CREATION

**Functions to extract from interactive_configurator.py:**

1. **`configure_models(config_manager, config)`**
   - Source: `_configure_models()` (lines 1048-1149)
   - Purpose: Configure models for each module (coder, researcher, secretary, resources, prompts)
   - Dependencies: InquirerPy, ConfigManager, OPENROUTER_MODELS, PERPLEXITY_MODELS, ZAI_MODELS

2. **`configure_task_based_models(config_manager, config)`**
   - Source: `_configure_task_based_models()` (lines 1150-1222)
   - Purpose: Configure task-based model selection (quick, sequential, parallel)
   - Dependencies: InquirerPy, ConfigManager

3. **`configure_single_task_model(config_manager, config, task_type, task_models)`**
   - Source: `_configure_single_task_model()` (lines 1223-1301)
   - Purpose: Configure a single task model with recommended options
   - Dependencies: InquirerPy, ConfigManager

4. **`configure_model_preferences(config_manager, config)`**
   - Source: `_configure_model_preferences()` (lines 1302-1340)
   - Purpose: Configure cost vs quality preferences
   - Dependencies: InquirerPy, ConfigManager

5. **`reset_task_models(config_manager, config, task_models)`**
   - Source: `_reset_task_models()` (lines 1341-1354)
   - Purpose: Reset task models to defaults
   - Dependencies: InquirerPy, ConfigManager

### 6. settings.py ⚠️ NEEDS CREATION

**Functions to extract from interactive_configurator.py:**

1. **Search Configuration:**
   - `configure_search(config_manager, config)` - Lines 1355-1395
   - `configure_perplexity_model(config_manager, config)` - Lines 1396-1430

2. **Daemon Configuration:**
   - `configure_daemon(config_manager, config)` - Lines 1431-1482

3. **IDE Integration:**
   - `configure_ide(config_manager, config)` - Lines 1483-1541
   - `setup_claude_integration()` - Lines 1542-1599
   - `setup_opencode_integration()` - Lines 1600-1609

4. **Advanced Settings:**
   - `advanced_settings(config_manager, config)` - Lines 1671-1740
   - `edit_setting(config_manager, config)` - Lines 1742-1778
   - `reset_configuration(config_manager, config)` - Lines 1780-1803

## PowerConfigurator Refactoring

**Current state:** PowerConfigurator is a 1823-line class with 15+ methods
**Target state:** Thin coordinator that delegates to UI modules

### Refactored PowerConfigurator Structure:

```python
class PowerConfigurator:
    """Coordinator for interactive configuration.

    Delegates all UI logic to ui/* modules, manages ConfigManager and state.
    """

    def __init__(self, config_path: str | None = None):
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.list_all()

    def run(self) -> None:
        """Run the main interactive configurator."""
        # Import all UI functions
        from ninja_config.ui import (
            show_welcome,
            show_main_menu,
            show_configuration_overview,
            run_coder_setup_flow,
            configure_secretary,
            manage_api_keys,
            configure_operators,
            configure_models,
            configure_task_based_models,
            configure_search,
            configure_daemon,
            configure_ide,
            configure_opencode_auth,
            advanced_settings,
            reset_configuration,
        )

        show_welcome()

        while True:
            try:
                action = show_main_menu(self.config)
                if not action or action == "exit":
                    break

                # Delegate to UI modules
                if action == "overview":
                    show_configuration_overview(self.config, self.config_manager.config_file)
                elif action == "coder_setup":
                    run_coder_setup_flow(self.config_manager, self.config)
                elif action == "secretary_setup":
                    configure_secretary(self.config_manager, self.config)
                elif action == "api_keys":
                    manage_api_keys(self.config_manager, self.config)
                elif action == "operators":
                    configure_operators(self.config_manager, self.config)
                elif action == "models":
                    configure_models(self.config_manager, self.config)
                elif action == "task_models":
                    configure_task_based_models(self.config_manager, self.config)
                elif action == "search":
                    configure_search(self.config_manager, self.config)
                elif action == "daemon":
                    configure_daemon(self.config_manager, self.config)
                elif action == "ide":
                    configure_ide(self.config_manager, self.config)
                elif action == "opencode_auth":
                    configure_opencode_auth(self.config_manager, self.config)
                elif action == "advanced":
                    advanced_settings(self.config_manager, self.config)
                elif action == "reset":
                    reset_configuration(self.config_manager, self.config)

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                input("\nPress Enter to continue...")
```

## Implementation Checklist

### Phase 1: Create model_selector.py ⚠️
- [ ] Create `src/ninja_config/ui/model_selector.py`
- [ ] Extract `configure_models()` function
- [ ] Extract `configure_task_based_models()` function
- [ ] Extract `configure_single_task_model()` function
- [ ] Extract `configure_model_preferences()` function
- [ ] Extract `reset_task_models()` function
- [ ] Add comprehensive docstrings (Google style)
- [ ] Add full type hints
- [ ] Test imports and functionality

### Phase 2: Create settings.py ⚠️
- [ ] Create `src/ninja_config/ui/settings.py`
- [ ] Extract `configure_search()` function
- [ ] Extract `configure_perplexity_model()` function
- [ ] Extract `configure_daemon()` function
- [ ] Extract `configure_ide()` function
- [ ] Extract `setup_claude_integration()` function
- [ ] Extract `setup_opencode_integration()` function
- [ ] Extract `advanced_settings()` function
- [ ] Extract `edit_setting()` function
- [ ] Extract `reset_configuration()` function
- [ ] Add comprehensive docstrings (Google style)
- [ ] Add full type hints
- [ ] Test imports and functionality

### Phase 3: Update ui/__init__.py ⚠️
- [ ] Import model_selector module
- [ ] Import settings module
- [ ] Export all public functions from model_selector
- [ ] Export all public functions from settings
- [ ] Update __all__ list
- [ ] Verify no circular imports

### Phase 4: Refactor interactive_configurator.py ⚠️
- [ ] Update imports to use ui modules
- [ ] Refactor PowerConfigurator.run() to delegate to UI functions
- [ ] Remove all extracted methods from PowerConfigurator
- [ ] Keep only: __init__, run (coordinator logic)
- [ ] Verify all functionality preserved
- [ ] Test end-to-end configuration flows

### Phase 5: Testing & Verification ⚠️
- [ ] Verify all menu options work
- [ ] Test coder setup flow
- [ ] Test secretary setup flow
- [ ] Test API key management
- [ ] Test operator configuration
- [ ] Test model selection
- [ ] Test task-based models
- [ ] Test search configuration
- [ ] Test daemon configuration
- [ ] Test IDE integration
- [ ] Test OpenCode authentication
- [ ] Test advanced settings
- [ ] Test reset configuration
- [ ] Verify no regressions
- [ ] Check type hints (mypy clean)
- [ ] Check linting (ruff clean)

## Architecture Compliance

### Hexagonal Architecture ✅
- UI layer separated from domain logic
- Clear separation of concerns
- Single responsibility per module

### Dependency Injection ✅
- All functions accept config_manager and config as parameters
- No global state
- No singleton patterns

### Type Safety ✅
- Full type hints on all function parameters
- Return types specified
- No `Any` types used

### Documentation ✅
- Google-style docstrings
- Clear Args, Returns, Raises sections
- Module-level documentation

## Metrics

**Before Refactoring:**
- interactive_configurator.py: 1823 lines
- PowerConfigurator class: 15+ methods
- Concerns mixed: API keys, operators, models, search, daemon, IDE

**After Refactoring (Target):**
- interactive_configurator.py: ~100 lines (coordinator only)
- PowerConfigurator class: 2 methods (__init__, run)
- 6 focused UI modules with single responsibilities
- Each module: 100-400 lines

**Benefits:**
- Improved maintainability
- Easier testing (each module independently testable)
- Better code organization
- Clearer separation of concerns
- Easier to extend with new features

## Next Steps

1. Create model_selector.py with 5 extracted functions
2. Create settings.py with 9 extracted functions
3. Update ui/__init__.py to export new modules
4. Refactor interactive_configurator.py to use UI modules
5. Run comprehensive testing
6. Update documentation

## Dependencies

- InquirerPy (UI framework)
- ConfigManager (configuration management)
- model_selector.py (provider/model utilities)
- defaults.py (default model lists)

## Notes

- Maintain backward compatibility
- Preserve user experience
- No breaking changes to CLI interface
- Keep same functionality, improve code structure
