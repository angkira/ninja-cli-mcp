"""Tests for the runner sub-agent (in-process routine ops + delegate routing)."""

from __future__ import annotations

import asyncio
import subprocess

import pytest

from ninja_agent import cli
from ninja_agent.models import (
    AgentDistillLogsRequest,
    AgentExecCommandRequest,
    AgentExecPipelineRequest,
    AgentRunAndDiagnoseRequest,
    AgentTailLogsRequest,
    PipelineStep,
)
from ninja_agent.runner import (
    MAX_LOG_LINES,
    DiagnosticsDistiller,
    LogDistiller,
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


# --- DiagnosticsDistiller tests -------------------------------------------


def test_diagnostics_distiller_pytest_pass():
    sample = """
============================= test session starts ==============================
platform darwin -- Python 3.13.0, pytest-8.0.0
rootdir: /repo
collected 15 items

tests/test_sample.py ...............                                    [100%]

============================== 15 passed in 0.42s ===============================
"""
    parsed = DiagnosticsDistiller.parse_test_runner(sample)
    assert parsed["passed_count"] == 15
    assert parsed["failed_count"] == 0
    assert parsed["skipped_count"] == 0
    assert parsed["error_count"] == 0
    assert parsed["failures"] == []

    distilled = DiagnosticsDistiller.distill(sample, "", returncode=0)
    assert distilled["passed_count"] == 15
    assert distilled["failed_count"] == 0
    assert distilled["summary"] == "OK, 15 passed"
    assert distilled["failures"] == []
    assert "OK, 15 passed" in distilled["condensed_output"]

    # Also test output with skipped items
    sample_skipped = "================== 12 passed, 3 skipped, 1 warning in 1.20s ==================="
    parsed_skipped = DiagnosticsDistiller.parse_test_runner(sample_skipped)
    assert parsed_skipped["passed_count"] == 12
    assert parsed_skipped["skipped_count"] == 3
    distilled_skipped = DiagnosticsDistiller.distill(sample_skipped, "", returncode=0)
    assert distilled_skipped["summary"] == "OK, 12 passed, 3 skipped"


def test_diagnostics_distiller_pytest_failure():
    sample = """
============================= test session starts ==============================
rootdir: /repo
collected 3 items

tests/test_math.py .F.                                                   [100%]

=================================== FAILURES ===================================
_________________________________ test_divide __________________________________

    def test_divide():
>       assert divide(10, 0) == 0
E       ZeroDivisionError: division by zero

tests/test_math.py:25: ZeroDivisionError
=========================== short test summary info ============================
FAILED tests/test_math.py::test_divide - ZeroDivisionError: division by zero
========================= 1 failed, 2 passed in 0.15s ==========================
"""
    parsed = DiagnosticsDistiller.parse_test_runner(sample)
    assert parsed["passed_count"] == 2
    assert parsed["failed_count"] == 1
    assert len(parsed["failures"]) == 1

    f = parsed["failures"][0]
    assert f.test_name == "tests/test_math.py::test_divide"
    assert f.file_path == "tests/test_math.py"
    assert f.line_number == 25
    assert "ZeroDivisionError" in f.error_message
    assert f.traceback is not None
    assert "ZeroDivisionError: division by zero" in f.traceback
    assert "assert divide(10, 0) == 0" in f.traceback

    distilled = DiagnosticsDistiller.distill(sample, "", returncode=1)
    assert distilled["failed_count"] == 1
    assert distilled["passed_count"] == 2
    assert "Test run failed: 1 failed, 2 passed" in distilled["summary"]
    assert len(distilled["failures"]) == 1


def test_diagnostics_distiller_compiler_linter_diagnostics():
    sample = """
src/ninja_agent/runner.py:10:5: error: Incompatible return value type (got "int", expected "str") [return-value]
src/ninja_agent/runner.py:25:1: E501 line too long (120 > 100 characters)
tests/test_agent.py:42: F401 'sys' imported but unused
"""
    diags = DiagnosticsDistiller.parse_diagnostics(sample)
    assert len(diags) == 3
    assert diags[0].file_path == "src/ninja_agent/runner.py"
    assert diags[0].line_number == 10
    assert "Incompatible return value type" in diags[0].error_message
    assert diags[1].file_path == "src/ninja_agent/runner.py"
    assert diags[1].line_number == 25
    assert "E501" in diags[1].error_message
    assert diags[2].file_path == "tests/test_agent.py"
    assert diags[2].line_number == 42
    assert "F401" in diags[2].error_message

    dist = DiagnosticsDistiller.distill(sample, "", returncode=1, framework_hint="mypy")
    assert dist["error_count"] == 3
    assert "Diagnostics found: 3 issues reported" in dist["summary"]
    assert len(dist["failures"]) == 3

    dist_clean = DiagnosticsDistiller.distill("", "", returncode=0, framework_hint="ruff")
    assert dist_clean["failures"] == []
    assert dist_clean["summary"] == "All checks passed cleanly."


def test_diagnostics_distiller_raw_traceback():
    sample = """
Starting database migration...
Traceback (most recent call last):
  File "scripts/migrate.py", line 45, in <module>
    run_migrations()
  File "scripts/migrate.py", line 22, in run_migrations
    raise ConnectionRefusedError("Unable to connect to database host:5432")
ConnectionRefusedError: Unable to connect to database host:5432
"""
    tb = DiagnosticsDistiller.parse_traceback(sample)
    assert len(tb) == 1
    f = tb[0]
    assert f.file_path == "scripts/migrate.py"
    assert f.line_number == 22
    assert "ConnectionRefusedError: Unable to connect to database host:5432" in f.error_message
    assert f.traceback is not None
    assert "Traceback (most recent call last):" in f.traceback

    dist = DiagnosticsDistiller.distill(sample, "", returncode=1)
    assert dist["failed_count"] == 1
    assert len(dist["failures"]) == 1
    assert "Command failed with exit code 1." in dist["summary"]


def test_diagnostics_distiller_condense_output():
    sample = """
============================= test session starts ==============================
platform darwin -- Python 3.13.0
rootdir: /repo
plugins: cov-5.0
collecting ... collected 50 items

..................................................                       [100%]
tests/test_x.py::test_one PASSED [ 50%]
tests/test_x.py::test_two PASSED [100%]

=================================== FAILURES ===================================
___________________________________ test_bad ___________________________________
>   assert False
E   AssertionError

========================= 1 failed, 49 passed in 0.50s =========================
"""
    condensed = DiagnosticsDistiller.condense_output(sample, "")
    assert "=== test session starts" not in condensed
    assert "rootdir: /repo" not in condensed
    assert "plugins: cov-5.0" not in condensed
    assert "collecting ..." not in condensed
    assert "PASSED" not in condensed
    assert ">   assert False" in condensed
    assert "AssertionError" in condensed
    assert "1 failed, 49 passed" in condensed

    # Truncation check
    huge = "regular log message line\n" * 1000
    cond = DiagnosticsDistiller.condense_output(huge, "", max_chars=400)
    assert len(cond) <= 400
    assert "...[condensed output truncated]" in cond


# --- LogDistiller tests ---------------------------------------------------


def test_log_distiller_normalization():
    # UUID masking
    msg_uuid = LogDistiller.normalize_message(
        "Session c2d3e4f5-a6b7-8901-cdef-123456789abc initialized"
    )
    assert "<UUID>" in msg_uuid
    assert "c2d3e4f5" not in msg_uuid

    # Hex pointer masking
    msg_hex = LogDistiller.normalize_message("Buffer pointer at 0x7ffee4b6a120 corrupted")
    assert "<HEX>" in msg_hex
    assert "0x7ffee4b6a120" not in msg_hex

    # ISO timestamp masking
    msg_iso = LogDistiller.normalize_message("2026-09-16T12:34:56.789Z [INFO] System ready")
    assert "<TIMESTAMP>" in msg_iso
    assert "2026-09-16" not in msg_iso

    msg_time = LogDistiller.normalize_message("12:34:56 [INFO] System ready")
    assert "<TIMESTAMP>" in msg_time

    # Numbers and IDs masking
    msg_id = LogDistiller.normalize_message("User id=987654321 processed in 12345 ms")
    assert "<ID>" in msg_id or "<NUM>" in msg_id


def test_log_distiller_clustering():
    entries = [
        "2026-09-16 10:00:01 [ERROR] Connection failed to host: 0x1234abc",
        "2026-09-16 10:00:02 [ERROR] Connection failed to host: 0x5678def",
        "2026-09-16 10:00:03 [ERROR] Connection failed to host: 0x9999aaa",
        "2026-09-16 10:00:04 [INFO] Heartbeat acknowledged from node-1",
    ]
    res = LogDistiller.distill(entries)
    clusters = res["clusters"]
    assert len(clusters) == 2
    # Cluster 0 is the most frequent
    assert clusters[0].count == 3
    assert clusters[0].level == "ERROR"
    assert "<HEX>" in clusters[0].pattern
    assert clusters[0].first_seen == "2026-09-16 10:00:01"
    assert clusters[0].last_seen == "2026-09-16 10:00:03"
    assert clusters[0].sample_line == entries[0]

    # Cluster 1
    assert clusters[1].count == 1
    assert clusters[1].level == "INFO"
    assert "Heartbeat acknowledged" in clusters[1].pattern

    assert "Distilled 4 log lines into 2 unique cluster(s)" in res["summary"]


def test_log_distiller_isolated_error_extraction():
    lines = [
        "2026-09-16 10:00:00 [INFO] Worker started",
        "Traceback (most recent call last):",
        '  File "worker.py", line 50, in process',
        "    data = fetch()",
        '  File "worker.py", line 20, in fetch',
        '    raise TimeoutError("upstream timed out")',
        "TimeoutError: upstream timed out",
        "2026-09-16 10:00:05 [INFO] Retrying job",
        "Traceback (most recent call last):",
        '  File "worker.py", line 55, in retry',
        '    raise RuntimeError("retry budget exhausted")',
        "RuntimeError: retry budget exhausted",
        "2026-09-16 10:00:06 [INFO] Worker exiting",
    ]
    errors = LogDistiller.extract_isolated_errors(lines)
    assert len(errors) == 2
    assert "TimeoutError: upstream timed out" in errors[0]
    assert "Traceback (most recent call last):" in errors[0]
    assert "RuntimeError: retry budget exhausted" in errors[1]
    assert "Worker exiting" not in errors[1]
    assert "Worker started" not in errors[0]


# --- RunnerToolExecutor.run_and_diagnose tests ----------------------------


def test_runner_run_and_diagnose_success(tmp_path):
    def fake_run(cmd, **kwargs):
        stdout = (
            "============================= test session starts ==============================\n"
            "rootdir: /repo\ncollected 5 items\n\n"
            "test_sample.py .....                                                     [100%]\n"
            "============================== 5 passed in 0.12s ===============================\n"
        )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    ex = RunnerToolExecutor(subprocess_runner=fake_run)
    req = AgentRunAndDiagnoseRequest(command="pytest", repo_root=str(tmp_path))
    res = run_async(ex.run_and_diagnose(req))
    assert res.success is True
    assert res.passed_count == 5
    assert res.failed_count == 0
    assert res.failures == []
    assert "OK, 5 passed" in res.summary


def test_runner_run_and_diagnose_failure(tmp_path):
    def fake_run(cmd, **kwargs):
        stdout = (
            "=================================== FAILURES ===================================\n"
            "__________________________________ test_fail ___________________________________\n"
            "    def test_fail():\n"
            ">       assert 1 == 2\n"
            "E       AssertionError: assert 1 == 2\n"
            "tests/test_x.py:10: AssertionError\n"
            "=========================== short test summary info ============================\n"
            "FAILED tests/test_x.py::test_fail - AssertionError: assert 1 == 2\n"
            "========================= 1 failed, 1 passed in 0.10s ==========================\n"
        )
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout=stdout, stderr="")

    ex = RunnerToolExecutor(subprocess_runner=fake_run)
    req = AgentRunAndDiagnoseRequest(command="pytest", repo_root=str(tmp_path))
    res = run_async(ex.run_and_diagnose(req))
    assert res.success is False
    assert res.failed_count == 1
    assert res.passed_count == 1
    assert len(res.failures) == 1
    f = res.failures[0]
    assert f.test_name == "tests/test_x.py::test_fail"
    assert f.file_path == "tests/test_x.py"
    assert f.line_number == 10
    assert "AssertionError" in f.error_message
    assert f.traceback is not None
    assert "assert 1 == 2" in f.traceback


