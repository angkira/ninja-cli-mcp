"""
Tests for activity-based timeout in NinjaDriver.

Tests the smart timeout functionality that only triggers after 20 seconds
of no output activity, while still respecting maximum timeout as a safety net.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ninja_coder.driver import NinjaConfig, NinjaDriver


@pytest.fixture
def driver(tmp_path, monkeypatch):
    """Create NinjaDriver instance with temp cache."""
    monkeypatch.setattr(
        "ninja_common.path_utils.get_cache_dir",
        lambda: tmp_path / "cache",
    )

    config = NinjaConfig(
        bin_path="aider",
        model="anthropic/claude-haiku-4.5",
        openai_api_key="test-key",
    )
    return NinjaDriver(config)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Test is flaky with mocking subprocess - needs investigation")
async def test_activity_based_timeout_no_output(driver, tmp_path, monkeypatch):
    """Test that timeout triggers after 20s of no output (inactivity)."""

    # Track time when process was killed
    process_killed = False
    kill_time = None
    start_time = None

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that produces no output."""
        nonlocal start_time
        start_time = asyncio.get_running_loop().time()

        process = MagicMock()
        process.returncode = 0

        # Create mock streams that never produce data
        mock_stdout = AsyncMock()
        mock_stderr = AsyncMock()

        # read() will wait forever (simulating hung process)
        async def never_read(*args, **kwargs):
            await asyncio.sleep(100)  # Sleep long enough
            return b""

        mock_stdout.read = never_read
        mock_stderr.read = never_read

        process.stdout = mock_stdout
        process.stderr = mock_stderr

        def kill():
            nonlocal process_killed, kill_time
            process_killed = True
            kill_time = asyncio.get_running_loop().time()

        process.kill = kill

        async def wait():
            pass

        process.wait = wait

        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Test inactivity timeout",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    result = await driver.execute_async(
        repo_root=str(tmp_path),
        step_id="test-inactivity",
        instruction=instruction,
        timeout_sec=300,  # Max timeout 5 minutes (should not be reached)
        task_type="quick",
    )

    # Verify process was killed due to inactivity
    assert process_killed is True
    assert result.success is False
    assert "timed out" in result.summary.lower()
    assert "activity" in result.notes.lower()
    assert result.exit_code == -1

    # Verify it was killed around 20s (inactivity timeout), not 300s (max timeout)
    if kill_time and start_time:
        elapsed = kill_time - start_time
        # Should timeout between 20-25s (allowing some margin for processing)
        assert 19 < elapsed < 30, f"Expected timeout around 20s, got {elapsed:.1f}s"


