"""Tests for RequestDeduplicator."""

import asyncio

import pytest

from ninja_common.security import RequestDeduplicator


class TestRequestDeduplicator:
    def test_make_key_deterministic(self) -> None:
        key1 = RequestDeduplicator.make_key("tool", {"a": 1, "b": 2})
        key2 = RequestDeduplicator.make_key("tool", {"b": 2, "a": 1})
        assert key1 == key2

    def test_make_key_different_tools(self) -> None:
        key1 = RequestDeduplicator.make_key("tool_a", {"x": 1})
        key2 = RequestDeduplicator.make_key("tool_b", {"x": 1})
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_concurrent_same_key_executes_once(self) -> None:
        dedup = RequestDeduplicator(ttl=60)
        call_count = 0

        async def slow_factory() -> str:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return "result"

        key = "test-key"
        tasks = [asyncio.create_task(dedup.deduplicate(key, slow_factory)) for _ in range(5)]
        results = await asyncio.gather(*tasks)
        assert call_count == 1
        assert all(r == "result" for r in results)

    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        dedup = RequestDeduplicator(ttl=60)
        call_count = 0

        async def factory() -> str:
            nonlocal call_count
            call_count += 1
            return "cached"

        r1 = await dedup.deduplicate("k", factory)
        r2 = await dedup.deduplicate("k", factory)
        assert r1 == r2 == "cached"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_ttl_expiry(self) -> None:
        dedup = RequestDeduplicator(ttl=0)
        call_count = 0

        async def factory() -> str:
            nonlocal call_count
            call_count += 1
            return f"r{call_count}"

        await dedup.deduplicate("k", factory)
        await asyncio.sleep(0.01)
        r2 = await dedup.deduplicate("k", factory)
        assert call_count == 2
        assert r2 == "r2"

    @pytest.mark.asyncio
    async def test_exception_caching(self) -> None:
        dedup = RequestDeduplicator(ttl=60)
        call_count = 0

        async def failing() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await dedup.deduplicate("k", failing)
        with pytest.raises(RuntimeError, match="boom"):
            await dedup.deduplicate("k", failing)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_different_keys_independent(self) -> None:
        dedup = RequestDeduplicator(ttl=60)
        calls: list[str] = []

        async def fa() -> str:
            calls.append("a")
            return "a"

        async def fb() -> str:
            calls.append("b")
            return "b"

        await dedup.deduplicate("a", fa)
        await dedup.deduplicate("b", fb)
        assert sorted(calls) == ["a", "b"]
