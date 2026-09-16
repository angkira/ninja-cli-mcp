"""Tests for the autonomous ninja_agent CLI (exec-command, tail-logs, processes, jobs, analyze, review)."""

from __future__ import annotations

import json

import pytest

from ninja_agent import cli
from ninja_agent.models import (
    AgentAnalyzeResult,
    AgentDistillLogsResult,
    AgentExecCommandResult,
    AgentExecPipelineResult,
    AgentJobsOverviewResult,
    AgentProcessesResult,
    AgentReviewResult,
    AgentRunAndDiagnoseResult,
    AgentTailLogsResult,
    FailureDetail,
    LogCluster,
    PipelineStepResult,
)


class _FakeExecutor:
    """Fake AgentToolExecutor recording requests and returning canned results."""

    last_instance: _FakeExecutor | None = None

    def __init__(self, runner=None) -> None:
        self.exec_requests: list = []
        self.logs_requests: list = []
        self.processes_calls: int = 0
        self.jobs_requests: list = []
        self.analyze_requests: list = []
        self.review_requests: list = []
        self.run_and_diagnose_requests: list = []
        self.pipeline_requests: list = []
        self.distill_logs_requests: list = []
        self.run_and_diagnose_result: AgentRunAndDiagnoseResult | None = None
        self.pipeline_result: AgentExecPipelineResult | None = None
        self.distill_logs_result: AgentDistillLogsResult | None = None
        _FakeExecutor.last_instance = self

    async def exec_command(self, request, client_id: str = "default"):
        self.exec_requests.append(request)
        return AgentExecCommandResult(success=True, summary=f"ran {request.command}")

    async def tail_logs(self, request, client_id: str = "default"):
        self.logs_requests.append(request)
        return AgentTailLogsResult(success=True, summary="tailed", entries=["line1"])

    async def processes(self, request=None, client_id: str = "default"):
        self.processes_calls += 1
        return AgentProcessesResult(success=True, summary="1/1 running", daemons={})

    async def jobs_overview(self, request=None, client_id: str = "default"):
        self.jobs_requests.append(request)
        return AgentJobsOverviewResult(success=True, summary="0 jobs", jobs=[])

    async def analyze(self, request, client_id: str = "default"):
        self.analyze_requests.append(request)
        return AgentAnalyzeResult(
            success=True, summary="analyzed", findings=["f1"], touched_paths=[]
        )

    async def review(self, request, client_id: str = "default"):
        self.review_requests.append(request)
        return AgentReviewResult(success=True, findings=[], summary="clean")

    async def run_and_diagnose(self, request, client_id: str = "default"):
        self.run_and_diagnose_requests.append(request)
        if self.run_and_diagnose_result is not None:
            return self.run_and_diagnose_result
        return AgentRunAndDiagnoseResult(
            success=True,
            summary=f"ran and diagnosed {request.command}",
            returncode=0,
            passed_count=1,
            failed_count=0,
            failures=[],
            condensed_output="OK, 1 passed",
        )

    async def exec_pipeline(self, request, client_id: str = "default"):
        self.pipeline_requests.append(request)
        if self.pipeline_result is not None:
            return self.pipeline_result
        return AgentExecPipelineResult(
            success=True,
            summary="pipeline completed successfully",
            total_duration_seconds=0.5,
            steps=[
                PipelineStepResult(
                    command=s.command,
                    name=s.name,
                    success=True,
                    returncode=0,
                    duration_seconds=0.1,
                    skipped=False,
                    summary=f"step {s.name or s.command} ok",
                )
                for s in request.steps
            ],
        )

    async def distill_logs(self, request, client_id: str = "default"):
        self.distill_logs_requests.append(request)
        if self.distill_logs_result is not None:
            return self.distill_logs_result
        return AgentDistillLogsResult(
            success=True,
            summary="distilled logs",
            total_lines_analyzed=5,
            clusters=[
                LogCluster(
                    pattern="[ERROR] test cluster",
                    count=2,
                    level="ERROR",
                    sample_line="[ERROR] test cluster sample",
                )
            ],
            isolated_errors=["Traceback line 1\nTraceback line 2"],
            source="test",
        )


