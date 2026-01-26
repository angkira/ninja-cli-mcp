# OpenCode Integration Plan
## Multi-CLI Strategy System for Maximum Benefits

### 🎯 Vision
Create a universal code generation system that supports multiple CLI backends (Aider, OpenCode, Gemini, Copilot) and intelligently selects the best tool for each task while leveraging their unique features.

---

## 1. Architecture Overview

### Current State
```
User Request
    ↓
ninja-coder (MCP Tool)
    ↓
Strategy Selection (bin_path based)
    ↓
Single CLI (aider, opencode, etc.)
    ↓
Result
```

### Proposed Architecture
```
User Request
    ↓
Task Analyzer (complexity, type, features needed)
    ↓
Strategy Router (intelligent CLI selection)
    ↓         ↓           ↓           ↓
Aider   OpenCode    Gemini    Copilot
(fast)  (sessions)  (native)  (github)
    ↓         ↓           ↓           ↓
Result Aggregator (unified format)
    ↓
Enhanced Result (with CLI-specific metadata)
```

---

## 2. CLI Comparison & Capabilities

### Aider
**Strengths:**
- ✅ Fast execution (proven, stable)
- ✅ Minimal overhead
- ✅ Great for simple tasks
- ✅ OpenRouter support (75+ models)
- ✅ Diff-based editing (precise)

**Limitations:**
- ❌ No session persistence
- ❌ No native MCP support
- ❌ No multi-agent orchestration
- ❌ Limited advanced features

**Use Cases:**
- Quick file edits
- Simple refactoring
- Single-file changes
- Fast iterations

---

### OpenCode
**Strengths:**
- ✅ Native MCP server support
- ✅ Session management (conversation history)
- ✅ HTTP API mode (more reliable)
- ✅ 75+ provider support
- ✅ Agent Client Protocol (stdin/stdout)
- ✅ Web UI option
- ✅ Custom agent framework
- ✅ Better error handling
- ✅ Background task execution

**Unique Features:**
1. **Sessions** (`opencode --continue <session_id>`)
2. **HTTP API** (`opencode serve` + REST calls)
3. **Agent Protocol** (`opencode acp` for streaming)
4. **Export/Import** (session portability)
5. **MCP Integration** (native tool calling)

**Use Cases:**
- Complex multi-step workflows
- Tasks requiring context retention
- Production environments (HTTP API)
- Integration with other tools (ACP)

**Command Examples:**
```bash
# Non-interactive execution
opencode run --model anthropic/claude-sonnet-4 --output json "Create auth.py..."

# Start HTTP server
opencode serve --port 8200 --password <secret>

# Continue previous session
opencode --continue <session-id> --model anthropic/claude-sonnet-4

# Export session for analysis
opencode sessions export <session-id> > session.json
```

---

### Oh-My-OpenCode (Multi-Agent Framework)
**Specialized Agents:**
1. **Chief AI Architect** - System design, architecture decisions
2. **Frontend Engineer** - React, Vue, UI components
3. **Backend Engineer** - APIs, databases, server logic
4. **Oracle** - Decision making, trade-off analysis
5. **Librarian** - Documentation, code organization
6. **Explorer** - Code analysis, refactoring
7. **DevOps Engineer** - CI/CD, deployment, infrastructure

**Activation:**
- Add `ultrawork` or `ulw` keyword to prompts
- Automatic multi-agent orchestration
- Parallel task execution

**Use Cases:**
- Full-stack applications
- Multi-repo projects
- Complex integrations
- Large-scale refactoring

---

### Gemini Code Assist
**Strengths:**
- ✅ Google's native code model
- ✅ Direct Gemini integration
- ✅ No API middleman
- ✅ Long context windows
- ✅ Fast for Gemini users

**Use Cases:**
- Users with Gemini Pro subscription
- Google Cloud integration
- Large context requirements

---

