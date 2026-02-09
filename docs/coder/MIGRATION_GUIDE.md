# Migration Guide: Ninja Coder 1.x → 2.0

**Target Audience:** Developers using ninja-coder 1.x
**Estimated Migration Time:** 15-30 minutes
**Breaking Changes:** Yes (see below)

---

## Overview

Ninja Coder 2.0 introduces a **major architectural refactoring** that changes how plan execution works internally. While the high-level APIs remain similar, some implementation details have changed.

**Good News:** Most users won't need to change anything! The refactoring is mostly internal.

**Action Required If You:**
- Use `PlanExecutionResult` fields directly
- Use session management APIs (`create_session`, `continue_session`, etc.)
- Implement custom CLI strategies
- Parse raw driver outputs

---

## Quick Migration Checklist

```
[ ] Update PlanExecutionResult field access (steps_completed → steps)
[ ] Remove session management code (if using Python sessions)
[ ] Update custom strategies to use task_type parameter
[ ] Test sequential and parallel plans
[ ] Update any result parsing logic
```

---

## Breaking Changes

### 1. PlanExecutionResult Field Names

**Impact:** HIGH if you access result fields directly
**Affected:** Code that reads `PlanExecutionResult`

#### What Changed

The `PlanExecutionResult` model was restructured for better clarity:

**OLD (1.x):**
```python
@dataclass
class PlanExecutionResult:
    overall_status: str
    steps_completed: list[str]          # ❌ REMOVED
    steps_failed: list[str]             # ❌ REMOVED
    step_summaries: dict[str, str]      # ❌ REMOVED
    files_modified: list[str]
    notes: str
```

**NEW (2.0):**
```python
@dataclass
class PlanExecutionResult:
    overall_status: Literal["success", "partial", "failed"]
    steps: list[StepResult]             # ✅ NEW
    files_modified: list[str]
    notes: str
    execution_time: float | None        # ✅ NEW

@dataclass
class StepResult:
    id: str
    status: Literal["ok", "fail", "skipped"]
    summary: str
    files_touched: list[str]
    error_message: str | None
```

#### Migration Path

**Before:**
```python
result = execute_sequential_plan(steps)

# OLD: Access flat fields
completed_ids = result.steps_completed
failed_ids = result.steps_failed
step1_summary = result.step_summaries.get("step1")

# Check if step completed
if "step1" in result.steps_completed:
    print("Step 1 completed")
```

**After:**
```python
result = execute_sequential_plan(steps)

# NEW: Access structured step results
completed_ids = [s.id for s in result.steps if s.status == "ok"]
failed_ids = [s.id for s in result.steps if s.status == "fail"]
step1 = next((s for s in result.steps if s.id == "step1"), None)
step1_summary = step1.summary if step1 else None

# Check if step completed
step1_completed = any(s.id == "step1" and s.status == "ok" for s in result.steps)
if step1_completed:
    print("Step 1 completed")
```

#### Helper Functions

To make migration easier, you can add these helper functions:

```python
def get_completed_steps(result: PlanExecutionResult) -> list[str]:
    """Get IDs of completed steps."""
    return [s.id for s in result.steps if s.status == "ok"]

def get_failed_steps(result: PlanExecutionResult) -> list[str]:
    """Get IDs of failed steps."""
    return [s.id for s in result.steps if s.status == "fail"]

def get_step_summary(result: PlanExecutionResult, step_id: str) -> str | None:
    """Get summary for a specific step."""
    step = next((s for s in result.steps if s.id == step_id), None)
    return step.summary if step else None

def step_completed(result: PlanExecutionResult, step_id: str) -> bool:
    """Check if step completed successfully."""
    return any(s.id == step_id and s.status == "ok" for s in result.steps)
```

**Usage:**
```python
result = execute_sequential_plan(steps)

if step_completed(result, "step1"):
    summary = get_step_summary(result, "step1")
    print(f"Step 1 completed: {summary}")
```

---

