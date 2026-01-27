"""
Multi-agent orchestration for complex coding tasks.

Integrates oh-my-opencode framework with specialized agents for
parallel execution of complex, full-stack development tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from ninja_common.logging_utils import get_logger


if TYPE_CHECKING:
    from ninja_coder.strategies.opencode_strategy import OpenCodeStrategy

logger = get_logger(__name__)


@dataclass
class AgentRole:
    """Definition of a specialized agent role."""

    name: str
    description: str
    keywords: list[str]  # Keywords that trigger this agent


class TaskComplexity:
    """Task complexity levels for routing."""

    SIMPLE = "simple"  # Single file, < 50 lines
    MODERATE = "moderate"  # 2-5 files, < 200 lines
    COMPLEX = "complex"  # 6-10 files, refactoring
    FULL_STACK = "full_stack"  # Multiple components, architecture


class TaskType:
    """Task types for specialized handling."""

    QUICK_FIX = "quick_fix"  # Bug fix, typo
    REFACTOR = "refactor"  # Code restructuring
    FEATURE = "feature"  # New functionality
    ARCHITECTURE = "architecture"  # System design
    MULTI_AGENT = "multi_agent"  # Requires orchestration


@dataclass
class TaskAnalysis:
    """Analysis result for intelligent routing."""

    complexity: str  # TaskComplexity value
    task_type: str  # TaskType value
    estimated_files: int
    requires_session: bool
    requires_multi_agent: bool
    keywords: list[str]
    suggested_cli: str  # "aider", "opencode", etc.


class MultiAgentOrchestrator:
    """Orchestrates oh-my-opencode multi-agent tasks."""

    # Agent definitions
    AGENTS: ClassVar[list[AgentRole]] = [
        AgentRole(
            name="Chief AI Architect",
            description="System design, architecture decisions, technical planning",
            keywords=["architecture", "design", "system", "structure", "plan"],
        ),
        AgentRole(
            name="Frontend Engineer",
            description="React, Vue, UI components, styling, responsive design",
            keywords=["frontend", "react", "vue", "ui", "component", "css", "html"],
        ),
        AgentRole(
            name="Backend Engineer",
            description="APIs, databases, server logic, data models",
            keywords=["backend", "api", "database", "server", "endpoint", "sql"],
        ),
        AgentRole(
            name="DevOps Engineer",
            description="CI/CD, deployment, infrastructure, Docker, monitoring",
            keywords=["devops", "docker", "ci/cd", "deploy", "infrastructure", "k8s"],
        ),
        AgentRole(
            name="Oracle",
            description="Decision making, trade-off analysis, code review",
            keywords=["review", "decision", "tradeoff", "evaluate", "assess"],
        ),
        AgentRole(
            name="Librarian",
            description="Documentation, code organization, README files",
            keywords=["documentation", "docs", "readme", "comments", "organize"],
        ),
        AgentRole(
            name="Explorer",
            description="Code analysis, refactoring, optimization",
            keywords=["refactor", "optimize", "analyze", "improve", "clean"],
        ),
    ]

    def __init__(self, opencode_strategy: OpenCodeStrategy):
        """Initialize orchestrator.

        Args:
            opencode_strategy: OpenCode strategy instance.
        """
        self.strategy = opencode_strategy
        logger.info("MultiAgentOrchestrator initialized with 7 specialized agents")

    def should_use_multi_agent(self, analysis: TaskAnalysis) -> bool:
        """Determine if task benefits from multi-agent orchestration.

        Args:
            analysis: Task analysis result.

        Returns:
            True if multi-agent should be used.
        """
        return (
            analysis.requires_multi_agent
            or analysis.complexity == TaskComplexity.FULL_STACK
            or analysis.task_type == TaskType.ARCHITECTURE
            or analysis.estimated_files > 10
        )

    def select_agents(self, prompt: str, analysis: TaskAnalysis) -> list[str]:
        """Select which agents are needed for this task.

        Args:
            prompt: Task prompt.
            analysis: Task analysis.

        Returns:
            List of agent names to activate.
        """
        prompt_lower = prompt.lower()
        selected = []

        # Always include Architect for complex tasks
        if analysis.complexity in [TaskComplexity.COMPLEX, TaskComplexity.FULL_STACK]:
            selected.append("Chief AI Architect")
            logger.debug("Added Chief AI Architect for complex task")

        # Select based on keywords
        for agent in self.AGENTS:
            if any(keyword in prompt_lower for keyword in agent.keywords):
                if agent.name not in selected:
                    selected.append(agent.name)
                    logger.debug(f"Added {agent.name} based on keywords")

        # Always include Oracle for coordination if multiple agents
        if len(selected) > 2 and "Oracle" not in selected:
            selected.append("Oracle")
            logger.debug("Added Oracle for coordination")

        # Always include Librarian for documentation
        if "Librarian" not in selected:
            selected.append("Librarian")
            logger.debug("Added Librarian for documentation")

        logger.info(f"Selected {len(selected)} agents: {', '.join(selected)}")
        return selected

    def build_ultrawork_prompt(
        self,
        task: str,
        agents: list[str],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Build enhanced prompt for oh-my-opencode.

        Args:
            task: Original task description.
            agents: List of agent names to activate.
            context: Optional additional context.

        Returns:
            Enhanced prompt with ultrawork directive.
        """
        prompt_parts = [
            "🎯 TASK:",
            task,
            "",
            "🤖 MULTI-AGENT MODE: ultrawork",
            "",
            "Required agents:",
        ]

        # Add agent descriptions
        for agent in agents:
            agent_def = next((a for a in self.AGENTS if a.name == agent), None)
            if agent_def:
                prompt_parts.append(f"  • {agent_def.name}: {agent_def.description}")

        prompt_parts.extend(
            [
                "",
                "Coordination instructions:",
                "  • Agents should communicate through shared session context",
                "  • Execute subtasks in parallel where possible",
                "  • Chief Architect designs first, others implement in parallel",
                "  • Oracle validates integration points",
                "  • Librarian documents final result",
                "",
            ]
        )

        # Add context if provided
        if context:
            prompt_parts.append("Additional context:")
            for key, value in context.items():
                prompt_parts.append(f"  • {key}: {value}")
            prompt_parts.append("")

        return "\n".join(prompt_parts)

    def analyze_task(self, prompt: str, context_paths: list[str] | None = None) -> TaskAnalysis:
        """Analyze task to determine complexity and requirements.

        Args:
            prompt: Task prompt.
            context_paths: Files to include in context.

        Returns:
            TaskAnalysis with complexity and routing suggestions.
        """
        prompt_lower = prompt.lower()
        keywords = []

        # Detect complexity indicators
        if any(kw in prompt_lower for kw in ["frontend", "backend", "api", "database"]):
            keywords.extend(["frontend", "backend", "api", "database"])
            complexity = TaskComplexity.FULL_STACK
        elif any(kw in prompt_lower for kw in ["refactor", "restructure", "reorganize"]):
            keywords.append("refactor")
            complexity = TaskComplexity.COMPLEX
        elif context_paths and len(context_paths) > 5:
            complexity = TaskComplexity.COMPLEX
        elif context_paths and len(context_paths) > 2:
            complexity = TaskComplexity.MODERATE
        else:
            complexity = TaskComplexity.SIMPLE

        # Detect task type
        if any(kw in prompt_lower for kw in ["fix", "bug", "error", "typo"]):
            task_type = TaskType.QUICK_FIX
        elif any(kw in prompt_lower for kw in ["refactor", "restructure"]):
            task_type = TaskType.REFACTOR
        elif any(kw in prompt_lower for kw in ["architecture", "design", "system"]):
            task_type = TaskType.ARCHITECTURE
        elif any(kw in prompt_lower for kw in ["ultrawork", "ulw", "multi-agent"]):
            task_type = TaskType.MULTI_AGENT
        else:
            task_type = TaskType.FEATURE

        # Determine if session/multi-agent needed
        requires_session = complexity in [TaskComplexity.COMPLEX, TaskComplexity.FULL_STACK]
        requires_multi_agent = (
            task_type == TaskType.MULTI_AGENT
            or complexity == TaskComplexity.FULL_STACK
            or "ultrawork" in prompt_lower
            or "ulw" in prompt_lower
        )

        # Suggest CLI
        if requires_multi_agent:
            suggested_cli = "opencode"  # Only OpenCode supports oh-my-opencode
        elif complexity == TaskComplexity.SIMPLE and task_type == TaskType.QUICK_FIX:
            suggested_cli = "aider"  # Aider is fastest for simple tasks
        elif complexity in [TaskComplexity.COMPLEX, TaskComplexity.FULL_STACK]:
            suggested_cli = "opencode"  # OpenCode better for complex tasks with sessions
        else:
            suggested_cli = "aider"  # Default to Aider for moderate tasks

        logger.debug(
            f"Task analysis: complexity={complexity}, type={task_type}, "
            f"multi_agent={requires_multi_agent}, cli={suggested_cli}"
        )

        return TaskAnalysis(
            complexity=complexity,
            task_type=task_type,
            estimated_files=len(context_paths) if context_paths else 1,
            requires_session=requires_session,
            requires_multi_agent=requires_multi_agent,
            keywords=keywords,
            suggested_cli=suggested_cli,
        )

    def get_agent_summary(self) -> dict[str, Any]:
        """Get summary of available agents.

        Returns:
            Dict with agent information.
        """
        return {
            "total_agents": len(self.AGENTS),
            "agents": [
                {
                    "name": agent.name,
                    "description": agent.description,
                    "keywords": agent.keywords,
                }
                for agent in self.AGENTS
            ],
        }