### GitHub Copilot CLI
**Strengths:**
- ✅ Native GitHub integration
- ✅ Repository awareness
- ✅ Pull request context
- ✅ Issue tracking integration
- ✅ GitHub Actions support

**Unique Features:**
1. **Repository context** (knows your PR history)
2. **GitHub Actions** (workflow integration)
3. **Issue linking** (connects code to issues)

**Use Cases:**
- GitHub-centric workflows
- Open source projects
- Teams using GitHub Enterprise

---

## 3. Implementation Strategy

### Phase 1: Enhanced Strategy System (Week 1-2)

#### 3.1 Strategy Base Class Enhancement
```python
# src/ninja_coder/strategies/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

class CLICapability(Enum):
    """Capabilities that a CLI backend might support."""
    SESSIONS = "sessions"  # Persistent conversation history
    HTTP_API = "http_api"  # REST API mode
    MULTI_AGENT = "multi_agent"  # Multiple specialized agents
    MCP_NATIVE = "mcp_native"  # Native MCP server support
    STREAMING = "streaming"  # Real-time output streaming
    BACKGROUND_TASKS = "background_tasks"  # Async execution
    REPO_AWARENESS = "repo_awareness"  # Git/GitHub integration
    EXPORT_IMPORT = "export_import"  # Session portability

@dataclass
class StrategyMetadata:
    """Metadata about a strategy's capabilities."""
    cli_name: str
    version: str
    capabilities: list[CLICapability]
    max_context_tokens: int
    supports_providers: list[str]  # ["openrouter", "anthropic", "google"]
    best_for: list[str]  # ["quick_edits", "complex_workflows", etc.]

class BaseStrategy(ABC):
    """Enhanced base class for CLI strategies."""

    @abstractmethod
    def get_metadata(self) -> StrategyMetadata:
        """Return strategy capabilities and metadata."""
        pass

    @abstractmethod
    def supports_feature(self, capability: CLICapability) -> bool:
        """Check if strategy supports a specific capability."""
        pass

    # Existing methods...
    @abstractmethod
    def build_command(...) -> CLICommandResult:
        pass

    @abstractmethod
    def parse_output(...) -> ParsedResult:
        pass
```

#### 3.2 OpenCode Strategy Implementation
```python
# src/ninja_coder/strategies/opencode_strategy.py

class OpenCodeStrategy(BaseStrategy):
    """Strategy for OpenCode CLI with advanced features."""

    def __init__(self, config: NinjaConfig):
        super().__init__(config)
        self.session_manager = OpenCodeSessionManager()
        self.http_client = None  # For HTTP API mode

    def get_metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            cli_name="opencode",
            version=self._get_version(),
            capabilities=[
                CLICapability.SESSIONS,
                CLICapability.HTTP_API,
                CLICapability.MCP_NATIVE,
                CLICapability.STREAMING,
                CLICapability.BACKGROUND_TASKS,
                CLICapability.EXPORT_IMPORT,
            ],
            max_context_tokens=200000,  # OpenCode supports large contexts
            supports_providers=["anthropic", "openai", "google", "openrouter"],
            best_for=[
                "complex_workflows",
                "multi_step_tasks",
                "context_heavy_tasks",
                "production_deployments",
            ],
        )

    def supports_feature(self, capability: CLICapability) -> bool:
        return capability in self.get_metadata().capabilities

    # Session management methods
    def create_session(self, initial_prompt: str) -> str:
        """Create new OpenCode session and return session ID."""
        pass

    def continue_session(self, session_id: str, prompt: str) -> ParsedResult:
        """Continue existing session with new prompt."""
        pass

    def export_session(self, session_id: str) -> dict:
        """Export session for analysis or backup."""
        pass

    # HTTP API mode methods
    def start_http_server(self, port: int) -> bool:
        """Start OpenCode HTTP server."""
        pass

    def execute_via_http(self, prompt: str) -> ParsedResult:
        """Execute task via HTTP API (more reliable than subprocess)."""
        pass

    # Multi-agent support
    def enable_ultrawork(self, prompt: str) -> str:
        """Enhance prompt with oh-my-opencode multi-agent activation."""
        return f"{prompt}\n\nultrawork"  # Activates multi-agent mode
```

