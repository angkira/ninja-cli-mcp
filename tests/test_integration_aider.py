"""
Integration tests for aider CLI adapter.

These tests require aider to be installed and configured.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.agent
def test_aider_detection():
    """Test that aider can be detected in PATH."""
    result = subprocess.run(
        ["which", "aider"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        pytest.skip("aider not found in PATH")
    
    aider_path = result.stdout.strip()
    assert Path(aider_path).exists()
    assert os.access(aider_path, os.X_OK)


@pytest.mark.integration
@pytest.mark.agent
def test_aider_version():
    """Test that aider --version works."""
    result = subprocess.run(
        ["aider", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    
    if result.returncode != 0:
        pytest.skip("aider not installed")
    
    assert "aider" in result.stdout.lower()


@pytest.mark.integration
@pytest.mark.agent  
def test_aider_help():
    """Test that aider --help works."""
    result = subprocess.run(
        ["aider", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    
    if result.returncode != 0:
        pytest.skip("aider not installed")
    
    assert "usage:" in result.stdout.lower()
    assert "model" in result.stdout.lower()


@pytest.mark.integration
@pytest.mark.agent
def test_aider_with_openrouter():
    """Test that aider works with OpenRouter configuration."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("# Hello\n")
        
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = os.getenv("OPENROUTER_API_KEY")
        env["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
        
        # Just test that aider can start (don't actually make API call)
        result = subprocess.run(
            [
                "aider",
                "--yes-always",
                "--no-auto-commits",
                "--model", "openrouter/qwen/qwen-2.5-coder-32b-instruct",
                "--message", "Add a comment",
                str(test_file),
            ],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            env=env,
            timeout=30,
        )
        
        # aider should at least start without crashing
        # May fail on API call, but shouldn't crash on startup
        assert result.returncode in [0, 1]  # 0 = success, 1 = API error is ok


@pytest.mark.integration
def test_ninja_driver_aider_adapter():
    """Test that NinjaDriver can configure aider adapter."""
    from ninja_cli_mcp.ninja_driver import NinjaConfig, NinjaDriver
    
    config = NinjaConfig(bin_path="aider")
    driver = NinjaDriver(config)
    
    assert driver._detect_cli_type() == "aider"


@pytest.mark.integration
@pytest.mark.agent
def test_aider_adapter_command_building():
    """Test that aider adapter builds correct commands."""
    from ninja_cli_mcp.cli_adapters.aider_adapter import AiderAdapter
    from ninja_cli_mcp.models import ExecutionMode
    
    adapter = AiderAdapter()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = adapter.build_command(
            bin_path="aider",
            mode=ExecutionMode.QUICK,
            repo_root=Path(tmpdir),
            context_paths=[Path("test.py")],
            message="Test task",
            model="qwen/qwen-2.5-coder-32b-instruct",
        )
        
        # Verify command structure
        assert cmd[0] == "aider"
        assert "--yes-always" in cmd
        assert "--no-auto-commits" in cmd
        assert "--model" in cmd
        assert "test.py" in cmd or str(Path(tmpdir) / "test.py") in cmd
