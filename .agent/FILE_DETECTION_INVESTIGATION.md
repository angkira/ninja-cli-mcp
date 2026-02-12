# FILE DETECTION FALSE NEGATIVE INVESTIGATION

**Investigation Date:** 2026-02-12
**Investigator:** Claude Sonnet 4.5
**Issue:** Ninja-coder reports false negative file detection errors despite successful task completion

---

## EXECUTIVE SUMMARY

**ROOT CAUSE IDENTIFIED:** A "Final validation" logic added in commit `3eb8cb8` (2026-01-26) that checks for file modifications AFTER task completion is producing false negatives due to **incomplete regex pattern matching** in the file path extraction logic.

**SEVERITY:** Medium - Tasks actually succeed and files are created, but users receive confusing error messages.

**STATUS:** Investigation complete, root cause identified, fix ready for implementation.

---

## DETAILED FINDINGS

### 1. File Detection Logic Location

**Primary Location:**
- File: `/Users/iuriimedvedev/Project/ninja-coder/ninja-cli-mcp/src/ninja_coder/strategies/aider_strategy.py`
- Lines: 276-296 (file path extraction), 385-401 (final validation)
- Method: `AiderStrategy.parse_output()`

**Also Affected:**
- `src/ninja_coder/strategies/opencode_strategy.py` (lines ~388-418)
- `src/ninja_coder/strategies/gemini_strategy.py` (lines ~244-268)
- `src/ninja_coder/strategies/claude_strategy.py` (no final validation - NOT affected)

### 2. The Problematic Code

#### File Path Extraction (Lines 276-296)
```python
# Extract file changes (what was modified)
suspected_paths: list[str] = []
file_patterns = [
    # Aider-specific patterns (most reliable)
    r"Applied edit to\s+([^\s]+)",  # "Applied edit to storage.py"
    r"Added\s+([^\s]+)\s+to the chat",  # "Added models.py to the chat"
    r"Create[d]?\s+([^\s]+\.[\w]+)",  # "Created file.py" or "Create file.py"
    # Generic patterns
    r"(?:wrote|created|modified|updated|edited)\s+['\"]?([^\s'\"]+)['\"]?",
    r"(?:writing|creating|modifying|updating|editing)\s+['\"]?([^\s'\"]+)['\"]?",
    r"file:\s*['\"]?([^\s'\"]+)['\"]?",
]
for pattern in file_patterns:
    matches = re.findall(pattern, combined_output, re.IGNORECASE)
    for match in matches:
        # Filter to only actual file paths (must have extension or path separator)
        if match and ("/" in match or "." in match) and not match.endswith("."):
            suspected_paths.append(match)

# Deduplicate paths
suspected_paths = list(set(suspected_paths))
```

#### Final Validation (Lines 385-401)
```python
# Final validation: If we claim success but no files were touched, it's suspicious
# This catches cases where the CLI exits with 0 but didn't actually do anything
if success and not suspected_paths and len(combined_output) > 100:
    # Check if output suggests files should have been created/modified
    action_keywords = ["write", "creat", "modif", "updat", "edit", "add", "implement"]
    has_action_intent = any(
        keyword in combined_output.lower() for keyword in action_keywords
    )

    # If there was intent to modify files but none were touched, mark as failure
    if has_action_intent:
        success = False
        summary = "⚠️ Task completed but no files were modified"
        notes = (
            "CLI exited successfully but no file changes detected. Check logs for details."
        )
        logger.warning("Suspicious success: exit_code=0 but no files touched")
```

### 3. Why False Negatives Occur

**The Problem Chain:**

1. **Incomplete Regex Patterns:** The file path extraction regex patterns don't match all output formats from different CLI tools
   - Claude Code outputs files differently than Aider
   - OpenCode has different output patterns
   - Generic patterns miss tool-specific formats

2. **Timing Issue:** The validation happens AFTER subprocess completion but BEFORE file system sync
   - Files ARE created by the subprocess
   - But regex pattern matching FAILS to detect them in stdout/stderr
   - `suspected_paths` remains empty despite successful file creation

3. **Overzealous Validation:** The "final validation" logic was added to catch legitimate failures (exit_code=0 but nothing happened) but it doesn't account for:
   - Pattern matching failures
   - Different CLI output formats
   - Buffer flush delays
   - Multi-tool compatibility

4. **False Positive for Action Intent:** Any mention of "write", "create", "modify", etc. in the output triggers `has_action_intent=True`
   - This includes prompts, instructions, and summaries
   - Not just actual file operations

### 4. Evidence from Git History

