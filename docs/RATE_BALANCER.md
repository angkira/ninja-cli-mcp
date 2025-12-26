# Rate Balancer Implementation

## Overview

The Ninja CLI MCP rate balancer provides intelligent rate limiting with automatic request queuing and retry logic using a token bucket algorithm. Instead of failing requests when rate limits are hit, the balancer queues them and waits for capacity to become available.

## Architecture

### Token Bucket Algorithm

The rate balancer uses a token bucket implementation where:
- Tokens represent available request capacity
- Tokens refill automatically over time based on the configured rate
- Requests consume tokens when executed
- If no tokens available, requests wait instead of failing

### Key Components

1. **`TokenBucket`**: Manages token allocation and refill
   - Automatic token refill based on time elapsed
   - Thread-safe with asyncio locks
   - Configurable max tokens and refill rate

2. **`RateBalancer`**: Orchestrates rate limiting across functions
   - Per-client, per-function token buckets
   - Exponential backoff retry logic
   - Metrics collection for monitoring

3. **`@rate_balanced` Decorator**: Easy-to-use function decorator
   - Drop-in replacement for `@rate_limited`
   - Configurable retry policies
   - Automatic client ID extraction

## Usage

### Basic Usage

```python
from ninja_common import rate_balanced

@rate_balanced(max_calls=30, time_window=60, max_retries=3)
async def my_function(request, client_id="default"):
    # Your code here
    pass
```

### Configuration Parameters

- **`max_calls`**: Maximum number of calls allowed per time window
- **`time_window`**: Time window in seconds (default: 60)
- **`max_retries`**: Maximum retry attempts on failure (default: 3)
- **`initial_backoff`**: Initial backoff delay in seconds (default: 1.0)
- **`max_backoff`**: Maximum backoff delay in seconds (default: 60.0)
- **`backoff_multiplier`**: Exponential backoff multiplier (default: 2.0)

### Advanced Usage

```python
from ninja_common import RateBalancer, RateLimitConfig

# Create custom rate balancer
balancer = RateBalancer()

# Create custom config
config = RateLimitConfig(
    max_calls=10,
    time_window=60,
    max_retries=5,
    initial_backoff=2.0,
    max_backoff=120.0,
    backoff_multiplier=3.0,
)

# Execute with retry
result = await balancer.execute_with_retry(
    my_async_function,
    arg1,
    arg2,
    config=config,
    client_id="my-client",
    kwarg1=value1,
)
```

## How It Works

### Request Flow

1. **Request arrives** at rate-balanced function
2. **Check token bucket** for available tokens
3. **If tokens available**:
   - Consume token
   - Execute function
   - Return result
4. **If no tokens available**:
   - Calculate wait time for token refill
   - Wait for tokens to become available
   - Retry from step 2
5. **On function failure**:
   - Apply exponential backoff
   - Retry up to max_retries times
   - Collect metrics

### Token Refill

Tokens refill continuously based on the formula:

```python
tokens_to_add = time_passed * refill_rate
refill_rate = max_calls / time_window
```

For example:
- `max_calls=30, time_window=60` → refill_rate = 0.5 tokens/second
- After 10 seconds: 5 tokens refilled
- After 60 seconds: 30 tokens refilled (capped at max_calls)

### Exponential Backoff

When retrying after a failure:

```python
backoff = min(initial_backoff * (backoff_multiplier ** attempt), max_backoff)
```

Example with `initial_backoff=1.0, backoff_multiplier=2.0`:
- Attempt 0: 1.0s
- Attempt 1: 2.0s
- Attempt 2: 4.0s
- Attempt 3: 8.0s
- Attempt 4: 16.0s

## Metrics

The rate balancer collects metrics for each function:

```python
from ninja_common import get_rate_balancer

balancer = get_rate_balancer()
metrics = balancer.get_metrics("my_function")

# Returns:
{
    "function": "my_function",
    "total_requests": 100,
    "successful": 95,
    "failed": 5,
    "success_rate": 0.95,
    "avg_retries": 0.3,
    "avg_duration": 1.2,
}
```

## Benefits

### 1. No Failed Requests

Instead of rejecting requests when rate limit is hit:
- ❌ **Before**: Request fails with rate limit error
- ✅ **After**: Request queues and waits for capacity

### 2. Automatic Retries

Transient failures are handled automatically:
- ❌ **Before**: Client must implement retry logic
- ✅ **After**: Built-in exponential backoff retry

### 3. Better Resource Utilization

Requests are distributed over time:
- ❌ **Before**: Burst requests get rejected
- ✅ **After**: Requests queue and execute when capacity available

### 4. Per-Client Fairness

Each client gets their own token bucket:
- ❌ **Before**: Single rate limit shared by all clients
- ✅ **After**: Per-client tracking prevents one client from starving others

### 5. Observability

Built-in metrics provide visibility:
- ❌ **Before**: No insight into rate limiting behavior
- ✅ **After**: Track success rate, retry count, duration

## Migration Guide

### Updating Existing Code

Replace `@rate_limited` with `@rate_balanced`:

