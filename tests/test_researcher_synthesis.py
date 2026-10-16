"""
Unit tests for the researcher LLM synthesis engine.

No network access is performed; ``httpx`` and secret access are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ninja_researcher import synthesis
from ninja_researcher.synthesis import (
    SynthesisEngine,
    build_answer_messages,
    build_report_messages,
    complete,
    resolve_synthesis_engine,
    synthesize_answer,
    synthesize_report,
)


def _secrets(mapping: dict[str, str]):
    """Return a get_secret replacement backed by a fixed mapping."""
    return lambda name: mapping.get(name)


@pytest.fixture(autouse=True)
def _clean_engine_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear engine-selection env vars so leaked values never affect resolution."""
    for var in ("NINJA_RESEARCHER_MODEL", "NINJA_RESEARCHER_LLM", "NINJA_SEARCH_PROVIDER"):
        monkeypatch.delenv(var, raising=False)


def test_resolve_engine_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit off switch disables synthesis entirely."""
    monkeypatch.setenv("NINJA_RESEARCHER_LLM", "off")
    monkeypatch.setattr(synthesis, "get_secret", _secrets({"PERPLEXITY_API_KEY": "pk"}))
    assert resolve_synthesis_engine() is None


def test_resolve_engine_auto_prefers_perplexity(monkeypatch: pytest.MonkeyPatch) -> None:
    """In auto mode Perplexity wins when both keys are present."""
    monkeypatch.setenv("NINJA_RESEARCHER_LLM", "auto")
    monkeypatch.setattr(
        synthesis,
        "get_secret",
        _secrets({"PERPLEXITY_API_KEY": "pk", "OPENROUTER_API_KEY": "ok"}),
    )
    engine = resolve_synthesis_engine()
    assert engine is not None
    assert engine.kind == "perplexity"
    assert engine.model == "sonar-pro"
    assert engine.label == "perplexity/sonar-pro"


def test_resolve_engine_auto_falls_back_to_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a Perplexity key auto mode selects OpenRouter."""
    monkeypatch.setenv("NINJA_RESEARCHER_LLM", "auto")
    monkeypatch.setattr(synthesis, "get_secret", _secrets({"OPENROUTER_API_KEY": "ok"}))
    engine = resolve_synthesis_engine()
    assert engine is not None
    assert engine.kind == "openrouter"
    assert engine.model == "anthropic/claude-sonnet-4"


def test_resolve_engine_honours_sonar_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare sonar model id is used with Perplexity."""
    monkeypatch.setenv("NINJA_RESEARCHER_LLM", "perplexity")
    monkeypatch.setenv("NINJA_RESEARCHER_MODEL", "sonar-reasoning")
    monkeypatch.setattr(synthesis, "get_secret", _secrets({"PERPLEXITY_API_KEY": "pk"}))
    engine = resolve_synthesis_engine()
    assert engine is not None
    assert engine.model == "sonar-reasoning"


def test_resolve_engine_perplexity_ignores_namespaced_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A namespaced model is not sent to Perplexity; the default sonar model is used."""
    monkeypatch.setenv("NINJA_RESEARCHER_LLM", "perplexity")
    monkeypatch.setenv("NINJA_RESEARCHER_MODEL", "anthropic/claude-sonnet-4")
    monkeypatch.setattr(synthesis, "get_secret", _secrets({"PERPLEXITY_API_KEY": "pk"}))
    engine = resolve_synthesis_engine()
    assert engine is not None
    assert engine.model == "sonar-pro"


def test_resolve_engine_missing_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """A forced engine with no key resolves to None."""
    monkeypatch.setenv("NINJA_RESEARCHER_LLM", "perplexity")
    monkeypatch.setattr(synthesis, "get_secret", _secrets({}))
    assert resolve_synthesis_engine() is None


@pytest.mark.asyncio
async def test_complete_returns_content_and_citations() -> None:
    """complete() strips content and filters non-string citations."""
    engine = SynthesisEngine("perplexity", "sonar", "k", "https://api.perplexity.ai")
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "  hello world  "}}],
        "citations": ["https://a.com", "https://b.com", 5],
    }
    mock_response.raise_for_status = MagicMock()

    with patch("ninja_researcher.synthesis.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        content, citations = await complete(
            engine, [{"role": "user", "content": "q"}], return_citations=True
        )

    assert content == "hello world"
    assert citations == ["https://a.com", "https://b.com"]


@pytest.mark.asyncio
async def test_synthesize_report_uses_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """synthesize_report returns the completion content."""
    engine = SynthesisEngine("openrouter", "m", "k", "https://openrouter.ai/api/v1")

    async def fake_complete(*_args, **_kwargs):
        return "REPORT BODY", []

    monkeypatch.setattr(synthesis, "complete", fake_complete)
    out = await synthesize_report(
        engine, "Topic", [{"title": "S", "url": "u", "snippet": "body"}], "technical"
    )
    assert out == "REPORT BODY"


@pytest.mark.asyncio
async def test_synthesize_answer_uses_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """synthesize_answer returns the completion content."""
    engine = SynthesisEngine("openrouter", "m", "k", "https://openrouter.ai/api/v1")

    async def fake_complete(*_args, **_kwargs):
        return "ANSWER", []

    monkeypatch.setattr(synthesis, "complete", fake_complete)
    out = await synthesize_answer(engine, "Q", [{"title": "S", "url": "u", "snippet": "b"}])
    assert out == "ANSWER"


def test_build_report_messages_includes_sources_and_topic() -> None:
    """The report prompt carries the topic and source bodies."""
    messages = build_report_messages(
        "My Topic", [{"title": "T", "url": "https://x", "snippet": "SNIPPET"}], "comprehensive"
    )
    assert messages[0]["role"] == "system"
    assert "My Topic" in messages[1]["content"]
    assert "SNIPPET" in messages[1]["content"]


def test_build_answer_messages_includes_question() -> None:
    """The answer prompt carries the question and sources."""
    messages = build_answer_messages("Q?", [{"title": "T", "url": "https://x", "snippet": "SNIP"}])
    assert "Q?" in messages[1]["content"]
    assert "SNIP" in messages[1]["content"]


def test_sources_block_truncates_long_bodies() -> None:
    """_sources_block caps each source body length."""
    long_body = "x" * 5000
    block = synthesis._sources_block([{"title": "T", "url": "u", "snippet": long_body}])
    assert len(block) < 5000
    assert "x" * 100 in block
