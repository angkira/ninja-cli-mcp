"""Tool executor for prompt operations."""

import asyncio
from typing import Any

from ninja_common.security import monitored, rate_limited
from ninja_prompts.models import (
    PromptRegistryRequest,
    PromptRegistryResult,
    PromptSuggestRequest,
    PromptSuggestResult,
    PromptSuggestion,
    PromptChainRequest,
    PromptChainResult,
    ChainStepOutput,
)
from ninja_prompts.prompt_manager import PromptManager
from ninja_prompts.template_engine import TemplateEngine


class PromptToolExecutor:
    """Executes prompt-related operations."""

    def __init__(self):
        """Initialize the executor with manager and engine."""
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
                prompt = self.manager.get_prompt(request.prompt_id)
                if not prompt:
                    return PromptRegistryResult(
                        status="error", message=f"Prompt not found: {request.prompt_id}"
                    )
                return PromptRegistryResult(
                    status="ok", prompts=[prompt.model_dump()]
                )
            elif request.action == "create":
                from ninja_prompts.models import PromptTemplate

                prompt = PromptTemplate(
                    id=request.prompt_id or "",
                    name=request.name or "",
                    description=request.description or "",
                    template=request.template or "",
                    variables=request.variables or [],
                    tags=request.tags or [],
                    scope="user",
                )
                self.manager.save_prompt(prompt)
                return PromptRegistryResult(
                    status="ok",
                    message=f"Prompt created: {prompt.id}",
                    prompts=[prompt.model_dump()],
                )
            elif request.action == "delete":
                success = self.manager.delete_prompt(request.prompt_id)
                if not success:
                    return PromptRegistryResult(
                        status="error", message=f"Prompt not found: {request.prompt_id}"
                    )
                return PromptRegistryResult(
                    status="ok", message=f"Prompt deleted: {request.prompt_id}"
                )
            else:
                return PromptRegistryResult(
                    status="error", message=f"Unknown action: {request.action}"
                )
        except Exception as e:
            return PromptRegistryResult(status="error", message=str(e))

    @rate_limited(60, 60)
    @monitored
    async def prompt_suggest(
        self, request: PromptSuggestRequest, client_id: str = "default"
    ) -> PromptSuggestResult:
        """Suggest relevant prompts based on context.

        Args:
            request: Suggestion request with context
            client_id: Client identifier for monitoring

        Returns:
            PromptSuggestResult with ranked suggestions
        """
        try:
            prompts = self.manager.list_prompts()
            suggestions: list[PromptSuggestion] = []

            context = request.context or {}
            task = context.get("task", "").lower()
            language = context.get("language", "").lower()
            file_type = context.get("file_type", "").lower()

            # Score each prompt
            for prompt in prompts:
                score = 0.0
                reasons = []

                # Task matching
                if task and any(tag.lower() in task for tag in prompt.tags):
                    score += 0.4
                    reasons.append(f"Matches task '{task}'")

                # Language matching
                if language and language in prompt.description.lower():
                    score += 0.3
                    reasons.append(f"Supports {language}")

                # File type matching
                if file_type and file_type in prompt.description.lower():
                    score += 0.3
                    reasons.append(f"For {file_type} files")

                # Default minimal score for all prompts
                if score == 0:
                    score = 0.1

                if score > 0:
                    suggestion = PromptSuggestion(
                        prompt_id=prompt.id,
                        name=prompt.name,
                        relevance_score=min(score, 1.0),
                        reason="; ".join(reasons) if reasons else "General purpose",
                    )
                    suggestions.append(suggestion)

            # Sort by relevance
            suggestions.sort(key=lambda s: s.relevance_score, reverse=True)

            # Limit results
            max_suggestions = request.max_suggestions or 5
            suggestions = suggestions[:max_suggestions]

            return PromptSuggestResult(status="ok", suggestions=suggestions)
        except Exception as e:
            return PromptSuggestResult(status="error", message=str(e))

    @rate_limited(60, 60)
    @monitored
    async def prompt_chain(
        self, request: PromptChainRequest, client_id: str = "default"
    ) -> PromptChainResult:
        """Execute a prompt chain workflow.

        Args:
            request: Chain request with steps
            client_id: Client identifier for monitoring

        Returns:
            PromptChainResult with executed steps
        """
        try:
            executed_steps: list[ChainStepOutput] = []
            context: dict[str, Any] = {}

            for step in request.steps:
                prompt = self.manager.get_prompt(step.prompt_id)
                if not prompt:
                    return PromptChainResult(
                        status="error",
                        chain_id=request.chain_id,
                        message=f"Prompt not found: {step.prompt_id}",
                    )

                # Prepare variables for rendering
                vars_to_use = step.variables.copy() if step.variables else {}

                # Add previous step outputs to context
                for prev_step in executed_steps:
                    context[f"prev.{prev_step.step_name}"] = prev_step.output

                # Resolve template variables
                for key, value in vars_to_use.items():
                    if isinstance(value, str) and value.startswith("{{prev."):
                        # Replace with previous step output
                        prev_key = value.strip("{}")
                        vars_to_use[key] = context.get(prev_key, value)

                # Validate required variables
                missing = self.engine.validate_variables(prompt.template, vars_to_use)
                if missing:
                    return PromptChainResult(
                        status="error",
                        chain_id=request.chain_id,
                        message=f"Missing required variables: {missing}",
                    )

                # Render template
                output = self.engine.render(prompt.template, vars_to_use)

                # Store step output
                step_output = ChainStepOutput(
                    step_name=step.name, output=output, prompt_id=step.prompt_id
                )
                executed_steps.append(step_output)

            return PromptChainResult(
                status="ok", chain_id=request.chain_id, executed_steps=executed_steps
            )
        except Exception as e:
            return PromptChainResult(
                status="error", chain_id=request.chain_id, message=str(e)
            )
