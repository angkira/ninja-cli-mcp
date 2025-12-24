# Ninja MCP Refactoring Plan

## Completed Steps

1. ✅ Created `src/ninja_common/` with shared infrastructure:
   - `__init__.py` - Module exports
   - `logging_utils.py` - Centralized logging
   - `metrics.py` - Token tracking and cost analysis
   - `path_utils.py` - Secure path handling
   - `security.py` - Rate limiting, validation, monitoring
   - `daemon.py` - Daemon management

2. ✅ Created `src/ninja_coder/` module structure:
   - `__init__.py` - Module exports
   - `models.py` - Coder-specific data models

## Next Steps

### Phase 1: Complete Coder Module (Priority 1)
- [ ] Move `src/ninja_cli_mcp/tools.py` → `src/ninja_coder/tools.py`
- [ ] Move `src/ninja_cli_mcp/ninja_driver.py` → `src/ninja_coder/driver.py`
- [ ] Move `src/ninja_cli_mcp/server.py` → `src/ninja_coder/server.py`
- [ ] Update imports to use `ninja_common` and `ninja_coder`
- [ ] Create `src/ninja_coder/cli.py` for coder-specific CLI commands

### Phase 2: Create Researcher Module (Priority 2)
- [ ] Create `src/ninja_researcher/__init__.py`
- [ ] Create `src/ninja_researcher/models.py` - Research-specific models
- [ ] Create `src/ninja_researcher/search_providers.py` - Tavily, DuckDuckGo integration
- [ ] Create `src/ninja_researcher/tools.py` - Research tools
- [ ] Create `src/ninja_researcher/server.py` - Researcher MCP server
- [ ] Create `src/ninja_researcher/report_generator.py` - Parallel report generation

### Phase 3: Create Secretary Module (Priority 3)
- [ ] Create `src/ninja_secretary/__init__.py`
- [ ] Create `src/ninja_secretary/models.py` - Secretary-specific models
- [ ] Create `src/ninja_secretary/codebase_explorer.py` - Code analysis with tree-sitter
- [ ] Create `src/ninja_secretary/session_protocol.py` - Session tracking
- [ ] Create `src/ninja_secretary/doc_manager.py` - Documentation CRUD
- [ ] Create `src/ninja_secretary/tools.py` - Secretary tools
- [ ] Create `src/ninja_secretary/server.py` - Secretary MCP server

### Phase 4: Update Configuration (Priority 1)
- [ ] Update `pyproject.toml` with new module structure
- [ ] Create module-specific extras: `[coder]`, `[researcher]`, `[secretary]`
- [ ] Add dependencies for each module
- [ ] Update entry points for each module

### Phase 5: Update Scripts (Priority 2)
- [ ] Update `scripts/install_interactive.sh` for multi-module selection
- [ ] Create `scripts/daemon/` directory with daemon management scripts
- [ ] Update IDE integration scripts for multiple modules
- [ ] Create module-specific run scripts

### Phase 6: Update Tests (Priority 2)
- [ ] Move tests to module-specific directories
- [ ] Update test imports
- [ ] Add tests for new modules
- [ ] Update CI/CD configuration

### Phase 7: Documentation (Priority 3)
- [ ] Update README.md with new architecture
- [ ] Create ARCHITECTURE.md (already provided in previous response)
- [ ] Create module-specific documentation
- [ ] Update CONTRIBUTING.md

## File Migration Map

### From `src/ninja_cli_mcp/` to `src/ninja_coder/`:
- `tools.py` → `tools.py` (update imports)
- `ninja_driver.py` → `driver.py` (rename)
- `server.py` → `server.py` (update imports)
- `models.py` → `models.py` (already created)

### From `src/ninja_cli_mcp/` to `src/ninja_common/`:
- `logging_utils.py` → `logging_utils.py` (already created)
- `metrics.py` → `metrics.py` (already created)
- `path_utils.py` → `path_utils.py` (already created)
- `security.py` → `security.py` (already created)

### To be deprecated:
- `src/ninja_cli_mcp/` (entire directory after migration)

## Import Updates Required

All files importing from `ninja_cli_mcp` need to update to:
- `from ninja_common import ...` for shared utilities
- `from ninja_coder import ...` for coder-specific code
- `from ninja_researcher import ...` for researcher code
- `from ninja_secretary import ...` for secretary code

## Configuration Changes

### pyproject.toml
```toml
[project.optional-dependencies]
coder = [
    "gitpython>=3.1.0",
]
researcher = [
    "tavily-python>=0.3.0",
    "duckduckgo-search>=6.0.0",
    "beautifulsoup4>=4.12.0",
]
secretary = [
    "tree-sitter>=0.21.0",
    "tree-sitter-python>=0.21.0",
    "pygments>=2.17.0",
]
all = [
    "ninja-mcp[coder,researcher,secretary]",
]

[project.scripts]
ninja-coder = "ninja_coder.server:run"
ninja-researcher = "ninja_researcher.server:run"
ninja-secretary = "ninja_secretary.server:run"
ninja-daemon = "ninja_common.daemon:main"
```

## Testing Strategy

1. **Unit Tests**: Test each module independently
2. **Integration Tests**: Test module interactions
3. **E2E Tests**: Test complete workflows
4. **Backward Compatibility**: Ensure old code still works during migration

## Rollout Plan

1. **Week 1**: Complete Coder module refactoring
2. **Week 2**: Implement Researcher module
3. **Week 3**: Implement Secretary module
4. **Week 4**: Update documentation and scripts
5. **Week 5**: Testing and bug fixes
6. **Week 6**: Release v0.2.0

## Breaking Changes

- Module names changed from `ninja_cli_mcp` to `ninja_coder`, `ninja_researcher`, `ninja_secretary`
- Tool names prefixed with module name (e.g., `ninja_quick_task` → `coder_quick_task`)
- Separate MCP servers for each module
- New configuration structure

## Migration Guide for Users

1. Update IDE configurations to use new module names
2. Update environment variables (see configs/)
3. Re-run installer: `./scripts/install_interactive.sh`
4. Update any scripts calling MCP tools

## Questions to Resolve

1. Should we maintain backward compatibility with old `ninja_cli_mcp` package?
2. What's the migration path for existing users?
3. Should we version the MCP protocol separately?
4. How do we handle shared state between modules?
