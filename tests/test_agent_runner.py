"""Tests for the runner sub-agent (in-process routine ops + delegate routing)."""

from __future__ import annotations

import asyncio
import subprocess

import pytest

from ninja_agent import cli
from ninja_agent.models import AgentExecCommandRequest, AgentTailLogsRequest
from ninja_agent.runner import (
    MAX_LOG_LINES,
    RunnerToolExecutor,
    find_denied,
    looks_like_write,
    redact_text,
)
from ninja_agent.tools import AgentToolExecutor


def run_async(coro):
    return asyncio.run(coro)


# --- guards ---------------------------------------------------------------


def test_looks_like_write_splits_read_only_from_mutating():
    assert not looks_like_write("git status")
    assert not looks_like_write("pytest -q tests/test_agent.py")
    assert looks_like_write("git commit -m 'x'")
    assert looks_like_write("mkdir -p foo && touch foo/bar")
    assert looks_like_write("echo hi > out.txt")


def test_find_denied_blocks_destructive_patterns():
    assert find_denied("rm -rf /") is not None
    assert find_denied("mkfs.ext4 /dev/sda1") is not None
    assert find_denied("dd if=/dev/zero of=/dev/sda") is not None
    assert find_denied("shutdown now") is not None
    assert find_denied("pytest -q") is None


def test_redact_text_covers_secrets_and_emails():
    assert "[REDACTED_API_KEY]" in redact_text("key=sk-abcdefghij1234567890zzz")
    assert "[REDACTED_EMAIL]" in redact_text("contact bob@example.com here")


def test_run_command_refuses_dangerous(tmp_path):
    ex = RunnerToolExecutor()
    res = run_async(ex.run_command("rm -rf /", repo_root=str(tmp_path), allow_write=True))
    assert res.success is False
    assert "Refused" in res.summary


def test_run_command_refuses_write_without_flag(tmp_path):
    ex = RunnerToolExecutor()
    res = run_async(ex.run_command("git commit -m x", repo_root=str(tmp_path)))
    assert res.success is False
    assert "allow_write" in res.summary


def test_run_command_refuses_cwd_escape(tmp_path):
    ex = RunnerToolExecutor()
    res = run_async(ex.run_command("echo hi", cwd="/tmp", repo_root=str(tmp_path)))
    assert res.success is False
    assert "escapes" in res.summary


def test_run_command_success_and_output_cap(tmp_path):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok-line\n", stderr="")

    ex = RunnerToolExecutor(subprocess_runner=fake_run)
    res = run_async(ex.run_command("echo hi", repo_root=str(tmp_path)))
    assert res.success is True
    assert "ok-line" in res.stdout


def test_run_command_timeout(tmp_path):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, timeout=kwargs.get("timeout", 1))

    ex = RunnerToolExecutor(subprocess_runner=fake_run)
    res = run_async(ex.run_command("sleep 5", repo_root=str(tmp_path), timeout=1))
    assert res.success is False
    assert "timed out" in res.summary


def test_run_command_write_with_safety_dry_run(tmp_path):
    seen = {}

    def fake_safety(repo_root, allow_dirty=True, create_tag=False):
        seen["create_tag"] = create_tag
        return {"warnings": ["dry-run note"]}

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="wrote\n", stderr="")

    ex = RunnerToolExecutor(subprocess_runner=fake_run, safety_checker=fake_safety)
    res = run_async(ex.run_command("mkdir -p sub", repo_root=str(tmp_path), allow_write=True))
    assert res.success is True
    assert res.safety_warnings == ["dry-run note"]
    assert seen["create_tag"] is False  # dry-run: never creates a tag


# --- tail_logs / processes / jobs ------------------------------------------


def test_tail_logs_caps_and_redacts():
    lines = [f"line {i} contact bob@example.com" for i in range(300)]

    def fake_query(module=None, level=None, limit=50, session_id=None):
        return [{"timestamp": "t", "level": "INFO", "message": line} for line in lines]

    ex = RunnerToolExecutor(structured_log_query=fake_query)
    res = run_async(ex.tail_logs(limit=500))
    assert res.success is True
    assert len(res.entries) <= MAX_LOG_LINES
    assert all("[REDACTED_EMAIL]" in e for e in res.entries)