#### 3.3 Strategy Router
```python
# src/ninja_coder/strategy_router.py

from dataclasses import dataclass
from enum import Enum

class TaskComplexity(Enum):
    SIMPLE = "simple"  # Single file, < 100 lines
    MODERATE = "moderate"  # Multiple files, standard workflow
    COMPLEX = "complex"  # Multi-step, requires planning
    FULL_STACK = "full_stack"  # Frontend + backend + infra

class TaskType(Enum):
    FILE_EDIT = "file_edit"
    REFACTOR = "refactor"
    NEW_FEATURE = "new_feature"
    BUG_FIX = "bug_fix"
    FULL_PROJECT = "full_project"

@dataclass
class TaskAnalysis:
    """Analysis of task requirements."""
    complexity: TaskComplexity
    task_type: TaskType
    estimated_files: int
    requires_context_retention: bool
    requires_multi_agent: bool
    preferred_providers: list[str]

class StrategyRouter:
    """Intelligently routes tasks to the best CLI strategy."""

    def __init__(self):
        self.strategies = self._load_strategies()

    def analyze_task(self, prompt: str, context: dict) -> TaskAnalysis:
        """Analyze task to determine requirements."""
        # Use heuristics or LLM to analyze
        words = prompt.lower()

        # Detect complexity
        if any(kw in words for kw in ["full stack", "entire application", "multi-tier"]):
            complexity = TaskComplexity.FULL_STACK
        elif any(kw in words for kw in ["refactor", "redesign", "architecture"]):
            complexity = TaskComplexity.COMPLEX
        elif len(prompt.split()) > 100 or context.get("file_count", 0) > 5:
            complexity = TaskComplexity.MODERATE
        else:
            complexity = TaskComplexity.SIMPLE

        # Detect task type
        if "bug" in words or "fix" in words:
            task_type = TaskType.BUG_FIX
        elif "refactor" in words:
            task_type = TaskType.REFACTOR
        elif any(kw in words for kw in ["create", "new", "implement"]):
            task_type = TaskType.NEW_FEATURE
        else:
            task_type = TaskType.FILE_EDIT

        return TaskAnalysis(
            complexity=complexity,
            task_type=task_type,
            estimated_files=self._estimate_file_count(prompt, context),
            requires_context_retention=complexity >= TaskComplexity.COMPLEX,
            requires_multi_agent=complexity == TaskComplexity.FULL_STACK,
            preferred_providers=context.get("providers", ["openrouter"]),
        )

    def select_strategy(self, analysis: TaskAnalysis) -> BaseStrategy:
        """Select best strategy based on task analysis."""
        # Simple tasks: Use Aider (fast)
        if analysis.complexity == TaskComplexity.SIMPLE:
            return self.strategies["aider"]

        # Full-stack: Use OpenCode with oh-my-opencode
        if analysis.complexity == TaskComplexity.FULL_STACK:
            opencode = self.strategies["opencode"]
            opencode.enable_multi_agent = True
            return opencode

        # Complex tasks: Use OpenCode with sessions
        if analysis.requires_context_retention:
            return self.strategies["opencode"]

        # Default to Aider
        return self.strategies["aider"]

    def route_task(self, prompt: str, context: dict) -> tuple[BaseStrategy, TaskAnalysis]:
        """Analyze and route task to best strategy."""
        analysis = self.analyze_task(prompt, context)
        strategy = self.select_strategy(analysis)
        return strategy, analysis
```

---

### Phase 2: Session Management (Week 3-4)

