"""
Search providers for the Researcher module.

Implements multiple search providers:
- DuckDuckGo (free, no API key required)
- Serper.dev (Google Search API, requires API key)
- Perplexity AI (requires API key)

Providers raise :class:`ProviderError` on real failures (network errors, HTTP
429/5xx, auth errors, decode errors). A successful search that simply finds no
matches returns an empty list and is NOT an error.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx
from ddgs import DDGS

from ninja_common.logging_utils import get_logger
from ninja_researcher.models import ErrorKind


logger = get_logger(__name__)


class ProviderError(Exception):
    """A classified, typed failure raised by a search provider."""

    def __init__(
        self,
        kind: ErrorKind,
        message: str,
        retry_after_s: float | None = None,
    ) -> None:
        """
        Initialize a provider error.

        Args:
            kind: Error classification.
            message: Short, neutral human-readable message.
            retry_after_s: Suggested retry delay in seconds, when known.
        """
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_after_s = retry_after_s


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header value into seconds, when it is a number."""
    if not value:
        return None
    try:
        parsed = float(value.strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def provider_error_from_status(response: httpx.Response) -> ProviderError:
    """
    Build a classified :class:`ProviderError` from an HTTP error response.

    Args:
        response: The failing HTTP response.

    Returns:
        A ``ProviderError`` classified as ``rate_limited`` for 429 and
        ``upstream`` for every other status.
    """
    status = response.status_code
    if status == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        return ProviderError(
            ErrorKind.rate_limited,
            f"Provider rate limited the request (HTTP {status})",
            retry_after,
        )
    return ProviderError(ErrorKind.upstream, f"Provider returned HTTP {status}")


def classify_exception(exc: BaseException) -> ProviderError:
    """
    Classify an arbitrary provider exception into a :class:`ProviderError`.

    Args:
        exc: The exception raised by the provider.

    Returns:
        A classified ``ProviderError``.
    """
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, httpx.HTTPStatusError):
        return provider_error_from_status(exc.response)
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError(ErrorKind.upstream, "Provider request timed out")
    if isinstance(exc, (ValueError, KeyError)):
        return ProviderError(ErrorKind.parse, "Provider returned an unparseable response")
    text = str(exc).lower()
    if "rate" in text and "limit" in text:
        return ProviderError(ErrorKind.rate_limited, "Provider rate limit exceeded")
    return ProviderError(ErrorKind.upstream, "Provider request failed")


