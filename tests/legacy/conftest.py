"""Legacy tests conftest - skip all tests in this directory."""

import pytest


# Skip all tests in this directory - they reference the old ninja_cli_mcp package
# which was refactored into separate modules (ninja_coder, ninja_researcher, etc.)
collect_ignore_glob = ["test_*.py"]


def pytest_collection_modifyitems(config, items):
    """Skip all tests in the legacy directory."""
    skip_legacy = pytest.mark.skip(reason="Legacy tests - references old ninja_cli_mcp package")
    for item in items:
        if "legacy" in str(item.fspath):
            item.add_marker(skip_legacy)
