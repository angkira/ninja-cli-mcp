"""
Unit tests for search providers.

Tests for DuckDuckGo, Serper, and Perplexity search providers.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ninja_researcher.search_providers import (
    DuckDuckGoProvider,
    PerplexityProvider,
    SearchProviderFactory,
    SerperProvider,
)


class TestDuckDuckGoProvider:
    """Tests for DuckDuckGo search provider."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Test that DuckDuckGo search returns results."""
        with patch("ninja_researcher.search_providers.DDGS") as mock_ddgs:
            # Mock the search results
            mock_instance = MagicMock()
            mock_instance.text.return_value = [
                {
                    "title": "Test Result 1",
                    "href": "https://example.com/1",
                    "body": "Test snippet 1",
                },
                {
                    "title": "Test Result 2",
                    "href": "https://example.com/2",
                    "body": "Test snippet 2",
                },
            ]
            mock_ddgs.return_value = mock_instance

            provider = DuckDuckGoProvider()
            results = await provider.search("test query", max_results=5)

            assert len(results) == 2
            assert results[0]["title"] == "Test Result 1"
            assert results[0]["url"] == "https://example.com/1"
            assert results[0]["snippet"] == "Test snippet 1"
            assert "score" in results[0]

    @pytest.mark.asyncio
    async def test_search_handles_empty_results(self):
        """Test that DuckDuckGo handles empty results."""
        with patch("ninja_researcher.search_providers.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.return_value = []
            mock_ddgs.return_value = mock_instance

            provider = DuckDuckGoProvider()
            results = await provider.search("nonexistent query", max_results=5)

            assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_handles_exception(self):
        """Test that DuckDuckGo handles exceptions gracefully."""
        with patch("ninja_researcher.search_providers.DDGS") as mock_ddgs:
            mock_instance = MagicMock()
            mock_instance.text.side_effect = Exception("API Error")
            mock_ddgs.return_value = mock_instance

            provider = DuckDuckGoProvider()
            results = await provider.search("test query", max_results=5)

            assert len(results) == 0

    def test_is_available(self):
        """Test that DuckDuckGo is always available."""
        provider = DuckDuckGoProvider()
        assert provider.is_available() is True

    def test_get_name(self):
        """Test provider name."""
        provider = DuckDuckGoProvider()
        assert provider.get_name() == "duckduckgo"


class TestSerperProvider:
    """Tests for Serper search provider."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Test that Serper search returns results."""
        provider = SerperProvider(api_key="test_key")

        with patch("httpx.AsyncClient") as mock_client:
            # Mock the HTTP response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "organic": [
                    {
                        "title": "Test Result 1",
                        "link": "https://example.com/1",
                        "snippet": "Test snippet 1",
                    },
                    {
                        "title": "Test Result 2",
                        "link": "https://example.com/2",
                        "snippet": "Test snippet 2",
                    },
                ]
            }
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            results = await provider.search("test query", max_results=5)

            assert len(results) == 2
            assert results[0]["title"] == "Test Result 1"
            assert results[0]["url"] == "https://example.com/1"
            assert results[0]["snippet"] == "Test snippet 1"

    @pytest.mark.asyncio
    async def test_search_without_api_key(self):
        """Test that Serper returns empty results without API key."""
        provider = SerperProvider(api_key="")

        results = await provider.search("test query", max_results=5)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_handles_http_error(self):
        """Test that Serper handles HTTP errors."""
        provider = SerperProvider(api_key="test_key")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("HTTP Error")
            )

            results = await provider.search("test query", max_results=5)

            assert len(results) == 0

    def test_is_available_with_key(self):
        """Test that Serper is available with API key."""
        provider = SerperProvider(api_key="test_key")
        assert provider.is_available() is True

    def test_is_available_without_key(self):
        """Test that Serper is not available without API key."""
        provider = SerperProvider(api_key="")
        assert provider.is_available() is False

    def test_get_name(self):
        """Test provider name."""
        provider = SerperProvider(api_key="test_key")
        assert provider.get_name() == "serper"


