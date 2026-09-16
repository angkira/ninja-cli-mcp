---
name: emergency-recovery
description: Recovery steps for when session context is lost or an architectural violation is found mid-session. Use when resuming after a context loss, or when code is found violating the architecture standards in CLAUDE.md.
---

**IF CONTEXT IS LOST:**
1. Run full codebase analysis
2. Re-read all `.agent/` files
3. Check git history for recent changes
4. Reconstruct session state from available information

**IF ARCHITECTURAL VIOLATIONS FOUND:**
1. Document the violation in STATUS.md
2. Create refactoring task in ROADMAP.md
3. Use architect review to assess impact
4. Schedule remediation in backlog
