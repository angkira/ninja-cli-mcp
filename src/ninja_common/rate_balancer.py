"""
Rate balancer with retry policies and request queuing.

Provides intelligent rate limiting that queues requests instead of failing them,
with configurable retry policies and exponential backoff.
"""

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

from ninja_common.logging_utils import get_logger


logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    max_calls: int = 30  # Maximum calls per time window
    time_window: int = 60  # Time window in seconds
    max_queue_size: int = 100  # Maximum queued requests per client
    max_retries: int = 3  # Maximum retry attempts
    initial_backoff: float = 1.0  # Initial backoff in seconds
    max_backoff: float = 60.0  # Maximum backoff in seconds
    backoff_multiplier: float = 2.0  # Exponential backoff multiplier


@dataclass
class RequestMetrics:
    """Metrics for a request."""

    start_time: float
    end_time: float = 0.0
    retries: int = 0
    success: bool = False
    error: str | None = None


class TokenBucket:
    """Token bucket for rate limiting with automatic refill."""

    def __init__(self, max_tokens: int, refill_rate: float):
        """
        Initialize token bucket.

        Args:
            max_tokens: Maximum number of tokens.
            refill_rate: Tokens added per second.
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.tokens = float(max_tokens)
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    async def consume(self, tokens: int = 1, wait: bool = True) -> bool:
        """
        Consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume.
            wait: If True, wait for tokens to become available.

        Returns:
            True if tokens were consumed, False otherwise.
        """
        async with self.lock:
            # Refill tokens based on time passed
            now = time.time()
            time_passed = now - self.last_refill
            self.tokens = min(
                self.max_tokens, self.tokens + (time_passed * self.refill_rate)
            )
            self.last_refill = now

            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            if not wait:
                return False

            # Calculate wait time
            tokens_needed = tokens - self.tokens
            wait_time = tokens_needed / self.refill_rate

            # Limit wait time to reasonable amount
            if wait_time > 60:  # Don't wait more than 60 seconds
                return False

            logger.info(f"Rate limit reached, waiting {wait_time:.2f}s for tokens")

        # Wait outside the lock to allow other operations
        await asyncio.sleep(wait_time)

        # Try again
        return await self.consume(tokens, wait=False)


class RateBalancer:
    """
    Intelligent rate balancer with queuing and retry policies.

    Features:
    - Token bucket algorithm with automatic refill
    - Request queuing when rate limit is reached
    - Exponential backoff retry policies
    - Per-client tracking
    - Metrics collection
    """

    def __init__(self):
        """Initialize the rate balancer."""
        self.buckets: dict[str, TokenBucket] = {}
        self.queues: dict[str, deque] = defaultdict(deque)
        self.metrics: dict[str, list[RequestMetrics]] = defaultdict(list)
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _get_bucket_key(self, func_name: str, client_id: str) -> str:
        """Get unique bucket key for function and client."""
        return f"{func_name}:{client_id}"

    def _get_or_create_bucket(
        self, func_name: str, client_id: str, config: RateLimitConfig
    ) -> TokenBucket:
        """Get or create token bucket for function and client."""
        key = self._get_bucket_key(func_name, client_id)

        if key not in self.buckets:
            # Create bucket with refill rate
            refill_rate = config.max_calls / config.time_window
            self.buckets[key] = TokenBucket(config.max_calls, refill_rate)

        return self.buckets[key]

    async def execute_with_retry(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        config: RateLimitConfig,
        client_id: str = "default",
        **kwargs: Any,
    ) -> T:
        """
        Execute function with rate limiting and retry logic.

        Args:
            func: Async function to execute.
            *args: Function arguments.
            config: Rate limit configuration.
            client_id: Client identifier.
            **kwargs: Function keyword arguments.

        Returns:
            Function result.

        Raises:
            Exception: If all retries fail.
        """
        func_name = func.__name__
        bucket = self._get_or_create_bucket(func_name, client_id, config)

        metrics = RequestMetrics(start_time=time.time())
        last_error = None

        for attempt in range(config.max_retries + 1):
            try:
                # Wait for token availability
                got_token = await bucket.consume(tokens=1, wait=True)

                if not got_token:
                    # Could not get token even after waiting
                    backoff = min(
                        config.initial_backoff * (config.backoff_multiplier**attempt),
                        config.max_backoff,
                    )
                    logger.warning(
                        f"Rate limit exceeded for {func_name}, retrying in {backoff:.2f}s "
                        f"(attempt {attempt + 1}/{config.max_retries + 1})"
                    )
                    await asyncio.sleep(backoff)
                    continue

                # Execute function
                logger.debug(f"Executing {func_name} for client {client_id}")
                result = await func(*args, **kwargs)

                # Success!
                metrics.end_time = time.time()
                metrics.retries = attempt
                metrics.success = True
                self.metrics[func_name].append(metrics)

                if attempt > 0:
                    logger.info(
                        f"{func_name} succeeded after {attempt} retries "
                        f"({metrics.end_time - metrics.start_time:.2f}s total)"
                    )

                return result

            except Exception as e:
                last_error = e
                metrics.retries = attempt + 1

                if attempt < config.max_retries:
                    backoff = min(
                        config.initial_backoff * (config.backoff_multiplier**attempt),
                        config.max_backoff,
                    )
                    logger.warning(
                        f"{func_name} failed: {e}, retrying in {backoff:.2f}s "
                        f"(attempt {attempt + 1}/{config.max_retries + 1})"
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        f"{func_name} failed after {config.max_retries + 1} attempts: {e}"
                    )

        # All retries failed
        metrics.end_time = time.time()
        metrics.success = False
        metrics.error = str(last_error)
        self.metrics[func_name].append(metrics)

        raise last_error  # type: ignore

    def get_metrics(self, func_name: str | None = None) -> dict[str, Any]:
        """
        Get metrics for functions.

        Args:
            func_name: Optional function name to filter by.

        Returns:
            Dictionary with metrics.
        """
        if func_name:
            metrics_list = self.metrics.get(func_name, [])
            return self._calculate_metrics(func_name, metrics_list)

        # Return metrics for all functions
        return {
            name: self._calculate_metrics(name, metrics_list)
            for name, metrics_list in self.metrics.items()
        }

    def _calculate_metrics(
        self, func_name: str, metrics_list: list[RequestMetrics]
    ) -> dict[str, Any]:
        """Calculate aggregate metrics."""
        if not metrics_list:
            return {
                "function": func_name,
                "total_requests": 0,
                "successful": 0,
                "failed": 0,
                "avg_retries": 0.0,
                "avg_duration": 0.0,
            }

        successful = sum(1 for m in metrics_list if m.success)
        failed = len(metrics_list) - successful
        avg_retries = sum(m.retries for m in metrics_list) / len(metrics_list)
        durations = [m.end_time - m.start_time for m in metrics_list if m.end_time > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "function": func_name,
            "total_requests": len(metrics_list),
            "successful": successful,
            "failed": failed,
            "success_rate": successful / len(metrics_list) if metrics_list else 0.0,
            "avg_retries": avg_retries,
            "avg_duration": avg_duration,
        }

    def reset_metrics(self, func_name: str | None = None) -> None:
        """Reset metrics for function(s)."""
        if func_name:
            self.metrics[func_name] = []
        else:
            self.metrics.clear()


# Global rate balancer instance
_rate_balancer: RateBalancer | None = None


def get_rate_balancer() -> RateBalancer:
    """Get the global rate balancer instance."""
    global _rate_balancer  # noqa: PLW0603
    if _rate_balancer is None:
        _rate_balancer = RateBalancer()
    return _rate_balancer


def reset_rate_balancer() -> None:
    """Reset the global rate balancer (for testing)."""
    global _rate_balancer  # noqa: PLW0603
    _rate_balancer = None


def rate_balanced(
    max_calls: int = 30,
    time_window: int = 60,
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    max_backoff: float = 60.0,
    backoff_multiplier: float = 2.0,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator for rate-balanced async functions with automatic retry.

    This decorator provides:
    - Rate limiting with token bucket algorithm
    - Automatic request queuing and waiting
    - Exponential backoff retry on failures
    - Per-client tracking
    - Metrics collection

    Args:
        max_calls: Maximum calls per time window.
        time_window: Time window in seconds.
        max_retries: Maximum retry attempts.
        initial_backoff: Initial backoff in seconds.
        max_backoff: Maximum backoff in seconds.
        backoff_multiplier: Exponential backoff multiplier.

    Returns:
        Decorated async function.

    Example:
        @rate_balanced(max_calls=10, time_window=60, max_retries=3)
        async def my_function(request, client_id="default"):
            # Function implementation
            pass
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        config = RateLimitConfig(
            max_calls=max_calls,
            time_window=time_window,
            max_retries=max_retries,
            initial_backoff=initial_backoff,
            max_backoff=max_backoff,
            backoff_multiplier=backoff_multiplier,
        )

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Extract client_id from kwargs or use default
            client_id = kwargs.pop("client_id", "default")

            # Get rate balancer
            balancer = get_rate_balancer()

            # Execute with retry
            return await balancer.execute_with_retry(
                func, *args, config=config, client_id=client_id, **kwargs
            )

        return wrapper

    return decorator
