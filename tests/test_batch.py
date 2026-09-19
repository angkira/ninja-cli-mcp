"""
Tests for the serial deep-research batch tool (P1-2).

The underlying ``deep_research`` executor method is mocked so these tests are
fast and fully offline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from ninja_researcher.models import (
    DeepResearchBatchRequest,
    DeepResearchRequest,
    ErrorInfo,
    ErrorKind,
    ResearchResult,
)
from ninja_researcher.tools import ResearchToolExecutor, reset_executor


def _ok_result(topic: str) -> ResearchResult:
    """Build a successful research result."""
    return ResearchResult(status="ok", topic=topic, sources_found=1, sources=[], summary="ok")


def _error_result(topic: str, kind: ErrorKind = ErrorKind.rate_limited) -> ResearchResult:
    """Build a failed research result with a typed error."""
    return ResearchResult(
        status="error",
        topic=topic,
        sources_found=0,
        sources=[],
        summary="",
        error=ErrorInfo(kind=kind, message="rate limited", retry_after_s=1.0),
    )


def _requests(count: int) -> list[DeepResearchRequest]:
    """Build *count* minimal deep-research requests."""
    return [DeepResearchRequest(topic=f"t{i}", queries=["q"], enrich=False) for i in range(count)]


def _executor_with(mock: AsyncMock) -> ResearchToolExecutor:
    """Create an executor whose deep_research is replaced by *mock*."""
    reset_executor()
    executor = ResearchToolExecutor()
    executor.deep_research = mock  # type: ignore[method-assign]
    return executor


@pytest.mark.asyncio
async def test_batch_runs_strictly_serially() -> None:
    """Calls never overlap; they execute in request order."""
    active = 0
    peak = 0
    order: list[str] = []

    async def fake_deep_research(
        request: DeepResearchRequest, client_id: str = "default"
    ) -> ResearchResult:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        order.append(request.topic)
        import asyncio

        await asyncio.sleep(0.01)
        active -= 1
        return _ok_result(request.topic)

    executor = _executor_with(AsyncMock(side_effect=fake_deep_research))
    batch = DeepResearchBatchRequest(requests=_requests(3), inter_call_delay_s=0)

    result = await executor.deep_research_batch(batch)

    assert peak == 1
    assert order == ["t0", "t1", "t2"]
    assert result.status == "ok"
    assert result.completed == 3


@pytest.mark.asyncio
async def test_batch_delay_between_but_not_after_last() -> None:
    """The inter-call delay is applied n-1 times, never after the last call."""
    executor = _executor_with(
        AsyncMock(side_effect=lambda request, client_id="default": _ok_result(request.topic))
    )
    batch = DeepResearchBatchRequest(
        requests=_requests(3), inter_call_delay_s=5.0, on_error="continue"
    )

    with patch("ninja_researcher.tools.asyncio.sleep", new=AsyncMock()) as sleep:
        await executor.deep_research_batch(batch)

    assert sleep.await_count == 2
    sleep.assert_awaited_with(5.0)


@pytest.mark.asyncio
async def test_batch_retry_backoff_retries_rate_limited_twice() -> None:
    """retry_backoff retries a rate-limited request exactly twice, then accepts."""
    responses = [
        _error_result("t0"),
        _error_result("t0"),
        _ok_result("t0"),
    ]
    executor = _executor_with(AsyncMock(side_effect=responses))
    batch = DeepResearchBatchRequest(
        requests=_requests(1), inter_call_delay_s=0, on_error="retry_backoff"
    )

    with patch("ninja_researcher.tools.asyncio.sleep", new=AsyncMock()) as sleep:
        result = await executor.deep_research_batch(batch)

    assert result.results[0].status == "ok"
    assert executor.deep_research.await_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [20.0, 40.0]


@pytest.mark.asyncio
async def test_batch_abort_stops_early_with_partial_results() -> None:
    """on_error='abort' stops at the first error and returns partial results."""
    responses = [_ok_result("t0"), _error_result("t1"), _ok_result("t2")]
    executor = _executor_with(AsyncMock(side_effect=responses))
    batch = DeepResearchBatchRequest(requests=_requests(3), inter_call_delay_s=0, on_error="abort")

    result = await executor.deep_research_batch(batch)

    assert result.status == "aborted"
    assert result.completed == 2
    assert len(result.results) == 2
    assert result.error is not None
    assert executor.deep_research.await_count == 2


@pytest.mark.asyncio
async def test_batch_continue_does_not_retry() -> None:
    """on_error='continue' keeps going without retrying."""
    responses = [_error_result("t0"), _ok_result("t1")]
    executor = _executor_with(AsyncMock(side_effect=responses))
    batch = DeepResearchBatchRequest(
        requests=_requests(2), inter_call_delay_s=0, on_error="continue"
    )

    result = await executor.deep_research_batch(batch)

    assert result.status == "partial"
    assert result.completed == 2
    assert executor.deep_research.await_count == 2


def test_batch_rejects_more_than_five_requests() -> None:
    """Pydantic validation rejects batches larger than five."""
    with pytest.raises(ValidationError):
        DeepResearchBatchRequest(requests=_requests(6))


def test_batch_rejects_empty_requests() -> None:
    """Pydantic validation rejects an empty batch."""
    with pytest.raises(ValidationError):
        DeepResearchBatchRequest(requests=[])
