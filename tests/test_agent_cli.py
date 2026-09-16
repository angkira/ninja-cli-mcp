"""Tests for the autonomous ninja_agent CLI (exec-command, tail-logs, processes, jobs, analyze, review)."""

from __future__ import annotations

import json

import pytest

from ninja_agent import cli
from ninja_agent.models import (
    AgentAnalyzeResult,
    AgentExecCommandResult,
    AgentJobsOverviewResult,
    AgentProcessesResult,
    AgentReviewResult,
    AgentTailLogsResult,
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
