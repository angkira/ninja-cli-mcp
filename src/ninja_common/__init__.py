"""Common infrastructure for Ninja MCP modules."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("ninja-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from ninja_common.daemon import DaemonManager
from ninja_common.logging_utils import get_logger, setup_logging
from ninja_common.metrics import MetricsTracker, TaskMetrics
from ninja_common.rate_balancer import (
    RateBalancer,
    RateLimitConfig,
    get_rate_balancer,
    rate_balanced,
    reset_rate_balancer,
)
from ninja_common.security import InputValidator, RateLimiter, ResourceMonitor


__all__ = [
    "DaemonManager",
    "InputValidator",
    "MetricsTracker",
    "RateBalancer",
    "RateLimitConfig",
    "RateLimiter",
    "ResourceMonitor",
    "TaskMetrics",
    "get_logger",
    "get_rate_balancer",
    "rate_balanced",
    "reset_rate_balancer",
    "setup_logging",
]