@pytest.fixture
def fake_executor(monkeypatch):
    fake = _FakeExecutor()
    monkeypatch.setattr(cli, "AgentToolExecutor", lambda *a, **k: fake)
    return fake


def test_exec_command_argparse_and_calls_executor(fake_executor, capsys):
    rc = cli.main(["exec-command", "--command", "git status", "--repo-root", "/r"])
    assert rc == 0
    req = fake_executor.exec_requests[0]
    assert req.command == "git status"
    assert req.repo_root == "/r"
    assert "git status" in capsys.readouterr().out


def test_exec_command_allow_write_flag(fake_executor):
    rc = cli.main(["exec-command", "--command", "mkdir sub", "--repo-root", "/r", "--allow-write"])
    assert rc == 0
    assert fake_executor.exec_requests[0].allow_write is True


def test_tail_logs_argparse(fake_executor):
    rc = cli.main(["tail-logs", "--module", "coder", "--level", "ERROR", "--limit", "10"])
    assert rc == 0
    req = fake_executor.logs_requests[0]
    assert req.module == "coder"
    assert req.level == "ERROR"
    assert req.limit == 10


def test_processes_argparse(fake_executor, capsys):
    rc = cli.main(["processes"])
    assert rc == 0
    assert fake_executor.processes_calls == 1
    assert "running" in capsys.readouterr().out


def test_jobs_overview_argparse(fake_executor):
    rc = cli.main(["jobs-overview", "--limit", "5"])
    assert rc == 0
    assert fake_executor.jobs_requests[0].limit == 5


def test_analyze_argparse_and_calls_executor(fake_executor, capsys):
    rc = cli.main(["analyze", "--repo-root", "/r", "--focus", "auth"])
    assert rc == 0
    req = fake_executor.analyze_requests[0]
    assert req.repo_root == "/r"
    assert req.focus == "auth"
    assert "analyzed" in capsys.readouterr().out


def test_review_argparse_and_calls_executor(fake_executor, capsys):
    rc = cli.main(["review", "--repo-root", "/r", "--files", "a.py", "b.py"])
    assert rc == 0
    req = fake_executor.review_requests[0]
    assert req.file_paths == ["a.py", "b.py"]
    assert "clean" in capsys.readouterr().out