```python
# Before
from ninja_common.security import rate_limited

@rate_limited(max_calls=30, time_window=60)
async def my_function(request, client_id="default"):
    pass

# After
from ninja_common import rate_balanced

@rate_balanced(
    max_calls=30,
    time_window=60,
    max_retries=3,
    initial_backoff=1.0,
    max_backoff=60.0
)
async def my_function(request, client_id="default"):
    pass
```

### Key Differences

| Feature | `@rate_limited` | `@rate_balanced` |
|---------|----------------|------------------|
| Behavior on limit hit | Fails immediately | Queues and waits |
| Retry on failure | No | Yes (configurable) |
| Backoff strategy | N/A | Exponential |
| Metrics | Basic | Comprehensive |
| Per-client tracking | Yes | Yes |
| Token refill | Manual | Automatic |

## Testing

The rate balancer is thoroughly tested:

```bash
# Run rate balancer tests
pytest tests/test_researcher/test_researcher_integration.py::test_rate_limiting -v

# Run all tests to verify no rate limit failures
pytest tests/ -v
```

Expected results:
- ✅ All tests pass (100% success rate)
- ✅ No rate limit failures
- ✅ Requests queue and retry automatically

## Performance Considerations

### Memory Usage

- Each client-function pair gets one `TokenBucket` (~200 bytes)
- Metrics are stored in memory (can be reset)
- Typical usage: < 1 MB for 1000 active client-function pairs

### CPU Overhead

- Token refill calculation: O(1) per request
- Exponential backoff: O(1) per retry
- Metrics aggregation: O(n) where n = number of requests
- Minimal overhead (~0.1ms per request)

### Wait Times

Maximum wait time depends on configuration:
- Token bucket refill: Up to 60 seconds by default
- Exponential backoff: Up to max_backoff (default 60s)
- Total max wait: token_wait + (max_retries * max_backoff)

## Best Practices

### 1. Set Appropriate Rate Limits

Match rate limits to your API provider's limits:
```python
# DuckDuckGo: ~30 requests/minute
@rate_balanced(max_calls=30, time_window=60)

# High-frequency operations: higher limits
@rate_balanced(max_calls=60, time_window=60)

# Expensive operations: lower limits
@rate_balanced(max_calls=5, time_window=60, initial_backoff=2.0)
```

### 2. Configure Backoff Appropriately

More expensive operations should have longer backoff:
```python
# Quick operations: short backoff
@rate_balanced(max_calls=30, time_window=60, initial_backoff=0.5)

# Expensive operations: longer backoff
@rate_balanced(max_calls=5, time_window=60, initial_backoff=2.0, max_backoff=120.0)
```

### 3. Monitor Metrics

Regularly check metrics to optimize configuration:
```python
balancer = get_rate_balancer()
metrics = balancer.get_metrics()

# Look for:
# - High retry counts → increase rate limits or backoff
# - Low success rates → investigate failures
# - Long durations → optimize function or increase timeout
```

### 4. Reset for Testing

Reset balancer state between tests:
```python
from ninja_common import reset_rate_balancer

@pytest.fixture
def clean_balancer():
    reset_rate_balancer()
    yield
    reset_rate_balancer()
```

## Troubleshooting

### Requests Taking Too Long

**Symptom**: Functions hang or timeout
**Causes**:
- Rate limit too restrictive
- Too many concurrent requests
- Backoff too aggressive

**Solutions**:
```python
# Increase rate limit
@rate_balanced(max_calls=60, time_window=60)  # Was 30

# Reduce backoff
@rate_balanced(initial_backoff=0.5, max_backoff=30.0)  # Was 1.0, 60.0

# Reduce retries for fast fail
@rate_balanced(max_retries=1)  # Was 3
```

### High Retry Counts

**Symptom**: Metrics show avg_retries > 1.0
**Causes**:
- Transient failures in downstream services
- Rate limits too low
- Network issues

**Solutions**:
```python
# Increase rate limit
@rate_balanced(max_calls=40, time_window=60)  # Was 30

# Add circuit breaker (future enhancement)
# Implement retry budget limits
```

### Memory Growth

**Symptom**: Memory usage increases over time
**Causes**:
- Metrics accumulating
- Many unique client IDs

**Solutions**:
```python
# Periodically reset metrics
balancer = get_rate_balancer()
balancer.reset_metrics()  # Reset all
balancer.reset_metrics("my_function")  # Reset specific function

# Implement metrics rotation (future enhancement)
```

## Future Enhancements

Potential improvements to the rate balancer:

1. **Circuit Breaker**: Fail fast when downstream consistently fails
2. **Adaptive Rate Limiting**: Adjust limits based on success rate
3. **Priority Queuing**: Higher priority for certain clients/requests
4. **Distributed Rate Limiting**: Share rate limits across instances
5. **Metrics Export**: Prometheus, StatsD integration
6. **Request Deadlines**: Cancel requests that exceed timeout
7. **Rate Limit Headers**: Expose current capacity to clients

## References

- [Token Bucket Algorithm](https://en.wikipedia.org/wiki/Token_bucket)
- [Exponential Backoff](https://en.wikipedia.org/wiki/Exponential_backoff)
- [Rate Limiting Patterns](https://cloud.google.com/architecture/rate-limiting-strategies-techniques)

## License

MIT License - See LICENSE file for details