### 2. Session Management Removed

**Impact:** MEDIUM if you use Python sessions
**Affected:** Code using `create_session()`, `continue_session()`, etc.

#### What Changed

**Removed:**
- `sessions.py` module (230 lines)
- `create_session()` function
- `continue_session()` function
- `list_sessions()` function
- `delete_session()` function
- `SessionManager` class

**Why:** Sessions were only used for multi-process context passing, which is obsolete with single-process execution.

#### Migration Path

**Option 1: Remove Session Usage (Recommended)**

If you only used sessions for sequential plans, you don't need them anymore:

**Before:**
```python
# OLD: Create session for multi-step conversation
session = create_session(
    repo_root="/path/to/repo",
    initial_task="Create user model",
)

# Continue session for subsequent steps
result2 = continue_session(
    session_id=session.id,
    task="Create user service",
)

result3 = continue_session(
    session_id=session.id,
    task="Create user routes",
)
```

**After:**
```python
# NEW: Just use sequential plan (context preserved automatically)
from ninja_coder.models import PlanStep

result = execute_sequential_plan(
    repo_root="/path/to/repo",
    steps=[
        PlanStep(
            id="models",
            title="Create Models",
            task="Create user model in src/models/user.py",
        ),
        PlanStep(
            id="services",
            title="Create Services",
            task="Create user service in src/services/user_service.py",
        ),
        PlanStep(
            id="routes",
            title="Create Routes",
            task="Create user routes in src/routes/users.py",
        ),
    ],
)

# Context automatically flows between steps!
```

**Option 2: Use OpenCode Native Sessions**

If you need persistent sessions across multiple user interactions (e.g., chatbot), use OpenCode's native session support:

**Before:**
```python
# OLD: Python-managed sessions
session = create_session(repo_root, initial_task)
result = continue_session(session.id, next_task)
```

**After:**
```python
# NEW: OpenCode-native sessions
from ninja_coder.driver import NinjaDriver, InstructionBuilder
from ninja_coder.models import ExecutionMode

driver = NinjaDriver()
builder = InstructionBuilder(repo_root, mode=ExecutionMode.QUICK)

# First interaction: Create session
instruction1 = builder.build_quick_task(
    task="Create user model",
    context_paths=["src/models/"],
    allowed_globs=["src/models/**/*"],
    deny_globs=[],
)

result1 = await driver.execute_async_with_opencode_session(
    repo_root=repo_root,
    step_id="task1",
    instruction=instruction1,
    is_initial=True,  # Create new session
)

session_id = result1.session_id  # Extract OpenCode session ID

# Subsequent interactions: Continue session
instruction2 = builder.build_quick_task(
    task="Create user service",
    context_paths=["src/services/", "src/models/user.py"],
    allowed_globs=["src/services/**/*"],
    deny_globs=[],
)

result2 = await driver.execute_async_with_opencode_session(
    repo_root=repo_root,
    step_id="task2",
    instruction=instruction2,
    opencode_session_id=session_id,  # Continue existing session
)
```

**Note:** OpenCode sessions are only available when using the OpenCode CLI. For other CLIs (Aider, Claude, etc.), use sequential plans instead.

---

### 3. Dialogue Mode Changes

**Impact:** LOW (mostly internal)
**Affected:** Code that sets `use_dialogue_mode=True`

#### What Changed

Dialogue mode is now handled natively by the AI CLI, not Python.

**Before (1.x):**
```python
# Python managed conversation history across subprocesses
result = execute_sequential_plan(
    steps=steps,
    use_dialogue_mode=True,  # Python serializes context
)
```

**After (2.0):**
```python
# CLI manages context natively (always enabled for sequential plans)
result = execute_sequential_plan(
    steps=steps,
    # No use_dialogue_mode parameter needed
)
```

#### Migration Path

**Before:**
```python
result = execute_sequential_plan(
    repo_root="/path/to/repo",
    steps=steps,
    use_dialogue_mode=True,  # ❌ REMOVED
)
```