@pytest.mark.asyncio
async def test_activity_based_timeout_with_periodic_output(driver, tmp_path, monkeypatch):
    """Test that timeout does NOT trigger when process produces periodic output."""

    process_killed = False
    chunks_sent = 0

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that produces output every 5 seconds."""
        nonlocal chunks_sent

        process = MagicMock()
        process.returncode = 0

        # Create mock streams that produce data periodically
        mock_stdout = AsyncMock()
        mock_stderr = AsyncMock()

        start_time = asyncio.get_running_loop().time()

        # Simulate periodic output (every 1s to stay well under 20s inactivity timeout)
        async def periodic_read(*args, **kwargs):
            nonlocal chunks_sent
            elapsed = asyncio.get_running_loop().time() - start_time

            # Return a chunk every 1 second
            expected_chunks = int(elapsed)
            if chunks_sent < expected_chunks and chunks_sent < 10:
                chunks_sent += 1
                await asyncio.sleep(0.01)  # Tiny delay to simulate real I/O
                return b"Processing... chunk " + str(chunks_sent).encode()
            elif chunks_sent >= 10:
                await asyncio.sleep(0.01)
                return b""  # EOF after 10 chunks
            else:
                # Not time for next chunk yet, wait a bit
                await asyncio.sleep(0.1)
                # Recursion will be cancelled by wait_for, that's fine
                return await periodic_read(*args, **kwargs)

        mock_stdout.read = periodic_read

        async def stderr_read(*args, **kwargs):
            # Stderr has no data, return EOF once stdout is done
            if chunks_sent >= 10:
                await asyncio.sleep(0.01)
                return b""  # EOF
            else:
                # Not done yet, wait
                await asyncio.sleep(0.1)
                # Will be cancelled and retried
                return await stderr_read(*args, **kwargs)

        mock_stderr.read = stderr_read

        process.stdout = mock_stdout
        process.stderr = mock_stderr

        def kill():
            nonlocal process_killed
            process_killed = True

        process.kill = kill

        async def wait():
            pass

        process.wait = wait

        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Test periodic output",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    result = await driver.execute_async(
        repo_root=str(tmp_path),
        step_id="test-periodic",
        instruction=instruction,
        timeout_sec=300,
        task_type="quick",
    )

    # Verify process completed successfully (not killed by inactivity timeout)
    assert process_killed is False
    assert result.success is True
    assert chunks_sent == 10  # All 10 chunks were sent


@pytest.mark.asyncio
async def test_activity_based_timeout_max_timeout_reached(driver, tmp_path, monkeypatch):
    """Test that maximum timeout is still enforced as a safety net."""

    process_killed = False
    chunks_sent = 0
    kill_time = None
    start_time = None

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that produces output continuously but takes too long overall."""
        nonlocal chunks_sent, start_time
        start_time = asyncio.get_running_loop().time()

        process = MagicMock()
        process.returncode = 0

        # Create mock streams that produce data every 1s (well within inactivity timeout)
        mock_stdout = AsyncMock()
        mock_stderr = AsyncMock()

        async def continuous_read(*args, **kwargs):
            nonlocal chunks_sent
            await asyncio.sleep(1)  # Output every 1s (no inactivity)
            chunks_sent += 1
            # Keep producing output indefinitely
            return b"Processing... chunk " + str(chunks_sent).encode()

        mock_stdout.read = continuous_read

        async def stderr_read(*args, **kwargs):
            await asyncio.sleep(100)
            return b""

        mock_stderr.read = stderr_read

        process.stdout = mock_stdout
        process.stderr = mock_stderr

        def kill():
            nonlocal process_killed, kill_time
            process_killed = True
            kill_time = asyncio.get_running_loop().time()

        process.kill = kill

        async def wait():
            pass

        process.wait = wait

        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Test max timeout",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    # Set a short max timeout (10s) to test it's enforced
    result = await driver.execute_async(
        repo_root=str(tmp_path),
        step_id="test-max-timeout",
        instruction=instruction,
        timeout_sec=10,  # Max timeout 10 seconds
        task_type="quick",
    )

    # Verify process was killed due to max timeout (not inactivity)
    assert process_killed is True
    assert result.success is False
    assert "timed out" in result.summary.lower()
    assert "maximum timeout" in result.notes.lower()
    assert result.exit_code == -1

    # Verify it was killed around 10s (max timeout), not 20s (inactivity timeout)
    if kill_time and start_time:
        elapsed = kill_time - start_time
        # Should timeout between 10-15s
        assert 9 < elapsed < 16, f"Expected timeout around 10s, got {elapsed:.1f}s"