def test_runner_run_and_diagnose_safety_and_timeout(tmp_path):
    ex = RunnerToolExecutor()

    # Destructive command refused
    req_danger = AgentRunAndDiagnoseRequest(command="rm -rf /", repo_root=str(tmp_path))
    res_danger = run_async(ex.run_and_diagnose(req_danger))
    assert res_danger.success is False
    assert "Refused" in res_danger.summary

    # Write command refused without allow_write
    req_write = AgentRunAndDiagnoseRequest(command="git commit -m msg", repo_root=str(tmp_path))
    res_write = run_async(ex.run_and_diagnose(req_write))
    assert res_write.success is False
    assert "allow_write" in res_write.summary

    # Timeout handling
    def fake_timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, timeout=kwargs.get("timeout", 1))

    ex_timeout = RunnerToolExecutor(subprocess_runner=fake_timeout)
    req_timeout = AgentRunAndDiagnoseRequest(
        command="sleep 10", repo_root=str(tmp_path), timeout=1
    )
    res_timeout = run_async(ex_timeout.run_and_diagnose(req_timeout))
    assert res_timeout.success is False
    assert "timed out" in res_timeout.summary


# --- RunnerToolExecutor.exec_pipeline tests --------------------------------


def test_runner_exec_pipeline_sequential(tmp_path):
    executed: list[str] = []

    def fake_run(cmd, **kwargs):
        executed.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=f"out: {cmd}\n", stderr="")

    ex = RunnerToolExecutor(subprocess_runner=fake_run)
    steps = [
        PipelineStep(name="step_a", command="echo a"),
        PipelineStep(name="step_b", command="echo b"),
        PipelineStep(name="step_c", command="echo c"),
    ]
    req = AgentExecPipelineRequest(steps=steps, repo_root=str(tmp_path))
    res = run_async(ex.exec_pipeline(req))

    assert res.success is True
    assert len(res.steps) == 3
    assert executed == ["echo a", "echo b", "echo c"]
    assert all(s.success for s in res.steps)
    assert all(not s.skipped for s in res.steps)
    assert "3/3 steps succeeded" in res.summary


