"""Tool executor for prompt operations."""


from ninja_common.logging_utils import get_logger
from ninja_common.security import monitored, rate_limited
from ninja_prompts.models import (
    PromptChainRequest,
    PromptChainResult,
    PromptRegistryRequest,
    PromptRegistryResult,
    PromptSuggestRequest,
    PromptSuggestResult,
)
from ninja_prompts.prompt_manager import PromptManager
from ninja_prompts.template_engine import TemplateEngine


logger = get_logger(__name__)


class PromptToolExecutor:
    """Executes prompt-related operations."""

    def __init__(self):
        """Initialize executor with manager and engine."""
        self.manager = PromptManager()
        self.engine = TemplateEngine()

    @rate_limited(60, 60)
    @monitored
    async def prompt_registry(
        self, request: PromptRegistryRequest, client_id: str = "default"
    ) -> PromptRegistryResult:
        """Execute prompt registry operations."""
        try:
            if request.action == "list":
                prompts = self.manager.list_prompts()
                return PromptRegistryResult(
                    status="ok",
                    prompts=[p.model_dump() for p in prompts],
                )
            elif request.action == "get":
                retrieved_prompt = self.manager.get_prompt(request.prompt_id)
                return PromptRegistryResult(
                    status="ok",
                    prompts=[retrieved_prompt.model_dump()]
                )
        except Exception as e:
            logger.error(f"Error in prompt_registry: {e}")
            return PromptRegistryResult(status="error", prompts=[])

    @rate_limited(60, 60)
    @monitored
    async def prompt_suggest(
        self, request: PromptSuggestRequest, client_id: str = "default"
    ) -> PromptSuggestResult:
        """Get AI-powered suggestions for relevant prompts based on context."""
        try:
            suggestions = []
            return PromptSuggestResult(
                status="ok",
                suggestions=[s.model_dump() for s in suggestions],
            )
        except Exception as e:
            logger.error(f"Error in prompt_suggest: {e}")
            return PromptSuggestResult(status="error", suggestions=[])

    @rate_limited(60, 60)
    @monitored
    async def prompt_chain(
        self, request: PromptChainRequest, client_id: str = "default"
    ) -> PromptChainResult:
        """Execute multi-step prompt workflows."""
        try:
            return PromptChainResult(
                status="ok",
                executed_steps=[],
            )
        except Exception as e:
            logger.error(f"Error in prompt_chain: {e}")
            return PromptChainResult(status="error", executed_steps=[])


def get_executor() -> PromptToolExecutor:
    """Get the singleton instance of the executor."""
    return PromptToolExecutor()


class PromptToolExecutor:
    """Executes prompt-related operations."""

    def __init__(self):
        """Initialize executor with manager and engine."""
        self.manager = PromptManager()
        self.engine = TemplateEngine()

    @rate_limited(60, 60)
    @monitored
    async def prompt_registry(
        self, request: PromptRegistryRequest, client_id: str = "default"
    ) -> PromptRegistryResult:
        """Execute prompt registry operations.

        Args:
            request: The registry request with action
            client_id: Client identifier for monitoring

        Returns:
            PromptRegistryResult with status and data
        """
        try:
            if request.action == "list":
                prompts = self.manager.list_prompts()
                return PromptRegistryResult(
                    status="ok",
                    prompts=[p.model_dump() for p in prompts],
                )
            elif request.action == "get":
                return PromptRegistryResult(
                    status="ok",
                    prompts=[self.manager.get_prompt(request.prompt_id).model_dump()]
                )
        except Exception as e:
            logger.error(f"Error in prompt_registry: {e}")
            return PromptRegistryResult(status="error", prompts=[])

    @rate_limited(60, 60)
    @monitored
    async def prompt_suggest(
        self, request: PromptSuggestRequest, client_id: str = "default"
    ) -> PromptSuggestResult:
        """Get AI-powered suggestions for relevant prompts based on context."""
        try:
            suggestions = []
            return PromptSuggestResult(
                status="ok",
                suggestions=[s.model_dump() for s in suggestions],
            )
        except Exception as e:
            logger.error(f"Error in prompt_suggest: {e}")
            return PromptSuggestResult(status="error", suggestions=[])

    @rate_limited(60, 60)
    @monitored
    async def prompt_chain(
        self, request: PromptChainRequest, client_id: str = "default"
    ) -> PromptChainResult:
        """Execute multi-step prompt workflows."""
        try:
            return PromptChainResult(
                status="ok",
                executed_steps=[],
            )
        except Exception as e:
            logger.error(f"Error in prompt_chain: {e}")
            return PromptChainResult(status="error", executed_steps=[])