#### 2.1 Session Manager
```python
# src/ninja_coder/session_manager.py

from pathlib import Path
import json
from datetime import datetime

class SessionManager:
    """Manages persistent coding sessions across CLI backends."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir / "sessions"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        project_path: str,
        strategy_name: str,
        initial_context: dict
    ) -> str:
        """Create new session and return session ID."""
        session_id = f"{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        session_data = {
            "id": session_id,
            "project_path": project_path,
            "strategy": strategy_name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "messages": [],
            "context": initial_context,
            "metadata": {}
        }

        self._save_session(session_id, session_data)
        return session_id

    def add_message(self, session_id: str, role: str, content: str):
        """Add message to session history."""
        session = self._load_session(session_id)
        session["messages"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        session["updated_at"] = datetime.now().isoformat()
        self._save_session(session_id, session)

    def get_session_context(self, session_id: str) -> dict:
        """Get full session context for continuation."""
        session = self._load_session(session_id)
        return {
            "messages": session["messages"],
            "context": session["context"],
            "metadata": session["metadata"]
        }

    def export_session(self, session_id: str, format: str = "json") -> str:
        """Export session in various formats (json, markdown, html)."""
        session = self._load_session(session_id)

        if format == "json":
            return json.dumps(session, indent=2)
        elif format == "markdown":
            return self._to_markdown(session)
        # ... other formats
```

#### 2.2 Driver Integration
```python
# src/ninja_coder/driver.py - Enhanced

class NinjaDriver:
    def __init__(self, ...):
        # Existing init
        self.session_manager = SessionManager(cache_dir)
        self.router = StrategyRouter()

    async def execute_with_session(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> NinjaResult:
        """Execute task with session support."""

        # Create or load session
        if session_id is None:
            session_id = self.session_manager.create_session(
                project_path=self.repo_root,
                strategy_name=self.config.bin_path,
                initial_context=kwargs
            )

        # Get session context
        context = self.session_manager.get_session_context(session_id)

        # Route to best strategy
        strategy, analysis = self.router.route_task(prompt, context)

        # Execute with context
        if strategy.supports_feature(CLICapability.SESSIONS):
            result = await strategy.execute_with_session(session_id, prompt)
        else:
            # Fallback to stateless execution
            result = await strategy.execute(prompt)

        # Save to session
        self.session_manager.add_message(session_id, "user", prompt)
        self.session_manager.add_message(session_id, "assistant", result.summary)

        return result
```

---

### Phase 3: HTTP API Mode (Week 5-6)

#### 3.1 OpenCode HTTP Server Manager
```python
# src/ninja_coder/opencode_server.py

import httpx
from contextlib import asynccontextmanager

class OpenCodeHTTPClient:
    """HTTP client for OpenCode serve mode."""

    def __init__(self, base_url: str, password: Optional[str] = None):
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(300.0),
            auth=(None, password) if password else None
        )

    async def execute_task(
        self,
        prompt: str,
        files: list[str] = None,
        model: str = None
    ) -> dict:
        """Execute coding task via HTTP API."""
        payload = {
            "prompt": prompt,
            "files": files or [],
            "model": model or "anthropic/claude-sonnet-4",
            "options": {
                "temperature": 0.7,
                "max_tokens": 8000
            }
        }

        response = await self.client.post("/api/chat", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_session(self, session_id: str) -> dict:
        """Get session data."""
        response = await self.client.get(f"/api/sessions/{session_id}")
        return response.json()

    async def health_check(self) -> bool:
        """Check if server is healthy."""
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except:
            return False

class OpenCodeServerManager:
    """Manages OpenCode HTTP server lifecycle."""

    def __init__(self, port: int = 8200):
        self.port = port
        self.process = None
        self.client = None

    async def start(self, password: Optional[str] = None) -> bool:
        """Start OpenCode HTTP server."""
        cmd = [
            "opencode",
            "serve",
            "--port", str(self.port),
            "--host", "127.0.0.1"
        ]

        if password:
            cmd.extend(["--password", password])

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Wait for server to be ready
        self.client = OpenCodeHTTPClient(
            f"http://127.0.0.1:{self.port}",
            password
        )

        for _ in range(30):  # 30 second timeout
            if await self.client.health_check():
                return True
            await asyncio.sleep(1)

        return False

    async def stop(self):
        """Stop OpenCode HTTP server."""
        if self.process:
            self.process.terminate()
            await self.process.wait()
```