def test_runner_exec_pipeline_fail_fast(tmp_path):
    def fake_run(cmd, **kwargs):
        if "step_two" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="failed step")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok\n", stderr="")

    ex = RunnerToolExecutor(subprocess_runner=fake_run)
    steps = [
        PipelineStep(name="s1", command="echo step_one"),
        PipelineStep(name="s2", command="echo step_two"),
        PipelineStep(name="s3", command="echo step_three"),
    ]
    req = AgentExecPipelineRequest(steps=steps, repo_root=str(tmp_path), fail_fast=True)
    res = run_async(ex.exec_pipeline(req))

    assert res.success is False
    assert len(res.steps) == 3
    assert res.steps[0].success is True
    assert res.steps[1].success is False
    assert res.steps[2].skipped is True
    assert "Skipped due to earlier pipeline failure" in res.steps[2].summary


def test_runner_exec_pipeline_continue_on_error(tmp_path):
    executed: list[str] = []

    def fake_run(cmd, **kwargs):
        executed.append(cmd)
        if "step_one" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="step 1 warning")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok\n", stderr="")

    ex = RunnerToolExecutor(subprocess_runner=fake_run)
    steps = [
        PipelineStep(name="s1", command="echo step_one", continue_on_error=True),
        PipelineStep(name="s2", command="echo step_two"),
    ]
    req = AgentExecPipelineRequest(steps=steps, repo_root=str(tmp_path), fail_fast=True)
    res = run_async(ex.exec_pipeline(req))

    assert len(res.steps) == 2
    assert res.steps[0].success is False
    assert res.steps[1].success is True
    assert res.steps[1].skipped is False
    assert executed == ["echo step_one", "echo step_two"]
    assert res.success is True


