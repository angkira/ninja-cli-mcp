"""
Tests for quick research, Perplexity-native deep research, and LLM report synthesis.

No network access is performed; providers and the synthesis engine are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ninja_researcher.models import (
    DeepResearchRequest,
    ErrorKind,
    GenerateReportRequest,
    QuickResearchRequest,
)
from ninja_researcher.search_providers import SearchProviderFactory
from ninja_researcher.tools import ResearchToolExecutor, reset_executor


@pytest.fixture(autouse=True)
def _env_only_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve secrets from env only so the developer store never affects tests."""
    import os

    from ninja_common import secrets

    monkeypatch.setattr(secrets, "get_secret", lambda name: os.environ.get(name))


def make_executor() -> ResearchToolExecutor:
    """Create a fresh executor with a clean global singleton."""
    reset_executor()
    return ResearchToolExecutor()


def _perplexity_provider(answer: str = "ANSWER", citations: list[str] | None = None):
    """Build a mocked Perplexity provider that returns a cited answer."""
    cites = citations or []
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.get_name.return_value = "perplexity"
    provider.supports_answers = True
    provider.research = AsyncMock(
        return_value={
            "answer": answer,
            "sources": [
                {"title": f"source {i}", "url": url, "snippet": ""}
                for i, url in enumerate(cites, 1)
            ],
            "citations": cites,
            "model": "sonar",
        }
    )
    return provider


def _engine(label: str = "openrouter/m") -> MagicMock:
    """Build a mocked synthesis engine with a stable label."""
    engine = MagicMock()
    engine.label = label
    return engine


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def test_default_provider_honours_configured_perplexity(monkeypatch: pytest.MonkeyPatch) -> None:
    """NINJA_SEARCH_PROVIDER=perplexity is honoured when a key is present."""
    monkeypatch.setenv("NINJA_SEARCH_PROVIDER", "perplexity")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    assert SearchProviderFactory.get_default_provider() == "perplexity"


def test_default_provider_ignores_unavailable_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured provider without a key falls back to DuckDuckGo."""
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setenv("NINJA_SEARCH_PROVIDER", "perplexity")
    assert SearchProviderFactory.get_default_provider() == "duckduckgo"


# ---------------------------------------------------------------------------
# quick_research
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quick_research_perplexity_returns_cited_answer() -> None:
    """With Perplexity selected, the native cited answer is returned."""
    executor = make_executor()
    provider = _perplexity_provider("The sky is blue.", ["https://a.com", "https://b.com"])

    with (
        patch.object(executor.provider_factory, "get_default_provider", return_value="perplexity"),
        patch.object(executor.provider_factory, "get_provider", return_value=provider),
    ):
        result = await executor.quick_research(QuickResearchRequest(query="why is the sky blue?"))

    assert result.status == "ok"
    assert result.provider == "perplexity"
    assert result.answer == "The sky is blue."
    assert len(result.sources) == 2
    provider.research.assert_awaited_once()


@pytest.mark.asyncio
async def test_quick_research_explicit_provider_is_used() -> None:
    """An explicit provider overrides the default."""
    executor = make_executor()
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.search = AsyncMock(
        return_value=[{"title": "T", "url": "https://x.com", "snippet": "body"}]
    )

    with patch.object(
        executor.provider_factory, "get_provider", return_value=provider
    ) as get_provider:
        result = await executor.quick_research(
            QuickResearchRequest(query="q", search_provider="duckduckgo", enrich=False)
        )

    get_provider.assert_called_once_with("duckduckgo")
    assert result.status == "ok"
    assert result.provider == "duckduckgo"


@pytest.mark.asyncio
async def test_quick_research_unavailable_provider_is_env_error() -> None:
    """An unavailable provider (missing key) yields a typed env error."""
    executor = make_executor()
    provider = MagicMock()
    provider.is_available.return_value = False

    with patch.object(executor.provider_factory, "get_provider", return_value=provider):
        result = await executor.quick_research(
            QuickResearchRequest(query="q", search_provider="serper")
        )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == ErrorKind.env


@pytest.mark.asyncio
async def test_quick_research_invalid_provider_is_typed_error() -> None:
    """An unknown provider is classified, not raised."""
    executor = make_executor()
    result = await executor.quick_research(
        QuickResearchRequest(query="q", search_provider="not-a-provider")
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == ErrorKind.parse


@pytest.mark.asyncio
async def test_quick_research_synthesizes_answer_with_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a non-Perplexity provider and an engine, a cited answer is synthesized."""
    monkeypatch.setenv("NINJA_RESEARCHER_LLM", "openrouter")
    executor = make_executor()
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.search = AsyncMock(
        return_value=[{"title": "T", "url": "https://x.com", "snippet": "body"}]
    )

    with (
        patch.object(executor.provider_factory, "get_provider", return_value=provider),
        patch(
            "ninja_researcher.tools.resolve_synthesis_engine", return_value=_engine("openrouter/m")
        ),
        patch("ninja_researcher.tools.synthesize_answer", AsyncMock(return_value="SYNTH")),
    ):
        result = await executor.quick_research(
            QuickResearchRequest(query="q", search_provider="duckduckgo", enrich=False)
        )

    assert result.status == "ok"
    assert result.answer == "SYNTH"
    assert result.model == "openrouter/m"


