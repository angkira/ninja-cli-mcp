"""Ninja Prompts - Reusable prompt templates and multi-step workflows."""

__version__ = "0.2.0"

from ninja_prompts.models import (
    ChainStepOutput,
    PromptChainRequest,
    PromptChainResult,
    PromptChainStep,
    PromptRegistryRequest,
    PromptRegistryResult,
    PromptSuggestion,
    PromptSuggestRequest,
    PromptSuggestResult,
    PromptTemplate,
    PromptVariable,
)
from ninja_prompts.prompt_manager import PromptManager
from ninja_prompts.template_engine import TemplateEngine
from ninja_prompts.tools import PromptToolExecutor


_executor = None


def get_executor() -> PromptToolExecutor:
    """Get or create the singleton PromptToolExecutor."""
    global _executor
    if _executor is None:
        _executor = PromptToolExecutor()
    return _executor


__all__ = [
    "ChainStepOutput",
    "PromptChainRequest",
    "PromptChainResult",
    "PromptChainStep",
    "PromptManager",
    "PromptRegistryRequest",
    "PromptRegistryResult",
    "PromptSuggestRequest",
    "PromptSuggestResult",
    "PromptSuggestion",
    "PromptTemplate",
    "PromptToolExecutor",
    "PromptVariable",
    "TemplateEngine",
    "get_executor",
]