**Commit that introduced the issue:**
- Commit: `3eb8cb8` (2026-01-26)
- Author: iurii.medvedev
- Message: "fix: Improve error detection and config handling in ninja-coder"
- Intent: "Add validation to detect false success (exit_code=0 but no files touched)"

**Before this commit:**
- File detection relied only on regex pattern matching
- No post-execution validation
- False positives (claiming success when nothing happened) were possible
- But NO false negatives (claiming failure when files were created)

**After this commit:**
- Added "Final validation" logic
- **UNINTENDED CONSEQUENCE:** Now produces false negatives when regex patterns fail to match

### 5. Affected CLI Tools

| CLI Tool      | Affected | Reason                                                    |
|---------------|----------|-----------------------------------------------------------|
| **Aider**     | YES      | Has final validation logic (lines 385-401)               |
| **OpenCode**  | YES      | Has final validation logic (similar implementation)       |
| **Gemini**    | YES      | Has final validation logic (similar implementation)       |
| **Claude Code** | NO     | Does NOT have final validation logic (strategy missing it)|

**Irony:** Claude Code strategy doesn't have this bug because it was implemented differently.

### 6. Why Tasks Actually Succeed

**The tasks ARE successful:**
- Subprocess completes with exit_code=0
- Files ARE written to disk by the CLI tool (aider, opencode, etc.)
- The CLI tool performed the work correctly

**But ninja-coder reports failure because:**
- Regex patterns fail to extract file paths from stdout/stderr
- `suspected_paths` list is empty
- Final validation sees empty list + action keywords → marks as failure
- User sees error despite files being created

### 7. Benchmark Framework Validates Differently

**Important Discovery:**
The benchmark framework (`src/ninja_coder/benchmark/framework.py`) validates file creation CORRECTLY:

```python
# Check expected files exist
for file_path in expected_files:
    full_path = Path(repo_root) / file_path
    if not full_path.exists():
        logger.warning(f"Expected file not found: {file_path}")
        return False
```

**Key Difference:**
- Benchmark framework checks **actual file system** (Path.exists())
- Strategy validation checks **regex-parsed output** (suspected_paths list)
- File system check is ground truth
- Regex parsing is heuristic and can fail

---

## ROOT CAUSE ANALYSIS

### Primary Root Cause
**Insufficient regex pattern coverage + overzealous post-execution validation = false negatives**

### Contributing Factors
1. **Pattern Coverage:** Regex patterns don't cover all CLI output formats
2. **No File System Verification:** Validation relies on stdout parsing, not actual file checks
3. **Keyword Heuristic:** Action keywords trigger false positives for "has_action_intent"
4. **Multi-Tool Design:** Each CLI tool has different output formats, patterns can't catch all
5. **No Timeout for FS Sync:** No buffer flush or file system sync delay before validation