class SearchProvider(ABC):
    """Base class for search providers."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """
        Search for a query.

        Args:
            query: Search query.
            max_results: Maximum number of results to return.

        Returns:
            List of search results with title, url, snippet and optional score.

        Raises:
            ProviderError: On a real provider failure.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available (has API key if needed)."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the provider name."""
        pass


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo search provider using duckduckgo-search library."""

    def __init__(self) -> None:
        """Initialize DuckDuckGo provider."""
        self.ddgs = DDGS()

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """
        Search using DuckDuckGo.

        Args:
            query: Search query.
            max_results: Maximum number of results.

        Returns:
            List of search results (empty on a successful zero-hit search).

        Raises:
            ProviderError: On a real provider failure.
        """
        try:
            logger.info(f"Searching DuckDuckGo for: {query}")

            import asyncio

            results = await asyncio.to_thread(
                lambda: list(self.ddgs.text(query, max_results=max_results))
            )

            # Normalize results to common format. DuckDuckGo returns real
            # titles/snippets but no relevance signal, so no score is set.
            normalized = [
                {
                    "title": result.get("title", ""),
                    "url": result.get("href", result.get("link", "")),
                    "snippet": result.get("body", result.get("snippet", "")),
                }
                for result in results
            ]

            logger.info(f"DuckDuckGo returned {len(normalized)} results")
            return normalized

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            raise classify_exception(e) from e

    def is_available(self) -> bool:
        """DuckDuckGo is always available (no API key needed)."""
        return True

    def get_name(self) -> str:
        """Get provider name."""
        return "duckduckgo"


class SerperProvider(SearchProvider):
    """Serper.dev search provider (Google Search API)."""

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize Serper provider.

        Args:
            api_key: Serper API key. If None, reads from SERPER_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("SERPER_API_KEY", "")
        self.base_url = "https://google.serper.dev/search"

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """
        Search using Serper.dev.

        Args:
            query: Search query.
            max_results: Maximum number of results.

        Returns:
            List of search results (empty on a successful zero-hit search).

        Raises:
            ProviderError: On a real provider failure.
        """
        if not self.api_key:
            raise ProviderError(ErrorKind.env, "Serper API key is not configured")

        try:
            logger.info(f"Searching Serper.dev for: {query}")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    json={"q": query, "num": max_results},
                    headers={
                        "X-API-KEY": self.api_key,
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            # Parse organic results. Serper returns real titles/snippets but its
            # "position" is an ordinal, not a relevance score, so no score is set.
            organic = data.get("organic", [])
            normalized = [
                {
                    "title": result.get("title", ""),
                    "url": result.get("link", ""),
                    "snippet": result.get("snippet", ""),
                }
                for result in organic[:max_results]
            ]

            logger.info(f"Serper.dev returned {len(normalized)} results")
            return normalized

        except httpx.HTTPStatusError as e:
            logger.error(f"Serper.dev HTTP error: {e.response.status_code}")
            raise provider_error_from_status(e.response) from e
        except Exception as e:
            logger.error(f"Serper.dev search failed: {e}")
            raise classify_exception(e) from e

    def is_available(self) -> bool:
        """Check if Serper API key is configured."""
        return bool(self.api_key)

    def get_name(self) -> str:
        """Get provider name."""
        return "serper"


class PerplexityProvider(SearchProvider):
    """Perplexity AI search provider."""

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize Perplexity provider.

        Args:
            api_key: Perplexity API key. If None, reads from PERPLEXITY_API_KEY env var.
        """
        from ninja_common.secrets import get_secret

        self.api_key = api_key or get_secret("PERPLEXITY_API_KEY") or ""
        self.base_url = "https://api.perplexity.ai/chat/completions"

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """
        Search using Perplexity AI.

        Args:
            query: Search query.
            max_results: Maximum number of results (used for response length hint).

        Returns:
            List of search results extracted from Perplexity response.

        Raises:
            ProviderError: On a real provider failure.
        """
        if not self.api_key:
            raise ProviderError(ErrorKind.env, "Perplexity API key is not configured")

        try:
            logger.info(f"Searching Perplexity AI for: {query}")

            # Use Perplexity's sonar model for search
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    json={
                        "model": "sonar",
                        "messages": [
                            {
                                "role": "system",
                                "content": f"You are a search engine. Return up to {max_results} relevant search results with URLs. Format each result as: TITLE | URL | SNIPPET",
                            },
                            {"role": "user", "content": query},
                        ],
                        "return_citations": True,
                        "return_related_questions": False,
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            # Extract citations from Perplexity response. Perplexity does not
            # provide per-source titles/snippets, so titles are derived from the
            # URL and snippets are left empty for the enrichment stage to fill.
            normalized = []
            citations = data.get("citations", [])

            for url in citations[:max_results]:
                normalized.append(
                    {
                        "title": self._title_from_url(url),
                        "url": url,
                        "snippet": "",
                    }
                )

            # If no citations, create a single result with the response
            if not normalized and data.get("choices"):
                content = data["choices"][0].get("message", {}).get("content", "")
                if content:
                    normalized.append(
                        {
                            "title": "Perplexity AI Response",
                            "url": "https://www.perplexity.ai/",
                            "snippet": content[:500],
                        }
                    )

            logger.info(f"Perplexity AI returned {len(normalized)} results")
            return normalized

        except httpx.HTTPStatusError as e:
            logger.error(f"Perplexity AI HTTP error: {e.response.status_code}")
            raise provider_error_from_status(e.response) from e
        except Exception as e:
            logger.error(f"Perplexity AI search failed: {e}")
            raise classify_exception(e) from e

    @staticmethod
    def _title_from_url(url: str) -> str:
        """
        Derive a human-readable title from a URL's hostname and path.

        Args:
            url: Source URL.

        Returns:
            A title string, never an ordinal placeholder.
        """
        parsed = urlparse(url)
        host = parsed.netloc or url
        path = parsed.path.rstrip("/")
        return f"{host}{path}" if path else host

    def is_available(self) -> bool:
        """Check if Perplexity API key is configured."""
        return bool(self.api_key)

    def get_name(self) -> str:
        """Get provider name."""
        return "perplexity"


class SearchProviderFactory:
    """Factory for creating search providers."""

    _providers: ClassVar[dict[str, SearchProvider]] = {}

    @classmethod
    def get_provider(cls, provider_name: str) -> SearchProvider:
        """
        Get a search provider by name.

        Args:
            provider_name: Provider name (duckduckgo, serper, perplexity).

        Returns:
            SearchProvider instance.

        Raises:
            ValueError: If provider is not supported.
        """
        # Create provider if not cached
        if provider_name not in cls._providers:
            if provider_name == "duckduckgo":
                cls._providers[provider_name] = DuckDuckGoProvider()
            elif provider_name == "serper":
                cls._providers[provider_name] = SerperProvider()
            elif provider_name == "perplexity":
                cls._providers[provider_name] = PerplexityProvider()
            else:
                raise ValueError(f"Unsupported search provider: {provider_name}")

        return cls._providers[provider_name]

    @classmethod
    def get_available_providers(cls) -> list[str]:
        """
        Get list of available providers (those with API keys configured).

        Returns:
            List of provider names.
        """
        available = []

        # DuckDuckGo is always available
        available.append("duckduckgo")

        from ninja_common.secrets import get_secret

        # Check Serper
        if get_secret("SERPER_API_KEY"):
            available.append("serper")

        # Check Perplexity
        if get_secret("PERPLEXITY_API_KEY"):
            available.append("perplexity")

        return available

    @classmethod
    def get_default_provider(cls) -> str:
        """
        Get the default provider.

        Priority: Perplexity > Serper > DuckDuckGo.

        Returns:
            Default provider name.
        """
        from ninja_common.secrets import get_secret

        if get_secret("PERPLEXITY_API_KEY"):
            return "perplexity"
        if get_secret("SERPER_API_KEY"):
            return "serper"
        return "duckduckgo"