class TestPerplexityProvider:
    """Tests for Perplexity search provider."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Test that Perplexity search returns results."""
        provider = PerplexityProvider(api_key="test_key")

        with patch("httpx.AsyncClient") as mock_client:
            # Mock the HTTP response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "citations": [
                    "https://example.com/1",
                    "https://example.com/2",
                ],
                "choices": [
                    {
                        "message": {
                            "content": "This is a test response from Perplexity AI with citations and sources."
                        }
                    }
                ],
            }
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            results = await provider.search("test query", max_results=5)

            assert len(results) == 2
            assert results[0]["url"] == "https://example.com/1"
            assert results[1]["url"] == "https://example.com/2"
            assert "title" in results[0]
            assert "snippet" in results[0]

    @pytest.mark.asyncio
    async def test_search_without_api_key(self):
        """Test that Perplexity returns empty results without API key."""
        provider = PerplexityProvider(api_key="")

        results = await provider.search("test query", max_results=5)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_limits_results(self):
        """Test that Perplexity respects max_results."""
        provider = PerplexityProvider(api_key="test_key")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "citations": [f"https://example.com/{i}" for i in range(20)],
                "choices": [{"message": {"content": "Test content"}}],
            }
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            results = await provider.search("test query", max_results=5)

            assert len(results) == 5

    def test_is_available_with_key(self):
        """Test that Perplexity is available with API key."""
        provider = PerplexityProvider(api_key="test_key")
        assert provider.is_available() is True

    def test_is_available_without_key(self):
        """Test that Perplexity is not available without API key."""
        provider = PerplexityProvider(api_key="")
        assert provider.is_available() is False

    def test_get_name(self):
        """Test provider name."""
        provider = PerplexityProvider(api_key="test_key")
        assert provider.get_name() == "perplexity"


class TestSearchProviderFactory:
    """Tests for SearchProviderFactory."""

    def test_get_provider_duckduckgo(self):
        """Test getting DuckDuckGo provider."""
        provider = SearchProviderFactory.get_provider("duckduckgo")
        assert isinstance(provider, DuckDuckGoProvider)

    def test_get_provider_serper(self):
        """Test getting Serper provider."""
        provider = SearchProviderFactory.get_provider("serper")
        assert isinstance(provider, SerperProvider)

    def test_get_provider_perplexity(self):
        """Test getting Perplexity provider."""
        provider = SearchProviderFactory.get_provider("perplexity")
        assert isinstance(provider, PerplexityProvider)

    def test_get_provider_invalid(self):
        """Test that invalid provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported search provider"):
            SearchProviderFactory.get_provider("invalid_provider")

    def test_get_available_providers_default(self):
        """Test getting available providers (DuckDuckGo always available)."""
        with patch.dict(os.environ, {}, clear=True):
            providers = SearchProviderFactory.get_available_providers()
            assert "duckduckgo" in providers
            assert "serper" not in providers
            assert "perplexity" not in providers

    def test_get_available_providers_with_serper(self):
        """Test available providers with Serper API key."""
        with patch.dict(os.environ, {"SERPER_API_KEY": "test_key"}):
            providers = SearchProviderFactory.get_available_providers()
            assert "duckduckgo" in providers
            assert "serper" in providers

    def test_get_available_providers_with_perplexity(self):
        """Test available providers with Perplexity API key."""
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test_key"}):
            providers = SearchProviderFactory.get_available_providers()
            assert "duckduckgo" in providers
            assert "perplexity" in providers

    def test_get_default_provider_duckduckgo(self):
        """Test default provider is DuckDuckGo when no keys configured."""
        with patch.dict(os.environ, {}, clear=True):
            provider = SearchProviderFactory.get_default_provider()
            assert provider == "duckduckgo"

    def test_get_default_provider_serper(self):
        """Test default provider is Serper when Serper key configured."""
        with patch.dict(os.environ, {"SERPER_API_KEY": "test_key"}):
            provider = SearchProviderFactory.get_default_provider()
            assert provider == "serper"

    def test_get_default_provider_perplexity(self):
        """Test default provider is Perplexity when Perplexity key configured (highest priority)."""
        with patch.dict(
            os.environ,
            {"PERPLEXITY_API_KEY": "test_key", "SERPER_API_KEY": "test_key"},
        ):
            provider = SearchProviderFactory.get_default_provider()
            assert provider == "perplexity"

    def test_provider_caching(self):
        """Test that providers are cached."""
        provider1 = SearchProviderFactory.get_provider("duckduckgo")
        provider2 = SearchProviderFactory.get_provider("duckduckgo")
        assert provider1 is provider2