@pytest.mark.asyncio
async def test_activity_based_timeout_normal_completion(driver, tmp_path, monkeypatch):
    """Test that normal completion works without any timeout."""

    process_killed = False

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that completes normally."""
        process = MagicMock()
        process.returncode = 0

        # Create mock streams
        mock_stdout = AsyncMock()
        mock_stderr = AsyncMock()

        # Simulate quick completion with some output
        read_count = [0]

        async def quick_read(*args, **kwargs):
            read_count[0] += 1
            if read_count[0] == 1:
                return b"Task completed successfully"
            else:
                return b""  # EOF

        mock_stdout.read = quick_read

        async def stderr_read(*args, **kwargs):
            return b""  # No stderr

        mock_stderr.read = stderr_read

        process.stdout = mock_stdout
        process.stderr = mock_stderr

        def kill():
            nonlocal process_killed
            process_killed = True

        process.kill = kill

        async def wait():
            pass

        process.wait = wait

        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Test normal completion",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    result = await driver.execute_async(
        repo_root=str(tmp_path),
        step_id="test-completion",
        instruction=instruction,
        timeout_sec=300,
        task_type="quick",
    )

    # Verify process completed successfully (not killed)
    assert process_killed is False
    assert result.success is True
    assert "completed successfully" in result.stdout.lower()


@pytest.mark.asyncio
async def test_activity_based_timeout_stderr_activity(driver, tmp_path, monkeypatch):
    """Test that stderr activity also resets the inactivity timer."""

    process_killed = False
    stderr_chunks_sent = 0

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that produces output on stderr every 5 seconds."""
        nonlocal stderr_chunks_sent

        process = MagicMock()
        process.returncode = 0

        # Create mock streams
        mock_stdout = AsyncMock()
        mock_stderr = AsyncMock()

        # stdout has no data
        start_time = asyncio.get_running_loop().time()

        async def stdout_read(*args, **kwargs):
            # Stdout has no data, return EOF once stderr is done
            if stderr_chunks_sent >= 10:
                await asyncio.sleep(0.01)
                return b""  # EOF
            else:
                # Not done yet, wait
                await asyncio.sleep(0.1)
                return await stdout_read(*args, **kwargs)

        mock_stdout.read = stdout_read

        # stderr produces data periodically (every 1s to stay under 20s timeout)
        async def periodic_stderr_read(*args, **kwargs):
            nonlocal stderr_chunks_sent
            elapsed = asyncio.get_running_loop().time() - start_time

            # Return a chunk every 1 second
            expected_chunks = int(elapsed)
            if stderr_chunks_sent < expected_chunks and stderr_chunks_sent < 10:
                stderr_chunks_sent += 1
                await asyncio.sleep(0.01)
                return b"Warning: processing... " + str(stderr_chunks_sent).encode()
            elif stderr_chunks_sent >= 10:
                await asyncio.sleep(0.01)
                return b""  # EOF
            else:
                # Not time yet, wait
                await asyncio.sleep(0.1)
                return await periodic_stderr_read(*args, **kwargs)

        mock_stderr.read = periodic_stderr_read

        process.stdout = mock_stdout
        process.stderr = mock_stderr

        def kill():
            nonlocal process_killed
            process_killed = True

        process.kill = kill

        async def wait():
            pass

        process.wait = wait

        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Test stderr activity",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    result = await driver.execute_async(
        repo_root=str(tmp_path),
        step_id="test-stderr",
        instruction=instruction,
        timeout_sec=300,
        task_type="quick",
    )

    # Verify process completed successfully (stderr activity prevented timeout)
    assert process_killed is False
    assert result.success is True
    assert stderr_chunks_sent == 10


@pytest.mark.asyncio
async def test_activity_based_timeout_mixed_stdout_stderr(driver, tmp_path, monkeypatch):
    """Test that activity on either stdout or stderr resets the timer."""

    process_killed = False
    total_chunks = 0

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess with alternating stdout/stderr output."""
        nonlocal total_chunks

        process = MagicMock()
        process.returncode = 0

        mock_stdout = AsyncMock()
        mock_stderr = AsyncMock()

        stdout_count = [0]
        stderr_count = [0]
        start_time = asyncio.get_running_loop().time()

        # Alternating output (stay under 20s inactivity)
        async def stdout_read(*args, **kwargs):
            nonlocal total_chunks
            elapsed = asyncio.get_running_loop().time() - start_time

            # stdout produces every 2s: at t=2, 4, 6, 8, 10
            expected_chunks = int(elapsed / 2)
            if stdout_count[0] < expected_chunks and stdout_count[0] < 5:
                stdout_count[0] += 1
                total_chunks += 1
                await asyncio.sleep(0.01)
                return b"stdout chunk " + str(stdout_count[0]).encode()
            elif stdout_count[0] >= 5:
                await asyncio.sleep(0.01)
                return b""  # EOF
            else:
                await asyncio.sleep(0.1)
                return await stdout_read(*args, **kwargs)

        async def stderr_read(*args, **kwargs):
            nonlocal total_chunks
            elapsed = asyncio.get_running_loop().time() - start_time

            # stderr produces every 3s: at t=3, 6, 9, 12, 15
            expected_chunks = int(elapsed / 3)
            if stderr_count[0] < expected_chunks and stderr_count[0] < 5:
                stderr_count[0] += 1
                total_chunks += 1
                await asyncio.sleep(0.01)
                return b"stderr chunk " + str(stderr_count[0]).encode()
            elif stderr_count[0] >= 5:
                await asyncio.sleep(0.01)
                return b""  # EOF
            else:
                await asyncio.sleep(0.1)
                return await stderr_read(*args, **kwargs)

        mock_stdout.read = stdout_read
        mock_stderr.read = stderr_read

        process.stdout = mock_stdout
        process.stderr = mock_stderr

        def kill():
            nonlocal process_killed
            process_killed = True

        process.kill = kill

        async def wait():
            pass

        process.wait = wait

        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Test mixed output",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    result = await driver.execute_async(
        repo_root=str(tmp_path),
        step_id="test-mixed",
        instruction=instruction,
        timeout_sec=300,
        task_type="quick",
    )

    # Verify process completed successfully
    assert process_killed is False
    assert result.success is True
    assert total_chunks >= 8  # Should have received chunks from both streams


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
