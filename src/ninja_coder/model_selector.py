"""
Intelligent model selection based on task complexity.

This module provides automatic model routing to optimize for cost,
performance, and throughput based on the type of task being executed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ninja_coder.models import TaskComplexity
from ninja_common.defaults import MODEL_DATABASE
from ninja_common.logging_utils import get_logger


logger = get_logger(__name__)


@dataclass
class ModelRecommendation:
    """Model recommendation with reasoning."""

    model: str
    """Recommended model name."""

    provider: str
    """Provider name (z.ai, openrouter, etc.)."""

    reason: str
    """Human-readable reason for this recommendation."""

    cost_estimate: str
    """Estimated cost range for this task."""

    use_coding_plan_api: bool = False
    """Whether to use Coding Plan API (z.ai only)."""


class ModelSelector:
    """Intelligent model selection based on task complexity and constraints.

    This class routes tasks to optimal models using a database of model
    capabilities, costs, and performance metrics.
    """

    def __init__(self, default_model: str | None = None):
        """Initialize model selector.

        Args:
            default_model: Default model to use if no preference is set.
        """
        self.default_model = default_model
        self.model_db = MODEL_DATABASE

    def select_model(
        self,
        complexity: TaskComplexity,
        fanout: int = 1,
        prefer_cost: bool = False,
        prefer_quality: bool = False,
    ) -> ModelRecommendation:
        """Select best model for task.

        Args:
            complexity: Type of task (parallel, sequential, quick).
            fanout: Number of parallel tasks (if parallel).
            prefer_cost: Prioritize cost over quality.
            prefer_quality: Prioritize quality over cost.

        Returns:
            ModelRecommendation with selected model and reasoning.
        """
        # If default model is set and no preference, use it
        if self.default_model and not (prefer_cost or prefer_quality):
            return self._recommend_default()

        # Filter models suitable for task
        suitable_models = {
            name: info
            for name, info in self.model_db.items()
            if complexity.value in info["best_for"]
        }

        if not suitable_models:
            logger.warning(f"No models found for complexity '{complexity}', using default")
            return self._recommend_default()

        # Apply strategy based on complexity
        if complexity == TaskComplexity.PARALLEL:
            return self._select_for_parallel(suitable_models, fanout, prefer_cost)
        elif complexity == TaskComplexity.SEQUENTIAL:
            return self._select_for_sequential(suitable_models, prefer_quality)
        else:  # QUICK
            return self._select_for_quick(suitable_models, prefer_cost)

    def _select_for_parallel(
        self,
        models: dict[str, Any],
        fanout: int,
        prefer_cost: bool,
    ) -> ModelRecommendation:
        """Select model for parallel tasks.

        Args:
            models: Dictionary of suitable models.
            fanout: Number of parallel tasks.
            prefer_cost: Whether to prioritize cost.

        Returns:
            ModelRecommendation for parallel tasks.
        """
        # For high fanout (>10), prioritize concurrent limit and cost
        if fanout > 10:
            # GLM-4.6V: 20 concurrent, cheaper on z.ai
            if "glm-4.6v" in models:
                return ModelRecommendation(
                    model="glm-4.6v",
                    provider="z.ai",
                    reason=f"High fanout ({fanout}) tasks: GLM-4.6V supports 20 concurrent at low cost",
                    cost_estimate="$0.01-0.05 per task",
                    use_coding_plan_api=False,
                )

        # For medium fanout (5-10), balance quality and cost
        if "openrouter/anthropic/claude-haiku-4.5" in models and not prefer_cost:
            return ModelRecommendation(
                model="openrouter/anthropic/claude-haiku-4.5",
                provider="openrouter",
                reason="Balanced performance and cost for parallel tasks (LiveBench 82.0)",
                cost_estimate="$0.10-0.30 per task",
                use_coding_plan_api=False,
            )

        # Default to GLM-4.0 for cost
        if "zai/glm-4.0" in models:
            return ModelRecommendation(
                model="zai/glm-4.0",
                provider="z.ai",
                reason="Cost-effective option for parallel tasks",
                cost_estimate="$0.01-0.03 per task",
                use_coding_plan_api=False,
            )

        # Fallback to any available model
        return self._fallback_recommendation(models, "parallel")

    def _select_for_sequential(
        self,
        models: dict[str, Any],
        prefer_quality: bool,
    ) -> ModelRecommendation:
        """Select model for sequential tasks.

        Args:
            models: Dictionary of suitable models.
            prefer_quality: Whether to prioritize quality.

        Returns:
            ModelRecommendation for sequential tasks.
        """
        # GLM-4.7: Smartest on LiveBench (84.9), supports Coding Plan API
        if "zai-coding-plan/glm-4.7" in models and not prefer_quality:
            return ModelRecommendation(
                model="zai-coding-plan/glm-4.7",
                provider="z.ai",
                reason="Highest quality for sequential tasks (LiveBench 84.9) with Coding Plan API",
                cost_estimate="$0.20-0.50 per task",
                use_coding_plan_api=True,  # Use specialized endpoint
            )

        # Fallback to Claude Sonnet 4.5 if quality preferred
        if "openrouter/anthropic/claude-sonnet-4-20250514" in models and prefer_quality:
            return ModelRecommendation(
                model="openrouter/anthropic/claude-sonnet-4-20250514",
                provider="openrouter",
                reason="Premium quality for complex sequential tasks (LiveBench 88.0)",
                cost_estimate="$0.50-1.00 per task",
                use_coding_plan_api=False,
            )

        # Claude Opus 4 for maximum quality
        if "openrouter/anthropic/claude-opus-4" in models and prefer_quality:
            return ModelRecommendation(
                model="openrouter/anthropic/claude-opus-4",
                provider="openrouter",
                reason="Maximum quality for critical sequential tasks (LiveBench 91.0)",
                cost_estimate="$1.00-2.00 per task",
                use_coding_plan_api=False,
            )

        # Default to GLM-4.0 for cost
        if "zai/glm-4.0" in models:
            return ModelRecommendation(
                model="zai/glm-4.0",
                provider="z.ai",
                reason="Balanced option for sequential tasks",
                cost_estimate="$0.10-0.20 per task",
                use_coding_plan_api=False,
            )

        # Fallback to any available model
        return self._fallback_recommendation(models, "sequential")

    def _select_for_quick(
        self,
        models: dict[str, Any],
        prefer_cost: bool,
    ) -> ModelRecommendation:
        """Select model for quick tasks.

        Args:
            models: Dictionary of suitable models.
            prefer_cost: Whether to prioritize cost.

        Returns:
            ModelRecommendation for quick tasks.
        """
        # For quick tasks, prefer speed and reasonable quality
        if "openrouter/anthropic/claude-haiku-4.5" in models and not prefer_cost:
            return ModelRecommendation(
                model="openrouter/anthropic/claude-haiku-4.5",
                provider="openrouter",
                reason="Fast and capable for quick tasks (LiveBench 82.0)",
                cost_estimate="$0.05-0.15 per task",
                use_coding_plan_api=False,
            )

        # Fallback to GLM-4.0 for cost
        if "zai/glm-4.0" in models:
            return ModelRecommendation(
                model="zai/glm-4.0",
                provider="z.ai",
                reason="Cost-effective for quick tasks",
                cost_estimate="$0.02-0.05 per task",
                use_coding_plan_api=False,
            )

        # Fallback to any available model
        return self._fallback_recommendation(models, "quick")

    def _recommend_default(self) -> ModelRecommendation:
        """Return default model recommendation.

        Returns:
            ModelRecommendation for default model.
        """
        model = self.default_model or "openrouter/anthropic/claude-haiku-4.5"
        info = self.model_db.get(model, {})

        return ModelRecommendation(
            model=model,
            provider=info.get("provider", "openrouter"),
            reason="User-configured default model",
            cost_estimate="Varies",
            use_coding_plan_api=False,
        )

    def _fallback_recommendation(
        self,
        models: dict[str, Any],
        task_type: str,
    ) -> ModelRecommendation:
        """Provide fallback recommendation when preferred model not available.

        Args:
            models: Dictionary of available models.
            task_type: Type of task for logging.

        Returns:
            ModelRecommendation for first available model.
        """
        if not models:
            logger.warning(f"No models available for {task_type}, using default")
            return self._recommend_default()

        # Pick first available model
        model_name = next(iter(models))
        info = models[model_name]

        logger.info(f"Using fallback model {model_name} for {task_type} task")

        return ModelRecommendation(
            model=model_name,
            provider=info.get("provider", "unknown"),
            reason=f"Fallback option for {task_type} tasks",
            cost_estimate="Varies",
            use_coding_plan_api=info.get("supports_coding_plan_api", False),
        )

    @classmethod
    def from_env(cls) -> ModelSelector:
        """Create ModelSelector from environment variables.

        Returns:
            ModelSelector instance configured from environment.
        """
        default_model = os.environ.get("NINJA_MODEL")
        return cls(default_model=default_model)
