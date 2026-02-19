import pytest


"""
Test for OpenCode corruption detection and auto-fix.

This tests the fix for the bug where OpenCode writes Python list literals
instead of actual code content during sequential/parallel execution.
"""

import tempfile
from pathlib import Path

from ninja_coder.driver import NinjaConfig
from ninja_coder.strategies.opencode_strategy import OpenCodeStrategy


def test_corruption_detection_and_fix():
    """Test that corrupted files (Python list literals) are detected and fixed."""
    # Create a temporary file with corrupted content (Python list literal)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        corrupted_file = tmpdir_path / "test_corrupted.py"

        # Write corrupted content (what OpenCode bug produces)
        corrupted_content = """[
    'def hello():\\n    "',
    '\\n    Say hello.\\n    "',
    "\\n    return 'Hello, World!'",
]"""
        corrupted_file.write_text(corrupted_content)

        # Verify file is corrupted
        content_before = corrupted_file.read_text()
        assert content_before.strip().startswith('['), "File should start with ["

        # Create strategy and parse output with the corrupted file in touched_paths
        config = NinjaConfig.from_env()
        strategy = OpenCodeStrategy("opencode", config)

        # Simulate OpenCode output that mentions the file
        stdout = f"| Write {corrupted_file.name}\n\nTask completed."
        stderr = ""
        exit_code = 0

        # Parse output - this should detect and fix the corruption
        result = strategy.parse_output(
            stdout, stderr, exit_code, repo_root=str(tmpdir_path)
        )

        # Verify the result notes mention corruption
        assert result.success, "Should still be marked as success"
        assert "CORRUPTION DETECTED & AUTO-FIXED" in result.notes, \
            "Should mention corruption was fixed"
        assert "1 file(s)" in result.notes, \
            "Should mention number of files fixed"

        # Verify file was fixed
        content_after = corrupted_file.read_text()
        assert not content_after.strip().startswith('['), \
            "File should no longer start with ["

        # Verify content was properly joined
        expected_content = """def hello():
    "
    Say hello.
    "
    return 'Hello, World!'"""
        assert content_after == expected_content, \
            f"Content should be joined correctly.\nExpected:\n{expected_content}\n\nGot:\n{content_after}"


def test_no_false_positives():
    """Test that normal Python files are not incorrectly flagged as corrupted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        normal_file = tmpdir_path / "test_normal.py"

        # Write normal Python content with a list
        normal_content = """def get_items():
    return [
        "item1",
        "item2",
    ]
"""
        normal_file.write_text(normal_content)

        # Create strategy and parse output
        config = NinjaConfig.from_env()
        strategy = OpenCodeStrategy("opencode", config)

        stdout = f"| Write {normal_file.name}\n\nTask completed."
        stderr = ""
        exit_code = 0

        # Parse output
        result = strategy.parse_output(
            stdout, stderr, exit_code, repo_root=str(tmpdir_path)
        )

        # Verify no corruption was detected
        assert result.success
        assert "CORRUPTION DETECTED" not in (result.notes or ""), \
            "Should not flag normal Python files as corrupted"

        # Verify file was not modified
        content_after = normal_file.read_text()
        assert content_after == normal_content, \
            "Normal file should not be modified"


def test_corruption_with_absolute_path():
    """Test corruption fix works with absolute file paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        corrupted_file = tmpdir_path / "test_abs.py"

        # Write corrupted content
        corrupted_content = """[
    'x = ',
    '10',
]"""
        corrupted_file.write_text(corrupted_content)

        # Create strategy
        config = NinjaConfig.from_env()
        strategy = OpenCodeStrategy("opencode", config)

        # Use absolute path in output
        stdout = f"| Write {corrupted_file}\n\nTask completed."
        stderr = ""
        exit_code = 0

        # Parse without repo_root (absolute path should still work)
        result = strategy.parse_output(stdout, stderr, exit_code, repo_root=None)

        # Verify corruption was detected and fixed
        assert "CORRUPTION DETECTED & AUTO-FIXED" in result.notes

        # Verify file content
        content_after = corrupted_file.read_text()
        assert content_after == "x = 10", f"Got: {content_after}"
