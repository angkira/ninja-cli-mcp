"""Comprehensive End-to-End (E2E) and Smoke tests for autonomous ninja-agent features.

Covers:
1. Live CLI invocations via subprocess:
   - run-and-diagnose (success and failure scenarios, root cause diagnosis)
   - pipeline (multi-step sequential execution, timing, fail-fast behavior)
   - distill-logs (real log files, pattern clustering, traceback isolation)
   - --json output flags for all commands
2. Live MCP Server end-to-end communication:
   - In-process AgentToolExecutor verification
   - Live stdio JSON-RPC MCP ClientSession calling agent_run_and_diagnose,
     agent_exec_pipeline, agent_distill_logs
3. Real-world smoke scenarios:
   - Linting check (ruff check) via run-and-diagnose
   - Running targeted unit tests via run-and-diagnose
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from ninja_agent import cli
from ninja_agent.models import (
    AgentDistillLogsRequest,
    AgentExecPipelineRequest,
    AgentRunAndDiagnoseRequest,
    PipelineStep,
)
from ninja_agent.tools import AgentToolExecutor


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_cli_subprocess(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Execute ninja-agent CLI via python -m ninja_agent.cli or ninja-agent binary."""
    # Run using sys.executable -m ninja_agent.cli to guarantee virtualenv interpreter
    cmd = [sys.executable, "-m", "ninja_agent.cli", *args]
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_ninja_agent_bin(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Execute the ninja-agent executable directly."""
    # Find ninja-agent in same bin directory as python interpreter
    bin_path = Path(sys.executable).parent / "ninja-agent"
    cmd = [str(bin_path) if bin_path.exists() else "ninja-agent", *args]
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


# ==============================================================================
# 1. Live CLI Invocations (Subprocess)
# ==============================================================================


def test_cli_run_and_diagnose_success_live(tmp_path):
    """Test live CLI execution of a successful command."""
    proc = _run_cli_subprocess(
        ["run-and-diagnose", "--command", f"{sys.executable} -c 'print(\"hello e2e\")'"],
        cwd=tmp_path,
    )
    assert proc.returncode == 0
    assert "hello e2e" in proc.stdout or "OK" in proc.stdout or "Command finished" in proc.stdout

    # Test direct ninja-agent binary invocation
    proc_bin = _run_ninja_agent_bin(
        ["run-and-diagnose", "--command", f"{sys.executable} -c 'print(\"hello direct bin\")'"],
        cwd=tmp_path,
    )
    assert proc_bin.returncode == 0


def test_cli_run_and_diagnose_pytest_success_live(tmp_path):
    """Test live CLI execution of pytest passing scenario."""
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(
        "def test_ok():\n"
        "    assert 1 + 1 == 2\n"
    )
    proc = _run_cli_subprocess(
        [
            "run-and-diagnose",
            "--command",
            f"{sys.executable} -m pytest {test_file}",
            "--repo-root",
            str(tmp_path),
        ],
        cwd=tmp_path,
    )
    assert proc.returncode == 0
    assert "OK, 1 passed" in proc.stdout


def test_cli_run_and_diagnose_failure_and_root_cause_live(tmp_path):
    """Test live CLI execution of a failing command, verifying diagnosis and error extraction."""
    # Python assertion failure
    proc = _run_cli_subprocess(
        ["run-and-diagnose", "--command", f"{sys.executable} -c 'assert 1 == 2, \"mismatch error\"'"],
        cwd=tmp_path,
    )
    assert proc.returncode == 1
    assert "AssertionError: mismatch error" in proc.stdout or "mismatch error" in proc.stdout

    # Pytest failure with traceback diagnosis
    test_file = tmp_path / "test_failing.py"
    test_file.write_text(
        "def test_boom():\n"
        "    expected = 'apple'\n"
        "    actual = 'orange'\n"
        "    assert actual == expected, 'fruit mismatch'\n"
    )
    proc_pytest = _run_cli_subprocess(
        [
            "run-and-diagnose",
            "--command",
            f"{sys.executable} -m pytest {test_file}",
            "--repo-root",
            str(tmp_path),
        ],
        cwd=tmp_path,
    )
    assert proc_pytest.returncode == 1
    assert "Test run failed" in proc_pytest.stdout
    assert "fruit mismatch" in proc_pytest.stdout
    assert "Failures / Diagnostics" in proc_pytest.stdout


def test_cli_run_and_diagnose_json_live(tmp_path):
    """Test live CLI run-and-diagnose with --json flag."""
    test_file = tmp_path / "test_ok.py"
    test_file.write_text("def test_simple(): pass\n")

    proc = _run_cli_subprocess(
        [
            "run-and-diagnose",
            "--command",
            f"{sys.executable} -m pytest {test_file}",
            "--repo-root",
            str(tmp_path),
            "--json",
        ],
        cwd=tmp_path,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["success"] is True
    assert data["returncode"] == 0
    assert data["passed_count"] == 1
    assert data["failed_count"] == 0
    assert "condensed_output" in data
    assert isinstance(data["failures"], list)


def test_cli_pipeline_sequential_and_timing_live(tmp_path):
    """Test live multi-step pipeline execution and verification of timing and step output."""
    steps = [
        {"name": "step_one", "command": f"{sys.executable} -c 'print(\"step 1 completed\")'"},
        {"name": "step_two", "command": f"{sys.executable} -c 'print(\"step 2 completed\")'"},
    ]
    proc = _run_cli_subprocess(
        [
            "pipeline",
            "--steps",
            json.dumps(steps),
            "--repo-root",
            str(tmp_path),
        ],
        cwd=tmp_path,
    )
    assert proc.returncode == 0
    assert "[PASS] step_one" in proc.stdout
    assert "[PASS] step_two" in proc.stdout
    assert "2/2 steps succeeded" in proc.stdout


def test_cli_pipeline_fail_fast_live(tmp_path):
    """Test pipeline fail_fast behavior halting execution on failure."""
    steps = [
        {"name": "step_pass", "command": f"{sys.executable} -c 'print(\"pass\")'"},
        {"name": "step_fail", "command": f"{sys.executable} -c 'import sys; sys.exit(42)'"},
        {"name": "step_skipped", "command": f"{sys.executable} -c 'print(\"should not run\")'"},
    ]
    proc = _run_cli_subprocess(
        [
            "pipeline",
            "--steps",
            json.dumps(steps),
            "--fail-fast",
            "--repo-root",
            str(tmp_path),
        ],
        cwd=tmp_path,
    )
    assert proc.returncode == 1
    assert "[PASS] step_pass" in proc.stdout
    assert "[FAIL] step_fail" in proc.stdout
    assert "[SKIPPED]" in proc.stdout or "[SKIP]" in proc.stdout
    assert "Pipeline failed" in proc.stdout


def test_cli_pipeline_file_and_json_live(tmp_path):
    """Test pipeline passing a file path for --steps and receiving JSON output."""
    steps = [
        {"name": "file_step", "command": "echo 'file step ok'"},
    ]
    steps_file = tmp_path / "pipeline.json"
    steps_file.write_text(json.dumps(steps))

    proc = _run_cli_subprocess(
        [
            "pipeline",
            "--steps",
            str(steps_file),
            "--repo-root",
            str(tmp_path),
            "--json",
        ],
        cwd=tmp_path,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["success"] is True
    assert data["total_duration_seconds"] >= 0
    assert len(data["steps"]) == 1
    assert data["steps"][0]["name"] == "file_step"
    assert data["steps"][0]["success"] is True


def test_cli_distill_logs_real_files_and_json(tmp_path, monkeypatch):
    """Test live distill-logs with real log file containing repeated patterns and tracebacks."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    coder_log = logs_dir / "coder.log"

    sample_log_content = (
        "2026-09-16 12:00:01 [ERROR] Connection timed out to node 0x123abc\n"
        "2026-09-16 12:00:02 [ERROR] Connection timed out to node 0x456def\n"
        "2026-09-16 12:00:03 [ERROR] Connection timed out to node 0x789ghi\n"
        "2026-09-16 12:00:04 [INFO] Heartbeat received from host-1\n"
        "Traceback (most recent call last):\n"
        "  File 'service.py', line 42, in process\n"
        "    raise ConnectionResetError('socket dropped by peer')\n"
        "ConnectionResetError: socket dropped by peer\n"
    )
    coder_log.write_text(sample_log_content)

    # Point DaemonManager to tmp_path cache directory
    from ninja_common.daemon import DaemonManager

    def _custom_manager():
        return DaemonManager(cache_dir=tmp_path)

    monkeypatch.setattr("ninja_agent.runner.RunnerToolExecutor._get_daemon_manager", lambda self: _custom_manager())

    # Test in-process CLI to verify integration with mocked daemon cache directory
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["distill-logs", "--module", "coder", "--limit", "50", "--json"])
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert data["success"] is True
    assert data["total_lines_analyzed"] > 0
    assert len(data["clusters"]) >= 1
    assert len(data["isolated_errors"]) >= 1
    assert "ConnectionResetError: socket dropped by peer" in data["isolated_errors"][0]


