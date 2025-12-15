"""
Metrics tracking for token usage and costs.

This module provides functionality to track and persist metrics for each task
executed through the Ninja CLI MCP server, including:
- Token usage (input/output/cache)
- Real-time costs from OpenRouter API
- Task metadata (model, duration, status)
"""

import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib import request as urllib_request
from urllib.error import URLError


# OpenRouter pricing per million tokens (as of 2024)
# These are approximate values - actual prices may vary
MODEL_PRICING = {
    # Qwen models
    "qwen/qwen3-coder": {"input": 0.0, "output": 0.0},  # Free tier
    "qwen/qwen-2.5-coder-32b-instruct": {"input": 0.8, "output": 0.8},
    # Claude models
    "anthropic/claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "anthropic/claude-3.5-sonnet": {"input": 3.0, "output": 15.0},
    "anthropic/claude-opus-4": {"input": 15.0, "output": 75.0},
    "anthropic/claude-3-opus": {"input": 15.0, "output": 75.0},
    "anthropic/claude-3-haiku": {"input": 0.25, "output": 1.25},
    # OpenAI models
    "openai/gpt-4o": {"input": 2.5, "output": 10.0},
    "openai/gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "openai/gpt-4": {"input": 30.0, "output": 60.0},
    "openai/gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    "openai/o1-preview": {"input": 15.0, "output": 60.0},
    "openai/o1-mini": {"input": 3.0, "output": 12.0},
    # DeepSeek models
    "deepseek/deepseek-coder": {"input": 0.14, "output": 0.28},
    "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
    # Google models
    "google/gemini-pro-1.5": {"input": 1.25, "output": 5.0},
    "google/gemini-flash-1.5": {"input": 0.075, "output": 0.30},
    # Meta models
    "meta-llama/llama-3.1-405b-instruct": {"input": 2.7, "output": 2.7},
    "meta-llama/llama-3.1-70b-instruct": {"input": 0.52, "output": 0.75},
}

# Default pricing for unknown models
DEFAULT_PRICING = {"input": 1.0, "output": 2.0, "cache_read": 0.0, "cache_write": 0.0}


# Cache for OpenRouter model pricing (to avoid repeated API calls)
_pricing_cache: dict[str, dict] = {}
_pricing_cache_time: Optional[datetime] = None
PRICING_CACHE_TTL = timedelta(hours=24)  # Cache pricing for 24 hours


def fetch_openrouter_pricing() -> dict[str, dict]:
    """
    Fetch real-time pricing from OpenRouter API.

    Returns:
        Dictionary mapping model IDs to pricing information
    """
    global _pricing_cache, _pricing_cache_time

    # Return cached pricing if still valid
    if _pricing_cache and _pricing_cache_time:
        if datetime.now() - _pricing_cache_time < PRICING_CACHE_TTL:
            return _pricing_cache

    try:
        # Fetch models from OpenRouter API
        req = urllib_request.Request(
            "https://openrouter.ai/api/v1/models", headers={"Content-Type": "application/json"}
        )

        with urllib_request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        # Parse pricing from API response
        pricing_map = {}
        for model in data.get("data", []):
            model_id = model.get("id", "")
            pricing = model.get("pricing", {})

            if model_id and pricing:
                # Convert pricing from per-token to per-million-tokens
                pricing_map[model_id] = {
                    "input": float(pricing.get("prompt", "0")) * 1_000_000,
                    "output": float(pricing.get("completion", "0")) * 1_000_000,
                    "cache_read": float(pricing.get("input_cache_read", "0")) * 1_000_000,
                    "cache_write": float(pricing.get("input_cache_write", "0")) * 1_000_000,
                }

        # Update cache
        _pricing_cache = pricing_map
        _pricing_cache_time = datetime.now()

        return pricing_map

    except (URLError, json.JSONDecodeError, KeyError, ValueError) as e:
        # If API fails, return empty dict (will fall back to static pricing)
        return {}


def get_model_pricing(model: str) -> dict:
    """
    Get pricing for a model, trying OpenRouter API first, then falling back to static pricing.

    Args:
        model: Model identifier

    Returns:
        Dictionary with keys: input, output, cache_read, cache_write (prices per million tokens)
    """
    # Try to fetch from OpenRouter API
    api_pricing = fetch_openrouter_pricing()
    if model in api_pricing:
        return api_pricing[model]

    # Fall back to static pricing
    static_pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)

    # Add cache pricing if not present
    return {
        "input": static_pricing.get("input", DEFAULT_PRICING["input"]),
        "output": static_pricing.get("output", DEFAULT_PRICING["output"]),
        "cache_read": static_pricing.get("cache_read", DEFAULT_PRICING["cache_read"]),
        "cache_write": static_pricing.get("cache_write", DEFAULT_PRICING["cache_write"]),
    }


