"""
arXiv integration for the Researcher module.

Provides structured arXiv search over the public Atom API and full-text
fetching of arXiv papers (preferring the ar5iv HTML rendering) plus generic
web-page content extraction.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

import httpx

from ninja_common.logging_utils import get_logger
from ninja_researcher.models import ArxivPaper, ErrorInfo, ErrorKind, ExtractedNumber, PaperContent
from ninja_researcher.search_providers import ProviderError, provider_error_from_status


logger = get_logger(__name__)


ARXIV_API_URL = "http://export.arxiv.org/api/query"
AR5IV_URL = "https://ar5iv.labs.arxiv.org/html/{paper_id}"
ARXIV_ABS_URL = "https://arxiv.org/abs/{paper_id}"
USER_AGENT = "ninja-mcp-researcher/ninja-mcp"

_SORT_BY = {
    "relevance": "relevance",
    "lastUpdatedDate": "lastUpdatedDate",
    "submittedDate": "submittedDate",
}

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"
_NS = {"atom": _ATOM_NS, "arxiv": _ARXIV_NS}

_ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")
_NUMBER_RE = re.compile(
    r"\d+(?:[.,]\d+)?(?:\s*[-\u2013]\s*\d+(?:[.,]\d+)?)?"
    r"\s*(?:%|pp|bps|x|billion|million|thousand|ms|s)?",
    re.IGNORECASE,
)


def parse_arxiv_id(source: str) -> str | None:
    """
    Extract a normalized (version-less) arXiv id from a URL or bare id.

    Accepts ``arxiv.org/abs/<id>``, ``arxiv.org/pdf/<id>``,
    ``ar5iv.labs.arxiv.org/html/<id>``, ``export.arxiv.org/abs/<id>`` and bare
    ids (optionally with a ``vN`` suffix).

    Args:
        source: URL or bare identifier.

    Returns:
        The version-less id, or ``None`` when the source is not an arXiv id.
    """
    if not source:
        return None
    stripped = source.strip()
    if not stripped:
        return None

    bare = re.fullmatch(r"(\d{4}\.\d{4,5})(?:v\d+)?", stripped)
    if bare:
        return bare.group(1)

    candidate = stripped if "://" in stripped else f"https://{stripped}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    if not (host == "arxiv.org" or host.endswith(".arxiv.org")):
        return None

    match = _ARXIV_ID_RE.search(parsed.path)
    if match:
        return match.group(1)
    return None


def _error_info(error: ProviderError) -> ErrorInfo:
    """Convert a :class:`ProviderError` into an :class:`ErrorInfo` payload."""
    return ErrorInfo(kind=error.kind, message=error.message, retry_after_s=error.retry_after_s)


def _collapse(text: str | None) -> str:
    """Collapse all whitespace in *text* into single spaces."""
    if not text:
        return ""
    return " ".join(text.split())


def _build_search_query(query: str, categories: list[str] | None) -> str:
    """Build an arXiv ``search_query`` value from a query and category list."""
    parts = [f"all:{query}"]
    for category in categories or []:
        cleaned = category.strip()
        if cleaned:
            parts.append(f"cat:{cleaned}")
    return " AND ".join(parts)


def _parse_arxiv_feed(xml_text: str) -> list[ArxivPaper]:
    """
    Parse an arXiv Atom feed into a list of :class:`ArxivPaper`.

    Args:
        xml_text: Raw Atom XML response body.

    Returns:
        Papers in feed order, excluding withdrawn entries.

    Raises:
        ProviderError: When the XML cannot be parsed.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ProviderError(ErrorKind.parse, "arXiv returned malformed XML") from exc

    papers: list[ArxivPaper] = []
    for entry in root.findall("atom:entry", _NS):
        raw_id = entry.findtext("atom:id", default="", namespaces=_NS)
        paper_id = parse_arxiv_id(raw_id)
        if not paper_id:
            continue

        comment = _collapse(entry.findtext("arxiv:comment", default="", namespaces=_NS))
        if "withdrawn" in comment.lower():
            continue

        authors = [
            _collapse(name.text)
            for name in entry.findall("atom:author/atom:name", _NS)
            if name.text
        ]
        categories = [
            category.get("term", "")
            for category in entry.findall("atom:category", _NS)
            if category.get("term")
        ]
        primary = entry.find("arxiv:primary_category", _NS)
        primary_category = primary.get("term", "") if primary is not None else ""

        papers.append(
            ArxivPaper(
                id=paper_id,
                title=_collapse(entry.findtext("atom:title", default="", namespaces=_NS)),
                authors=authors,
                abstract=_collapse(entry.findtext("atom:summary", default="", namespaces=_NS)),
                url=ARXIV_ABS_URL.format(paper_id=paper_id),
                published=_collapse(entry.findtext("atom:published", default="", namespaces=_NS)),
                updated=_collapse(entry.findtext("atom:updated", default="", namespaces=_NS)),
                categories=categories,
                primary_category=primary_category,
                comment=comment or None,
            )
        )
    return papers


