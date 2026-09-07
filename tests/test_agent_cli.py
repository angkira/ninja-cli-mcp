"""Tests for the ninja_agent CLI (argparse + executor mocks + run composition)."""

from __future__ import annotations

import json

import pytest

from ninja_agent import cli
from ninja_agent.models import (
    AgentAnalyzeResult,
    AgentDelegateResult,
    AgentPlanResult,
    AgentPlanStep,
    AgentReviewResult,
)


class _FakeExecutor:
    """Fake AgentToolExecutor recording requests and returning canned results."""

    last_instance: _FakeExecutor | None = None

    def __init__(self) -> None:
        self.plan_requests: list = []
        self.analyze_requests: list = []
        self.delegate_requests: list = []
        self.review_requests: list = []
        _FakeExecutor.last_instance = self

    async def plan(self, request, client_id: str = "default"):
        self.plan_requests.append(request)
        return AgentPlanResult(
            success=True,
            plan=[
                AgentPlanStep(
                    title="Analyze context",
                    description="Inspect code",
                    delegate_to="secretary",
                    dependencies=[],
                ),
                AgentPlanStep(
                    title="Implement",
                    description="Write code",
                    delegate_to="coder",
                    dependencies=[0],
                ),
                AgentPlanStep(
                    title="Verify",
                    description="Review",
                    delegate_to="self",
                    dependencies=[0, 1],
                ),
            ],
            reasoning="test plan",
        )

    async def analyze(self, request, client_id: str = "default"):
        self.analyze_requests.append(request)
        return AgentAnalyzeResult(
            success=True, summary="analyzed", findings=["f1"], touched_paths=[]
        )

    async def delegate(self, request, client_id: str = "default"):
        self.delegate_requests.append(request)
        return AgentDelegateResult(
            success=True, summary=f"did {request.subtask}", delegate_to=request.delegate_to
        )

    async def review(self, request, client_id: str = "default"):
        self.review_requests.append(request)
        return AgentReviewResult(success=True, findings=[], summary="clean")


@pytest.fixture
def fake_executor(monkeypatch):
    fake = _FakeExecutor()
    monkeypatch.setattr(cli, "AgentToolExecutor", lambda: fake)
    return fake


def test_plan_argparse_and_calls_executor(fake_executor, capsys):
    rc = cli.main(["plan", "--task", "Add feature", "--repo-root", "/tmp/r"])
    assert rc == 0
    assert len(fake_executor.plan_requests) == 1
    req = fake_executor.plan_requests[0]
    assert req.task == "Add feature"
    assert req.repo_root == "/tmp/r"
    out = capsys.readouterr().out
    assert "Analyze context" in out


def test_plan_with_context_and_steps(fake_executor):
    rc = cli.main(
        ["plan", "--task", "t", "--repo-root", "/r", "--context", "a.py", "b.py", "--steps", "2"]
    )
    assert rc == 0
    req = fake_executor.plan_requests[0]
    assert req.context_paths == ["a.py", "b.py"]
    assert req.steps_requested == 2


def test_plan_json_output(fake_executor, capsys):
    rc = cli.main(["plan", "--task", "t", "--repo-root", "/r", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert len(payload["plan"]) == 3


def test_analyze_argparse_and_calls_executor(fake_executor, capsys):
    rc = cli.main(["analyze", "--repo-root", "/r", "--focus", "auth"])
    assert rc == 0
    req = fake_executor.analyze_requests[0]
    assert req.repo_root == "/r"
    assert req.focus == "auth"
    assert "analyzed" in capsys.readouterr().out


def test_delegate_argparse_and_calls_executor(fake_executor, capsys):
    rc = cli.main(
        [
            "delegate",
            "--to",
            "coder",
            "--subtask",
            "Write X",
            "--repo-root",
            "/r",
            "--model-class",
            "fast",
        ]
    )
    assert rc == 0
    req = fake_executor.delegate_requests[0]
    assert req.delegate_to == "coder"
    assert req.subtask == "Write X"
    assert req.model_class == "fast"
    assert "Write X" in capsys.readouterr().out


def test_delegate_unknown_target_rejected():
    with pytest.raises(SystemExit) as exc:
        cli.main(["delegate", "--to", "unknown", "--subtask", "x", "--repo-root", "/r"])
    assert exc.value.code == 2


def test_review_argparse_and_calls_executor(fake_executor, capsys):
    rc = cli.main(["review", "--repo-root", "/r", "--files", "a.py", "b.py"])
    assert rc == 0
    req = fake_executor.review_requests[0]
    assert req.file_paths == ["a.py", "b.py"]
    assert "clean" in capsys.readouterr().out


def test_run_composes_plan_delegate_review(fake_executor, capsys):
    rc = cli.main(["run", "--task", "Add feature", "--repo-root", "/r", "--context", "a.py"])
    assert rc == 0
    # plan called once with the task
    assert len(fake_executor.plan_requests) == 1
    assert fake_executor.plan_requests[0].task == "Add feature"
    # only delegatable steps (secretary + coder, not self) are delegated
    delegated = [r.delegate_to for r in fake_executor.delegate_requests]
    assert delegated == ["secretary", "coder"]
    # context files are reviewed
    assert fake_executor.review_requests[0].file_paths == ["a.py"]
    out = capsys.readouterr().out
    assert "Plan" in out and "Delegations" in out and "Review" in out


def test_run_without_context_skips_review(fake_executor):
    rc = cli.main(["run", "--task", "t", "--repo-root", "/r"])
    assert rc == 0
    assert fake_executor.review_requests == []


def test_run_json_output(fake_executor, capsys):
    rc = cli.main(["run", "--task", "t", "--repo-root", "/r", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "plan" in payload and "delegations" in payload and "review" in payload
    assert len(payload["delegations"]) == 2


def test_run_plan_failure_returns_nonzero(monkeypatch, capsys):
    from ninja_agent.models import AgentPlanResult as _PR

    class _FailPlan(_FakeExecutor):
        async def plan(self, request, client_id: str = "default"):
            return _PR(success=False, plan=[], reasoning="boom")

    fake = _FailPlan()
    monkeypatch.setattr(cli, "AgentToolExecutor", lambda: fake)
    rc = cli.main(["run", "--task", "t", "--repo-root", "/r"])
    assert rc == 1
    assert "boom" in capsys.readouterr().err
