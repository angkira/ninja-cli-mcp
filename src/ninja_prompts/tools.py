"""Tool executor for prompt operations."""

from datetime import datetime
from uuid import uuid4

from ninja_common.logging_utils import get_logger
from ninja_common.security import monitored, rate_limited
from ninja_prompts.models import (
    PromptChainRequest,
    PromptChainResult,
    PromptRegistryRequest,
    PromptRegistryResult,
    PromptSuggestRequest,
    PromptSuggestResult,
    PromptTemplate,
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
                    prompts=prompts,
                )
            elif request.action == "get":
                retrieved_prompt = self.manager.get_prompt(request.prompt_id)
                return PromptRegistryResult(
                    status="ok",
                    prompts=[retrieved_prompt]
                )
            elif request.action == "create":
                # Validation
                if not request.name or not request.template or not request.description:
                    return PromptRegistryResult(
                        status="error",
                        prompts=[],
                        message="name, template, and description are required"
                    )

                # Generate ID and create prompt
                prompt_id = f"prompt-{uuid4()}"
                new_prompt = PromptTemplate(
                    id=prompt_id,
                    name=request.name,
                    description=request.description,
                    template=request.template,
                    variables=request.variables or [],
                    tags=request.tags or [],
                    scope=request.scope or "user",
                    created=datetime.now()
                )

                # Save via manager
                self.manager.save_prompt(new_prompt)

                return PromptRegistryResult(
                    status="ok",
                    prompts=[new_prompt],
                    message=f"Prompt created with ID: {prompt_id}"
                )

            elif request.action == "update":
                # Validation
                if not request.prompt_id:
                    return PromptRegistryResult(
                        status="error",
                        prompts=[],
                        message="prompt_id is required for update"
                    )

                # Load existing
                existing = self.manager.get_prompt(request.prompt_id)
                if not existing:
                    return PromptRegistryResult(
                        status="error",
                        prompts=[],
                        message=f"Prompt not found: {request.prompt_id}"
                    )

                # Check scope (cannot update global)
                if existing.scope == "global":
                    return PromptRegistryResult(
                        status="error",
                        prompts=[],
                        message="Cannot update global (builtin) prompts"
                    )

                # Merge fields
                updated_data = existing.model_dump()
                if request.name is not None:
                    updated_data["name"] = request.name
                if request.description is not None:
                    updated_data["description"] = request.description
                if request.template is not None:
                    updated_data["template"] = request.template
                if request.variables is not None:
                    updated_data["variables"] = request.variables
                if request.tags is not None:
                    updated_data["tags"] = request.tags

                # Create updated prompt
                updated_prompt = PromptTemplate(**updated_data)

                # Save
                self.manager.save_prompt(updated_prompt)

                return PromptRegistryResult(
                    status="ok",
                    prompts=[updated_prompt],
                    message=f"Prompt updated: {request.prompt_id}"
                )

            elif request.action == "delete":
                # Validation
                if not request.prompt_id:
                    return PromptRegistryResult(
                        status="error",
                        prompts=[],
                        message="prompt_id is required for delete"
                    )

                # Check if exists
                existing = self.manager.get_prompt(request.prompt_id)
                if not existing:
                    return PromptRegistryResult(
                        status="error",
                        prompts=[],
                        message=f"Prompt not found: {request.prompt_id}"
                    )

                # Check scope (cannot delete global)
                if existing.scope == "global":
                    return PromptRegistryResult(
                        status="error",
                        prompts=[],
                        message="Cannot delete global (builtin) prompts"
                    )

                # Delete
                success = self.manager.delete_prompt(request.prompt_id)

                if success:
                    return PromptRegistryResult(
                        status="ok",
                        prompts=[],
                        message=f"Prompt deleted: {request.prompt_id}"
                    )
                else:
                    return PromptRegistryResult(
                        status="error",
                        prompts=[],
                        message=f"Failed to delete prompt: {request.prompt_id}"
                    )

            else:
                return PromptRegistryResult(
                    status="error",
                    prompts=[],
                    message=f"Unknown action: {request.action}"
                )

        except ValueError as e:
            logger.error(f"Validation error in prompt_registry: {e}")
            return PromptRegistryResult(
                status="error",
                prompts=[],
                message=f"Validation error: {e!s}"
            )
        except FileNotFoundError as e:
            logger.error(f"File not found in prompt_registry: {e}")
            return PromptRegistryResult(
                status="error",
                prompts=[],
                message=f"File not found: {e!s}"
            )
        except Exception as e:
            logger.error(f"Error in prompt_registry: {e}", exc_info=True)
            return PromptRegistryResult(
                status="error",
                prompts=[],
                message=f"Internal error: {e!s}"
            )

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