#### 3.2 Production Mode Configuration
```python
# ~/.ninja-mcp.env additions

# OpenCode HTTP API mode (more reliable for production)
NINJA_OPENCODE_MODE=http  # or "cli" for subprocess mode
NINJA_OPENCODE_PORT=8200
NINJA_OPENCODE_PASSWORD=secure_random_password

# Enable multi-agent for complex tasks
NINJA_ENABLE_ULTRAWORK=true

# Session persistence
NINJA_SESSION_RETENTION_DAYS=30
NINJA_AUTO_EXPORT_SESSIONS=true
```

---

### Phase 4: Multi-Agent Integration (Week 7-8)

#### 4.1 Oh-My-OpenCode Integration
```python
# src/ninja_coder/multi_agent.py

class MultiAgentOrchestrator:
    """Orchestrates oh-my-opencode multi-agent tasks."""

    def __init__(self, opencode_strategy: OpenCodeStrategy):
        self.strategy = opencode_strategy

    def should_use_multi_agent(self, analysis: TaskAnalysis) -> bool:
        """Determine if task benefits from multi-agent."""
        return (
            analysis.complexity == TaskComplexity.FULL_STACK or
            analysis.estimated_files > 10 or
            any(kw in analysis.keywords for kw in [
                "frontend", "backend", "api", "database", "ui"
            ])
        )

    async def execute_multi_agent(
        self,
        prompt: str,
        agents_needed: list[str]
    ) -> NinjaResult:
        """Execute with specific agent configuration."""

        # Prepare ultrawork prompt
        ultrawork_prompt = f"""
{prompt}

ultrawork

Required agents:
{', '.join(agents_needed)}

Coordinate parallel execution where possible.
Ensure all agents communicate through shared session.
"""

        return await self.strategy.execute(ultrawork_prompt)

    def decompose_task(self, prompt: str) -> dict[str, str]:
        """Decompose complex task into agent-specific subtasks."""
        # Use LLM to analyze and decompose
        return {
            "architect": "Design system architecture",
            "frontend": "Implement React components",
            "backend": "Create API endpoints",
            "devops": "Setup CI/CD pipeline"
        }
```

---

### Phase 5: Unified MCP Interface (Week 9-10)

#### 5.1 Enhanced Tool Definitions
```python
# src/ninja_coder/tools.py - Enhanced

def get_tool_definitions() -> list[Tool]:
    return [
        Tool(
            name="coder_simple_task",
            description="Quick code generation (auto-selects best CLI)",
            inputSchema={
                "task": "Task description",
                "repo_root": "Repository path",
                "mode": "quick | full",
                # New parameters
                "preferred_cli": "aider | opencode | gemini | copilot | auto",
                "enable_sessions": "true | false",
                "enable_multi_agent": "true | false (for full-stack tasks)",
            }
        ),
        Tool(
            name="coder_with_session",
            description="Execute with session persistence",
            inputSchema={
                "task": "Task description",
                "session_id": "Continue existing session (optional)",
                "export_session": "Export session after completion",
            }
        ),
        Tool(
            name="coder_multi_agent",
            description="Complex task with multi-agent orchestration",
            inputSchema={
                "task": "Complex task description",
                "required_agents": "List of agents needed",
                "parallel_execution": "true | false",
            }
        ),
    ]
```

---

## 4. Feature Matrix

| Feature | Aider | OpenCode | Gemini | Copilot |
|---------|-------|----------|--------|---------|
| **Speed** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Sessions** | ❌ | ✅ | ❌ | ✅ |
| **HTTP API** | ❌ | ✅ | ❌ | ❌ |
| **Multi-Agent** | ❌ | ✅ (oh-my) | ❌ | ❌ |
| **MCP Native** | ❌ | ✅ | ❌ | ❌ |
| **Provider Support** | 75+ (OR) | 75+ | 1 (Gemini) | 1 (GitHub) |
| **Cost** | Pay-per-use | Pay-per-use | Subscription | Subscription |
| **Repo Awareness** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Best For** | Quick edits | Complex tasks | Gemini users | GitHub users |