def test_runner_exec_pipeline_allow_write_per_step(tmp_path):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="done\n", stderr="")

    ex = RunnerToolExecutor(subprocess_runner=fake_run)
    steps = [
        PipelineStep(name="w1", command="mkdir sub1", allow_write=False),
        PipelineStep(name="w2", command="mkdir sub2", allow_write=True),
    ]
    req = AgentExecPipelineRequest(steps=steps, repo_root=str(tmp_path), fail_fast=False)
    res = run_async(ex.exec_pipeline(req))

    assert res.steps[0].success is False
    assert "allow_write" in res.steps[0].summary
    assert res.steps[1].success is True
    assert res.steps[1].returncode == 0


# --- RunnerToolExecutor.distill_logs tests ---------------------------------


def test_runner_distill_logs():
    raw_logs = [
        "2026-09-16 10:00:01 [ERROR] Failed query user_id=12345 in 100ms",
        "2026-09-16 10:00:02 [ERROR] Failed query user_id=67890 in 110ms",
        "2026-09-16 10:00:03 [ERROR] Failed query user_id=11111 in 105ms",
        "2026-09-16 10:00:04 [INFO] Cache refreshed",
        "2026-09-16 10:00:05 [INFO] Cache refreshed",
        "Traceback (most recent call last):",
        '  File "db.py", line 12, in query',
        '    raise ConnectionError("connection lost")',
        "ConnectionError: connection lost",
    ]

    def fake_query(module=None, level=None, limit=50, session_id=None):
        return raw_logs

    ex = RunnerToolExecutor(structured_log_query=fake_query)
    req = AgentDistillLogsRequest(module="coder", limit=50)
    res = run_async(ex.distill_logs(req))

    assert res.success is True
    assert res.total_lines_analyzed == len(raw_logs)
    assert len(res.clusters) >= 2
    assert len(res.isolated_errors) == 1
    assert "ConnectionError: connection lost" in res.isolated_errors[0]
    assert "Distilled" in res.summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
