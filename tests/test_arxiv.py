"""
Tests for the arXiv search integration (P0-3).

Atom parsing, field mapping, withdrawn filtering, category ANDing, error
classification and max_results clamping are all exercised without network.
"""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import httpx
import pytest

from ninja_researcher.arxiv import arxiv_search, parse_arxiv_id
from ninja_researcher.models import ArxivSearchRequest, ErrorKind
from ninja_researcher.tools import ResearchToolExecutor, reset_executor


ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2401.12345v2</id>
    <updated>2024-02-01T00:00:00Z</updated>
    <published>2024-01-15T00:00:00Z</published>
    <title>  A Great   Paper  </title>
    <summary>  An   abstract about robots. </summary>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <arxiv:comment>Accepted at a conference</arxiv:comment>
    <arxiv:primary_category term="cs.RO"/>
    <category term="cs.RO"/>
    <category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.99999v1</id>
    <updated>2024-03-01T00:00:00Z</updated>
    <published>2024-03-01T00:00:00Z</published>
    <title>Withdrawn Paper</title>
    <summary>This was withdrawn.</summary>
    <author><name>Carol</name></author>
    <arxiv:comment>withdrawn by the authors</arxiv:comment>
    <category term="cs.LG"/>
  </entry>
</feed>
"""


class _FakeResponse:
    """Minimal httpx response stand-in."""

    def __init__(
        self, text: str = "", status_code: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        """Raise an HTTPStatusError for non-2xx responses."""
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://export.arxiv.org/api/query")
            response = httpx.Response(self.status_code, request=request, headers=self.headers)
            raise httpx.HTTPStatusError("error", request=request, response=response)


class _FakeAsyncClient:
    """Async-context httpx client capturing the last request params."""

    last_params: ClassVar[dict[str, Any]] = {}
    response: ClassVar[_FakeResponse] = _FakeResponse()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._response = _FakeAsyncClient.response

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def get(self, url: str, params: dict[str, Any] | None = None) -> _FakeResponse:
        """Record params and return the scripted response."""
        _FakeAsyncClient.last_params = params or {}
        return self._response


@pytest.fixture(autouse=True)
def _reset() -> None:
    """Reset the executor singleton between tests."""
    reset_executor()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("2401.12345", "2401.12345"),
        ("2401.12345v3", "2401.12345"),
        ("https://arxiv.org/abs/2401.12345", "2401.12345"),
        ("https://arxiv.org/abs/2401.12345v2", "2401.12345"),
        ("https://arxiv.org/pdf/2401.12345.pdf", "2401.12345"),
        ("https://ar5iv.labs.arxiv.org/html/2401.12345", "2401.12345"),
        ("https://export.arxiv.org/abs/2401.12345", "2401.12345"),
        ("https://example.com/2401.12345", None),
        ("not-an-id", None),
        ("", None),
    ],
)
def test_parse_arxiv_id(source: str, expected: str | None) -> None:
    """parse_arxiv_id accepts all arXiv URL forms and strips versions."""
    assert parse_arxiv_id(source) == expected


@pytest.mark.asyncio
async def test_arxiv_search_field_mapping_and_withdrawn_filter() -> None:
    """Feed entries map to ArxivPaper fields and withdrawn entries are dropped."""
    _FakeAsyncClient.response = _FakeResponse(ATOM_FIXTURE)
    with patch("ninja_researcher.arxiv.httpx.AsyncClient", _FakeAsyncClient):
        papers = await arxiv_search("robots", categories=["cs.RO"])

    assert len(papers) == 1
    paper = papers[0]
    assert paper.id == "2401.12345"
    assert paper.title == "A Great Paper"
    assert paper.authors == ["Alice Smith", "Bob Jones"]
    assert paper.abstract == "An abstract about robots."
    assert paper.url == "https://arxiv.org/abs/2401.12345"
    assert paper.categories == ["cs.RO", "cs.LG"]
    assert paper.primary_category == "cs.RO"
    assert paper.comment == "Accepted at a conference"
    assert paper.published == "2024-01-15T00:00:00Z"


@pytest.mark.asyncio
async def test_arxiv_search_ands_categories_in_request() -> None:
    """Category filters are ANDed into the search_query parameter."""
    _FakeAsyncClient.response = _FakeResponse(ATOM_FIXTURE)
    with patch("ninja_researcher.arxiv.httpx.AsyncClient", _FakeAsyncClient):
        await arxiv_search("robot", categories=["cs.RO", "cs.LG"])

    assert _FakeAsyncClient.last_params["search_query"] == ("all:robot AND cat:cs.RO AND cat:cs.LG")


@pytest.mark.asyncio
async def test_arxiv_search_clamps_max_results() -> None:
    """max_results is clamped into the arXiv-supported 1..50 range."""
    _FakeAsyncClient.response = _FakeResponse(ATOM_FIXTURE)
    with patch("ninja_researcher.arxiv.httpx.AsyncClient", _FakeAsyncClient):
        await arxiv_search("robot", max_results=999)

    assert _FakeAsyncClient.last_params["max_results"] == 50


@pytest.mark.asyncio
async def test_arxiv_search_multiword_query_is_quoted() -> None:
    """Multi-word free text is emitted as a quoted all:"..." clause."""
    _FakeAsyncClient.response = _FakeResponse(ATOM_FIXTURE)
    with patch("ninja_researcher.arxiv.httpx.AsyncClient", _FakeAsyncClient):
        await arxiv_search("attention is all you need", categories=["cs.CL"])

    assert _FakeAsyncClient.last_params["search_query"] == (
        'all:"attention is all you need" AND cat:cs.CL'
    )


@pytest.mark.asyncio
async def test_arxiv_search_406_is_rate_limited() -> None:
    """A 406 from the arXiv API becomes rate_limited with retry_after 30s."""
    _FakeAsyncClient.response = _FakeResponse(status_code=406)
    executor = ResearchToolExecutor()

    with patch("ninja_researcher.arxiv.httpx.AsyncClient", _FakeAsyncClient):
        result = await executor.arxiv_search(ArxivSearchRequest(query="robot"))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == ErrorKind.rate_limited
    assert result.error.retry_after_s == 30.0


@pytest.mark.asyncio
async def test_arxiv_search_429_is_rate_limited() -> None:
    """A 429 response becomes a rate_limited ErrorInfo with retry_after_s."""
    _FakeAsyncClient.response = _FakeResponse(status_code=429, headers={"Retry-After": "5"})
    executor = ResearchToolExecutor()

    with patch("ninja_researcher.arxiv.httpx.AsyncClient", _FakeAsyncClient):
        result = await executor.arxiv_search(ArxivSearchRequest(query="robot"))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == ErrorKind.rate_limited
    assert result.error.retry_after_s == 5.0


@pytest.mark.asyncio
async def test_arxiv_search_parse_error_is_parse() -> None:
    """Malformed XML becomes a parse ErrorInfo."""
    _FakeAsyncClient.response = _FakeResponse(text="<not-xml")
    executor = ResearchToolExecutor()

    with patch("ninja_researcher.arxiv.httpx.AsyncClient", _FakeAsyncClient):
        result = await executor.arxiv_search(ArxivSearchRequest(query="robot"))

    assert result.error is not None
    assert result.error.kind == ErrorKind.parse
