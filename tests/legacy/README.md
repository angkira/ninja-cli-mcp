# Legacy Tests

This directory contains tests from the old `ninja_cli_mcp` monolithic architecture that was refactored into separate modules:
- `ninja_coder` - Code writing functionality
- `ninja_researcher` - Research and web search functionality
- `ninja_secretary` - Documentation and analysis functionality
- `ninja_common` - Common utilities and configuration

These tests are preserved for reference but are not actively maintained or run in CI.

## Files

- `test_cli_adapter.py` - Old CLI adapter tests
- `test_e2e.py` - Old end-to-end tests
- `test_integration_*.py` - Old integration tests for various AI providers
- `test_metrics.py` - Old metrics tests
- `test_models.py` - Old model configuration tests
- `test_paths.py` - Old path utility tests
- `test_security.py` - Old security tests
- `test_tools.py` - Old tool tests
- `test_qwen_driver.py` - Old Qwen driver tests

## Migration

If you need to migrate any of these tests to the new architecture:
1. Identify the relevant new module (coder/researcher/secretary/common)
2. Update imports to use the new module structure
3. Adapt test logic to work with the new MCP server architecture
4. Move the updated test to the appropriate test directory
