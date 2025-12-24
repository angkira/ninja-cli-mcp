"""
Search providers for the Researcher module.

Implements multiple search providers:
- DuckDuckGo (free, no API key required)
- Serper.dev (Google Search API, requires API key)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import httpx
from duckduckgo_search import DDGS

from ninja_common.logging_utils import get_logger

logger = get_logger(__name__)


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
            List of search results with title, url, snippet, score.
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

    def __init__(self):
        """Initialize DuckDuckGo provider."""
        self.ddgs = DDGS()

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """
        Search using DuckDuckGo.

        Args:
            query: Search query.
            max_results: Maximum number of results.

        Returns:
            List of search results.
        """
        try:
            logger.info(f"Searching DuckDuckGo for: {query}")

            # DuckDuckGo search is synchronous, but we run it in executor to not block
            import asyncio

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, lambda: list(self.ddgs.text(query, max_results=max_results))
            )

            # Normalize results to common format
            normalized = []
            for idx, result in enumerate(results):
                normalized.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("href", result.get("link", "")),
                        "snippet": result.get("body", result.get("snippet", "")),
                        "score": 1.0 - (idx * 0.05),  # Decreasing score by position
                    }
                )

            logger.info(f"DuckDuckGo returned {len(normalized)} results")
            return normalized

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []

    def is_available(self) -> bool:
        """DuckDuckGo is always available (no API key needed)."""
        return True

    def get_name(self) -> str:
        """Get provider name."""
        return "duckduckgo"


class SerperProvider(SearchProvider):
    """Serper.dev search provider (Google Search API)."""

    def __init__(self, api_key: str | None = None):
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
            List of search results.
        """
        if not self.api_key:
            logger.error("Serper API key not configured")
            return []

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

            # Parse organic results
            organic = data.get("organic", [])
            normalized = []

            for idx, result in enumerate(organic[:max_results]):
                normalized.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("link", ""),
                        "snippet": result.get("snippet", ""),
                        "score": result.get("position", idx + 1)
                        / 100.0,  # Convert position to score
                    }
                )

            logger.info(f"Serper.dev returned {len(normalized)} results")
            return normalized

        except httpx.HTTPStatusError as e:
            logger.error(f"Serper.dev HTTP error: {e.response.status_code} - {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"Serper.dev search failed: {e}")
            return []

    def is_available(self) -> bool:
        """Check if Serper API key is configured."""
        return bool(self.api_key)

    def get_name(self) -> str:
        """Get provider name."""
        return "serper"


class SearchProviderFactory:
    """Factory for creating search providers."""

    _providers: dict[str, SearchProvider] = {}

    @classmethod
    def get_provider(cls, provider_name: str) -> SearchProvider:
        """
        Get a search provider by name.

        Args:
            provider_name: Provider name (duckduckgo, serper).

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

        # Check Serper
        if os.environ.get("SERPER_API_KEY"):
            available.append("serper")

        return available

    @classmethod
    def get_default_provider(cls) -> str:
        """
        Get the default provider.

        Returns Serper if API key is configured, otherwise DuckDuckGo.

        Returns:
            Default provider name.
        """
        if os.environ.get("SERPER_API_KEY"):
            return "serper"
        return "duckduckgo"