# ==============================================================================
# 2. Live MCP Server End-to-End Communication
# ==============================================================================


@pytest.mark.asyncio
async def test_mcp_server_agent_tool_executor_live(tmp_path):
    """Verify live AgentToolExecutor running autonomous diagnostics and pipeline."""
    executor = AgentToolExecutor()

    # 1. run_and_diagnose
    run_req = AgentRunAndDiagnoseRequest(
        command=f"{sys.executable} -c 'print(\"agent tool exec\")'",
        repo_root=str(tmp_path),
    )
    diag_res = await executor.run_and_diagnose(run_req)
    assert diag_res.success is True
    assert diag_res.returncode == 0
    assert "completed" in diag_res.summary.lower() or "ok" in diag_res.summary.lower()

    # 2. exec_pipeline
    pipe_req = AgentExecPipelineRequest(
        steps=[
            PipelineStep(name="p1", command=f"{sys.executable} -c 'print(\"pipeline 1\")'"),
            PipelineStep(name="p2", command=f"{sys.executable} -c 'print(\"pipeline 2\")'"),
        ],
        repo_root=str(tmp_path),
        fail_fast=True,
    )
    pipe_res = await executor.exec_pipeline(pipe_req)
    assert pipe_res.success is True
    assert len(pipe_res.steps) == 2
    assert pipe_res.steps[0].success is True
    assert pipe_res.steps[1].success is True

    # 3. distill_logs
    distill_req = AgentDistillLogsRequest(module="coder", limit=20)
    distill_res = await executor.distill_logs(distill_req)
    assert distill_res.success is True
    assert isinstance(distill_res.clusters, list)
    assert isinstance(distill_res.isolated_errors, list)


