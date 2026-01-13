"""Ninja Prompts - Reusable prompt templates and multi-step workflows."""

__version__ = "0.2.0"

from ninja_prompts.models import (
    PromptVariable,
    PromptTemplate,
    PromptRegistryRequest,
    PromptRegistryResult,
    PromptSuggestRequest,
    PromptSuggestion,
    PromptSuggestResult,
    PromptChainStep,
    PromptChainRequest,
    ChainStepOutput,
    PromptChainResult,
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
    "PromptVariable",
    "PromptTemplate",
    "PromptRegistryRequest",
    "PromptRegistryResult",
    "PromptSuggestRequest",
    "PromptSuggestion",
    "PromptSuggestResult",
    "PromptChainStep",
    "PromptChainRequest",
    "ChainStepOutput",
    "PromptChainResult",
    "PromptManager",
    "TemplateEngine",
    "PromptToolExecutor",
    "get_executor",
]