def test_json_output(fake_executor, capsys):
    rc = cli.main(["processes", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["success"] is True


@pytest.mark.parametrize(
    "argv",
    [
        ["delegate", "--to", "coder", "--subtask", "x", "--repo-root", "/r"],
        ["delegate-coder", "--subtask", "x", "--repo-root", "/r"],
        ["delegate-researcher", "--subtask", "x", "--repo-root", "/r"],
        ["delegate-secretary", "--subtask", "x", "--repo-root", "/r"],
        ["delegate-runner", "--subtask", "x", "--repo-root", "/r"],
        ["delegate-git", "--operation", "status", "--repo-root", "/r"],
        ["runner", "--subtask", "x", "--repo-root", "/r"],
        ["plan", "--task", "t", "--repo-root", "/r"],
        ["run", "--task", "t", "--repo-root", "/r"],
    ],
)
def test_removed_commands_error_with_migration(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2
    assert "coder_*" in capsys.readouterr().err


def test_cli_run_and_diagnose_success(fake_executor, capsys):
    rc = cli.main(["run-and-diagnose", "--command", "pytest tests/"])
    assert rc == 0
    assert len(fake_executor.run_and_diagnose_requests) == 1
    req = fake_executor.run_and_diagnose_requests[0]
    assert req.command == "pytest tests/"
    out = capsys.readouterr().out
    assert "ran and diagnosed pytest tests/" in out
    assert "OK, 1 passed" in out


def test_cli_run_and_diagnose_failure(fake_executor, capsys):
    fake_executor.run_and_diagnose_result = AgentRunAndDiagnoseResult(
        success=False,
        summary="Test run failed: 1 failed, 0 passed",
        returncode=1,
        failed_count=1,
        failures=[
            FailureDetail(
                test_name="tests/test_x.py::test_fail",
                file_path="tests/test_x.py",
                line_number=25,
                error_message="AssertionError: 1 != 2",
                traceback="> assert 1 == 2\nE AssertionError: 1 != 2",
            )
        ],
    )
    rc = cli.main(["run-and-diagnose", "--command", "pytest tests/"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "Test run failed: 1 failed, 0 passed" in out
    assert "Failures / Diagnostics (1):" in out
    assert "[tests/test_x.py::test_fail] AssertionError: 1 != 2" in out
    assert "> assert 1 == 2" in out


def test_cli_run_and_diagnose_json(fake_executor, capsys):
    rc = cli.main(["run-and-diagnose", "--command", "pytest tests/", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is True
    assert "failures" in data
    assert "condensed_output" in data
    assert "summary" in data
    assert data["summary"] == "ran and diagnosed pytest tests/"


def test_cli_pipeline_inline(fake_executor, capsys):
    rc = cli.main(["pipeline", "--steps", '[{"name": "test", "command": "echo hi"}]'])
    assert rc == 0
    assert len(fake_executor.pipeline_requests) == 1
    req = fake_executor.pipeline_requests[0]
    assert len(req.steps) == 1
    assert req.steps[0].name == "test"
    assert req.steps[0].command == "echo hi"
    out = capsys.readouterr().out
    assert "[PASS] test" in out


def test_cli_pipeline_file(fake_executor, tmp_path, capsys):
    steps_file = tmp_path / "steps.json"
    steps_file.write_text(json.dumps([{"name": "build", "command": "make build"}]))
    rc = cli.main(["pipeline", "--steps", str(steps_file)])
    assert rc == 0
    assert len(fake_executor.pipeline_requests) == 1
    assert fake_executor.pipeline_requests[0].steps[0].name == "build"
    assert fake_executor.pipeline_requests[0].steps[0].command == "make build"
    out = capsys.readouterr().out
    assert "[PASS] build" in out


def test_cli_pipeline_invalid_json(fake_executor, capsys):
    rc = cli.main(["pipeline", "--steps", "invalid-json{"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Invalid JSON for --steps" in err


def test_cli_pipeline_failure(fake_executor, capsys):
    fake_executor.pipeline_result = AgentExecPipelineResult(
        success=False,
        summary="pipeline failed",
        total_duration_seconds=0.2,
        steps=[
            PipelineStepResult(
                command="false",
                name="fail_step",
                success=False,
                returncode=1,
                duration_seconds=0.1,
                skipped=False,
                summary="command exited with code 1",
            )
        ],
    )
    rc = cli.main(["pipeline", "--steps", '[{"name": "fail_step", "command": "false"}]'])
    assert rc == 1
    out = capsys.readouterr().out
    assert "pipeline failed" in out
    assert "[FAIL] fail_step" in out
    assert "command exited with code 1" in out


def test_cli_distill_logs(fake_executor, capsys):
    fake_executor.distill_logs_result = AgentDistillLogsResult(
        success=True,
        summary="Distilled 10 log lines",
        total_lines_analyzed=10,
        clusters=[
            LogCluster(
                pattern="[ERROR] <HEX> timeout",
                count=4,
                level="ERROR",
                sample_line="2026-09-16 [ERROR] 0x123 timeout",
            )
        ],
        isolated_errors=[
            "Traceback (most recent call last):\n  File 'app.py', line 10\nValueError: invalid input"
        ],
        source="test",
    )
    rc = cli.main(["distill-logs", "--module", "coder", "--level", "ERROR", "--limit", "50"])
    assert rc == 0
    assert len(fake_executor.distill_logs_requests) == 1
    req = fake_executor.distill_logs_requests[0]
    assert req.module == "coder"
    assert req.level == "ERROR"
    assert req.limit == 50
    out = capsys.readouterr().out
    assert "Distilled 10 log lines" in out
    assert "Log Clusters (1):" in out
    assert "[4x] [ERROR] [ERROR] <HEX> timeout" in out
    assert "Sample: 2026-09-16 [ERROR] 0x123 timeout" in out
    assert "Isolated Error Blocks (1):" in out
    assert "--- Error Block #1 ---" in out
    assert "ValueError: invalid input" in out


def test_cli_distill_logs_json(fake_executor, capsys):
    rc = cli.main(["distill-logs", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is True
    assert "clusters" in data
    assert "isolated_errors" in data
    assert "summary" in data