def test_processes_is_read_only_snapshot():
    class FakeDaemon:
        def status_all(self):
            return {"coder": {"running": True}}

    class FakeMonitor:
        def get_stats(self):
            return {"total_tasks": 3}

        async def check_resources(self):
            return {"healthy": True, "warnings": []}

    ex = RunnerToolExecutor(
        daemon_factory=lambda: FakeDaemon(),
        resource_monitor_factory=lambda: FakeMonitor(),
    )
    res = run_async(ex.processes())
    assert res.success is True
    assert res.daemons["coder"]["running"] is True
    assert res.resources["health"]["healthy"] is True


def test_jobs_overview_uses_injected_lister():
    async def fake_lister(limit):
        return [{"taskId": "j1", "status": "working"}]

    ex = RunnerToolExecutor(jobs_lister=fake_lister)
    res = run_async(ex.jobs_overview())
    assert res.success is True
    assert res.jobs[0]["taskId"] == "j1"


def test_handle_routes_structured_command(tmp_path):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="hi\n", stderr="")

    ex = RunnerToolExecutor(subprocess_runner=fake_run)
    out = run_async(ex.handle("whatever", str(tmp_path), command="echo hi"))
    assert out["success"] is True
    assert "hi" in out["stdout"]


def test_handle_routes_free_text_status_to_processes():
    class FakeDaemon:
        def status_all(self):
            return {"coder": {"running": False}}

    class FakeMonitor:
        def get_stats(self):
            return {}

        async def check_resources(self):
            return {"healthy": True}

    ex = RunnerToolExecutor(
        daemon_factory=lambda: FakeDaemon(),
        resource_monitor_factory=lambda: FakeMonitor(),
    )
    out = run_async(ex.handle("check daemon status please", "/tmp"))
    assert "daemon" in out["summary"]


# --- agent executor thin wrappers (no delegation) -------------------------------


def test_agent_exec_command_request_shape(tmp_path):
    req = AgentExecCommandRequest(
        command="git status",
        repo_root=str(tmp_path),
        timeout=30,
    )
    assert req.command == "git status"
    assert req.timeout == 30


def test_agent_exec_command_routes_to_runner(tmp_path, monkeypatch):
    executor = AgentToolExecutor()
    calls = {}

    class FakeRunner:
        async def run_command(self, cmd, **kwargs):
            from ninja_agent.runner import RunnerCommandResult

            calls["cmd"] = cmd
            calls.update(kwargs)
            return RunnerCommandResult(success=True, summary="did routine", stdout="ok")

    monkeypatch.setattr(executor, "_get_runner", lambda: FakeRunner())
    req = AgentExecCommandRequest(command="git status", repo_root=str(tmp_path))
    result = run_async(executor.exec_command(req))
    assert result.success is True
    assert "did routine" in result.summary
    assert calls["cmd"] == "git status"


def test_agent_tail_logs_routes_to_runner(monkeypatch):
    executor = AgentToolExecutor()
    calls = {}

    class FakeRunner:
        async def tail_logs(self, **kwargs):
            from ninja_agent.runner import RunnerLogsResult

            calls.update(kwargs)
            return RunnerLogsResult(success=True, summary="tailed", entries=["e1"])

    monkeypatch.setattr(executor, "_get_runner", lambda: FakeRunner())
    result = run_async(executor.tail_logs(AgentTailLogsRequest(module="coder")))
    assert result.success is True
    assert result.entries == ["e1"]
    assert calls["module"] == "coder"


def test_cli_exec_command(monkeypatch, capsys):
    from ninja_agent.models import AgentExecCommandResult

    class FakeExecutor:
        def __init__(self, *a, **k):
            pass

        async def exec_command(self, request, client_id="default"):
            assert request.command == "git status"
            return AgentExecCommandResult(success=True, summary="exec ok")

    monkeypatch.setattr(cli, "AgentToolExecutor", FakeExecutor)
    rc = cli.main(["exec-command", "--command", "git status", "--repo-root", "/r"])
    assert rc == 0
    assert "exec ok" in capsys.readouterr().out


def test_cli_removed_delegate_runner_errors_with_migration(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(
            [
                "delegate-runner",
                "--subtask",
                "check status",
                "--repo-root",
                "/r",
                "--log-module",
                "coder",
            ]
        )
    assert exc.value.code == 2
    assert "coder_*" in capsys.readouterr().err


def test_cli_legacy_runner_shortcut_errors_with_migration(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["runner", "--subtask", "check status", "--repo-root", "/r"])
    assert exc.value.code == 2
    assert "coder_*" in capsys.readouterr().err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
