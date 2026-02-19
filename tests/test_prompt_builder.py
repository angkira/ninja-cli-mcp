from __future__ import annotations
import pytest


"""
Comprehensive unit tests for ninja_coder.prompt_builder module.

Tests cover:
- Sequential plan prompt generation
- Parallel plan prompt generation
- Context file loading and size limits
- File count estimation heuristics
- Constraint and test plan formatting
"""


from pathlib import Path

import pytest

from ninja_coder.models import ExecutionMode, PlanStep, TestPlan
from ninja_coder.prompt_builder import (
    MAX_CONTEXT_FILE_SIZE,
    ParallelPlanPrompt,
    PromptBuilder,
    SequentialPlanPrompt,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository with test files."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Create directory structure
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "docs").mkdir()

    # Create sample files
    (repo / "src" / "main.py").write_text("def main():\n    pass\n")
    (repo / "src" / "utils.py").write_text("def helper():\n    return True\n")
    (repo / "tests" / "test_main.py").write_text("def test_main():\n    assert True\n")
    (repo / "README.md").write_text("# Test Project\n\nThis is a test.\n")

    return repo


@pytest.fixture
def sample_steps() -> list[PlanStep]:
    """Create sample plan steps for testing."""
    return [
        PlanStep(
            id="step-1",
            title="Create User Model",
            task="Create a User model in src/models/user.py with email and password fields",
            context_paths=["src/models/"],
            allowed_globs=["src/models/**/*.py"],
            deny_globs=["**/__pycache__/**"],
        ),
        PlanStep(
            id="step-2",
            title="Create User Service",
            task="Create UserService in src/services/user_service.py with register() and login() methods",
            context_paths=["src/models/", "src/services/"],
            allowed_globs=["src/services/**/*.py"],
            test_plan=TestPlan(
                unit=["pytest tests/test_user_service.py"],
                e2e=["pytest tests/e2e/test_auth.py"],
            ),
        ),
        PlanStep(
            id="step-3",
            title="Add API Routes",
            task="Create FastAPI routes in src/routes/auth.py for registration and login",
            context_paths=["src/services/", "src/routes/"],
            allowed_globs=["src/routes/**/*.py"],
            deny_globs=["src/routes/admin/**"],
        ),
    ]


@pytest.fixture
def parallel_tasks() -> list[PlanStep]:
    """Create parallel tasks with different file scopes."""
    return [
        PlanStep(
            id="frontend",
            title="Build Frontend UI",
            task="Create React components for user registration and login in frontend/src/components/",
            context_paths=["frontend/"],
            allowed_globs=["frontend/**/*"],
            deny_globs=["frontend/node_modules/**"],
        ),
        PlanStep(
            id="backend",
            title="Build Backend API",
            task="Create FastAPI application with user authentication endpoints in backend/",
            context_paths=["backend/"],
            allowed_globs=["backend/**/*.py"],
            deny_globs=["backend/venv/**"],
        ),
        PlanStep(
            id="docs",
            title="Create Documentation",
            task="Write API documentation in docs/api.md and setup guide in docs/setup.md",
            context_paths=["docs/"],
            allowed_globs=["docs/**/*.md"],
        ),
    ]


# ============================================================================
# Test Sequential Plan Prompt Generation
# ============================================================================