# ---------------------------------------------------------------------------
# deep_research report synthesis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deep_research_synthesizes_report_with_engine() -> None:
    """Deep research gathers sources via the provider and adds a synthesized report."""
    executor = make_executor()
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.search = AsyncMock(
        return_value=[{"title": "T", "url": "https://a.com", "snippet": "body"}]
    )
    engine = _engine("perplexity/sonar-pro")

    with (
        patch.object(executor.provider_factory, "get_default_provider", return_value="perplexity"),
        patch.object(executor.provider_factory, "get_provider", return_value=provider),
        patch("ninja_researcher.tools.resolve_synthesis_engine", return_value=engine),
        patch("ninja_researcher.tools.synthesize_report", AsyncMock(return_value="# REPORT")),
    ):
        result = await executor.deep_research(
            DeepResearchRequest(topic="Topic", queries=["q1"], max_sources=5, enrich=False)
        )

    assert result.status == "ok"
    assert result.provider == "perplexity"
    assert result.sources_found == 1
    assert result.report == "# REPORT"


@pytest.mark.asyncio
async def test_deep_research_report_empty_without_engine() -> None:
    """Without a synthesis engine the report is empty but sources are returned."""
    executor = make_executor()
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.search = AsyncMock(
        return_value=[{"title": "T", "url": "https://a.com", "snippet": "body"}]
    )

    with (
        patch.object(executor.provider_factory, "get_default_provider", return_value="duckduckgo"),
        patch.object(executor.provider_factory, "get_provider", return_value=provider),
    ):
        result = await executor.deep_research(
            DeepResearchRequest(topic="Topic", queries=["q1"], max_sources=5, enrich=False)
        )

    assert result.status == "ok"
    assert result.sources_found == 1
    assert result.report == ""


# ---------------------------------------------------------------------------
# generate_report synthesis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_report_uses_llm_when_engine_available() -> None:
    """Report generation calls the engine and reports the model used."""
    executor = make_executor()
    engine = _engine("perplexity/sonar-pro")

    with (
        patch("ninja_researcher.tools.resolve_synthesis_engine", return_value=engine),
        patch("ninja_researcher.tools.synthesize_report", AsyncMock(return_value="# LLM REPORT")),
    ):
        result = await executor.generate_report(
            GenerateReportRequest(
                topic="T",
                sources=[{"title": "S", "url": "u", "snippet": "b"}],
            )
        )

    assert result.status == "ok"
    assert result.report == "# LLM REPORT"
    assert result.model == "perplexity/sonar-pro"


@pytest.mark.asyncio
async def test_generate_report_template_when_no_engine() -> None:
    """Without an engine the deterministic template is used (model empty)."""
    executor = make_executor()
    result = await executor.generate_report(
        GenerateReportRequest(
            topic="T",
            sources=[{"title": "S", "url": "u", "snippet": "b"}],
            report_type="summary",
        )
    )
    assert result.status == "ok"
    assert result.report.startswith("# Summary")
    assert result.model == ""


@pytest.mark.asyncio
async def test_generate_report_use_llm_false_forces_template() -> None:
    """use_llm=False skips synthesis even when an engine is available."""
    executor = make_executor()
    engine = _engine("x/y")

    with (
        patch("ninja_researcher.tools.resolve_synthesis_engine", return_value=engine),
        patch(
            "ninja_researcher.tools.synthesize_report",
            AsyncMock(return_value="# LLM REPORT"),
        ) as synth,
    ):
        result = await executor.generate_report(
            GenerateReportRequest(
                topic="T",
                sources=[{"title": "S", "url": "u", "snippet": "b"}],
                report_type="summary",
                use_llm=False,
            )
        )

    synth.assert_not_awaited()
    assert result.report.startswith("# Summary")
    assert result.model == ""


@pytest.mark.asyncio
async def test_generate_report_falls_back_to_template_on_engine_failure() -> None:
    """A synthesis failure degrades to the template instead of erroring."""
    executor = make_executor()
    engine = _engine("x/y")

    with (
        patch("ninja_researcher.tools.resolve_synthesis_engine", return_value=engine),
        patch(
            "ninja_researcher.tools.synthesize_report",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        result = await executor.generate_report(
            GenerateReportRequest(
                topic="T",
                sources=[{"title": "S", "url": "u", "snippet": "b"}],
                report_type="summary",
            )
        )

    assert result.status == "ok"
    assert result.report.startswith("# Summary")
    assert result.model == ""
