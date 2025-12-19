# Security Analysis: ninja-cli-mcp

**Document Version:** 1.0  
**Date:** 2025-12-19  
**Analyzed Version:** 0.1.x

## Executive Summary

ninja-cli-mcp is an MCP (Model Context Protocol) server that orchestrates AI-powered code execution by delegating to CLI tools (aider, claude) which interact with OpenRouter APIs. The architecture provides good separation of concerns but has several security considerations that need attention.

**Overall Security Posture:** MODERATE
- ✅ Strong: Path validation, rate limiting, input sanitization basics
- ⚠️  Moderate: API key handling, subprocess execution
- ❌ Needs Work: Logging sensitive data, parallel execution isolation

## Architecture Overview

```
┌────────────────────┐
│   MCP Client       │ (Copilot CLI, Claude Code, VS Code)
│   (Planning Agent) │
└──────────┬─────────┘
           │ stdio (MCP Protocol)
           ▼
┌────────────────────┐
│ ninja-cli-mcp      │ Python MCP Server
│ - tools.py         │ Orchestrator (this project)
│ - ninja_driver.py  │
│ - security.py      │
└──────────┬─────────┘
           │ subprocess.Popen()
           ▼
┌────────────────────┐
│ AI Code CLI        │ (aider, claude, cursor)
│ - File I/O         │
│ - OpenRouter API   │
│ - Git operations   │
└────────────────────┘
```

## Threat Model