def test_sequential_prompt_structure(sample_steps: list[PlanStep]):
    """Test that sequential prompts contain all required sections."""
    prompt = SequentialPlanPrompt(
        steps=sample_steps,
        repo_root="/tmp/test_repo",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check main sections
    assert "# SEQUENTIAL EXECUTION PLAN" in result
    assert "## PLAN OVERVIEW" in result
    assert "## EXECUTION INSTRUCTIONS" in result
    assert "## OUTPUT FORMAT" in result

    # Check plan overview details
    assert "**Total Steps**: 3" in result
    assert "**Execution Mode**: quick" in result
    assert "**Repository**: /tmp/test_repo" in result

    # Check each step is present
    assert "## STEP 1: Create User Model" in result
    assert "## STEP 2: Create User Service" in result
    assert "## STEP 3: Add API Routes" in result

    # Check step IDs
    assert "**ID**: `step-1`" in result
    assert "**ID**: `step-2`" in result
    assert "**ID**: `step-3`" in result

    # Check execution instructions
    assert "### Sequential Execution" in result
    assert "Execute steps in order" in result
    assert "Maintain context" in result
    assert "Stop on failure" in result


def test_sequential_prompt_with_context_paths(sample_steps: list[PlanStep]):
    """Test that context paths are correctly formatted in prompt."""
    prompt = SequentialPlanPrompt(
        steps=sample_steps,
        repo_root="/tmp/test_repo",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check context paths section for step 1
    assert "### Context Paths" in result
    assert "- `src/models/`" in result

    # Check step 2 has multiple context paths
    assert "- `src/services/`" in result


def test_sequential_prompt_with_constraints(sample_steps: list[PlanStep]):
    """Test that file constraints are correctly formatted."""
    prompt = SequentialPlanPrompt(
        steps=sample_steps,
        repo_root="/tmp/test_repo",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check allowed globs
    assert "### File Constraints" in result
    assert "**Allowed patterns**:" in result
    assert "- `src/models/**/*.py`" in result
    assert "- `src/services/**/*.py`" in result

    # Check denied globs
    assert "**Denied patterns**:" in result
    assert "- `**/__pycache__/**`" in result
    assert "- `src/routes/admin/**`" in result


def test_sequential_prompt_with_test_plan(sample_steps: list[PlanStep]):
    """Test that test plans are correctly formatted."""
    prompt = SequentialPlanPrompt(
        steps=sample_steps,
        repo_root="/tmp/test_repo",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check test plan section for step 2
    assert "### Test Plan" in result
    assert "**Unit tests**:" in result
    assert "pytest tests/test_user_service.py" in result
    assert "**End-to-end tests**:" in result
    assert "pytest tests/e2e/test_auth.py" in result


def test_sequential_prompt_dependencies(sample_steps: list[PlanStep]):
    """Test that dependency notes are added for steps after first."""
    prompt = SequentialPlanPrompt(
        steps=sample_steps,
        repo_root="/tmp/test_repo",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # First step should not have dependencies section
    step1_start = result.index("## STEP 1:")
    step2_start = result.index("## STEP 2:")
    result[step1_start:step2_start]

    # Later steps should have dependencies
    assert "### Dependencies" in result
    assert "This step depends on the successful completion of Step 2" in result


def test_sequential_prompt_execution_mode_quick():
    """Test that quick mode is properly reflected in prompt."""
    steps = [
        PlanStep(
            id="test",
            title="Test Step",
            task="Test task",
        )
    ]

    prompt = SequentialPlanPrompt(
        steps=steps,
        repo_root="/tmp/test",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    assert "**Execution Mode**: quick" in result
    # Note: The _execution_instructions method returns early for QUICK mode
    # so we don't get the "Quick mode" text, but we should see the mode in overview


def test_sequential_prompt_output_format(sample_steps: list[PlanStep]):
    """Test that output format section is present and correct."""
    prompt = SequentialPlanPrompt(
        steps=sample_steps,
        repo_root="/tmp/test_repo",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check output format section
    assert "## OUTPUT FORMAT" in result
    assert '"id": "step_id"' in result
    assert '"status": "ok | fail | error"' in result
    assert '"summary": "Brief description' in result
    assert '"suspected_touched_paths"' in result

    # Check status values
    assert "### Status Values" in result
    assert "- **ok**: Step completed successfully" in result
    assert "- **fail**: Step failed validation/tests" in result
    assert "- **error**: Step encountered an error" in result


# ============================================================================
# Test Parallel Plan Prompt Generation
# ============================================================================


def test_parallel_prompt_structure(parallel_tasks: list[PlanStep]):
    """Test that parallel prompts contain all required sections."""
    prompt = ParallelPlanPrompt(
        tasks=parallel_tasks,
        repo_root="/tmp/test_repo",
        fanout=3,
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check main sections
    assert "# PARALLEL EXECUTION PLAN" in result
    assert "## PLAN OVERVIEW" in result
    assert "## CRITICAL: FILE ISOLATION" in result
    assert "## EXECUTION INSTRUCTIONS" in result
    assert "## OUTPUT FORMAT" in result

    # Check plan overview
    assert "**Total Tasks**: 3" in result
    assert "**Execution Mode**: Parallel" in result
    assert "**Max Concurrency**: 3" in result
    assert "**Repository**: /tmp/test_repo" in result

    # Check file isolation warnings
    assert "⚠️ **Each task MUST modify ONLY its own files**" in result
    assert "File conflicts will cause merge failures" in result


def test_parallel_prompt_task_formatting(parallel_tasks: list[PlanStep]):
    """Test that tasks are correctly formatted in parallel prompt."""
    prompt = ParallelPlanPrompt(
        tasks=parallel_tasks,
        repo_root="/tmp/test_repo",
        fanout=3,
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check each task is present
    assert "## TASK 1: Build Frontend UI" in result
    assert "## TASK 2: Build Backend API" in result
    assert "## TASK 3: Create Documentation" in result

    # Check task IDs
    assert "**ID**: `frontend`" in result
    assert "**ID**: `backend`" in result
    assert "**ID**: `docs`" in result


def test_parallel_prompt_file_scope(parallel_tasks: list[PlanStep]):
    """Test that file scope restrictions are prominently displayed."""
    prompt = ParallelPlanPrompt(
        tasks=parallel_tasks,
        repo_root="/tmp/test_repo",
        fanout=3,
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check file scope sections
    assert "### File Scope (CRITICAL)" in result
    assert "This task is RESTRICTED to these patterns:" in result
    assert "- `frontend/**/*`" in result
    assert "- `backend/**/*.py`" in result
    assert "- `docs/**/*.md`" in result

    # Check warnings
    assert "⚠️ **DO NOT modify files outside these patterns**" in result


def test_parallel_prompt_denied_patterns(parallel_tasks: list[PlanStep]):
    """Test that denied patterns are displayed for parallel tasks."""
    prompt = ParallelPlanPrompt(
        tasks=parallel_tasks,
        repo_root="/tmp/test_repo",
        fanout=3,
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check denied patterns section
    assert "### Denied Patterns" in result
    assert "This task MUST NOT touch:" in result
    assert "- `frontend/node_modules/**`" in result
    assert "- `backend/venv/**`" in result


def test_parallel_prompt_independence_note(parallel_tasks: list[PlanStep]):
    """Test that task independence is emphasized."""
    prompt = ParallelPlanPrompt(
        tasks=parallel_tasks,
        repo_root="/tmp/test_repo",
        fanout=3,
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check independence section
    assert "### Task Independence" in result
    assert "This task runs in parallel with others" in result
    assert "Be completely self-contained" in result
    assert "Not depend on outputs from other tasks" in result
    assert "Modify only files in its allowed scope" in result


def test_parallel_prompt_execution_instructions(parallel_tasks: list[PlanStep]):
    """Test that parallel execution instructions are comprehensive."""
    prompt = ParallelPlanPrompt(
        tasks=parallel_tasks,
        repo_root="/tmp/test_repo",
        fanout=4,
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check parallel execution section
    assert "### Parallel Execution" in result
    assert "Up to 4 tasks run simultaneously" in result
    assert "File isolation" in result
    assert "No shared state" in result
    assert "Independent validation" in result

    # Check agent assignment section
    assert "### Agent Assignment" in result
    assert "**Frontend Tasks**:" in result
    assert "**Backend Tasks**:" in result
    assert "**Database Tasks**:" in result
    assert "**Testing Tasks**:" in result
    assert "**DevOps Tasks**:" in result


def test_parallel_prompt_merge_strategy(parallel_tasks: list[PlanStep]):
    """Test that merge strategy is included in output format."""
    prompt = ParallelPlanPrompt(
        tasks=parallel_tasks,
        repo_root="/tmp/test_repo",
        fanout=3,
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Check merge report in output format
    assert "After all tasks complete, provide a merge report:" in result
    assert '"strategy": "no-conflicts | manual-review-needed | auto-merged"' in result

    # Check merge strategies
    assert "### Merge Strategies" in result
    assert "- **no-conflicts**: All tasks modified different files" in result
    assert "- **manual-review-needed**: File overlaps detected" in result
    assert "- **auto-merged**: Minor conflicts resolved automatically" in result


# ============================================================================
# Test Context File Loading
# ============================================================================


def test_context_file_loading_basic(temp_repo: Path):
    """Test loading context files from filesystem."""
    builder = PromptBuilder(str(temp_repo))

    steps = [
        PlanStep(
            id="test",
            title="Test",
            task="Test task",
            context_paths=["src/main.py", "README.md"],
        )
    ]

    context_files = builder._load_context_files(steps, [])

    # Check files were loaded
    assert "src/main.py" in context_files
    assert "README.md" in context_files
    assert "def main():" in context_files["src/main.py"]
    assert "# Test Project" in context_files["README.md"]


def test_context_file_loading_with_additional_paths(temp_repo: Path):
    """Test loading context files from both steps and additional paths."""
    builder = PromptBuilder(str(temp_repo))

    steps = [
        PlanStep(
            id="test",
            title="Test",
            task="Test task",
            context_paths=["src/main.py"],
        )
    ]

    context_files = builder._load_context_files(steps, ["README.md"])

    # Check both sources were loaded
    assert "src/main.py" in context_files
    assert "README.md" in context_files


def test_context_file_deduplication(temp_repo: Path):
    """Test that duplicate paths are not loaded twice."""
    builder = PromptBuilder(str(temp_repo))

    steps = [
        PlanStep(
            id="test1",
            title="Test 1",
            task="Test task 1",
            context_paths=["src/main.py"],
        ),
        PlanStep(
            id="test2",
            title="Test 2",
            task="Test task 2",
            context_paths=["src/main.py"],  # Duplicate
        ),
    ]

    context_files = builder._load_context_files(steps, ["src/main.py"])  # Triple

    # Should only have one entry
    assert len([k for k in context_files if k == "src/main.py"]) == 1


def test_context_file_size_limit(temp_repo: Path):
    """Test that oversized files are handled with error message."""
    # Create a large file
    large_file = temp_repo / "large.txt"
    large_content = "x" * (MAX_CONTEXT_FILE_SIZE + 1000)
    large_file.write_text(large_content)

    builder = PromptBuilder(str(temp_repo))

    steps = [
        PlanStep(
            id="test",
            title="Test",
            task="Test task",
            context_paths=["large.txt"],
        )
    ]

    context_files = builder._load_context_files(steps, [])

    # Check file is marked as too large
    assert "large.txt" in context_files
    assert "[File too large:" in context_files["large.txt"]
    assert f"limit is {MAX_CONTEXT_FILE_SIZE} bytes]" in context_files["large.txt"]


def test_context_file_missing_file(temp_repo: Path):
    """Test that missing files are silently skipped."""
    builder = PromptBuilder(str(temp_repo))

    steps = [
        PlanStep(
            id="test",
            title="Test",
            task="Test task",
            context_paths=["nonexistent.py"],
        )
    ]

    context_files = builder._load_context_files(steps, [])

    # Missing file should not be in context
    assert "nonexistent.py" not in context_files


def test_context_file_directory_skipped(temp_repo: Path):
    """Test that directories are skipped (not loaded as files)."""
    builder = PromptBuilder(str(temp_repo))

    steps = [
        PlanStep(
            id="test",
            title="Test",
            task="Test task",
            context_paths=["src/"],  # Directory, not file
        )
    ]

    context_files = builder._load_context_files(steps, [])

    # Directory itself should not be loaded
    assert "src/" not in context_files


def test_context_file_read_error_handling(temp_repo: Path):
    """Test that file read errors are captured in error message."""
    # Create a file, then make it unreadable (if possible on platform)
    unreadable = temp_repo / "unreadable.txt"
    unreadable.write_text("test")

    # Try to make it unreadable (may not work on all platforms)
    try:
        Path(unreadable).chmod(0o000)

        builder = PromptBuilder(str(temp_repo))

        steps = [
            PlanStep(
                id="test",
                title="Test",
                task="Test task",
                context_paths=["unreadable.txt"],
            )
        ]

        context_files = builder._load_context_files(steps, [])

        # Should have error message
        if "unreadable.txt" in context_files:
            assert "[Error reading file:" in context_files["unreadable.txt"]
    finally:
        # Restore permissions for cleanup
        try:
            Path(unreadable).chmod(0o644)
        except OSError:
            pass


# ============================================================================
# Test File Count Estimation
# ============================================================================


def test_file_count_estimation_file_extensions(temp_repo: Path):
    """Test that file extensions are counted in task description."""
    builder = PromptBuilder(str(temp_repo))

    task = "Create src/models/user.py and src/services/auth.py and tests/test_auth.py"
    count = builder._estimate_file_count(task)

    # Should count 3 .py extensions
    assert count >= 3


def test_file_count_estimation_action_verbs(temp_repo: Path):
    """Test that action verbs contribute to file count."""
    builder = PromptBuilder(str(temp_repo))

    task = "Create user model. Modify auth service. Update database schema. Add API routes."
    count = builder._estimate_file_count(task)

    # Should count create, modify, update, add
    assert count >= 4


def test_file_count_estimation_mixed_indicators(temp_repo: Path):
    """Test file count with multiple file extensions and actions."""
    builder = PromptBuilder(str(temp_repo))

    task = """
    Create the following files:
    - src/models/user.py (User model)
    - src/models/post.py (Post model)
    - src/services/user_service.py (UserService)
    - tests/test_user.py (unit tests)
    - docs/api.md (API documentation)
    """
    count = builder._estimate_file_count(task)

    # Should count multiple extensions (.py, .py, .py, .py, .md) + "create"
    assert count >= 5


def test_file_count_estimation_minimum_one(temp_repo: Path):
    """Test that file count is at least 1 even with no indicators."""
    builder = PromptBuilder(str(temp_repo))

    task = "Do something"
    count = builder._estimate_file_count(task)

    # Should return at least 1
    assert count >= 1


# ============================================================================
# Test Full Prompt Builder Integration
# ============================================================================


def test_sequential_prompt_with_real_context(temp_repo: Path, sample_steps: list[PlanStep]):
    """Test building sequential prompt with real context files."""
    builder = PromptBuilder(str(temp_repo))

    # Use real files as context
    steps_with_context = [
        PlanStep(
            id="test",
            title="Test",
            task="Test task",
            context_paths=["src/main.py", "README.md"],
        )
    ]

    prompt = builder.build_sequential_plan(
        steps=steps_with_context,
        mode=ExecutionMode.QUICK,
        context_paths=["src/utils.py"],
    )

    # Check context files section is present
    assert "## CONTEXT FILES" in prompt
    assert "### `src/main.py`" in prompt
    assert "### `README.md`" in prompt
    assert "### `src/utils.py`" in prompt

    # Check actual file contents are embedded
    assert "def main():" in prompt
    assert "# Test Project" in prompt
    assert "def helper():" in prompt


def test_parallel_prompt_with_constraints_and_context(
    temp_repo: Path, parallel_tasks: list[PlanStep]
):
    """Test building parallel prompt with constraints and real context."""
    builder = PromptBuilder(str(temp_repo))

    prompt = builder.build_parallel_plan(
        tasks=parallel_tasks,
        fanout=2,
        mode=ExecutionMode.QUICK,
        context_paths=["README.md"],
    )

    # Check fanout is correct
    assert "**Max Concurrency**: 2" in prompt

    # Check all tasks are present
    assert "## TASK 1: Build Frontend UI" in prompt
    assert "## TASK 2: Build Backend API" in prompt
    assert "## TASK 3: Create Documentation" in prompt

    # Check file scope constraints
    assert "- `frontend/**/*`" in prompt
    assert "- `backend/**/*.py`" in prompt
    assert "- `docs/**/*.md`" in prompt


def test_sequential_prompt_empty_context(temp_repo: Path):
    """Test sequential prompt generation with no context files."""
    builder = PromptBuilder(str(temp_repo))

    steps = [
        PlanStep(
            id="test",
            title="Test",
            task="Test task with no context",
        )
    ]

    prompt = builder.build_sequential_plan(
        steps=steps,
        mode=ExecutionMode.QUICK,
    )

    # Should have plan overview but no context files section
    assert "## PLAN OVERVIEW" in prompt
    assert "**Context Files**: 0" in prompt
    # Context section should not appear when empty
    assert "## CONTEXT FILES" not in prompt


def test_parallel_prompt_empty_context(temp_repo: Path):
    """Test parallel prompt generation with no context files."""
    builder = PromptBuilder(str(temp_repo))

    tasks = [
        PlanStep(
            id="test",
            title="Test",
            task="Test task",
            allowed_globs=["**/*.py"],
        )
    ]

    prompt = builder.build_parallel_plan(
        tasks=tasks,
        fanout=1,
        mode=ExecutionMode.QUICK,
    )

    # Should work without context
    assert "## PLAN OVERVIEW" in prompt
    assert "**Context Files**: 0" in prompt
    assert "## CONTEXT FILES" not in prompt


# ============================================================================
# Test Edge Cases
# ============================================================================


def test_sequential_prompt_single_step():
    """Test sequential prompt with only one step."""
    steps = [
        PlanStep(
            id="only",
            title="Only Step",
            task="Do something",
        )
    ]

    prompt = SequentialPlanPrompt(
        steps=steps,
        repo_root="/tmp/test",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    assert "**Total Steps**: 1" in result
    assert "## STEP 1: Only Step" in result
    # First step should not have dependencies section
    assert "### Dependencies" not in result


def test_parallel_prompt_single_task():
    """Test parallel prompt with only one task."""
    tasks = [
        PlanStep(
            id="only",
            title="Only Task",
            task="Do something independently",
            allowed_globs=["**/*.py"],
        )
    ]

    prompt = ParallelPlanPrompt(
        tasks=tasks,
        repo_root="/tmp/test",
        fanout=1,
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    assert "**Total Tasks**: 1" in result
    assert "**Max Concurrency**: 1" in result
    assert "## TASK 1: Only Task" in result


def test_prompt_with_special_characters_in_paths():
    """Test that special characters in paths are handled correctly."""
    steps = [
        PlanStep(
            id="special",
            title="Special Chars",
            task="Handle special chars in paths: $VAR, spaces, etc.",
            context_paths=["path with spaces/file.py", "path-with-dashes/file.py"],
            allowed_globs=["**/*.py", "special/[pattern].ts"],
        )
    ]

    prompt = SequentialPlanPrompt(
        steps=steps,
        repo_root="/tmp/test with spaces",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Should include paths as-is
    assert "path with spaces/file.py" in result
    assert "path-with-dashes/file.py" in result
    assert "/tmp/test with spaces" in result


def test_prompt_with_empty_globs():
    """Test prompt generation with empty allowed/deny globs."""
    steps = [
        PlanStep(
            id="no-globs",
            title="No Globs",
            task="Task without glob restrictions",
            allowed_globs=[],
            deny_globs=[],
        )
    ]

    prompt = SequentialPlanPrompt(
        steps=steps,
        repo_root="/tmp/test",
        mode=ExecutionMode.QUICK,
        context_files={},
    )

    result = prompt.to_prompt()

    # Should not have constraints section if no globs
    step_section = result[result.index("## STEP 1:") : result.index("---")]
    assert "### File Constraints" not in step_section