async def arxiv_search(
    query: str,
    categories: list[str] | None = None,
    max_results: int = 10,
    sort_by: str = "relevance",
    full_metadata: bool = False,
) -> list[ArxivPaper]:
    """
    Search arXiv via the public Atom API.

    Args:
        query: Free-text search query.
        categories: Optional arXiv categories ANDed with the query.
        max_results: Maximum number of papers (clamped to 1..50).
        sort_by: One of ``relevance``, ``lastUpdatedDate``, ``submittedDate``.
        full_metadata: Retained for API symmetry; parsing is identical.

    Returns:
        Matching papers, excluding withdrawn entries.

    Raises:
        ProviderError: On network, HTTP, or parse failures.
    """
    del full_metadata  # parsing always returns full metadata; caller may trim
    clamped = max(1, min(50, max_results))
    params: dict[str, str | int] = {
        "search_query": _build_search_query(query, categories),
        "start": 0,
        "max_results": clamped,
        "sortBy": _SORT_BY.get(sort_by, "relevance"),
    }

    try:
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            response = await client.get(ARXIV_API_URL, params=params)
            response.raise_for_status()
            text = response.text
    except httpx.HTTPStatusError as exc:
        raise provider_error_from_status(exc.response) from exc
    except httpx.TimeoutException as exc:
        raise ProviderError(ErrorKind.upstream, "arXiv request timed out") from exc
    except httpx.HTTPError as exc:
        raise ProviderError(ErrorKind.upstream, "arXiv request failed") from exc

    return _parse_arxiv_feed(text)


