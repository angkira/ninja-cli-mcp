"""Tests for the autonomous ninja_agent (exec-command, tail-logs, processes, jobs, analyze, review)."""

from __future__ import annotations

import asyncio
import subprocess

from ninja_agent.models import (
    DELEGATE_MIGRATION,
    AgentAnalyzeRequest,
    AgentExecCommandRequest,
    AgentJobsOverviewRequest,
    AgentReviewRequest,
    AgentTailLogsRequest,
)
from ninja_agent.server import _REMOVED_TOOLS, TOOLS
from ninja_agent.tools import AgentToolExecutor


def run_async(coro):
    return asyncio.run(coro)


# --- tool registry ----------------------------------------------------------


def test_server_registers_autonomous_toolset():
    names = [tool.name for tool in TOOLS]
    assert names == [
        "agent_exec_command",
        "agent_tail_logs",
        "agent_processes",
        "agent_jobs_overview",
        "agent_analyze",
        "agent_review",
        "agent_run_and_diagnose",
        "agent_exec_pipeline",
        "agent_distill_logs",
    ]
    assert not any("delegate" in n for n in names)
    assert "agent_plan" not in names


def test_removed_tools_carry_migration_hint():
    for tool in (
        "agent_delegate",
        "agent_delegate_coder",
        "agent_delegate_researcher",
        "agent_delegate_secretary",
        "agent_delegate_runner",
        "agent_delegate_git",
        "agent_plan",
    ):
        assert tool in _REMOVED_TOOLS
    assert "coder_*" in DELEGATE_MIGRATION
    assert "autonomous" in DELEGATE_MIGRATION.lower() or "автоном" in DELEGATE_MIGRATION.lower()


def test_executor_has_no_delegation_surface():
    executor = AgentToolExecutor()
    for attr in (
        "delegate_coder",
        "delegate_researcher",
        "delegate_secretary",
        "delegate_runner",
        "delegate_git",
        "delegate_plan_step",
        "plan",
        "_get_coder",
        "_get_secretary",
        "_get_researcher",
        "_delegate_coder",
    ):
        assert not hasattr(executor, attr), attr
    for attr in (
        "exec_command",
        "tail_logs",
        "processes",
        "jobs_overview",
        "analyze",
        "review",
        "run_and_diagnose",
        "exec_pipeline",
        "distill_logs",
    ):
        assert hasattr(executor, attr), attr


# --- exec_command / tail_logs / processes / jobs_overview --------------------


def test_exec_command_routes_to_runner(tmp_path):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok-line\n", stderr="")

    from ninja_agent.runner import RunnerToolExecutor

    executor = AgentToolExecutor(runner=RunnerToolExecutor(subprocess_runner=fake_run))
    req = AgentExecCommandRequest(command="echo hi", repo_root=str(tmp_path))
    result = run_async(executor.exec_command(req))
    assert result.success is True
    assert "ok-line" in result.stdout


def test_exec_command_refuses_write_without_flag(tmp_path):
    executor = AgentToolExecutor()
    req = AgentExecCommandRequest(command="git commit -m x", repo_root=str(tmp_path))
    result = run_async(executor.exec_command(req))
    assert result.success is False
    assert "allow_write" in result.summary


def test_tail_logs_routes_to_runner():
    def fake_query(module=None, level=None, limit=50, session_id=None):
        return [{"timestamp": "t", "level": "INFO", "message": "hello"}]

    from ninja_agent.runner import RunnerToolExecutor

    executor = AgentToolExecutor(runner=RunnerToolExecutor(structured_log_query=fake_query))
    result = run_async(executor.tail_logs(AgentTailLogsRequest(module="coder")))
    assert result.success is True
    assert any("hello" in e for e in result.entries)


def test_processes_snapshot():
    class FakeDaemon:
        def status_all(self):
            return {"coder": {"running": True}}

    class FakeMonitor:
        def get_stats(self):
            return {"total_tasks": 3}

        async def check_resources(self):
            return {"healthy": True, "warnings": []}

    from ninja_agent.runner import RunnerToolExecutor

    executor = AgentToolExecutor(
        runner=RunnerToolExecutor(
            daemon_factory=lambda: FakeDaemon(),
            resource_monitor_factory=lambda: FakeMonitor(),
        )
    )
    result = run_async(executor.processes())
    assert result.success is True
    assert result.daemons["coder"]["running"] is True