---

## 5. Migration Path

### For Existing Users
1. **No Breaking Changes**: Current `NINJA_CODE_BIN=aider` continues to work
2. **Opt-In Features**: Enable new features via environment variables
3. **Gradual Adoption**: Test with `preferred_cli=auto` to try intelligent routing

### New Users
1. **Smart Defaults**: Auto-detect installed CLIs and configure best option
2. **Interactive Setup**: `ninja-config setup` asks preferences
3. **Guided Tour**: First-run tutorial shows available features

---

## 6. Testing Strategy

### Unit Tests
- Strategy selection logic
- Session management
- HTTP client
- Multi-agent orchestration

### Integration Tests
- Aider fallback (existing tests pass)
- OpenCode HTTP API
- Session continuity
- Multi-agent coordination

### Performance Tests
- Aider vs OpenCode speed comparison
- HTTP API vs subprocess reliability
- Multi-agent parallelization gains

---

## 7. Documentation Plan

### User Docs
- **Getting Started**: Which CLI to choose?
- **Feature Guides**: Sessions, Multi-Agent, HTTP API
- **Migration Guide**: Upgrading from Aider-only
- **Troubleshooting**: Common issues per CLI

### Developer Docs
- **Strategy Development**: How to add new CLI support
- **Architecture**: System design decisions
- **API Reference**: All classes and methods

---

## 8. Success Metrics

### Performance
- ✅ No regression in Aider performance (current baseline)
- ✅ OpenCode HTTP API: 99.5% uptime
- ✅ Multi-agent: 2-3x faster on full-stack tasks

### Adoption
- ✅ 80% of users on auto-routing within 3 months
- ✅ 50% of complex tasks use sessions
- ✅ 20% of full-stack tasks use multi-agent

### Quality
- ✅ 99%+ test pass rate
- ✅ < 1% regression rate
- ✅ User satisfaction: 4.5+ / 5.0

---

## 9. Timeline

### Quarter 1 (Weeks 1-13)
- ✅ Phase 1: Strategy System (Weeks 1-2)
- ✅ Phase 2: Session Management (Weeks 3-4)
- ✅ Phase 3: HTTP API Mode (Weeks 5-6)
- ✅ Phase 4: Multi-Agent (Weeks 7-8)
- ✅ Phase 5: Unified Interface (Weeks 9-10)
- ✅ Testing & Docs (Weeks 11-13)

### Quarter 2 (Weeks 14-26)
- ✅ Production hardening
- ✅ Performance optimization
- ✅ User feedback integration
- ✅ Advanced features (custom agents, workflow automation)

---

## 10. Open Questions

1. **oh-my-opencode Installation**: Package not on npm - need to investigate source
2. **Copilot CLI Access**: Requires GitHub Copilot subscription - test account needed
3. **Gemini Code Assist**: Beta access - availability unclear
4. **OpenCode Billing**: Per-API-call vs subscription - cost modeling needed

---

## Conclusion

This plan transforms ninja-coder from a single-CLI wrapper into a **universal code generation orchestrator** that:
- ✅ Intelligently selects the best tool for each task
- ✅ Leverages unique features of each CLI
- ✅ Provides unified interface across all backends
- ✅ Enables advanced capabilities (sessions, multi-agent, HTTP API)
- ✅ Maintains backward compatibility
- ✅ Scales to production workloads

**Next Steps**:
1. Get approval on architecture
2. Start Phase 1 implementation
3. Set up test environment with all CLIs
4. Begin strategy router development

---

**Status**: 🔵 Awaiting Approval
**Author**: Ninja MCP Team
**Date**: 2026-01-26
**Version**: 1.0.0