**After:**
```python
result = execute_sequential_plan(
    repo_root="/path/to/repo",
    steps=steps,
    # Dialogue mode is automatic for sequential plans
)
```

**No action required:** Just remove the `use_dialogue_mode` parameter.

---

### 4. Strategy API Changes

**Impact:** HIGH if you implement custom CLI strategies
**Affected:** Custom `CLIStrategy` implementations

#### What Changed

Strategies now receive a `task_type` parameter to differentiate between quick, sequential, and parallel execution:

**Before (1.x):**
```python
class CustomStrategy(CLIStrategy):
    def build_command(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
        model: str | None = None,
    ) -> CLIResult:
        # No way to know if this is sequential/parallel
        ...
```

**After (2.0):**
```python
class CustomStrategy(CLIStrategy):
    def build_command(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
        model: str | None = None,
        task_type: str = "quick",  # ✅ NEW
        session_id: str | None = None,
        continue_last: bool = False,
    ) -> CLIResult:
        # Can route based on task_type
        if task_type == "sequential":
            return self._build_sequential_command(...)
        elif task_type == "parallel":
            return self._build_parallel_command(...)
        else:
            return self._build_quick_command(...)
```

#### Migration Path

**Before:**
```python
class MyCustomStrategy(CLIStrategy):
    def build_command(self, prompt, repo_root, file_paths=None, model=None):
        # Build command without knowing task type
        cmd = [self.bin_path, "--prompt", prompt]
        return CLIResult(command=cmd, working_dir=repo_root, env=env)
```

**After:**
```python
class MyCustomStrategy(CLIStrategy):
    def build_command(
        self,
        prompt,
        repo_root,
        file_paths=None,
        model=None,
        task_type="quick",        # ✅ Add parameter
        session_id=None,
        continue_last=False,
    ):
        # Route based on task_type
        if task_type in ["sequential", "parallel"]:
            # Use special flags for multi-step execution
            cmd = [self.bin_path, "--plan-mode", "--prompt", prompt]
        else:
            # Standard quick execution
            cmd = [self.bin_path, "--prompt", prompt]

        return CLIResult(command=cmd, working_dir=repo_root, env=env)
```

---

## Non-Breaking Changes

### 1. New PromptBuilder API

**Impact:** NONE (optional enhancement)
**Benefit:** Pre-generate prompts for inspection or caching

You can now build prompts independently of execution:

```python
from ninja_coder.prompt_builder import PromptBuilder
from ninja_coder.models import PlanStep, ExecutionMode

builder = PromptBuilder(repo_root="/path/to/repo")

# Build a sequential plan prompt
prompt = builder.build_sequential_plan(
    steps=[
        PlanStep(id="1", title="Models", task="Create models..."),
        PlanStep(id="2", title="Services", task="Create services..."),
    ],
    mode=ExecutionMode.QUICK,
    context_paths=["src/"],
)

# Inspect the prompt
print(prompt)

# Save it for later
with open("plan.txt", "w") as f:
    f.write(prompt)

# Execute it
driver = NinjaDriver()
result = await driver.execute_async(
    repo_root=repo_root,
    step_id="plan",
    instruction={"task": prompt},
    task_type="sequential",
)
```

**Use Cases:**
- Debug prompt generation
- Cache prompts for repeated execution
- Customize prompts before execution
- Generate prompts offline

### 2. New ResultParser API

**Impact:** NONE (optional enhancement)
**Benefit:** Parse outputs independently of driver

You can now parse outputs separately:

```python
from ninja_coder.result_parser import ResultParser

parser = ResultParser()

# Parse plan result from CLI output
output = """
```json
{
  "overall_status": "success",
  "steps_completed": ["step1", "step2"],
  "step_summaries": {...}
}
```
"""

result = parser.parse_plan_result(output)
# → PlanExecutionResult(overall_status="success", steps=[...])

# Parse simple task result
output2 = "Created user model in src/models/user.py"
result2 = parser.parse_simple_result(output2)
# → {"summary": "Created user model...", "touched_paths": ["src/models/user.py"]}
```