def test_jobs_overview():
    async def fake_lister(limit):
        return [{"taskId": "j1", "status": "working"}]

    from ninja_agent.runner import RunnerToolExecutor

    executor = AgentToolExecutor(runner=RunnerToolExecutor(jobs_lister=fake_lister))
    result = run_async(executor.jobs_overview(AgentJobsOverviewRequest(limit=10)))
    assert result.success is True
    assert result.jobs[0]["taskId"] == "j1"


# --- analyze (own, no secretary) ----------------------------------------------


def test_analyze_counts_python_symbols(tmp_path):
    (tmp_path / "mod.py").write_text(
        '"""Module."""\nclass A:\n    pass\n\ndef f():\n    """Doc."""\n    return 1\n'
    )
    (tmp_path / "notes.txt").write_text("hello\n")
    executor = AgentToolExecutor()
    result = run_async(executor.analyze(AgentAnalyzeRequest(repo_root=str(tmp_path))))
    assert result.success is True
    assert any("function" in f for f in result.findings)
    assert "mod.py" in result.touched_paths


def test_analyze_focus_narrows_scope(tmp_path):
    (tmp_path / "auth.py").write_text("X = 1\n")
    (tmp_path / "other.py").write_text("Y = 2\n")
    executor = AgentToolExecutor()
    result = run_async(executor.analyze(AgentAnalyzeRequest(repo_root=str(tmp_path), focus="auth")))
    assert result.success is True
    assert result.touched_paths == ["auth.py"]
    assert "auth" in result.summary


def test_analyze_focus_without_match_falls_back(tmp_path):
    (tmp_path / "other.py").write_text("Y = 2\n")
    executor = AgentToolExecutor()
    result = run_async(
        executor.analyze(AgentAnalyzeRequest(repo_root=str(tmp_path), focus="zzz-no-match"))
    )
    assert result.success is True
    assert result.touched_paths == ["other.py"]
    assert "fell back" in result.summary


def test_analyze_reports_syntax_errors(tmp_path):
    (tmp_path / "broken.py").write_text("def f(:\n")
    executor = AgentToolExecutor()
    result = run_async(executor.analyze(AgentAnalyzeRequest(repo_root=str(tmp_path))))
    assert result.success is True
    assert any("Syntax error" in f for f in result.findings)


def test_analyze_missing_root_fails(tmp_path):
    executor = AgentToolExecutor()
    result = run_async(executor.analyze(AgentAnalyzeRequest(repo_root=str(tmp_path / "nope"))))
    assert result.success is False


# --- review (own heuristics, no LLM) ------------------------------------------


def test_review_flags_missing_docstrings_and_empty_except(tmp_path):
    py = tmp_path / "sample.py"
    py.write_text(
        "def no_docstring():\n"
        "    return 1\n"
        "\n"
        "def with_docstring():\n"
        '    """Does a thing."""\n'
        "    try:\n"
        "        pass\n"
        "    except Exception:\n"
        "        pass\n"
    )
    executor = AgentToolExecutor()
    req = AgentReviewRequest(repo_root=str(tmp_path), file_paths=["sample.py"])
    result = run_async(executor.review(req))
    assert result.success
    messages = [f.message for f in result.findings]
    assert any("no docstring" in m for m in messages)
    assert any("pass" in m for m in messages)
    assert "No files modified" in result.summary


def test_review_reports_missing_file(tmp_path):
    executor = AgentToolExecutor()
    req = AgentReviewRequest(repo_root=str(tmp_path), file_paths=["does_not_exist.py"])
    result = run_async(executor.review(req))
    assert result.success
    assert any(f.severity == "warning" and "not found" in f.message for f in result.findings)


def test_review_is_deterministic_without_llm(tmp_path):
    (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
    executor = AgentToolExecutor()
    req = AgentReviewRequest(repo_root=str(tmp_path), file_paths=["mod.py"])
    first = run_async(executor.review(req))
    second = run_async(executor.review(req))
    assert first.model_dump() == second.model_dump()
