"""
Tests for typed error propagation across researcher tools (P0-1 / P0-2).

All providers and HTTP clients are mocked; no network access is performed.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from ninja_common.rate_balancer import reset_rate_balancer
from ninja_researcher.models import (
    DeepResearchRequest,
    ErrorKind,
    FactCheckRequest,
    SummarizeSourcesRequest,
)
from ninja_researcher.search_providers import ProviderError
from ninja_researcher.tools import ResearchToolExecutor, reset_executor


@pytest.fixture(autouse=True)
def _fresh_rate_balancer() -> None:
    """Reset the global rate balancer so tests never wait on shared tokens."""
    reset_rate_balancer()


def make_executor() -> ResearchToolExecutor:
    """Create a fresh executor with a clean global singleton."""
    reset_executor()
    return ResearchToolExecutor()


class _FakeProvider:
    """A provider whose behaviour is scripted per call."""

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.calls = 0

    def is_available(self) -> bool:
        """The fake provider is always available."""
        return True

    def get_name(self) -> str:
        """Return a stable fake provider name."""
        return "fake"

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Return or raise the next scripted outcome."""
        outcome = self._outcomes[min(self.calls, len(self._outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_deep_research_rate_limited_is_typed() -> None:
    """A rate-limited provider produces error.kind == 'rate_limited', not raw text."""
    provider = _FakeProvider(
        [ProviderError(ErrorKind.rate_limited, "boom-secret", retry_after_s=7.0)]
    )
    executor = make_executor()
    request = DeepResearchRequest(topic="topic", queries=["q1"], enrich=False)

    with (
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_default_provider",
            return_value="fake",
        ),
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_provider",
            return_value=provider,
        ),
    ):
        result = await executor.deep_research(request)

    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == ErrorKind.rate_limited
    assert result.error.retry_after_s == 7.0
    assert "boom-secret" not in result.summary
    assert result.summary == ""


@pytest.mark.asyncio
async def test_deep_research_all_fail_vs_partial_vs_empty() -> None:
    """Distinguish all-fail (error), partial-failure (ok), and legit-empty (no error)."""
    # All queries fail.
    all_fail = _FakeProvider([ProviderError(ErrorKind.upstream, "nope")])
    executor = make_executor()
    with (
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_default_provider",
            return_value="fake",
        ),
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_provider",
            return_value=all_fail,
        ),
    ):
        failed = await executor.deep_research(
            DeepResearchRequest(topic="t", queries=["q1", "q2"], enrich=False)
        )
    assert failed.status == "error"
    assert failed.error is not None
    assert failed.error.kind == ErrorKind.upstream

    # Partial: first query fails, second succeeds.
    partial = _FakeProvider(
        [
            ProviderError(ErrorKind.upstream, "nope"),
            [{"title": "T", "url": "https://example.com/a", "snippet": "s"}],
        ]
    )
    executor = make_executor()
    with (
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_default_provider",
            return_value="fake",
        ),
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_provider",
            return_value=partial,
        ),
    ):
        ok = await executor.deep_research(
            DeepResearchRequest(topic="t", queries=["q1", "q2"], enrich=False)
        )
    assert ok.status == "ok"
    assert ok.sources_found == 1
    assert ok.error is None

    # Legit empty: provider succeeds but finds nothing.
    empty = _FakeProvider([[]])
    executor = make_executor()
    with (
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_default_provider",
            return_value="fake",
        ),
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_provider",
            return_value=empty,
        ),
    ):
        none_found = await executor.deep_research(
            DeepResearchRequest(topic="t", queries=["q1"], enrich=False)
        )
    assert none_found.status == "ok"
    assert none_found.sources_found == 0
    assert none_found.error is None


@pytest.mark.asyncio
async def test_summarize_sources_missing_bs4_is_env_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing bs4 import becomes an 'env' error without leaking import text."""
    monkeypatch.setitem(sys.modules, "bs4", None)
    executor = make_executor()

    result = await executor.summarize_sources(
        SummarizeSourcesRequest(urls=["https://example.com"], max_length=100)
    )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == ErrorKind.env
    assert "No module named" not in result.combined_summary
    assert result.combined_summary == ""


class _FakeResponse:
    """Minimal httpx response stand-in."""

    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        """Raise an HTTPStatusError for non-2xx responses."""
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)


class _FakeAsyncClient:
    """Async-context httpx client returning a scripted response per URL."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def get(self, url: str, follow_redirects: bool = True) -> _FakeResponse:
        """Dispatch to the scripted handler."""
        return self._handler(url)


@pytest.mark.asyncio
async def test_summarize_sources_per_url_failure_is_isolated() -> None:
    """One failing URL gets a typed error; the other succeeds unaffected."""
    html = "<html><body><p>" + ("word " * 60) + "</p></body></html>"

    def handler(url: str) -> _FakeResponse:
        if "bad" in url:
            raise httpx.ConnectError("connection refused")
        return _FakeResponse(html)

    executor = make_executor()
    with patch("httpx.AsyncClient", lambda *a, **k: _FakeAsyncClient(handler)):
        result = await executor.summarize_sources(
            SummarizeSourcesRequest(
                urls=["https://good.example.com", "https://bad.example.com"],
                max_length=100,
            )
        )

    assert result.status == "partial"
    by_url = {entry["url"]: entry for entry in result.summaries}
    assert by_url["https://good.example.com"]["status"] == "ok"
    assert by_url["https://bad.example.com"]["status"] == "error"
    assert by_url["https://bad.example.com"]["error"]["kind"] == "upstream"
    assert "connection refused" not in by_url["https://bad.example.com"]["summary"]
    assert result.combined_summary


@pytest.mark.asyncio
async def test_fact_check_provider_error_is_typed() -> None:
    """A provider failure during auto-search surfaces as a typed error."""
    provider = _FakeProvider([ProviderError(ErrorKind.rate_limited, "boom-secret", 3.0)])
    executor = make_executor()

    with (
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_default_provider",
            return_value="fake",
        ),
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_provider",
            return_value=provider,
        ),
    ):
        result = await executor.fact_check(FactCheckRequest(claim="the sky is blue"))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == ErrorKind.rate_limited
    assert "boom-secret" not in result.verdict
    assert result.verdict == ""


@pytest.mark.asyncio
async def test_generate_report_error_is_typed() -> None:
    """An unexpected failure produces a typed error and an empty report body."""
    from ninja_researcher.models import GenerateReportRequest

    executor = make_executor()
    with patch.object(
        executor,
        "_generate_comprehensive_report",
        side_effect=RuntimeError("boom-secret"),
    ):
        result = await executor.generate_report(
            GenerateReportRequest(
                topic="t",
                sources=[{"url": "https://example.com", "title": "T", "snippet": "s"}],
            )
        )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == ErrorKind.upstream
    assert result.report == ""
    assert "boom-secret" not in result.report
