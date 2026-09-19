"""
Tests for deep-research domain filters (P1-3).

Filter helpers are tested directly, and integration is exercised through
``deep_research`` with a mocked provider (enrich disabled).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from ninja_researcher.models import DeepResearchRequest
from ninja_researcher.tools import (
    ResearchToolExecutor,
    _apply_domain_filters,
    _host_matches,
    reset_executor,
)


class _Provider:
    """Provider returning a fixed ordered source list."""

    def __init__(self, sources: list[dict[str, Any]]) -> None:
        self._sources = sources

    def is_available(self) -> bool:
        return True

    def get_name(self) -> str:
        return "fake"

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        return list(self._sources)


def _source(url: str) -> dict[str, Any]:
    """Build a minimal source dict."""
    return {"title": url, "url": url, "snippet": "s"}


async def _research(sources: list[dict[str, Any]], **kwargs: Any) -> Any:
    """Run deep_research with a mocked provider and no enrichment."""
    reset_executor()
    executor = ResearchToolExecutor()
    provider = _Provider(sources)
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
        return await executor.deep_research(
            DeepResearchRequest(topic="t", queries=["q"], enrich=False, **kwargs)
        )


def test_host_matches_suffix_including_subdomains() -> None:
    """Suffix matching covers the bare domain and all subdomains."""
    assert _host_matches("arxiv.org", ["arxiv.org"])
    assert _host_matches("export.arxiv.org", ["arxiv.org"])
    assert not _host_matches("notarxiv.org", ["arxiv.org"])
    assert not _host_matches("arxiv.org.evil.com", ["arxiv.org"])


def test_apply_domain_filters_exclude_and_include_precedence() -> None:
    """Exclusion always wins over inclusion."""
    sources = [
        _source("https://arxiv.org/a"),
        _source("https://export.arxiv.org/b"),
        _source("https://example.com/c"),
    ]

    only_arxiv = _apply_domain_filters(sources, ["arxiv.org"], None, None)
    assert [s["url"] for s in only_arxiv] == [
        "https://arxiv.org/a",
        "https://export.arxiv.org/b",
    ]

    excluded = _apply_domain_filters(sources, ["arxiv.org"], ["arxiv.org"], None)
    assert excluded == []

    drop_subdomain = _apply_domain_filters(sources, None, ["export.arxiv.org"], None)
    assert [s["url"] for s in drop_subdomain] == [
        "https://arxiv.org/a",
        "https://example.com/c",
    ]


def test_apply_domain_filters_prefer_is_stable() -> None:
    """Prefer ordering moves matches first and preserves relative order."""
    sources = [
        _source("https://a.com/1"),
        _source("https://b.com/2"),
        _source("https://arxiv.org/3"),
        _source("https://c.com/4"),
    ]

    ordered = _apply_domain_filters(sources, None, None, ["arxiv.org"])
    assert [s["url"] for s in ordered] == [
        "https://arxiv.org/3",
        "https://a.com/1",
        "https://b.com/2",
        "https://c.com/4",
    ]


@pytest.mark.asyncio
async def test_deep_research_no_filters_is_unchanged() -> None:
    """With no filters, source order and count are unchanged."""
    sources = [_source("https://a.com/1"), _source("https://b.com/2")]
    result = await _research(sources)

    assert result.status == "ok"
    assert [s["url"] for s in result.sources] == ["https://a.com/1", "https://b.com/2"]


@pytest.mark.asyncio
async def test_deep_research_filters_before_enrichment() -> None:
    """Excluded sources are dropped from the result entirely."""
    sources = [
        _source("https://arxiv.org/a"),
        _source("https://spam.com/b"),
    ]
    result = await _research(sources, exclude_domains=["spam.com"])

    assert [s["url"] for s in result.sources] == ["https://arxiv.org/a"]


@pytest.mark.asyncio
async def test_deep_research_prefer_ordering() -> None:
    """prefer_domains reorders sources with matches first."""
    sources = [
        _source("https://a.com/1"),
        _source("https://arxiv.org/2"),
        _source("https://b.com/3"),
    ]
    result = await _research(sources, prefer_domains=["arxiv.org"])

    assert [s["url"] for s in result.sources] == [
        "https://arxiv.org/2",
        "https://a.com/1",
        "https://b.com/3",
    ]
