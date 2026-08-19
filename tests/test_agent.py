"""Tests for the ninja_agent module (orchestrator: plan, analyze, delegate, review)."""

from __future__ import annotations

import asyncio

import pytest

from ninja_agent.models import (
    AgentDelegateRequest,
    AgentPlanRequest,
    AgentReviewRequest,
)
from ninja_agent.tools import AgentToolExecutor


def run_async(coro):
    return asyncio.run(coro)


def test_plan_default_routes_code_to_coder(tmp_path):
    """Default implementation task routes analysis->secretary, code->coder, verify->self."""
    executor = AgentToolExecutor()
    req = AgentPlanRequest(task="Add a new feature to the CLI", repo_root=str(tmp_path))
    result = run_async(executor.plan(req))
    assert result.success
    delegate_targets = [step.delegate_to for step in result.plan]
    assert "coder" in delegate_targets
    assert "secretary" in delegate_targets
    assert "self" in delegate_targets
    assert result.plan[0].delegate_to == "secretary"
    assert result.plan[-1].delegate_to == "self"


def test_plan_research_routes_to_researcher(tmp_path):
    """Research keyword routes to the researcher as the first step."""
    executor = AgentToolExecutor()
    req = AgentPlanRequest(
        task="Research the latest MCP protocol spec", repo_root=str(tmp_path)
    )
    result = run_async(executor.plan(req))
    assert result.success
    delegate_targets = [step.delegate_to for step in result.plan]
    assert "researcher" in delegate_targets
    assert result.plan[0].delegate_to == "researcher"


def test_plan_analysis_only_no_coder(tmp_path):
    """Pure analysis task should not include an implementation (coder) step."""
    executor = AgentToolExecutor()
    req = AgentPlanRequest(task="Analyze the architecture and explain it", repo_root=str(tmp_path))
    result = run_async(executor.plan(req))
    assert result.success
    delegate_targets = [step.delegate_to for step in result.plan]
    assert "secretary" in delegate_targets
    assert "coder" not in delegate_targets


def test_plan_steps_requested_caps_plan(tmp_path):
    executor = AgentToolExecutor()
    req = AgentPlanRequest(
        task="Build a full authentication system with tests",
        repo_root=str(tmp_path),
        steps_requested=2,
    )
    result = run_async(executor.plan(req))
    assert result.success
    assert len(result.plan) <= 2


def test_review_flags_missing_docstrings_and_empty_except(tmp_path):
    py = tmp_path / "sample.py"
    py.write_text(
        "def no_docstring():\n"
        "    return 1\n"
        "\n"
        "def with_docstring():\n"
        "    \"\"\"Does a thing.\"\"\"\n"
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


def test_delegate_rejects_unknown_target():
    """Unknown delegate_to values are rejected by pydantic validation."""
    import pydantic

    bad = "unknown"
    with pytest.raises(pydantic.ValidationError):
        AgentDelegateRequest(
            subtask="x", repo_root="/tmp/x", delegate_to=bad  # type: ignore[arg-type]
        )


def test_delegate_routes_to_researcher(tmp_path, monkeypatch):
    """Delegation to researcher should call ResearchToolExecutor.web_search."""
    executor = AgentToolExecutor()
    calls = {}

    class FakeResearcher:
        async def web_search(self, request, client_id="default"):
            calls["query"] = request.query
            return type("R", (), {"results": []})()

    monkeypatch.setattr(executor, "_get_researcher", lambda: FakeResearcher())
    req = AgentDelegateRequest(
        subtask="What is the MCP spec?",
        repo_root=str(tmp_path),
        delegate_to="researcher",
    )
    result = run_async(executor.delegate(req))
    assert result.success
    assert result.delegate_to == "researcher"
    assert calls.get("query") == "What is the MCP spec?"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
