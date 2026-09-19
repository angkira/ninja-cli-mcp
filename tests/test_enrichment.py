"""
Tests for source enrichment and domain-based source typing (P1-4).

HTTP is mocked; no network access is performed.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ninja_researcher.enrichment import classify_source_type, enrich_sources
from ninja_researcher.models import DeepResearchRequest
from ninja_researcher.tools import ResearchToolExecutor, reset_executor


def _long_text(marker: str) -> str:
    """Return a block of text longer than the 200-char snippet threshold."""
    return f"{marker} " + ("padding words " * 30)


class _FakeResponse:
    """Minimal httpx response stand-in."""

    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        """Raise an HTTPStatusError for non-2xx responses."""
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com")
            raise httpx.HTTPStatusError(
                "error", request=request, response=httpx.Response(self.status_code, request=request)
            )


class _FakeAsyncClient:
    """Async-context httpx client using a scripted handler."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def get(self, url: str, follow_redirects: bool = True) -> _FakeResponse:
        """Dispatch to the scripted handler."""
        return self._handler(url)


def test_classify_source_type() -> None:
    """Domains map to the expected coarse source types."""
    assert classify_source_type("https://arxiv.org/abs/2401.1") == "paper"
    assert classify_source_type("https://openreview.net/forum?id=x") == "paper"
    assert classify_source_type("https://github.com/foo/bar") == "repo"
    assert classify_source_type("https://www.gitlab.com/foo/bar") == "repo"
    assert classify_source_type("https://cs.stanford.edu/paper") == "academic"
    assert classify_source_type("https://youtube.com/watch?v=1") == "video"
    assert classify_source_type("https://example.com/post") == "web"


@pytest.mark.asyncio
async def test_enrich_extracts_title_and_meta() -> None:
    """A page title and a long meta description replace provider values."""
    html = (
        "<html><head><title>Real Page Title</title>"
        f'<meta name="description" content="{_long_text("meta")}"/></head>'
        "<body><p>short</p></body></html>"
    )
    sources = [{"title": "Search result 1", "url": "https://example.com/a", "snippet": "old"}]

    with patch(
        "httpx.AsyncClient", lambda *a, **k: _FakeAsyncClient(lambda url: _FakeResponse(html))
    ):
        enriched = await enrich_sources(sources)

    assert enriched[0]["title"] == "Real Page Title"
    assert enriched[0]["snippet"].startswith("meta")
    assert len(enriched[0]["snippet"]) >= 200
    assert enriched[0]["source_type"] == "web"


@pytest.mark.asyncio
async def test_enrich_falls_back_to_long_text_block() -> None:
    """Without a usable meta description, a long paragraph becomes the snippet."""
    html = (
        f"<html><head><title>T</title></head><body><p>{_long_text('paragraph')}</p></body></html>"
    )
    sources = [{"title": "T", "url": "https://example.com/a", "snippet": "old"}]

    with patch(
        "httpx.AsyncClient", lambda *a, **k: _FakeAsyncClient(lambda url: _FakeResponse(html))
    ):
        enriched = await enrich_sources(sources)

    assert enriched[0]["snippet"].startswith("paragraph")


@pytest.mark.asyncio
async def test_enrich_total_failure_retains_provider_values() -> None:
    """When every fetch fails, provider titles/snippets are retained."""

    def handler(url: str) -> _FakeResponse:
        raise httpx.ConnectError("no network")

    sources = [
        {"title": "Provider Title", "url": "https://example.com/a", "snippet": "provider snippet"}
    ]

    with patch("httpx.AsyncClient", lambda *a, **k: _FakeAsyncClient(handler)):
        enriched = await enrich_sources(sources)

    assert enriched[0]["title"] == "Provider Title"
    assert enriched[0]["snippet"] == "provider snippet"
    assert enriched[0]["source_type"] == "web"


@pytest.mark.asyncio
async def test_enrich_respects_concurrency_cap() -> None:
    """No more than max_concurrency fetches run simultaneously."""
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def handler(url: str) -> _FakeResponse:
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.01)
        async with lock:
            active -= 1
        return _FakeResponse("<html><title>T</title></html>")

    class _SleepingClient(_FakeAsyncClient):
        async def get(self, url: str, follow_redirects: bool = True) -> _FakeResponse:
            return await handler(url)

    sources = [{"url": f"https://example.com/{i}", "title": "t", "snippet": "s"} for i in range(6)]

    with patch("httpx.AsyncClient", lambda *a, **k: _SleepingClient(handler)):
        await enrich_sources(sources, max_concurrency=2)

    assert peak <= 2


@pytest.mark.asyncio
async def test_deep_research_enrich_false_skips_fetching() -> None:
    """enrich=False means enrich_sources is never invoked."""
    reset_executor()
    executor = ResearchToolExecutor()

    class _Provider:
        def is_available(self) -> bool:
            return True

        def get_name(self) -> str:
            return "fake"

        async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
            return [{"title": "T", "url": "https://example.com/a", "snippet": "s"}]

    with (
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_default_provider",
            return_value="fake",
        ),
        patch(
            "ninja_researcher.tools.SearchProviderFactory.get_provider",
            return_value=_Provider(),
        ),
        patch("ninja_researcher.tools.enrich_sources", new=AsyncMock()) as mocked,
    ):
        result = await executor.deep_research(
            DeepResearchRequest(topic="t", queries=["q"], enrich=False)
        )

    mocked.assert_not_awaited()
    assert result.sources_found == 1
