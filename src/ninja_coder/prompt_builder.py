"""
Prompt builder for structured plan execution.

This module creates detailed, structured prompts for AI code CLI execution,
supporting both sequential and parallel multi-step plans.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import ExecutionMode, PlanStep


# ============================================================================
# Constants
# ============================================================================

MAX_CONTEXT_FILE_SIZE = 50 * 1024  # 50KB limit per file
MAX_CONTEXT_SNIPPET_CHARS = 4000  # per-file inline cap for prompts
MAX_TOTAL_CONTEXT_CHARS = 12000  # total inline budget across files


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
            lines.extend(
                [
                    "### Context Paths",
                    "",
                    "Pay special attention to these files/directories:",
                    "",
                ]
            )
            for path in step.context_paths:
                lines.append(f"- `{path}`")
            lines.append("")

        # File constraints
        if step.allowed_globs or step.deny_globs:
            lines.extend(
                [
                    "### File Constraints",
                    "",
                ]
            )
            if step.allowed_globs:
                lines.extend(
                    [
                        "**Allowed patterns**:",
                        "",
                    ]
                )
                for pattern in step.allowed_globs:
                    lines.append(f"- `{pattern}`")
                lines.append("")
            if step.deny_globs:
                lines.extend(
                    [
                        "**Denied patterns**:",
                        "",
                    ]
                )
                for pattern in step.deny_globs:
                    lines.append(f"- `{pattern}`")
                lines.append("")

        # Test plan
        if step.test_plan.unit or step.test_plan.e2e:
            lines.extend(
                [
                    "### Test Plan",
                    "",
                ]
            )
            if step.test_plan.unit:
                lines.extend(
                    [
                        "**Unit tests**:",
                        "",
                    ]
                )
                for cmd in step.test_plan.unit:
                    lines.append(f"```bash\n{cmd}\n```")
                    lines.append("")
            if step.test_plan.e2e:
                lines.extend(
                    [
                        "**End-to-end tests**:",
                        "",
                    ]
                )
                for cmd in step.test_plan.e2e:
                    lines.append(f"```bash\n{cmd}\n```")
                    lines.append("")

        # Dependencies note
        if index > 1:
            lines.extend(
                [
                    "### Dependencies",
                    "",
                    f"This step depends on the successful completion of Step {index - 1}.",
                    "Use context and artifacts from previous steps as needed.",
                    "",
                ]
            )

        lines.append("---")
        lines.append("")

        return lines

    def _execution_instructions(self) -> list[str]:
        """Generate execution instructions."""
        lines = [
            "## EXECUTION INSTRUCTIONS",
            "",
            "1. Execute steps in order; each step may use previous outputs.",
            "2. Stop on first failure and report it.",
            "3. Use specialist subagents if available; else general-purpose.",
            "",
            "### Error Handling",
            "",
            f"- Mode: {self.mode.value}",
        ]

        if self.mode == ExecutionMode.QUICK:
            lines.extend(
                [
                    "- Quick mode: single pass, no test-fix loop.",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "- Full mode: test-fix loop up to max_iterations per step.",
                    "",
                ]
            )
        return lines

    def _format_context_files(self) -> list[str]:
        """Format context files section with a total inline budget."""
        lines = [
            "## CONTEXT FILES",
            "",
            f"Read-only excerpts ({len(self.context_files)} files, budget {MAX_TOTAL_CONTEXT_CHARS} chars). "
            "Read full files from disk when needed.",
            "",
        ]
        budget = MAX_TOTAL_CONTEXT_CHARS
        for path, content in self.context_files.items():
            if budget <= 0:
                lines.extend(["", f"...[{len(self.context_files)} files total, budget exhausted]"])
                break
            excerpt = content[: min(len(content), MAX_CONTEXT_SNIPPET_CHARS, budget)]
            truncated = len(content) > len(excerpt)
            lines.extend([f"### `{path}`", "", "```", excerpt, "```", ""])
            if truncated:
                lines.append(f"...[truncated {len(content) - len(excerpt)} chars]")
                lines.append("")
            budget -= len(excerpt)
        return lines

    def _output_format(self) -> list[str]:
        """Define expected output format."""
        return [
            "## OUTPUT FORMAT",
            "",
            "Return exactly one JSON object per step, no prose, no code:",
            "",
            "```json",
            json.dumps(
                {
                    "id": "step_id",
                    "status": "ok | fail | error",
                    "summary": "1-2 sentences, files touched",
                    "notes": "warnings / follow-ups",
                    "suspected_touched_paths": ["path/to/file1.py"],
                },
                indent=2,
            ),
            "```",
            "",
            "Status: ok=done, fail=validation/tests (recoverable), error=unrecoverable.",
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
            "- **Execution Mode**: Parallel",
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
            lines.extend(
                [
                    "### File Scope (CRITICAL)",
                    "",
                    "This task is RESTRICTED to these patterns:",
                    "",
                ]
            )
            for pattern in task.allowed_globs:
                lines.append(f"- `{pattern}`")
            lines.extend(
                [
                    "",
                    "⚠️ **DO NOT modify files outside these patterns**",
                    "",
                ]
            )

        if task.deny_globs:
            lines.extend(
                [
                    "### Denied Patterns",
                    "",
                    "This task MUST NOT touch:",
                    "",
                ]
            )
            for pattern in task.deny_globs:
                lines.append(f"- `{pattern}`")
            lines.append("")

        # Context paths
        if task.context_paths:
            lines.extend(
                [
                    "### Context Paths",
                    "",
                    "Reference these for context (read-only unless in allowed scope):",
                    "",
                ]
            )
            for path in task.context_paths:
                lines.append(f"- `{path}`")
            lines.append("")

        # Independence note
        lines.extend(
            [
                "### Task Independence",
                "",
                "This task runs in parallel with others. It MUST:",
                "",
                "- Be completely self-contained",
                "- Not depend on outputs from other tasks",
                "- Modify only files in its allowed scope",
                "- Not assume any particular execution order",
                "",
            ]
        )

        lines.append("---")
        lines.append("")

        return lines

    def _execution_instructions(self) -> list[str]:
        """Generate execution instructions for parallel execution."""
        return [
            "## EXECUTION INSTRUCTIONS",
            "",
            f"1. Up to {self.fanout} tasks run concurrently; no shared state.",
            "2. Each task modifies ONLY its own allowed scope; overlapping writes = failure.",
            "3. Use specialist subagents if available; else general-purpose.",
            "4. After all tasks: verify no file overlaps, merge, report conflicts.",
            "",
        ]

    def _format_context_files(self) -> list[str]:
        """Format context files section with a total inline budget."""
        lines = [
            "## CONTEXT FILES",
            "",
            f"Read-only excerpts ({len(self.context_files)} files, budget {MAX_TOTAL_CONTEXT_CHARS} chars). "
            "Read full files from disk when needed.",
            "",
        ]
        budget = MAX_TOTAL_CONTEXT_CHARS
        for path, content in self.context_files.items():
            if budget <= 0:
                lines.extend(["", f"...[{len(self.context_files)} files total, budget exhausted]"])
                break
            excerpt = content[: min(len(content), MAX_CONTEXT_SNIPPET_CHARS, budget)]
            truncated = len(content) > len(excerpt)
            lines.extend([f"### `{path}`", "", "```", excerpt, "```", ""])
            if truncated:
                lines.append(f"...[truncated {len(content) - len(excerpt)} chars]")
                lines.append("")
            budget -= len(excerpt)
        return lines

    def _output_format(self) -> list[str]:
        """Define expected output format."""
        return [
            "## OUTPUT FORMAT",
            "",
            "Return exactly one JSON object per task plus a merge report. No prose, no code:",
            "",
            "```json",
            json.dumps(
                {
                    "id": "task_id",
                    "status": "ok | fail | error",
                    "summary": "1-2 sentences, files touched",
                    "notes": "warnings / follow-ups",
                    "suspected_touched_paths": ["path/to/file1.py"],
                },
                indent=2,
            ),
            "```",
            "",
            "```json",
            json.dumps(
                {
                    "strategy": "no-conflicts | manual-review-needed | auto-merged",
                    "notes": "merge details and conflicts",
                },
                indent=2,
            ),
            "```",
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
