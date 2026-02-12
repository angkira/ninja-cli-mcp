"""
Prompt builder for structured plan execution.

This module creates detailed, structured prompts for AI code CLI execution,
supporting both sequential and parallel multi-step plans.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import ExecutionMode, PlanStep


# ============================================================================
# Constants
# ============================================================================

MAX_CONTEXT_FILE_SIZE = 50 * 1024  # 50KB limit per file


# ============================================================================
# Prompt Templates
# ============================================================================


@dataclass
class SequentialPlanPrompt:
    """Structured prompt for sequential plan execution."""

    steps: list[PlanStep]
    repo_root: str
    mode: ExecutionMode
    context_files: dict[str, str]  # path -> content

    def to_prompt(self) -> str:
        """Generate detailed sequential plan prompt."""
        lines = [
            "# SEQUENTIAL EXECUTION PLAN",
            "",
            "You are executing a multi-step plan with dependencies. Each step must complete successfully before the next begins.",
            "",
            "## PLAN OVERVIEW",
            "",
            f"- **Total Steps**: {len(self.steps)}",
            f"- **Execution Mode**: {self.mode.value}",
            f"- **Repository**: {self.repo_root}",
            f"- **Context Files**: {len(self.context_files)}",
            "",
        ]

        # Add each step with detailed instructions
        for i, step in enumerate(self.steps, 1):
            lines.extend(self._format_step(i, step))

        # Add execution instructions
        lines.extend(self._execution_instructions())

        # Add context files
        if self.context_files:
            lines.extend(self._format_context_files())

        # Add output format
        lines.extend(self._output_format())

        return "\n".join(lines)

    def _format_step(self, index: int, step: PlanStep) -> list[str]:
        """Format a single step with all details."""
        lines = [
            f"## STEP {index}: {step.title}",
            "",
            f"**ID**: `{step.id}`",
            "",
            "### Task Description",
            "",
            step.task,
            "",
        ]

        # Context paths
        if step.context_paths:
            lines.extend([
                "### Context Paths",
                "",
                "Pay special attention to these files/directories:",
                "",
            ])
            for path in step.context_paths:
                lines.append(f"- `{path}`")
            lines.append("")

        # File constraints
        if step.allowed_globs or step.deny_globs:
            lines.extend([
                "### File Constraints",
                "",
            ])
            if step.allowed_globs:
                lines.extend([
                    "**Allowed patterns**:",
                    "",
                ])
                for pattern in step.allowed_globs:
                    lines.append(f"- `{pattern}`")
                lines.append("")
            if step.deny_globs:
                lines.extend([
                    "**Denied patterns**:",
                    "",
                ])
                for pattern in step.deny_globs:
                    lines.append(f"- `{pattern}`")
                lines.append("")

        # Test plan
        if step.test_plan.unit or step.test_plan.e2e:
            lines.extend([
                "### Test Plan",
                "",
            ])
            if step.test_plan.unit:
                lines.extend([
                    "**Unit tests**:",
                    "",
                ])
                for cmd in step.test_plan.unit:
                    lines.append(f"```bash\n{cmd}\n```")
                    lines.append("")
            if step.test_plan.e2e:
                lines.extend([
                    "**End-to-end tests**:",
                    "",
                ])
                for cmd in step.test_plan.e2e:
                    lines.append(f"```bash\n{cmd}\n```")
                    lines.append("")

        # Dependencies note
        if index > 1:
            lines.extend([
                "### Dependencies",
                "",
                f"This step depends on the successful completion of Step {index - 1}.",
                "Use context and artifacts from previous steps as needed.",
                "",
            ])

        lines.append("---")
        lines.append("")

        return lines

    def _execution_instructions(self) -> list[str]:
        """Generate execution instructions."""
        return [
            "## EXECUTION INSTRUCTIONS",
            "",
            "### Sequential Execution",
            "",
            "1. **Execute steps in order**: Complete Step 1 before Step 2, Step 2 before Step 3, etc.",
            "2. **Maintain context**: Each step can reference outputs from previous steps.",
            "3. **Stop on failure**: If any step fails, stop execution and report the failure.",
            "4. **Validate thoroughly**: Ensure each step's requirements are met before proceeding.",
            "",
            "### Context Flow",
            "",
            "- Previous steps may create files, modify code, or establish patterns",
            "- Later steps can build upon these changes",
            "- Maintain consistency across all steps",
            "",
            "### Multi-Agent Activation",
            "",
            "If specialized agents are available (Frontend, Backend, Database, etc.):",
            "",
            "1. **Analyze each step's task** to identify the most relevant agent",
            "2. **Activate appropriate agents** based on keywords and file patterns:",
            "   - Frontend: React, Vue, Angular, UI components, styling",
            "   - Backend: API, routes, services, controllers, business logic",
            "   - Database: Models, migrations, schemas, queries, ORM",
            "   - Testing: Tests, specs, fixtures, mocks",
            "   - DevOps: CI/CD, Docker, deployment, infrastructure",
            "3. **Use general-purpose agent** if no specialist matches",
            "",
            "### Error Handling",
            "",
            f"- **Mode**: {self.mode.value}",
        ]

        if self.mode == ExecutionMode.QUICK:
            return [
                "- **Quick mode**: Single-pass execution, no test-fix loop",
                "- If errors occur, report them and stop",
                "",
            ]
        else:
            return [
                "- **Full mode**: Test-fix loop enabled",
                "- Run tests after implementation",
                "- Fix issues and re-test up to max_iterations",
                "- Report final status",
                "",
            ]

    def _format_context_files(self) -> list[str]:
        """Format context files section."""
        lines = [
            "## CONTEXT FILES",
            "",
            f"The following {len(self.context_files)} files are provided for context:",
            "",
        ]

        for path, content in self.context_files.items():
            lines.extend([
                f"### `{path}`",
                "",
                "```",
                content,
                "```",
                "",
            ])

        return lines

    def _output_format(self) -> list[str]:
        """Define expected output format."""
        return [
            "## OUTPUT FORMAT",
            "",
            "For each step, provide a structured result:",
            "",
            "```json",
            json.dumps(
                {
                    "id": "step_id",
                    "status": "ok | fail | error",
                    "summary": "Brief description of what was accomplished",
                    "notes": "Additional details, warnings, or recommendations",
                    "suspected_touched_paths": ["path/to/file1.py", "path/to/file2.ts"],
                },
                indent=2,
            ),
            "```",
            "",
            "### Status Values",
            "",
            "- **ok**: Step completed successfully",
            "- **fail**: Step failed validation/tests (recoverable)",
            "- **error**: Step encountered an error (unrecoverable)",
            "",
            "### Summary Guidelines",
            "",
            "- Be concise (1-3 sentences)",
            "- Focus on what was accomplished",
            "- Mention key files created/modified",
            "- Note any important decisions made",
            "",
            "### Notes Guidelines",
            "",
            "- Include warnings or caveats",
            "- Suggest follow-up actions if needed",
            "- Document any deviations from the plan",
            "- Highlight dependencies for next steps",
            "",
        ]


@dataclass
class ParallelPlanPrompt:
    """Structured prompt for parallel plan execution."""

    tasks: list[PlanStep]
    repo_root: str
    fanout: int
    mode: ExecutionMode
    context_files: dict[str, str]  # path -> content

    def to_prompt(self) -> str:
        """Generate detailed parallel plan prompt."""
        lines = [
            "# PARALLEL EXECUTION PLAN",
            "",
            "You are executing multiple independent tasks in parallel. Each task must be completely independent with no shared file modifications.",
            "",
            "## PLAN OVERVIEW",
            "",
            f"- **Total Tasks**: {len(self.tasks)}",
            f"- **Execution Mode**: Parallel",
            f"- **Max Concurrency**: {self.fanout}",
            f"- **Repository**: {self.repo_root}",
            f"- **Context Files**: {len(self.context_files)}",
            "",
            "## CRITICAL: FILE ISOLATION",
            "",
            "⚠️ **Each task MUST modify ONLY its own files**",
            "",
            "- Tasks run simultaneously on separate branches/workspaces",
            "- File conflicts will cause merge failures",
            "- Verify task independence before execution",
            "- Use allowed_globs/deny_globs to enforce boundaries",
            "",
        ]

        # Add each task with detailed instructions
        for i, task in enumerate(self.tasks, 1):
            lines.extend(self._format_task(i, task))

        # Add execution instructions
        lines.extend(self._execution_instructions())

        # Add context files
        if self.context_files:
            lines.extend(self._format_context_files())

        # Add output format
        lines.extend(self._output_format())

        return "\n".join(lines)

    def _format_task(self, index: int, task: PlanStep) -> list[str]:
        """Format a single task with all details."""
        lines = [
            f"## TASK {index}: {task.title}",
            "",
            f"**ID**: `{task.id}`",
            "",
            "### Task Description",
            "",
            task.task,
            "",
        ]

        # File scope
        if task.allowed_globs:
            lines.extend([
                "### File Scope (CRITICAL)",
                "",
                "This task is RESTRICTED to these patterns:",
                "",
            ])
            for pattern in task.allowed_globs:
                lines.append(f"- `{pattern}`")
            lines.extend([
                "",
                "⚠️ **DO NOT modify files outside these patterns**",
                "",
            ])

        if task.deny_globs:
            lines.extend([
                "### Denied Patterns",
                "",
                "This task MUST NOT touch:",
                "",
            ])
            for pattern in task.deny_globs:
                lines.append(f"- `{pattern}`")
            lines.append("")

        # Context paths
        if task.context_paths:
            lines.extend([
                "### Context Paths",
                "",
                "Reference these for context (read-only unless in allowed scope):",
                "",
            ])
            for path in task.context_paths:
                lines.append(f"- `{path}`")
            lines.append("")

        # Independence note
        lines.extend([
            "### Task Independence",
            "",
            "This task runs in parallel with others. It MUST:",
            "",
            "- Be completely self-contained",
            "- Not depend on outputs from other tasks",
            "- Modify only files in its allowed scope",
            "- Not assume any particular execution order",
            "",
        ])

        lines.append("---")
        lines.append("")

        return lines

    def _execution_instructions(self) -> list[str]:
        """Generate execution instructions for parallel execution."""
        lines = [
            "## EXECUTION INSTRUCTIONS",
            "",
            "### Parallel Execution",
            "",
            f"1. **Concurrent execution**: Up to {self.fanout} tasks run simultaneously",
            "2. **File isolation**: Each task modifies only its own files",
            "3. **No shared state**: Tasks cannot communicate or share data",
            "4. **Independent validation**: Each task is tested independently",
            "",
            "### Agent Assignment",
            "",
            "Each task should be analyzed and assigned to the most appropriate agent:",
            "",
            "**Frontend Tasks**:",
            "- React, Vue, Angular, Svelte components",
            "- UI styling (CSS, Sass, Tailwind)",
            "- Client-side state management",
            "- Browser APIs and interactions",
            "",
            "**Backend Tasks**:",
            "- API endpoints and routes",
            "- Business logic and services",
            "- Authentication and authorization",
            "- Server-side processing",
            "",
            "**Database Tasks**:",
            "- Schema design and models",
            "- Migrations and data transformations",
            "- Query optimization",
            "- ORM configuration",
            "",
            "**Testing Tasks**:",
            "- Unit tests and specs",
            "- Integration tests",
            "- Test fixtures and mocks",
            "- Test infrastructure",
            "",
            "**DevOps Tasks**:",
            "- CI/CD pipelines",
            "- Docker and containerization",
            "- Deployment scripts",
            "- Infrastructure as code",
            "",
            "**General Tasks**:",
            "- Documentation",
            "- Configuration files",
            "- Multi-domain features",
            "- Refactoring across boundaries",
            "",
            "### Multi-Agent Activation",
            "",
            "For each task:",
            "",
            "1. **Analyze task keywords** (Frontend, Backend, Database, Test, DevOps, etc.)",
            "2. **Check file patterns** (frontend/*, backend/*, database/*, etc.)",
            "3. **Activate specialized agent** if available",
            "4. **Fall back to general-purpose agent** if no specialist matches",
            "5. **Execute task** within the agent's context and expertise",
            "",
            "### Merge Strategy",
            "",
            "After all tasks complete:",
            "",
            "1. **Verify no conflicts**: Check that file modifications don't overlap",
            "2. **Merge changes**: Combine all task branches",
            "3. **Report conflicts**: Document any merge issues",
            "",
        ]

        return lines

    def _format_context_files(self) -> list[str]:
        """Format context files section."""
        lines = [
            "## CONTEXT FILES",
            "",
            f"The following {len(self.context_files)} files are provided for context:",
            "",
        ]

        for path, content in self.context_files.items():
            lines.extend([
                f"### `{path}`",
                "",
                "```",
                content,
                "```",
                "",
            ])

        return lines

    def _output_format(self) -> list[str]:
        """Define expected output format."""
        return [
            "## OUTPUT FORMAT",
            "",
            "For each task, provide a structured result:",
            "",
            "```json",
            json.dumps(
                {
                    "id": "task_id",
                    "status": "ok | fail | error",
                    "summary": "Brief description of what was accomplished",
                    "notes": "Additional details, warnings, or recommendations",
                    "suspected_touched_paths": ["path/to/file1.py", "path/to/file2.ts"],
                },
                indent=2,
            ),
            "```",
            "",
            "After all tasks complete, provide a merge report:",
            "",
            "```json",
            json.dumps(
                {
                    "strategy": "no-conflicts | manual-review-needed | auto-merged",
                    "notes": "Details about merge process and any conflicts",
                },
                indent=2,
            ),
            "```",
            "",
            "### Status Values",
            "",
            "- **ok**: Task completed successfully",
            "- **fail**: Task failed validation/tests (recoverable)",
            "- **error**: Task encountered an error (unrecoverable)",
            "",
            "### Merge Strategies",
            "",
            "- **no-conflicts**: All tasks modified different files, clean merge",
            "- **manual-review-needed**: File overlaps detected, manual intervention required",
            "- **auto-merged**: Minor conflicts resolved automatically",
            "",
        ]


# ============================================================================
# Prompt Builder
# ============================================================================


class PromptBuilder:
    """Builder for creating structured plan prompts with context."""

    def __init__(self, repo_root: str):
        """Initialize prompt builder.

        Args:
            repo_root: Absolute path to repository root
        """
        self.repo_root = Path(repo_root)

    def build_sequential_plan(
        self,
        steps: list[PlanStep],
        mode: ExecutionMode,
        context_paths: list[str] | None = None,
    ) -> str:
        """Build prompt for sequential plan execution.

        Args:
            steps: List of plan steps to execute in order
            mode: Execution mode (quick or full)
            context_paths: Additional context files to load

        Returns:
            Formatted prompt string
        """
        # Load context files
        context_files = self._load_context_files(steps, context_paths or [])

        # Create prompt
        prompt = SequentialPlanPrompt(
            steps=steps,
            repo_root=str(self.repo_root),
            mode=mode,
            context_files=context_files,
        )

        return prompt.to_prompt()

    def build_parallel_plan(
        self,
        tasks: list[PlanStep],
        fanout: int,
        mode: ExecutionMode,
        context_paths: list[str] | None = None,
    ) -> str:
        """Build prompt for parallel plan execution.

        Args:
            tasks: List of independent tasks to execute in parallel
            fanout: Maximum concurrent executions
            mode: Execution mode (quick or full)
            context_paths: Additional context files to load

        Returns:
            Formatted prompt string
        """
        # Load context files
        context_files = self._load_context_files(tasks, context_paths or [])

        # Create prompt
        prompt = ParallelPlanPrompt(
            tasks=tasks,
            repo_root=str(self.repo_root),
            fanout=fanout,
            mode=mode,
            context_files=context_files,
        )

        return prompt.to_prompt()

    def _load_context_files(
        self,
        steps: list[PlanStep],
        additional_paths: list[str],
    ) -> dict[str, str]:
        """Load context files from step context_paths and additional paths.

        Args:
            steps: Plan steps with context_paths
            additional_paths: Additional paths to load

        Returns:
            Dictionary mapping file paths to content
        """
        context_files: dict[str, str] = {}
        seen_paths: set[str] = set()

        # Collect all context paths
        all_paths = list(additional_paths)
        for step in steps:
            all_paths.extend(step.context_paths)

        # Load each unique file
        for path_str in all_paths:
            if path_str in seen_paths:
                continue
            seen_paths.add(path_str)

            path = self.repo_root / path_str
            if not path.exists():
                continue

            # Only load files (not directories)
            if not path.is_file():
                continue

            # Check file size
            try:
                size = path.stat().st_size
                if size > MAX_CONTEXT_FILE_SIZE:
                    context_files[path_str] = (
                        f"[File too large: {size} bytes, limit is {MAX_CONTEXT_FILE_SIZE} bytes]"
                    )
                    continue

                # Read content
                content = path.read_text(encoding="utf-8", errors="replace")
                context_files[path_str] = content

            except Exception as e:
                context_files[path_str] = f"[Error reading file: {e}]"

        return context_files

    def _estimate_file_count(self, task: str) -> int:
        """Estimate number of files mentioned in task description.

        Args:
            task: Task description

        Returns:
            Estimated file count (rough heuristic)
        """
        # Count file-like patterns
        indicators = [
            ".py",
            ".ts",
            ".js",
            ".tsx",
            ".jsx",
            ".java",
            ".go",
            ".rs",
            ".cpp",
            ".c",
            ".h",
            ".hpp",
            ".md",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".xml",
            ".html",
            ".css",
            ".scss",
            ".sql",
        ]

        count = 0
        for indicator in indicators:
            count += task.count(indicator)

        # Also count explicit "create" or "modify" verbs
        count += task.lower().count("create ")
        count += task.lower().count("modify ")
        count += task.lower().count("update ")
        count += task.lower().count("add ")

        return max(1, count)  # At least 1 file
