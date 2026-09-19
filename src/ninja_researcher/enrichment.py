"""
Source enrichment for the Researcher module.

Replaces synthetic provider snippets with real page-extracted text and
classifies each source by domain. All failures degrade silently to the
provider-provided values; enrichment never raises and never delays a result
beyond the configured per-fetch timeout.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import httpx

from ninja_common.logging_utils import get_logger


logger = get_logger(__name__)


USER_AGENT = "ninja-mcp-researcher/ninja-mcp"
_MIN_SNIPPET_CHARS = 200
_MAX_SNIPPET_CHARS = 1200

_PAPER_DOMAINS = (
    "arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "semanticscholar.org",
    "neurips.cc",
)
_REPO_DOMAINS = ("github.com", "gitlab.com")
_VIDEO_DOMAINS = ("youtube.com", "youtu.be")


def classify_source_type(url: str) -> str:
    """
    Classify a URL into a coarse source type by domain.

    Args:
        url: Source URL.

    Returns:
        One of ``paper``, ``repo``, ``academic``, ``video`` or ``web``.
    """
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    if any(host == domain or host.endswith(f".{domain}") for domain in _PAPER_DOMAINS):
        return "paper"
    if any(host == domain or host.endswith(f".{domain}") for domain in _REPO_DOMAINS):
        return "repo"
    if host.endswith(".edu"):
        return "academic"
    if any(host == domain or host.endswith(f".{domain}") for domain in _VIDEO_DOMAINS):
        return "video"
    return "web"


def _extract_page_text(html: str) -> tuple[str, str]:
    """
    Extract a real title and a substantial text block from an HTML page.

    Args:
        html: Raw HTML body.

    Returns:
        ``(title, snippet)`` where snippet may be empty when no usable block
        of at least :data:`_MIN_SNIPPET_CHARS` characters exists.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    title = ""
    if soup.title is not None:
        title = " ".join(soup.title.get_text(" ", strip=True).split())

    meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    description = ""
    meta_attrs = getattr(meta, "attrs", None) if meta is not None else None
    if isinstance(meta_attrs, dict) and meta_attrs.get("content"):
        description = " ".join(str(meta_attrs.get("content", "")).split())

    snippet = ""
    if len(description) >= _MIN_SNIPPET_CHARS:
        snippet = description
    else:
        for block in soup.find_all(["p", "article", "section", "div"]):
            text = " ".join(block.get_text(" ", strip=True).split())
            if len(text) >= _MIN_SNIPPET_CHARS:
                snippet = text
                break

    snippet = snippet[:_MAX_SNIPPET_CHARS]
    return title, snippet


async def _fetch_one(url: str, timeout_s: float) -> tuple[str, str]:
    """
    Fetch and extract one URL.

    Args:
        url: URL to fetch.
        timeout_s: Per-fetch timeout in seconds.

    Returns:
        ``(title, snippet)``; both empty on any failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout_s, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return _extract_page_text(response.text)
    except Exception as exc:
        logger.info(f"Enrichment failed for {url}: {exc}")
        return "", ""


async def enrich_sources(
    sources: list[dict[str, Any]],
    max_concurrency: int = 5,
    timeout_s: float = 15.0,
) -> list[dict[str, Any]]:
    """
    Enrich provider sources with real page text and source types.

    Each unique URL is fetched at most once under a semaphore. A successful
    extraction replaces ``snippet`` when it yields at least 200 characters and
    replaces ``title`` when a real one is found; otherwise the provider values
    are retained. ``source_type`` is always set from the domain.

    Args:
        sources: Provider source dicts with at least ``url``.
        max_concurrency: Maximum simultaneous page fetches.
        timeout_s: Per-fetch timeout in seconds.

    Returns:
        A new list of enriched source dicts (order preserved).
    """
    unique_urls: list[str] = []
    seen: set[str] = set()
    for source in sources:
        url = str(source.get("url", ""))
        if url and url not in seen:
            seen.add(url)
            unique_urls.append(url)

    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _bounded(url: str) -> tuple[str, str]:
        async with semaphore:
            return await _fetch_one(url, timeout_s)

    fetched = await asyncio.gather(*[_bounded(url) for url in unique_urls])
    extracted: dict[str, tuple[str, str]] = dict(zip(unique_urls, fetched, strict=False))

    enriched: list[dict[str, Any]] = []
    for source in sources:
        url = str(source.get("url", ""))
        new_source = dict(source)
        new_source["source_type"] = classify_source_type(url)

        title, snippet = extracted.get(url, ("", ""))
        if title:
            new_source["title"] = title
        if snippet and len(snippet) >= _MIN_SNIPPET_CHARS:
            new_source["snippet"] = snippet
        enriched.append(new_source)

    return enriched