async def _fetch_text(url: str) -> str:
    """
    Fetch a URL and return its response body.

    Args:
        url: Page to fetch.

    Returns:
        Response body text.

    Raises:
        ProviderError: On network or HTTP failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as exc:
        raise provider_error_from_status(exc.response) from exc
    except httpx.TimeoutException as exc:
        raise ProviderError(ErrorKind.upstream, "Page request timed out") from exc
    except httpx.HTTPError as exc:
        raise ProviderError(ErrorKind.upstream, "Page request failed") from exc


async def _fetch_html_for_source(source: str, arxiv_id: str | None) -> str:
    """
    Fetch HTML for a source, preferring ar5iv for arXiv ids.

    Args:
        source: Original source string.
        arxiv_id: Normalized arXiv id, if the source is an arXiv reference.

    Returns:
        HTML body.

    Raises:
        ProviderError: When both the preferred and fallback fetches fail.
    """
    if arxiv_id:
        try:
            return await _fetch_text(AR5IV_URL.format(paper_id=arxiv_id))
        except ProviderError as exc:
            if exc.kind is ErrorKind.rate_limited:
                raise
            logger.info(f"ar5iv unavailable for {arxiv_id}, falling back to abs page")
        return await _fetch_text(ARXIV_ABS_URL.format(paper_id=arxiv_id))
    return await _fetch_text(source)


def _extract_sections(soup: Any, sections: list[str]) -> dict[str, str]:
    """
    Extract requested sections from a parsed document.

    Args:
        soup: Parsed BeautifulSoup document.
        sections: Case-insensitive section heading names.

    Returns:
        Mapping of requested section name to its extracted text.
    """
    headings = soup.find_all(re.compile(r"^h[1-4]$"))
    extracted: dict[str, str] = {}
    for requested in sections:
        needle = requested.strip().lower()
        if not needle:
            continue
        for index, heading in enumerate(headings):
            heading_text = _collapse(heading.get_text(" ", strip=True))
            if needle not in heading_text.lower():
                continue
            level = int(heading.name[1])
            parts = [heading_text]
            for following in headings[index + 1 :]:
                if int(following.name[1]) <= level:
                    break
                parts.append(_collapse(following.get_text(" ", strip=True)))
            # Include paragraph text between headings.
            for sibling in heading.next_siblings:
                if getattr(sibling, "name", None) in {"h1", "h2", "h3", "h4"}:
                    break
                if getattr(sibling, "name", None):
                    text = _collapse(sibling.get_text(" ", strip=True))
                    if text:
                        parts.append(text)
            extracted[requested] = "\n".join(part for part in parts if part)
            break
    return extracted


def _extract_numbers(text: str, section: str) -> list[ExtractedNumber]:
    """
    Extract numeric tokens with their containing sentence.

    Args:
        text: Text to scan.
        section: Section label to attach to each number.

    Returns:
        Deduplicated numeric tokens (order preserved).
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    numbers: list[ExtractedNumber] = []
    seen: set[tuple[str, str]] = set()
    for sentence in sentences:
        cleaned_sentence = _collapse(sentence)
        if not cleaned_sentence:
            continue
        for match in _NUMBER_RE.finditer(cleaned_sentence):
            value = _collapse(match.group(0))
            if not value:
                continue
            key = (value, cleaned_sentence)
            if key in seen:
                continue
            seen.add(key)
            numbers.append(ExtractedNumber(value=value, context=cleaned_sentence, section=section))
            if len(numbers) >= 200:
                return numbers
    return numbers


async def fetch_paper(
    source: str,
    sections: list[str] | None,
    extract_numbers: bool,
) -> PaperContent:
    """
    Fetch and parse a paper or web page.

    For arXiv sources the ar5iv HTML rendering is preferred, falling back to
    the abstract page. Non-arXiv URLs are fetched directly.

    Args:
        source: arXiv URL/id or generic URL.
        sections: Optional section headings to extract.
        extract_numbers: Whether to extract numeric tokens with context.

    Returns:
        Parsed :class:`PaperContent`; failures are embedded in ``error``.
    """
    arxiv_id = parse_arxiv_id(source)

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return PaperContent(
            source=source,
            arxiv_id=arxiv_id,
            error=ErrorInfo(
                kind=ErrorKind.env,
                message=(
                    "Missing optional dependency 'bs4'. Install it with the "
                    "researcher/runtime extra, e.g. `uv pip install beautifulsoup4`."
                ),
            ),
        )

    try:
        html = await _fetch_html_for_source(source, arxiv_id)
    except ProviderError as exc:
        return PaperContent(source=source, arxiv_id=arxiv_id, error=_error_info(exc))

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    title = _collapse(soup.title.get_text(" ", strip=True) if soup.title else "")
    if not title:
        heading = soup.find(["h1", "h2"])
        title = _collapse(heading.get_text(" ", strip=True)) if heading else ""

    abstract = ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    meta_attrs = getattr(meta, "attrs", None) if meta is not None else None
    if isinstance(meta_attrs, dict) and meta_attrs.get("content"):
        abstract = _collapse(str(meta_attrs.get("content", "")))
    if not abstract:
        abstract_node = soup.find(id=re.compile("abstract", re.IGNORECASE))
        if abstract_node is not None:
            abstract = _collapse(abstract_node.get_text(" ", strip=True))

    requested = sections or []
    section_texts = _extract_sections(soup, requested) if requested else {}

    numbers: list[ExtractedNumber] = []
    if extract_numbers:
        body_text = _collapse(soup.get_text(" ", strip=True))
        numbers = _extract_numbers(body_text, section=requested[0] if requested else "")

    return PaperContent(
        source=source,
        arxiv_id=arxiv_id,
        title=title,
        abstract=abstract,
        sections=section_texts,
        numbers=numbers,
    )