@dataclass
class TaskMetrics:
    """Metrics for a single task execution."""

    task_id: str
    timestamp: str
    model: str
    tool_name: str
    task_description: str

    # Token usage
    input_tokens: int
    output_tokens: int
    total_tokens: int

    # Costs (in USD)
    input_cost: float
    output_cost: float
    total_cost: float

    # Task metadata
    duration_sec: float
    success: bool
    execution_mode: str

    # Cache tokens (optional)
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    # Cache costs (optional)
    cache_read_cost: float = 0.0
    cache_write_cost: float = 0.0

    # Additional context
    repo_root: Optional[str] = None
    file_scope: Optional[str] = None
    error_message: Optional[str] = None


class MetricsTracker:
    """Manages metrics tracking and persistence."""

    def __init__(self, repo_root: Path):
        """
        Initialize metrics tracker.

        Args:
            repo_root: Repository root path
        """
        self.repo_root = repo_root
        self.metrics_dir = repo_root / ".ninja-cli-mcp" / "metrics"
        self.metrics_file = self.metrics_dir / "tasks.csv"
        self._ensure_metrics_dir()

    def _ensure_metrics_dir(self) -> None:
        """Ensure metrics directory exists."""
        self.metrics_dir.mkdir(parents=True, exist_ok=True)

        # Create CSV with headers if it doesn't exist
        if not self.metrics_file.exists():
            with open(self.metrics_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._get_fieldnames())
                writer.writeheader()

    def _get_fieldnames(self) -> list[str]:
        """Get CSV fieldnames from TaskMetrics dataclass."""
        return [
            "task_id",
            "timestamp",
            "model",
            "tool_name",
            "task_description",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "input_cost",
            "output_cost",
            "cache_read_cost",
            "cache_write_cost",
            "total_cost",
            "duration_sec",
            "success",
            "execution_mode",
            "repo_root",
            "file_scope",
            "error_message",
        ]

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> tuple[float, float, float, float, float]:
        """
        Calculate costs for token usage including cache tokens.

        Args:
            model: Model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cache_read_tokens: Number of cache read tokens
            cache_write_tokens: Number of cache write tokens

        Returns:
            Tuple of (input_cost, output_cost, cache_read_cost, cache_write_cost, total_cost) in USD
        """
        pricing = get_model_pricing(model)

        # Costs are per million tokens
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        cache_read_cost = (cache_read_tokens / 1_000_000) * pricing["cache_read"]
        cache_write_cost = (cache_write_tokens / 1_000_000) * pricing["cache_write"]
        total_cost = input_cost + output_cost + cache_read_cost + cache_write_cost

        return input_cost, output_cost, cache_read_cost, cache_write_cost, total_cost

    def record_task(self, metrics: TaskMetrics) -> None:
        """
        Record task metrics to CSV.

        Args:
            metrics: TaskMetrics instance to record
        """
        with open(self.metrics_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._get_fieldnames())
            writer.writerow(asdict(metrics))

    def get_summary(self) -> dict:
        """
        Get summary statistics from all recorded metrics.

        Returns:
            Dictionary with summary statistics
        """
        if not self.metrics_file.exists():
            return {
                "total_tasks": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "successful_tasks": 0,
                "failed_tasks": 0,
            }

        total_tasks = 0
        total_tokens = 0
        total_cost = 0.0
        successful_tasks = 0
        failed_tasks = 0
        model_usage = {}

        with open(self.metrics_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_tasks += 1
                total_tokens += int(row.get("total_tokens", 0))
                total_cost += float(row.get("total_cost", 0.0))

                if row.get("success", "").lower() == "true":
                    successful_tasks += 1
                else:
                    failed_tasks += 1

                model = row.get("model", "unknown")
                model_usage[model] = model_usage.get(model, 0) + 1

        return {
            "total_tasks": total_tasks,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 4),
            "successful_tasks": successful_tasks,
            "failed_tasks": failed_tasks,
            "model_usage": model_usage,
        }

    def get_recent_tasks(self, limit: int = 10) -> list[dict]:
        """
        Get most recent tasks.

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of task dictionaries
        """
        if not self.metrics_file.exists():
            return []

        tasks = []
        with open(self.metrics_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            tasks = list(reader)

        # Return last N tasks (most recent)
        return tasks[-limit:] if len(tasks) > limit else tasks


def extract_token_usage(output: str) -> tuple[int, int, int, int]:
    """
    Extract token usage from AI CLI output.

    This function attempts to parse token usage from the CLI output.
    Different models may report tokens differently, so we use heuristics.

    Args:
        output: Raw output from the AI CLI

    Returns:
        Tuple of (input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)
    """
    import re

    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0

    # Try to find token usage patterns in output
    # Common patterns:
    # - "Input tokens: 1234"
    # - "Output tokens: 5678"
    # - "cache_read_tokens: 100"
    # - "cache_write_tokens: 200"
    # - Usage: {"input": 1234, "output": 5678, "cached_tokens": 100}

    # Pattern for "input tokens: 1234" or "input_tokens: 1234" (case-insensitive)
    input_pattern = r"input[_ ]tokens?\s*:\s*(\d+)"
    input_match = re.search(input_pattern, output, re.IGNORECASE)
    if input_match:
        input_tokens = int(input_match.group(1))

    # Pattern for "output tokens: 5678" or "output_tokens: 5678" (case-insensitive)
    output_pattern = r"output[_ ]tokens?\s*:\s*(\d+)"
    output_match = re.search(output_pattern, output, re.IGNORECASE)
    if output_match:
        output_tokens = int(output_match.group(1))

    # Pattern for cache read tokens
    cache_read_pattern = r"cache[_ ]read[_ ]tokens?\s*:\s*(\d+)"
    cache_read_match = re.search(cache_read_pattern, output, re.IGNORECASE)
    if cache_read_match:
        cache_read_tokens = int(cache_read_match.group(1))

    # Pattern for cache write tokens
    cache_write_pattern = r"cache[_ ]write[_ ]tokens?\s*:\s*(\d+)"
    cache_write_match = re.search(cache_write_pattern, output, re.IGNORECASE)
    if cache_write_match:
        cache_write_tokens = int(cache_write_match.group(1))

    # Also check for "cached_tokens" (OpenRouter format)
    if not cache_read_tokens:
        cached_pattern = r"cached[_ ]tokens?\s*:\s*(\d+)"
        cached_match = re.search(cached_pattern, output, re.IGNORECASE)
        if cached_match:
            cache_read_tokens = int(cached_match.group(1))

    # If we couldn't extract tokens, estimate based on output length
    # Rough estimate: ~4 chars per token
    if input_tokens == 0 and output_tokens == 0:
        output_tokens = max(1, len(output) // 4)

    return input_tokens, output_tokens, cache_read_tokens, cache_write_tokens


def create_task_metrics(
    task_id: str,
    model: str,
    tool_name: str,
    task_description: str,
    output: str,
    duration_sec: float,
    success: bool,
    execution_mode: str = "quick",
    repo_root: Optional[str] = None,
    file_scope: Optional[str] = None,
    error_message: Optional[str] = None,
) -> TaskMetrics:
    """
    Create TaskMetrics from task execution results.

    Args:
        task_id: Unique task identifier
        model: Model used for execution
        tool_name: Name of the tool/command
        task_description: Description of the task
        output: Raw output from the AI CLI
        duration_sec: Execution duration in seconds
        success: Whether the task succeeded
        execution_mode: Execution mode (quick, full, etc.)
        repo_root: Repository root path
        file_scope: File scope pattern
        error_message: Error message if task failed

    Returns:
        TaskMetrics instance
    """
    # Extract token usage from output
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens = extract_token_usage(output)
    total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_write_tokens

    # Calculate costs
    tracker = MetricsTracker(Path(repo_root) if repo_root else Path.cwd())
    input_cost, output_cost, cache_read_cost, cache_write_cost, total_cost = tracker.calculate_cost(
        model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
    )

    return TaskMetrics(
        task_id=task_id,
        timestamp=datetime.now().isoformat(),
        model=model,
        tool_name=tool_name,
        task_description=task_description[:200],  # Truncate long descriptions
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        input_cost=round(input_cost, 6),
        output_cost=round(output_cost, 6),
        cache_read_cost=round(cache_read_cost, 6),
        cache_write_cost=round(cache_write_cost, 6),
        total_cost=round(total_cost, 6),
        duration_sec=round(duration_sec, 2),
        success=success,
        execution_mode=execution_mode,
        repo_root=repo_root,
        file_scope=file_scope,
        error_message=error_message[:200] if error_message else None,
    )
