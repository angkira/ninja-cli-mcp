---
description: Delegate code writing to ninja-coder (opencode serve)
---

You are delegating a coding task to the ninja-coder.

**Task**: $ARGUMENTS

**Instructions**:
1. Determine the repo root (use the current working directory if not specified in the task)
2. Run the coding task via opencode serve:
   ```
   bash claude-integration/scripts/opencode-task.sh "<repo_root>" "<detailed task specification>"
   ```
3. Parse the JSON output
4. If successful, verify the changed files with `git diff` or by reading them
5. Run any relevant tests if they exist
6. Report the results concisely