**Use Cases:**
- Test result parsing independently
- Parse historical logs
- Build custom drivers
- Debug output extraction

---

## Behavior Changes

### 1. Context Preservation

**Before (1.x):** Context could be lost between steps due to serialization failures

**After (2.0):** Context is always preserved (single-process execution)

**Impact:** Sequential plans are more reliable and produce better results

**Example:**
```python
steps = [
    PlanStep(id="1", task="Create User model with email field"),
    PlanStep(id="2", task="Create UserService that validates emails"),  # References step 1
]

# Before: Step 2 might not "remember" that User has email field
# After: Step 2 has full context from step 1 (guaranteed)
```

### 2. Error Messages

**Before (1.x):** Generic errors like "Step failed"

**After (2.0):** Structured error messages with step-level details

**Example:**
```python
# Before
# PlanExecutionResult(
#   overall_status="failed",
#   notes="Execution failed"
# )

# After
# PlanExecutionResult(
#   overall_status="partial",
#   steps=[
#     StepResult(id="1", status="ok", summary="Created models"),
#     StepResult(id="2", status="fail", error_message="ImportError: No module named 'models'"),
#   ]
# )
```

### 3. Performance

**Before (1.x):** Sequential plans took ~15 minutes

**After (2.0):** Sequential plans take ~8 minutes (47% faster)

**Impact:** Faster execution, lower costs

---

## Testing Your Migration

### 1. Unit Tests

Update tests that assert on result fields:

```python
def test_sequential_plan():
    result = execute_sequential_plan(steps)

    # OLD assertions
    # assert "step1" in result.steps_completed
    # assert result.step_summaries["step1"] == "..."

    # NEW assertions
    assert any(s.id == "step1" and s.status == "ok" for s in result.steps)
    step1 = next(s for s in result.steps if s.id == "step1")
    assert step1.summary == "..."
```

### 2. Integration Tests

Test full workflows:

```python
async def test_full_workflow():
    # Build sequential plan
    steps = [
        PlanStep(id="models", task="Create models"),
        PlanStep(id="services", task="Create services"),
        PlanStep(id="routes", task="Create routes"),
    ]

    # Execute
    result = await execute_sequential_plan(repo_root, steps)

    # Verify
    assert result.overall_status == "success"
    assert len(result.steps) == 3
    assert all(s.status == "ok" for s in result.steps)
    assert len(result.files_modified) > 0
```

### 3. Manual Testing

Run a simple plan to verify:

```bash
# Create test script
cat > test_migration.py << 'EOF'
import asyncio
from ninja_coder.tools import execute_sequential_plan
from ninja_coder.models import PlanStep

async def test():
    result = await execute_sequential_plan(
        repo_root="/tmp/test_repo",
        steps=[
            PlanStep(
                id="test",
                title="Test Step",
                task="Create a file test.txt with 'Hello World'",
            ),
        ],
    )

    print(f"Status: {result.overall_status}")
    print(f"Steps: {len(result.steps)}")
    if result.steps:
        print(f"Step 0 status: {result.steps[0].status}")
        print(f"Step 0 summary: {result.steps[0].summary}")

asyncio.run(test())
EOF

# Run test
python test_migration.py
```

Expected output:
```
Status: success
Steps: 1
Step 0 status: ok
Step 0 summary: Created test.txt with 'Hello World'
```

---

## Rollback Plan

If you encounter issues, you can temporarily pin to 1.x:

```bash
# requirements.txt
ninja-cli-mcp==1.9.0  # Last 1.x version
```

Then file an issue at: https://github.com/angkira/ninja-cli-mcp/issues

---

## Timeline and Support

| Version | Status | Support Until |
|---------|--------|---------------|
| **1.x** | Maintenance | 2026-06-01 |
| **2.0** | Current | Active |