### Trust Boundaries
1. **MCP Client → ninja-cli-mcp**: Trusted (user's IDE/CLI)
2. **ninja-cli-mcp → AI Code CLI**: Partially trusted (subprocess)
3. **AI Code CLI → OpenRouter**: External service (untrusted network)
4. **AI Code CLI → Filesystem**: Needs strict controls

### Attack Vectors
- Malicious MCP client inputs
- Command injection via subprocess
- Path traversal to sensitive files
- API key theft from logs/memory
- Resource exhaustion (DoS)
- Prompt injection via task descriptions
- Side-channel attacks via timing

---

## Security Issues Found

### CRITICAL Severity

#### C1: API Key Exposure in Subprocess Environment
**Location:** `src/ninja_cli_mcp/ninja_driver.py:423-436`
```python
env = os.environ.copy()
env["OPENAI_API_KEY"] = self.config.openai_api_key
env["OPENAI_BASE_URL"] = self.config.openai_base_url
```

**Issue:** API keys passed via environment variables are visible to:
- Process listings (`ps auxe`)
- Child processes
- Core dumps
- Debuggers attached to subprocess

**Impact:** 🔴 CRITICAL - Full API key compromise
**CVSS:** 9.1 (Critical)

**Recommended Solution:**
1. Use aider's `--api-key-file` or config file instead of env vars
2. Store API keys in secure memory (mlock)
3. Clear env vars after subprocess creation
4. Use temporary files with 0600 permissions

**Implementation:**
```python
# Create temporary API key file
import tempfile
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key') as f:
    f.write(api_key)
    key_file = f.name
os.chmod(key_file, 0o600)

# Pass file path instead
cmd = [cli_bin, "--api-key-file", key_file, ...]

try:
    subprocess.run(cmd, ...)
finally:
    os.unlink(key_file)  # Secure delete
```

#### C2: Command Injection via Model Parameter
**Location:** `src/ninja_cli_mcp/ninja_driver.py:417-420`
```python
cmd.extend(["--model", f"openrouter/{self.config.model}"])
```

**Issue:** Model name is not validated before shell execution. Malicious input like:
```
model = "test; rm -rf /"
```
Could execute arbitrary commands if shell=True is used anywhere.

**Impact:** 🔴 CRITICAL - Arbitrary code execution
**CVSS:** 9.8 (Critical)

**Recommended Solution:**
1. Validate model names against whitelist/regex
2. Never use `shell=True` in subprocess calls
3. Escape special characters

**Implementation:**
```python
import re

def validate_model_name(model: str) -> str:
    """Validate model name format."""
    # Only allow alphanumeric, dash, underscore, slash, dot
    if not re.match(r'^[a-zA-Z0-9._/-]+$', model):
        raise ValueError(f"Invalid model name: {model}")
    if len(model) > 100:
        raise ValueError("Model name too long")
    return model

# In NinjaDriver
validated_model = validate_model_name(self.config.model)
cmd.extend(["--model", f"openrouter/{validated_model}"])
```

---

### HIGH Severity

#### H1: Insufficient Path Traversal Protection for Context Paths
**Location:** `src/ninja_cli_mcp/tools.py:100-130`

**Issue:** While `repo_root` is validated, `context_paths` inside the instruction are not strictly validated before being passed to aider:
```python
"context_paths": request.context_paths or [],
```

**Impact:** 🟠 HIGH - Read access to files outside repo
**CVSS:** 7.5 (High)

**Recommended Solution:**
```python
def validate_context_paths(paths: list[str], repo_root: Path) -> list[str]:
    """Validate that all context paths are within repo."""
    validated = []
    for path in paths:
        full_path = (repo_root / path).resolve()
        try:
            full_path.relative_to(repo_root)
            validated.append(str(full_path.relative_to(repo_root)))
        except ValueError:
            logger.warning(f"Rejecting path outside repo: {path}")
    return validated
```

#### H2: API Keys Logged in Plain Text
**Location:** `src/ninja_cli_mcp/logging_utils.py` and subprocess output

**Issue:** Task logs may contain:
- API keys in error messages
- Full environment variables in debug logs
- OpenRouter responses with keys in headers

**Impact:** 🟠 HIGH - Key exposure via logs
**CVSS:** 7.2 (High)

**Recommended Solution:**
1. Implement log sanitization
2. Redact sensitive patterns
3. Separate security-sensitive logs

**Implementation:**
```python
import re

SENSITIVE_PATTERNS = [
    (re.compile(r'sk-[a-zA-Z0-9-]{40,}'), '[REDACTED-API-KEY]'),
    (re.compile(r'Bearer [a-zA-Z0-9._-]+'), 'Bearer [REDACTED]'),
    (re.compile(r'"api[_-]?key"\s*:\s*"[^"]+'), '"api_key": "[REDACTED]'),
]

def sanitize_log_message(msg: str) -> str:
    """Remove sensitive data from log messages."""
    for pattern, replacement in SENSITIVE_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg

# In TaskLogger
def log(self, level: str, message: str):
    sanitized = sanitize_log_message(message)
    # ... log sanitized message
```

#### H3: No Subprocess Output Size Limits
**Location:** `src/ninja_cli_mcp/ninja_driver.py:451-467`

**Issue:** Subprocess stdout/stderr are read without size limits:
```python
stdout, stderr = await proc.communicate()
```

**Impact:** 🟠 HIGH - Memory exhaustion DoS
**CVSS:** 7.1 (High)

**Recommended Solution:**
```python
async def read_with_limit(stream, max_size=10*1024*1024):  # 10MB limit
    """Read stream with size limit."""
    chunks = []
    total_size = 0
    
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_size:
            raise ValueError(f"Output exceeds {max_size} bytes")
        chunks.append(chunk)
    
    return b''.join(chunks)

# Usage
stdout = await read_with_limit(proc.stdout)
stderr = await read_with_limit(proc.stderr)
```

#### H4: Weak Rate Limiting (100 calls/min per client)
**Location:** `src/ninja_cli_mcp/security.py:80`

**Issue:** 
- 100 calls/min is generous for code execution
- No cost-based limiting
- No per-repo limits
- Client ID easily spoofed

**Impact:** 🟠 HIGH - Resource abuse, API cost explosion
**CVSS:** 6.8 (Medium-High)

**Recommended Solution:**
```python
class EnhancedRateLimiter:
    def __init__(self):
        self.call_limits = {
            'quick_task': (20, 60),      # 20 per minute
            'sequential_plan': (10, 60),  # 10 per minute
            'parallel_plan': (5, 60),     # 5 per minute
        }
        self.cost_tracker = {}  # Track OpenRouter costs
        
    async def check_limit(self, client_id: str, tool_name: str, estimated_cost: float = 0):
        """Enhanced rate limiting with cost tracking."""
        max_calls, window = self.call_limits.get(tool_name, (50, 60))
        
        # Check call limit
        if not await self._check_call_limit(client_id, tool_name, max_calls, window):
            return False
            
        # Check cost limit (e.g., $10/hour per client)
        if not await self._check_cost_limit(client_id, estimated_cost, max_cost=10.0, window=3600):
            return False
            
        return True
```

---

### MEDIUM Severity

#### M1: No Parallel Execution Isolation
**Location:** `src/ninja_cli_mcp/tools.py:402-455`

**Issue:** Parallel execution runs in same working directory without isolation:
- Race conditions on shared files
- No resource quotas per task
- Can interfere with each other

**Impact:** 🟡 MEDIUM - Data corruption, race conditions
**CVSS:** 5.9 (Medium)

**Recommended Solution:**
```python
# Use git worktrees for true isolation
async def create_worktree_for_step(repo_root: Path, step_id: str) -> Path:
    """Create isolated git worktree for parallel execution."""
    worktree_path = repo_root.parent / f".worktrees/{step_id}"
    
    proc = await asyncio.create_subprocess_exec(
        "git", "worktree", "add", str(worktree_path),
        cwd=str(repo_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    
    return worktree_path

# In parallel execution
for step in steps:
    if parallel_mode:
        work_dir = await create_worktree_for_step(repo_root, step.id)
    else:
        work_dir = repo_root
```

#### M2: Glob Pattern Bypass via Symlinks
**Location:** `src/ninja_cli_mcp/path_utils.py:169-198`

**Issue:** Glob patterns don't follow symlinks by default, but if repo contains symlinks, they could bypass `allowed_globs`:
```python
normalize_globs()  # Doesn't resolve symlinks
```

**Impact:** 🟡 MEDIUM - Access control bypass
**CVSS:** 5.5 (Medium)

**Recommended Solution:**
```python
def resolve_symlinks_in_globs(patterns: list[str], repo_root: Path) -> list[str]:
    """Resolve symlinks in glob patterns."""
    resolved = []
    for pattern in patterns:
        # Check if pattern contains symlinks
        path = repo_root / pattern.split('*')[0].strip('/')
        if path.exists() and path.is_symlink():
            real_path = path.resolve()
            try:
                rel_path = real_path.relative_to(repo_root)
                resolved.append(str(rel_path / pattern.split('/')[-1]))
            except ValueError:
                # Symlink points outside repo - reject
                logger.warning(f"Symlink points outside repo: {pattern}")
                continue
        else:
            resolved.append(pattern)
    return resolved
```

#### M3: No Timeout for Individual Plan Steps
**Location:** `src/ninja_cli_mcp/tools.py:222-285`

**Issue:** Sequential/parallel plans inherit global timeout but don't enforce per-step timeouts:
```python
# Only global timeout exists
timeout_sec: int = 600
```

**Impact:** 🟡 MEDIUM - One stuck step blocks entire plan
**CVSS:** 5.3 (Medium)

**Recommended Solution:**
```python
async def execute_step_with_timeout(step: PlanStep, timeout: int):
    """Execute step with individual timeout."""
    try:
        return await asyncio.wait_for(
            self._execute_single_step(step),
            timeout=min(step.max_time or timeout, timeout)
        )
    except asyncio.TimeoutError:
        logger.error(f"Step {step.id} exceeded timeout")
        return StepResult(
            id=step.id,
            status="timeout",
            summary=f"Step exceeded {timeout}s timeout"
        )
```

#### M4: Insufficient Input Validation for Task Descriptions
**Location:** `src/ninja_cli_mcp/security.py:160-184`

**Issue:** Task descriptions sent to AI can contain prompt injection attacks:
```python
InputValidator.sanitize_string(value)  # Only checks length, logs warnings
```

**Impact:** 🟡 MEDIUM - Prompt injection, unintended behavior
**CVSS:** 5.1 (Medium)

**Recommended Solution:**
```python
def sanitize_task_description(task: str, max_length: int = 5000) -> str:
    """Sanitize task description for AI consumption."""
    if len(task) > max_length:
        raise ValueError(f"Task description too long ({len(task)} > {max_length})")
    
    # Remove or escape potential prompt injection patterns
    dangerous = [
        "ignore previous instructions",
        "disregard above",
        "new instructions:",
        "system:",
        "assistant:",
    ]
    
    task_lower = task.lower()
    for pattern in dangerous:
        if pattern in task_lower:
            logger.warning(f"Potential prompt injection detected: {pattern}")
            # Option 1: Reject
            raise ValueError("Task contains potentially dangerous instructions")
            # Option 2: Sanitize
            # task = task.replace(pattern, f"[removed:{pattern}]")
    
    return task
```

---

### LOW Severity

#### L1: Cache Directory Not Cleaned Up
**Location:** `src/ninja_cli_mcp/path_utils.py:74-108`

**Issue:** Cache dir `~/.cache/ninja-cli-mcp/<hash>/` grows indefinitely:
```python
internal = cache_base / "ninja-cli-mcp" / f"{repo_hash}-{repo_name}"
# No cleanup mechanism
```

**Impact:** 🟢 LOW - Disk space exhaustion over time
**CVSS:** 3.1 (Low)

**Recommended Solution:**
```python
def cleanup_old_cache(max_age_days: int = 30):
    """Clean up cache directories older than max_age_days."""
    import time
    
    cache_dir = Path.home() / ".cache" / "ninja-cli-mcp"
    if not cache_dir.exists():
        return
    
    cutoff_time = time.time() - (max_age_days * 86400)
    
    for repo_cache in cache_dir.iterdir():
        if repo_cache.is_dir():
            mtime = repo_cache.stat().st_mtime
            if mtime < cutoff_time:
                shutil.rmtree(repo_cache)
                logger.info(f"Cleaned up old cache: {repo_cache}")

# Call periodically or on startup
```

#### L2: No Integrity Checks for Subprocess Output
**Location:** `src/ninja_cli_mcp/ninja_driver.py:467-518`

**Issue:** Subprocess output is trusted without verification:
- Could be tampered with by malicious CLI
- No checksum validation

**Impact:** 🟢 LOW - Trust boundary issue
**CVSS:** 2.8 (Low)

**Recommended Solution:**
- Add digital signatures for trusted CLIs
- Validate JSON structure strictly
- Implement content-based detection of anomalies

#### L3: Resource Monitor Lacks Memory Leak Detection
**Location:** `src/ninja_cli_mcp/security.py:216-281`

**Issue:** ResourceMonitor tracks tasks but doesn't detect memory leaks:
```python
def record_task(self, duration: float):
    self.task_count += 1
    # No memory growth tracking
```

**Impact:** 🟢 LOW - Slow memory leaks undetected
**CVSS:** 2.5 (Low)

**Recommended Solution:**
```python
import tracemalloc

class EnhancedResourceMonitor(ResourceMonitor):
    def __init__(self):
        super().__init__()
        self.memory_snapshots = []
        tracemalloc.start()
    
    def check_memory_growth(self):
        """Detect memory leaks."""
        snapshot = tracemalloc.take_snapshot()
        self.memory_snapshots.append(snapshot)
        
        if len(self.memory_snapshots) > 10:
            # Compare with 10 tasks ago
            old_snapshot = self.memory_snapshots[-10]
            diff = snapshot.compare_to(old_snapshot, 'lineno')
            
            # Alert on significant growth
            total_growth = sum(stat.size_diff for stat in diff[:10])
            if total_growth > 10 * 1024 * 1024:  # 10MB growth
                logger.warning(f"Potential memory leak: {total_growth} bytes growth")
```

---

## Implementation Priority

### Phase 1: Critical Fixes (Week 1)
1. **C1**: Move API keys to secure file-based storage
2. **C2**: Add model name validation with whitelist

### Phase 2: High Priority (Week 2-3)
3. **H1**: Validate all context paths against repo root
4. **H2**: Implement log sanitization for sensitive data
5. **H3**: Add subprocess output size limits
6. **H4**: Enhanced rate limiting with cost tracking

### Phase 3: Medium Priority (Week 4-5)
7. **M1**: Git worktree isolation for parallel execution
8. **M2**: Symlink resolution in glob patterns
9. **M3**: Per-step timeout enforcement
10. **M4**: Prompt injection protection

### Phase 4: Low Priority (Week 6+)
11. **L1**: Cache cleanup mechanism
12. **L2**: Output integrity validation
13. **L3**: Memory leak detection

---

## Additional Recommendations

### Security Hardening Checklist
- [ ] Enable seccomp profiles for subprocess isolation (Linux)
- [ ] Use AppArmor/SELinux policies
- [ ] Implement audit logging for all file operations
- [ ] Add HMAC signatures for MCP messages
- [ ] Set up honeypot paths to detect malicious activity
- [ ] Implement circuit breakers for OpenRouter API
- [ ] Add telemetry for security events
- [ ] Create incident response playbook

### Monitoring & Detection
```python
class SecurityMonitor:
    """Monitor for security events."""
    
    def __init__(self):
        self.suspicious_patterns = []
        self.alert_thresholds = {
            'path_traversal_attempts': 5,
            'rate_limit_hits': 10,
            'large_outputs': 3,
        }
    
    def record_event(self, event_type: str, details: dict):
        """Record security event."""
        # Log to SIEM
        # Trigger alerts if threshold exceeded
        # Update security dashboard
```

### Penetration Testing Scenarios
1. **Path Traversal**: Try `../../../etc/passwd` in various inputs
2. **Command Injection**: Inject shell metacharacters in model names
3. **Resource Exhaustion**: Send 1000 concurrent requests
4. **Prompt Injection**: Craft task descriptions to manipulate AI behavior
5. **API Key Extraction**: Search logs and memory for keys
6. **Race Conditions**: Parallel writes to same file
7. **Symlink Attacks**: Create symlinks to sensitive files
8. **Timing Attacks**: Measure response times to infer data

---

## References

- OWASP Top 10 2021
- CWE-78: OS Command Injection
- CWE-22: Path Traversal  
- CWE-532: Information Exposure Through Log Files
- MCP Security Best Practices (2025)
- NIST SP 800-53: Security Controls

## Change Log

- **2025-12-19**: Initial security analysis (v1.0)
