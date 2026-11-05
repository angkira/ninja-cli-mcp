"""E2E test for new slim prompts (coder + agent + researcher).

Run: python -m pytest tests/test_prompt_e2e_new.py -q
"""
from __future__ import annotations

import pytest

from ninja_agent.tools import AgentToolExecutor
from ninja_coder.driver import InstructionBuilder
from ninja_coder.models import ExecutionMode, PlanStep
from ninja_coder.prompt_builder import MAX_TOTAL_CONTEXT_CHARS, PromptBuilder
from ninja_researcher.synthesis import (
    build_answer_messages,
    build_report_messages,
)


def _steps() -> list[PlanStep]:
    return [
        PlanStep(id="s1", title="A", task="Do A in src/a.py", context_paths=["src/a.py"],
                 allowed_globs=["src/**/*.py"]),
        PlanStep(id="s2", title="B", task="Do B in src/b.py", context_paths=["src/b.py"],
                 allowed_globs=["src/**/*.py"]),
    ]


def test_coder_quick_slim(tmp_path) -> None:
    ib = InstructionBuilder(str(tmp_path), ExecutionMode.QUICK)
    text = ib._build_quick_instructions("Fix typo", ["src/a.py"])
    assert "🎯" not in text and "🧠" not in text  # no emoji tax
    assert "allowed_globs" in text
    assert len(text) < 1200, f"quick prompt too long: {len(text)}"
    assert "ALWAYS" not in text  # no absolute test mandate


def test_coder_plan_truncates_context(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x=1\n" * 5000)
    (tmp_path / "src" / "b.py").write_text("y=2\n" * 5000)
    pb = PromptBuilder(str(tmp_path))
    prompt = pb.build_sequential_plan(_steps(), ExecutionMode.QUICK)
    assert "## CONTEXT FILES" in prompt
    assert "budget" in prompt
    # total inline bounded (files are ~20KB each, budget 12k)
    ctx_section = prompt.split("## CONTEXT FILES", 1)[1].split("## OUTPUT FORMAT")[0]
    assert len(ctx_section) < MAX_TOTAL_CONTEXT_CHARS + 2000
    # strict JSON output, no verbose guidelines
    assert "one ```json block per step" in prompt
    assert "Summary Guidelines" not in prompt
    # no keyword router noise
    assert "Frontend: React" not in prompt


def test_coder_parallel_slim(tmp_path) -> None:
    pb = PromptBuilder(str(tmp_path))
    prompt = pb.build_parallel_plan(_steps(), fanout=2, mode=ExecutionMode.QUICK)
    assert "**Frontend Tasks**" not in prompt
    assert "ONLY its own allowed scope" in prompt


@pytest.mark.asyncio
async def test_agent_review_errors_only(tmp_path) -> None:
    from ninja_agent.models import AgentReviewRequest

    (tmp_path / "m.py").write_text("def f():\n    pass\n")  # missing docstring, short
    ex = AgentToolExecutor()
    res = await ex.review(AgentReviewRequest(repo_root=str(tmp_path), file_paths=["m.py"]))
    assert res.success
    # style noise removed: no docstring info findings
    assert all("docstring" not in (f.message or "") for f in res.findings)

    (tmp_path / "bad.py").write_text("def broken(:\n")
    res2 = await ex.review(AgentReviewRequest(repo_root=str(tmp_path), file_paths=["bad.py"]))
    assert any(f.severity == "critical" for f in res2.findings)


def test_researcher_prompts_cite_every_sentence() -> None:
    sources = [{"title": "S", "url": "https://ex.com", "snippet": "body", "date": "2026-01-01"}]
    sys_msg = build_report_messages("T", sources, "comprehensive")[0]["content"]
    assert "Cite every factual sentence" in sys_msg
    assert "direct 1-2 sentence answer" in sys_msg
    ans_sys = build_answer_messages("Q?", sources)[0]["content"]
    assert "say so explicitly" in ans_sys


@pytest.mark.asyncio
async def test_researcher_factcheck_uncertain_without_engine(tmp_path, monkeypatch) -> None:
    from ninja_researcher import tools as rtools
    from ninja_researcher.models import FactCheckRequest

    monkeypatch.setenv("NINJA_RESEARCHER_LLM", "off")
    ex = rtools.ResearchToolExecutor()
    res = await ex.fact_check(FactCheckRequest(
        claim="the sky is blue",
        sources=["https://example.com/a"],
    ))
    assert res.status == "uncertain"
    assert "No synthesis engine" in res.verdict