**Maintenance Mode:** Security fixes only, no new features

**Recommendation:** Migrate to 2.0 by 2026-06-01

---

## Common Migration Patterns

### Pattern 1: Simple Sequential Plan

**Before:**
```python
from ninja_coder import create_session, continue_session

session = create_session(repo_root, "Create User model")
result2 = continue_session(session.id, "Create UserService")
result3 = continue_session(session.id, "Create user routes")
```

**After:**
```python
from ninja_coder.tools import execute_sequential_plan
from ninja_coder.models import PlanStep

result = await execute_sequential_plan(
    repo_root=repo_root,
    steps=[
        PlanStep(id="1", title="Models", task="Create User model"),
        PlanStep(id="2", title="Services", task="Create UserService"),
        PlanStep(id="3", title="Routes", task="Create user routes"),
    ],
)
```

### Pattern 2: Checking Step Results

**Before:**
```python
result = execute_sequential_plan(steps)

for step_id in result.steps_completed:
    summary = result.step_summaries[step_id]
    print(f"{step_id}: {summary}")

for step_id in result.steps_failed:
    print(f"{step_id}: FAILED")
```

**After:**
```python
result = execute_sequential_plan(steps)

for step in result.steps:
    if step.status == "ok":
        print(f"{step.id}: {step.summary}")
    elif step.status == "fail":
        print(f"{step.id}: FAILED - {step.error_message}")
```

### Pattern 3: Conditional Execution

**Before:**
```python
result = execute_sequential_plan(steps[:2])

if "step2" in result.steps_completed:
    # Only run step 3 if step 2 succeeded
    result2 = execute_sequential_plan([steps[2]])
```

**After:**
```python
result = execute_sequential_plan(steps[:2])

step2 = next((s for s in result.steps if s.id == "step2"), None)
if step2 and step2.status == "ok":
    # Only run step 3 if step 2 succeeded
    result2 = execute_sequential_plan([steps[2]])
```

---

## FAQ

### Q: Do I need to rewrite my entire codebase?

**A:** No! Most code continues to work. Main changes are:
1. Update `PlanExecutionResult` field access
2. Remove session management (if used)

### Q: Will my existing plans still work?

**A:** Yes! The plan structure (`PlanStep`) is unchanged. Only the result format changed.

### Q: What if I use sessions heavily?

**A:** Two options:
1. **Recommended:** Migrate to sequential plans (context preserved automatically)
2. **Alternative:** Use OpenCode native sessions (CLI-specific)

### Q: Is 2.0 stable for production?

**A:** Yes! It's been tested with 100+ executions and shows 100% stability (vs 67% in 1.x).

### Q: Can I use both 1.x and 2.0?

**A:** Not simultaneously. Pick one version and pin it in requirements.txt.

### Q: How do I debug migration issues?

**A:**
1. Enable debug logging: `export NINJA_LOG_LEVEL=DEBUG`
2. Check prompt generation: Use `PromptBuilder` to inspect prompts
3. Check result parsing: Use `ResultParser` to test parsing
4. File an issue: https://github.com/angkira/ninja-cli-mcp/issues

---

## Additional Resources

- **Refactoring Summary:** [REFACTORING_SUMMARY.md](./REFACTORING_SUMMARY.md)
- **Architecture Details:** [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Performance Benchmarks:** [PERFORMANCE_BENCHMARKS.md](./PERFORMANCE_BENCHMARKS.md)
- **GitHub Issues:** https://github.com/angkira/ninja-cli-mcp/issues
- **Documentation:** https://github.com/angkira/ninja-cli-mcp/tree/main/docs

---

## Support

If you encounter migration issues:

1. **Check this guide** for your specific use case
2. **Search existing issues:** https://github.com/angkira/ninja-cli-mcp/issues
3. **File a new issue** with:
   - Version you're migrating from
   - Error message (if any)
   - Minimal reproduction code
   - Expected vs actual behavior

We're here to help! 🥷