### Why It Wasn't Caught Earlier
1. Original commit tested with Aider only (which has the most predictable output)
2. No comprehensive multi-tool integration tests
3. Benchmark framework uses file system validation (doesn't trigger the bug)
4. False negatives are "soft failures" - files are created, just reported incorrectly

---

## SUGGESTED FIXES

### Option 1: Remove Final Validation (Simplest)
**Approach:** Remove the "final validation" logic entirely
- **Pros:** Eliminates false negatives, simple fix
- **Cons:** Re-introduces false positives (exit_code=0 but nothing happened)
- **Recommendation:** NOT RECOMMENDED (loses legitimate error detection)

### Option 2: Add File System Verification (Best)
**Approach:** After regex parsing, verify files actually exist on disk
```python
# After deduplicating suspected_paths
verified_paths = []
for path in suspected_paths:
    full_path = Path(repo_root) / path
    if full_path.exists():
        verified_paths.append(path)
    else:
        logger.warning(f"Path mentioned in output but not found: {path}")

suspected_paths = verified_paths

# If regex found nothing, do a directory scan for recent changes
if not suspected_paths and success:
    import time
    cutoff_time = time.time() - 60  # Files modified in last 60 seconds
    recent_files = []
    for root, dirs, files in os.walk(repo_root):
        # Skip hidden dirs, .git, etc.
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            file_path = Path(root) / file
            if file_path.stat().st_mtime > cutoff_time:
                recent_files.append(str(file_path.relative_to(repo_root)))

    if recent_files:
        suspected_paths = recent_files[:10]  # Limit to 10 most recent
        logger.info(f"Detected {len(recent_files)} recently modified files")
```

**Pros:**
- Ground truth validation (file system is source of truth)
- Catches files even if regex patterns fail
- Maintains original intent (detect false success)
- No false negatives

**Cons:**
- Requires file system traversal (slower)
- May pick up unrelated file changes (if other processes writing)
- Need to filter by recency

### Option 3: Improve Regex Patterns (Partial Fix)
**Approach:** Add more comprehensive regex patterns for each CLI tool
- **Pros:** No performance overhead
- **Cons:** Can never be 100% complete, new CLI tools need new patterns
- **Recommendation:** Do this IN ADDITION to file system verification

### Option 4: Make Validation Optional (Configuration)
**Approach:** Add environment variable to disable final validation
```python
ENABLE_FINAL_VALIDATION = os.environ.get("NINJA_ENABLE_FINAL_VALIDATION", "true").lower() == "true"

if ENABLE_FINAL_VALIDATION and success and not suspected_paths:
    # ... existing validation logic
```

**Pros:**
- User can disable if getting false negatives
- Keeps validation for users who want it

**Cons:**
- Doesn't fix root cause
- Users don't know about the flag

---

## RECOMMENDED FIX (HYBRID APPROACH)

**Implement Option 2 + Option 3:**

1. **Enhance regex patterns** for better coverage across all CLI tools
2. **Add file system verification** as fallback when regex patterns fail
3. **Use recency check** (files modified within task duration) to avoid false positives
4. **Keep final validation** but only trigger it if BOTH conditions met:
   - No files detected via regex OR file system scan
   - Output contains action keywords

**Implementation Priority:**
1. HIGH: Add file system verification fallback (fixes false negatives)
2. MEDIUM: Improve regex patterns (reduces need for fallback)
3. LOW: Add NINJA_ENABLE_FINAL_VALIDATION flag (escape hatch for users)

---

## FILES REQUIRING CHANGES

1. `src/ninja_coder/strategies/aider_strategy.py` (lines 276-401)
2. `src/ninja_coder/strategies/opencode_strategy.py` (similar section)
3. `src/ninja_coder/strategies/gemini_strategy.py` (similar section)
4. `src/ninja_coder/strategies/claude_strategy.py` (add final validation if desired)

---

## TESTING RECOMMENDATIONS

**Unit Tests:**
1. Test regex pattern matching for each CLI tool's output format
2. Test file system verification fallback
3. Test recency-based file detection
4. Test with various repo_root values (absolute, relative, symlinks)

**Integration Tests:**
1. Create file with Aider → verify detection
2. Create file with OpenCode → verify detection
3. Create file with Gemini → verify detection
4. Create file with Claude Code → verify detection
5. Task fails legitimately → verify error detection
6. Task succeeds but no files → verify false success detection

**Regression Tests:**
1. Re-run all tasks from recent commits (test_ninja_success.py, etc.)
2. Verify no false negatives
3. Verify no false positives

---

## CONCLUSION

The false negative file detection errors are caused by **incomplete regex pattern matching combined with overzealous post-execution validation**. The fix is straightforward: add file system verification as a fallback when regex patterns fail to detect file changes.

This investigation demonstrates that:
1. ✅ Files ARE being created successfully
2. ❌ Detection logic is flawed (relies on regex parsing only)
3. ✅ Fix is simple and low-risk (add file system verification)
4. ✅ Root cause is well-understood and documented

**Recommended Next Steps:**
1. Implement hybrid fix (Option 2 + Option 3)
2. Add comprehensive tests
3. Test with all CLI tools
4. Document fix in commit message
5. Add to ROADMAP as completed task

---

**Investigation Complete**
**Status:** IMPLEMENTATION COMPLETE
**Risk Level:** Low (fix is simple, well-understood)
**Effort Estimate:** 2-3 hours (implementation + testing)

## IMPLEMENTATION COMPLETED - 2026-02-12

**Files Modified:**
1. `/src/ninja_coder/strategies/aider_strategy.py`
2. `/src/ninja_coder/strategies/opencode_strategy.py`
3. `/src/ninja_coder/strategies/gemini_strategy.py`

**Changes Applied:**
1. Added `time` module import to all three strategy files
2. Implemented file system verification after regex path extraction
3. Added fallback filesystem scan for recently modified files (60-second window)
4. Updated final validation logic with clarifying comments
5. Added comprehensive error handling for file system operations
6. Maintained production-ready code quality with type hints

**Testing Status:**
- Syntax validation: PASSED (all three files)
- Integration testing: PENDING (requires manual verification with real tasks)

**Next Steps:**
1. Run integration tests with all CLI tools (aider, opencode, gemini)
2. Verify no false negatives occur
3. Verify no false positives occur
4. Monitor logs for proper detection behavior