@pytest.mark.asyncio
async def test_live_mcp_server_stdio_client_invocation():
    """Verify live stdio JSON-RPC MCP Server invocation for all three autonomous tools."""
    db_dir = tempfile.mkdtemp(prefix="ninja-agent-e2e-mcp-")
    env = {
        "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), str(REPO_ROOT / "src")]),
        "NINJA_LOG_LEVEL": "WARNING",
        "NINJA_TASKS_DB": str(Path(db_dir) / "tasks.db"),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ninja_agent.server"],
        env=env,
        cwd=str(REPO_ROOT),
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init_res = await session.initialize()
            assert init_res.serverInfo.name == "ninja-agent"

            # 1. agent_run_and_diagnose
            call_diag = await session.call_tool(
                "agent_run_and_diagnose",
                {
                    "command": f"{sys.executable} -c 'print(\"mcp rpc test\")'",
                    "repo_root": str(REPO_ROOT),
                },
            )
            assert call_diag.content
            diag_data = json.loads(call_diag.content[0].text)
            assert diag_data["success"] is True
            assert diag_data["returncode"] == 0

            # 2. agent_exec_pipeline
            call_pipe = await session.call_tool(
                "agent_exec_pipeline",
                {
                    "steps": [
                        {"name": "mcp_s1", "command": "echo 'step 1'"},
                        {"name": "mcp_s2", "command": "echo 'step 2'"},
                    ],
                    "repo_root": str(REPO_ROOT),
                    "fail_fast": True,
                },
            )
            assert call_pipe.content
            pipe_data = json.loads(call_pipe.content[0].text)
            assert pipe_data["success"] is True
            assert len(pipe_data["steps"]) == 2
            assert pipe_data["steps"][0]["name"] == "mcp_s1"

            # 3. agent_distill_logs
            call_distill = await session.call_tool(
                "agent_distill_logs",
                {
                    "limit": 10,
                },
            )
            assert call_distill.content
            distill_data = json.loads(call_distill.content[0].text)
            assert distill_data["success"] is True
            assert "clusters" in distill_data
            assert "isolated_errors" in distill_data


# ==============================================================================
# 3. Real-world Smoke Scenarios
# ==============================================================================


def test_smoke_run_and_diagnose_real_project_linting():
    """Smoke test running real ruff check on src/ninja_agent."""
    proc = _run_cli_subprocess(
        [
            "run-and-diagnose",
            "--command",
            "uv run ruff check src/ninja_agent",
            "--repo-root",
            str(REPO_ROOT),
            "--json",
        ],
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["success"] is True
    assert data["returncode"] == 0
    assert data["failures"] == []


def test_smoke_run_and_diagnose_real_project_unit_tests():
    """Smoke test running targeted real unit tests via run-and-diagnose."""
    proc = _run_cli_subprocess(
        [
            "run-and-diagnose",
            "--command",
            f"{sys.executable} -m pytest tests/test_agent.py -k test_executor_has_no_delegation_surface",
            "--repo-root",
            str(REPO_ROOT),
            "--json",
        ],
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["success"] is True
    assert data["returncode"] == 0
    assert data["passed_count"] >= 1
    assert data["failed_count"] == 0
