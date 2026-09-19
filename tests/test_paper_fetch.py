"""
Tests for the paper-fetch tool and arXiv id parsing (P1-1).

All fetching is mocked; no network access is performed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest

from ninja_researcher.arxiv import _extract_numbers, fetch_paper, parse_arxiv_id
from ninja_researcher.models import ErrorKind, PaperFetchRequest
from ninja_researcher.tools import ResearchToolExecutor, reset_executor


AR5IV_HTML = """
<html>
  <head>
    <title>Ar5iv Paper Title</title>
    <meta name="description" content="This is the abstract of the paper." />
  </head>
  <body>
    <h2>1 Introduction</h2>
    <p>We study robot learning in the wild.</p>
    <h2>2 Results</h2>
    <p>Accuracy improved by 12.5% over the baseline.</p>
    <p>Gains ranged 3-5x on the benchmark.</p>
    <h3>2.1 Ablation</h3>
    <p>Ablation showed 7 pp improvement.</p>
    <h2>3 Conclusion</h2>
    <p>We conclude that robots are useful.</p>
  </body>
</html>
"""

ABS_HTML = """
<html>
  <head>
    <title>Abstract Page</title>
    <meta name="description" content="Fallback abstract text." />
  </head>
  <body><blockquote class="abstract">Fallback abstract text.</blockquote></body>
</html>
"""


class _FakeResponse:
    """Minimal httpx response stand-in."""

    def __init__(self, text: str = "", status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        """Raise an HTTPStatusError for non-2xx responses."""
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://arxiv.org/abs/2401.12345")
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


@pytest.fixture(autouse=True)
def _reset() -> None:
    """Reset the executor singleton between tests."""
    reset_executor()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("2401.12345", "2401.12345"),
        ("2401.12345v2", "2401.12345"),
        ("https://arxiv.org/abs/2401.12345", "2401.12345"),
        ("https://arxiv.org/pdf/2401.12345v1", "2401.12345"),
        ("https://ar5iv.labs.arxiv.org/html/2401.12345", "2401.12345"),
        ("https://export.arxiv.org/abs/2401.12345", "2401.12345"),
        ("https://example.com/article", None),
        ("hello world", None),
    ],
)
def test_parse_arxiv_id_forms(source: str, expected: str | None) -> None:
    """parse_arxiv_id handles all supported forms and rejects non-arXiv URLs."""
    assert parse_arxiv_id(source) == expected


def test_extract_numbers_percent_range_and_dedupe() -> None:
    """Numbers include percents/ranges, carry sentence context, and dedupe."""
    text = "Accuracy improved by 12.5% over the baseline. Gains ranged 3-5x. Accuracy improved by 12.5% over the baseline."
    numbers = _extract_numbers(text, section="Results")

    values = [n.value for n in numbers]
    assert "12.5%" in values
    assert "3-5x" in values
    # Duplicate (value, context) pairs are collapsed.
    assert values.count("12.5%") == 1
    first = next(n for n in numbers if n.value == "12.5%")
    assert first.context == "Accuracy improved by 12.5% over the baseline."
    assert first.section == "Results"


@pytest.mark.asyncio
async def test_fetch_paper_extracts_sections_and_numbers() -> None:
    """ar5iv HTML yields the title, abstract, requested sections and numbers."""
    with patch(
        "ninja_researcher.arxiv.httpx.AsyncClient",
        lambda *a, **k: _FakeAsyncClient(lambda url: _FakeResponse(AR5IV_HTML)),
    ):
        paper = await fetch_paper("https://arxiv.org/abs/2401.12345", ["results"], True)

    assert paper.error is None
    assert paper.arxiv_id == "2401.12345"
    assert paper.title == "Ar5iv Paper Title"
    assert paper.abstract == "This is the abstract of the paper."
    assert "results" in paper.sections
    assert "12.5%" in paper.sections["results"]
    assert any(n.value == "12.5%" for n in paper.numbers)


@pytest.mark.asyncio
async def test_fetch_paper_abs_fallback_when_ar5iv_404() -> None:
    """When ar5iv returns 404, the abstract page is used as fallback."""

    def handler(url: str) -> _FakeResponse:
        if "ar5iv" in url:
            return _FakeResponse(status_code=404)
        return _FakeResponse(ABS_HTML)

    with patch(
        "ninja_researcher.arxiv.httpx.AsyncClient", lambda *a, **k: _FakeAsyncClient(handler)
    ):
        paper = await fetch_paper("2401.12345", None, False)

    assert paper.error is None
    assert paper.abstract == "Fallback abstract text."


@pytest.mark.asyncio
async def test_fetch_paper_failure_classified_upstream() -> None:
    """A total fetch failure is embedded as an upstream error."""

    def handler(url: str) -> _FakeResponse:
        return _FakeResponse(status_code=500)

    with patch(
        "ninja_researcher.arxiv.httpx.AsyncClient", lambda *a, **k: _FakeAsyncClient(handler)
    ):
        paper = await fetch_paper("2401.12345", None, False)

    assert paper.error is not None
    assert paper.error.kind == ErrorKind.upstream


@pytest.mark.asyncio
async def test_paper_fetch_executor_maps_error() -> None:
    """The executor wraps a failed fetch in an error PaperFetchResult."""

    def handler(url: str) -> _FakeResponse:
        return _FakeResponse(status_code=500)

    executor = ResearchToolExecutor()
    with patch(
        "ninja_researcher.arxiv.httpx.AsyncClient", lambda *a, **k: _FakeAsyncClient(handler)
    ):
        result = await executor.paper_fetch(PaperFetchRequest(source="2401.12345"))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.kind == ErrorKind.upstream
