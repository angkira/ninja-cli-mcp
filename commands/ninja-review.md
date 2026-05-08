---
description: Architectural code review
---

Review the following code for quality and architecture:

**Scope**: $ARGUMENTS

**Review checklist**:
1. Read the specified files (or recent git changes if no files specified)
2. Check for:
   - SOLID violations
   - Tight coupling / missing dependency injection
   - Missing error handling
   - Security issues (injection, hardcoded secrets)
   - Type safety (missing hints, Any usage)
   - Dead code or commented-out code
3. Grade: PASS / NEEDS_WORK / FAIL
4. List specific issues with file:line references
5. Suggest fixes for critical issues only
