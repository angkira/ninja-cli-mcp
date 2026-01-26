# OpenCode Integration Plan
## Local Multi-Agent System with Sessions & Logging

### 🎯 Vision
Create a powerful local code generation system supporting multiple CLI backends (Aider, OpenCode, Gemini, Copilot) with intelligent routing, multi-agent orchestration, session persistence, and comprehensive logging.

**Core Priorities:**
- ✅ **Local/Container Execution**: No remote dependencies, runs locally or in containers
- ✅ **Multi-Agent Orchestration**: oh-my-opencode integration for complex tasks
- ✅ **Session Management**: Persistent conversations across tasks
- ✅ **Comprehensive Logging**: Full traceability and debugging support

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

### Target Architecture
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
  │    Multi-Agent Orchestrator (oh-my-opencode)
  │         ↓
  │    [Architect, Frontend, Backend, DevOps, ...]
  │         ↓
  └─────────┴──────────→
    Session Manager (conversation history)
    ↓
Enhanced Result Logger (structured logs)
    ↓
User Result
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
- ✅ 75+ provider support
- ✅ Agent Client Protocol (stdin/stdout)
- ✅ Custom agent framework
- ✅ Better error handling
- ✅ Background task execution
- ✅ Local and containerized execution

**Unique Features:**
1. **Sessions** (`opencode --continue <session_id>`)
2. **Agent Protocol** (`opencode acp` for streaming)
3. **Export/Import** (session portability)
4. **MCP Integration** (native tool calling)
5. **oh-my-opencode** (multi-agent orchestration)

**Use Cases:**
- Complex multi-step workflows
- Tasks requiring context retention
- Multi-agent orchestration
- Integration with other tools (ACP)

**Command Examples:**
```bash
# Non-interactive execution (current mode)
opencode run --model anthropic/claude-sonnet-4-5 --output json "Create auth.py..."

# Continue previous session
opencode --continue <session-id> --model anthropic/claude-sonnet-4-5

# Export session for analysis
opencode export <session-id> --format json > session.json

# Multi-agent mode (oh-my-opencode)
opencode run --model anthropic/claude-sonnet-4-5 "Build full-stack app ultrawork"
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
- Parallel task execution with coordination
- Shared session context across agents

**Architecture:**
```
Task: "Build e-commerce platform"
    ↓
Chief Architect: Designs system (DB schema, API structure, components)
    ↓
Parallel Execution:
    ├─ Frontend Engineer: React UI components
    ├─ Backend Engineer: FastAPI endpoints + SQLAlchemy models
    ├─ DevOps Engineer: Docker compose, CI/CD
    └─ Librarian: README, API docs, architecture diagrams
    ↓
Oracle: Reviews, validates, coordinates integration
    ↓
Complete system delivered
```

**Use Cases:**
- Full-stack applications
- Multi-repo projects
- Complex integrations
- Large-scale refactoring
- Architecture design + implementation

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

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TaskComplexity(Enum):
    """Task complexity levels for routing."""
    SIMPLE = "simple"           # Single file, < 50 lines
    MODERATE = "moderate"       # 2-5 files, < 200 lines
    COMPLEX = "complex"         # 6-10 files, refactoring
    FULL_STACK = "full_stack"   # Multiple components, architecture


class TaskType(Enum):
    """Task types for specialized handling."""
    QUICK_FIX = "quick_fix"           # Bug fix, typo
    REFACTOR = "refactor"             # Code restructuring
    FEATURE = "feature"               # New functionality
    ARCHITECTURE = "architecture"     # System design
    MULTI_AGENT = "multi_agent"       # Requires orchestration


@dataclass
class TaskAnalysis:
    """Analysis result for intelligent routing."""
    complexity: TaskComplexity
    task_type: TaskType
    estimated_files: int
    requires_session: bool
    requires_multi_agent: bool
    keywords: list[str]
    suggested_cli: str  # "aider", "opencode", etc.


@dataclass
class CLICapabilities:
    """Capabilities of a CLI tool."""
    supports_streaming: bool
    supports_file_context: bool
    supports_model_routing: bool
    supports_sessions: bool
    supports_multi_agent: bool
    supports_native_mcp: bool
    max_context_files: int
    preferred_task_types: list[str]


class BaseCLIStrategy:
    """Base class for CLI strategies."""

    def __init__(self, bin_path: str, config: "NinjaConfig"):
        self.bin_path = bin_path
        self.config = config

    @property
    def name(self) -> str:
        """CLI tool name."""
        raise NotImplementedError

    @property
    def capabilities(self) -> CLICapabilities:
        """Return CLI capabilities."""
        raise NotImplementedError

    def analyze_task(self, prompt: str, context_paths: list[str] | None = None) -> TaskAnalysis:
        """Analyze task to determine complexity and requirements."""
        # Basic keyword analysis
        prompt_lower = prompt.lower()
        keywords = []

        # Detect complexity indicators
        if any(kw in prompt_lower for kw in ["frontend", "backend", "api", "database"]):
            keywords.extend(["frontend", "backend", "api", "database"])
            complexity = TaskComplexity.FULL_STACK
        elif any(kw in prompt_lower for kw in ["refactor", "restructure", "reorganize"]):
            keywords.append("refactor")
            complexity = TaskComplexity.COMPLEX
        elif context_paths and len(context_paths) > 5:
            complexity = TaskComplexity.COMPLEX
        elif context_paths and len(context_paths) > 2:
            complexity = TaskComplexity.MODERATE
        else:
            complexity = TaskComplexity.SIMPLE

        # Detect task type
        if any(kw in prompt_lower for kw in ["fix", "bug", "error", "typo"]):
            task_type = TaskType.QUICK_FIX
        elif any(kw in prompt_lower for kw in ["refactor", "restructure"]):
            task_type = TaskType.REFACTOR
        elif any(kw in prompt_lower for kw in ["architecture", "design", "system"]):
            task_type = TaskType.ARCHITECTURE
        elif any(kw in prompt_lower for kw in ["ultrawork", "ulw", "multi-agent"]):
            task_type = TaskType.MULTI_AGENT
        else:
            task_type = TaskType.FEATURE

        # Determine if session/multi-agent needed
        requires_session = complexity in [TaskComplexity.COMPLEX, TaskComplexity.FULL_STACK]
        requires_multi_agent = (
            task_type == TaskType.MULTI_AGENT or
            complexity == TaskComplexity.FULL_STACK or
            "ultrawork" in prompt_lower or
            "ulw" in prompt_lower
        )

        return TaskAnalysis(
            complexity=complexity,
            task_type=task_type,
            estimated_files=len(context_paths) if context_paths else 1,
            requires_session=requires_session,
            requires_multi_agent=requires_multi_agent,
            keywords=keywords,
            suggested_cli=self._suggest_cli(complexity, task_type, requires_multi_agent),
        )

    def _suggest_cli(
        self,
        complexity: TaskComplexity,
        task_type: TaskType,
        requires_multi_agent: bool,
    ) -> str:
        """Suggest best CLI for this task."""
        if requires_multi_agent:
            return "opencode"  # Only OpenCode supports oh-my-opencode
        elif complexity == TaskComplexity.SIMPLE and task_type == TaskType.QUICK_FIX:
            return "aider"  # Aider is fastest for simple tasks
        elif complexity in [TaskComplexity.COMPLEX, TaskComplexity.FULL_STACK]:
            return "opencode"  # OpenCode better for complex tasks with sessions
        else:
            return "aider"  # Default to Aider for moderate tasks

    def build_command(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
        model: str | None = None,
        additional_flags: dict[str, Any] | None = None,
    ) -> CLICommandResult:
        """Build CLI command."""
        raise NotImplementedError

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> ParsedResult:
        """Parse CLI output."""
        raise NotImplementedError
```

#### 3.2 OpenCode Strategy Enhancement
```python
# src/ninja_coder/strategies/opencode_strategy.py

class OpenCodeStrategy(BaseCLIStrategy):
    """Strategy for OpenCode CLI with sessions and multi-agent support."""

    def __init__(self, bin_path: str, config: NinjaConfig):
        super().__init__(bin_path, config)
        self._session: DialogueSession | None = None
        self._capabilities = CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=True,
            supports_sessions=True,           # ✅ Session support
            supports_multi_agent=True,        # ✅ oh-my-opencode
            supports_native_mcp=True,         # ✅ Native MCP
            max_context_files=100,
            preferred_task_types=["complex", "full_stack", "multi_agent"],
        )

    def build_command_with_session(
        self,
        prompt: str,
        repo_root: str,
        session_id: str | None = None,
        file_paths: list[str] | None = None,
        model: str | None = None,
        enable_multi_agent: bool = False,
    ) -> CLICommandResult:
        """Build OpenCode command with optional session continuation.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path.
            session_id: Optional session ID to continue.
            file_paths: List of files to include in context.
            model: Model to use (if None, use configured default).
            enable_multi_agent: If True, adds 'ultrawork' to activate oh-my-opencode.

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        model_name = model or self.config.model

        cmd = [self.bin_path]

        # Session continuation
        if session_id:
            cmd.extend(["--continue", session_id])

        cmd.extend(["run", "--model", model_name])

        # File context
        if file_paths:
            for file_path in file_paths:
                cmd.extend(["--file", file_path])

        # Output format for parsing
        cmd.extend(["--output", "json"])

        # Multi-agent activation
        if enable_multi_agent:
            prompt = f"{prompt}\n\nultrawork"

        # Prompt as positional argument
        cmd.append(prompt)

        env = os.environ.copy()
        timeout = int(os.environ.get("NINJA_OPENCODE_TIMEOUT", "600"))

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "provider": "local",
                "session_id": session_id,
                "multi_agent": enable_multi_agent,
                "model": model_name,
                "timeout": timeout,
            },
        )
```

#### 3.3 Strategy Router
```python
# src/ninja_coder/router.py

class StrategyRouter:
    """Routes tasks to optimal CLI strategy."""

    def __init__(self, strategies: dict[str, BaseCLIStrategy]):
        """Initialize router with available strategies.

        Args:
            strategies: Dict mapping CLI name to strategy instance.
        """
        self.strategies = strategies
        self.logger = get_logger(__name__)

    def select_strategy(
        self,
        prompt: str,
        context_paths: list[str] | None = None,
        preferred_cli: str | None = None,
    ) -> tuple[BaseCLIStrategy, TaskAnalysis]:
        """Select best strategy for task.

        Args:
            prompt: Task prompt.
            context_paths: Files to include in context.
            preferred_cli: User's preferred CLI (overrides auto-selection).

        Returns:
            Tuple of (selected_strategy, task_analysis).
        """
        # Use preferred CLI if specified and available
        if preferred_cli and preferred_cli in self.strategies:
            strategy = self.strategies[preferred_cli]
            analysis = strategy.analyze_task(prompt, context_paths)
            self.logger.info(f"Using preferred CLI: {preferred_cli}")
            return strategy, analysis

        # Analyze task with each strategy
        analyses = {}
        for cli_name, strategy in self.strategies.items():
            analyses[cli_name] = strategy.analyze_task(prompt, context_paths)

        # Select based on task requirements
        # Priority 1: Multi-agent tasks -> OpenCode (only one with oh-my-opencode)
        for cli_name, analysis in analyses.items():
            if analysis.requires_multi_agent:
                if cli_name == "opencode":
                    self.logger.info(f"Selected {cli_name} for multi-agent task")
                    return self.strategies[cli_name], analysis

        # Priority 2: Complex tasks with sessions -> OpenCode
        for cli_name, analysis in analyses.items():
            if analysis.requires_session and cli_name == "opencode":
                self.logger.info(f"Selected {cli_name} for session management")
                return self.strategies[cli_name], analysis

        # Priority 3: Simple/quick tasks -> Aider (fastest)
        for cli_name, analysis in analyses.items():
            if (
                analysis.complexity == TaskComplexity.SIMPLE and
                analysis.task_type == TaskType.QUICK_FIX and
                cli_name == "aider"
            ):
                self.logger.info(f"Selected {cli_name} for quick task")
                return self.strategies[cli_name], analysis

        # Default: Use suggested CLI from analysis
        default_cli = list(analyses.values())[0].suggested_cli
        if default_cli in self.strategies:
            self.logger.info(f"Selected {default_cli} (default)")
            return self.strategies[default_cli], analyses[default_cli]

        # Fallback: First available strategy
        fallback = next(iter(self.strategies.values()))
        self.logger.warning(f"Fallback to {fallback.name}")
        return fallback, analyses[fallback.name]
```

---

### Phase 2: Session Management (Week 3-4)

#### 2.1 Session Manager
```python
# src/ninja_coder/sessions.py

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json


@dataclass
class SessionMessage:
    """Single message in conversation."""
    role: str  # "system", "user", "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """Conversation session."""
    session_id: str
    repo_root: str
    model: str
    created_at: datetime
    updated_at: datetime
    messages: list[SessionMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, metadata: dict | None = None):
        """Add message to session."""
        msg = SessionMessage(role=role, content=content, metadata=metadata or {})
        self.messages.append(msg)
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "session_id": self.session_id,
            "repo_root": self.repo_root,
            "model": self.model,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "metadata": msg.metadata,
                }
                for msg in self.messages
            ],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """Deserialize from dict."""
        messages = [
            SessionMessage(
                role=msg["role"],
                content=msg["content"],
                timestamp=datetime.fromisoformat(msg["timestamp"]),
                metadata=msg.get("metadata", {}),
            )
            for msg in data.get("messages", [])
        ]
        return cls(
            session_id=data["session_id"],
            repo_root=data["repo_root"],
            model=data["model"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            messages=messages,
            metadata=data.get("metadata", {}),
        )


class SessionManager:
    """Manages persistent conversation sessions."""

    def __init__(self, cache_dir: Path):
        """Initialize session manager.

        Args:
            cache_dir: Directory for session storage.
        """
        self.cache_dir = cache_dir
        self.sessions_dir = cache_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger(__name__)

    def create_session(
        self,
        repo_root: str,
        model: str,
        system_prompt: str = "",
        metadata: dict | None = None,
    ) -> Session:
        """Create new session.

        Args:
            repo_root: Repository root path.
            model: Model name.
            system_prompt: Optional system prompt.
            metadata: Optional session metadata.

        Returns:
            New Session instance.
        """
        import uuid
        session_id = str(uuid.uuid4())[:8]
        now = datetime.utcnow()

        session = Session(
            session_id=session_id,
            repo_root=repo_root,
            model=model,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        if system_prompt:
            session.add_message("system", system_prompt)

        self._save_session(session)
        self.logger.info(f"Created session {session_id} for {repo_root}")
        return session

    def load_session(self, session_id: str) -> Session | None:
        """Load existing session.

        Args:
            session_id: Session identifier.

        Returns:
            Session instance or None if not found.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            self.logger.warning(f"Session {session_id} not found")
            return None

        with open(session_file, "r") as f:
            data = json.load(f)
            session = Session.from_dict(data)
            self.logger.info(f"Loaded session {session_id} ({len(session.messages)} messages)")
            return session

    def save_session(self, session: Session):
        """Save session to disk.

        Args:
            session: Session to save.
        """
        self._save_session(session)

    def _save_session(self, session: Session):
        """Internal save implementation."""
        session_file = self.sessions_dir / f"{session.session_id}.json"
        with open(session_file, "w") as f:
            json.dump(session.to_dict(), f, indent=2)

    def list_sessions(self, repo_root: str | None = None) -> list[Session]:
        """List all sessions, optionally filtered by repo.

        Args:
            repo_root: Optional repo root to filter by.

        Returns:
            List of Session instances.
        """
        sessions = []
        for session_file in self.sessions_dir.glob("*.json"):
            with open(session_file, "r") as f:
                data = json.load(f)
                if repo_root is None or data["repo_root"] == repo_root:
                    sessions.append(Session.from_dict(data))

        # Sort by updated_at (most recent first)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete session.

        Args:
            session_id: Session identifier.

        Returns:
            True if deleted, False if not found.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
            self.logger.info(f"Deleted session {session_id}")
            return True
        return False
```

#### 2.2 Driver Integration
```python
# src/ninja_coder/driver.py (additions)

class NinjaDriver:
    """Main driver with session support."""

    def __init__(self, config: NinjaConfig):
        self.config = config
        self.cache_dir = get_cache_dir()
        self.session_manager = SessionManager(self.cache_dir)
        # ... existing initialization ...

    async def execute_with_session(
        self,
        task: str,
        repo_root: str,
        session_id: str | None = None,
        context_paths: list[str] | None = None,
        model: str | None = None,
        create_session: bool = False,
    ) -> NinjaResult:
        """Execute task with session management.

        Args:
            task: Task description.
            repo_root: Repository root path.
            session_id: Optional session ID to continue.
            context_paths: Files to include in context.
            model: Optional model override.
            create_session: If True, create new session for conversation.

        Returns:
            NinjaResult with session_id if session was used.
        """
        # Load or create session
        session = None
        if session_id:
            session = self.session_manager.load_session(session_id)
            if not session:
                return NinjaResult(
                    success=False,
                    summary=f"Session {session_id} not found",
                    notes="",
                    touched_paths=[],
                )
        elif create_session:
            session = self.session_manager.create_session(
                repo_root=repo_root,
                model=model or self.config.model,
                metadata={"context_paths": context_paths},
            )

        # Add user message to session
        if session:
            session.add_message("user", task)
            self.session_manager.save_session(session)

        # Select strategy
        strategy, analysis = self.router.select_strategy(
            prompt=task,
            context_paths=context_paths,
            preferred_cli=self.config.code_bin,
        )

        # Build command with session support
        if hasattr(strategy, "build_command_with_session") and session:
            cmd_result = strategy.build_command_with_session(
                prompt=task,
                repo_root=repo_root,
                session_id=session.session_id if session else None,
                file_paths=context_paths,
                model=model,
                enable_multi_agent=analysis.requires_multi_agent,
            )
        else:
            cmd_result = strategy.build_command(
                prompt=task,
                repo_root=repo_root,
                file_paths=context_paths,
                model=model,
            )

        # Execute
        result = await self._execute_command(cmd_result, strategy)

        # Add assistant response to session
        if session:
            session.add_message(
                "assistant",
                result.summary,
                metadata={
                    "touched_paths": result.touched_paths,
                    "success": result.success,
                },
            )
            self.session_manager.save_session(session)
            result.session_id = session.session_id

        return result
```

---

### Phase 3: Multi-Agent Orchestration (Week 5-6)

#### 3.1 Oh-My-OpenCode Integration
```python
# src/ninja_coder/multi_agent.py

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentRole:
    """Definition of an agent role."""
    name: str
    description: str
    keywords: list[str]  # Keywords that trigger this agent


class MultiAgentOrchestrator:
    """Orchestrates oh-my-opencode multi-agent tasks."""

    # Agent definitions
    AGENTS = [
        AgentRole(
            name="Chief AI Architect",
            description="System design, architecture decisions, technical planning",
            keywords=["architecture", "design", "system", "structure", "plan"],
        ),
        AgentRole(
            name="Frontend Engineer",
            description="React, Vue, UI components, styling, responsive design",
            keywords=["frontend", "react", "vue", "ui", "component", "css", "html"],
        ),
        AgentRole(
            name="Backend Engineer",
            description="APIs, databases, server logic, data models",
            keywords=["backend", "api", "database", "server", "endpoint", "sql"],
        ),
        AgentRole(
            name="DevOps Engineer",
            description="CI/CD, deployment, infrastructure, Docker, monitoring",
            keywords=["devops", "docker", "ci/cd", "deploy", "infrastructure", "k8s"],
        ),
        AgentRole(
            name="Oracle",
            description="Decision making, trade-off analysis, code review",
            keywords=["review", "decision", "tradeoff", "evaluate", "assess"],
        ),
        AgentRole(
            name="Librarian",
            description="Documentation, code organization, README files",
            keywords=["documentation", "docs", "readme", "comments", "organize"],
        ),
        AgentRole(
            name="Explorer",
            description="Code analysis, refactoring, optimization",
            keywords=["refactor", "optimize", "analyze", "improve", "clean"],
        ),
    ]

    def __init__(self, opencode_strategy: "OpenCodeStrategy"):
        """Initialize orchestrator.

        Args:
            opencode_strategy: OpenCode strategy instance.
        """
        self.strategy = opencode_strategy
        self.logger = get_logger(__name__)

    def should_use_multi_agent(self, analysis: TaskAnalysis) -> bool:
        """Determine if task benefits from multi-agent orchestration.

        Args:
            analysis: Task analysis result.

        Returns:
            True if multi-agent should be used.
        """
        return (
            analysis.requires_multi_agent or
            analysis.complexity == TaskComplexity.FULL_STACK or
            analysis.task_type == TaskType.ARCHITECTURE or
            analysis.estimated_files > 10
        )

    def select_agents(self, prompt: str, analysis: TaskAnalysis) -> list[str]:
        """Select which agents are needed for this task.

        Args:
            prompt: Task prompt.
            analysis: Task analysis.

        Returns:
            List of agent names to activate.
        """
        prompt_lower = prompt.lower()
        selected = []

        # Always include Architect for complex tasks
        if analysis.complexity in [TaskComplexity.COMPLEX, TaskComplexity.FULL_STACK]:
            selected.append("Chief AI Architect")

        # Select based on keywords
        for agent in self.AGENTS:
            if any(keyword in prompt_lower for keyword in agent.keywords):
                if agent.name not in selected:
                    selected.append(agent.name)

        # Always include Oracle for coordination
        if len(selected) > 2 and "Oracle" not in selected:
            selected.append("Oracle")

        # Always include Librarian for documentation
        if "Librarian" not in selected:
            selected.append("Librarian")

        self.logger.info(f"Selected {len(selected)} agents: {', '.join(selected)}")
        return selected

    def build_ultrawork_prompt(
        self,
        task: str,
        agents: list[str],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Build enhanced prompt for oh-my-opencode.

        Args:
            task: Original task description.
            agents: List of agent names to activate.
            context: Optional additional context.

        Returns:
            Enhanced prompt with ultrawork directive.
        """
        prompt_parts = [
            "🎯 TASK:",
            task,
            "",
            "🤖 MULTI-AGENT MODE: ultrawork",
            "",
            "Required agents:",
        ]

        # Add agent descriptions
        for agent in agents:
            agent_def = next((a for a in self.AGENTS if a.name == agent), None)
            if agent_def:
                prompt_parts.append(f"  • {agent_def.name}: {agent_def.description}")

        prompt_parts.extend([
            "",
            "Coordination instructions:",
            "  • Agents should communicate through shared session context",
            "  • Execute subtasks in parallel where possible",
            "  • Chief Architect designs first, others implement in parallel",
            "  • Oracle validates integration points",
            "  • Librarian documents final result",
            "",
        ])

        # Add context if provided
        if context:
            prompt_parts.append("Additional context:")
            for key, value in context.items():
                prompt_parts.append(f"  • {key}: {value}")
            prompt_parts.append("")

        return "\n".join(prompt_parts)

    async def execute_multi_agent(
        self,
        task: str,
        repo_root: str,
        analysis: TaskAnalysis,
        context_paths: list[str] | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> "NinjaResult":
        """Execute task with multi-agent orchestration.

        Args:
            task: Task description.
            repo_root: Repository root path.
            analysis: Task analysis result.
            context_paths: Files to include in context.
            session_id: Optional session ID for continuation.
            model: Optional model override.

        Returns:
            NinjaResult with multi-agent execution metadata.
        """
        # Select agents
        agents = self.select_agents(task, analysis)

        # Build ultrawork prompt
        context = {
            "complexity": analysis.complexity.value,
            "task_type": analysis.task_type.value,
            "estimated_files": analysis.estimated_files,
        }
        enhanced_prompt = self.build_ultrawork_prompt(task, agents, context)

        # Log multi-agent activation
        self.logger.info(f"🤖 Activating {len(agents)} agents for task")
        self.logger.debug(f"Agents: {', '.join(agents)}")

        # Execute with OpenCode
        cmd_result = self.strategy.build_command_with_session(
            prompt=enhanced_prompt,
            repo_root=repo_root,
            session_id=session_id,
            file_paths=context_paths,
            model=model,
            enable_multi_agent=True,
        )

        # TODO: Execute command and parse result
        # For now, return placeholder
        from ninja_coder.driver import NinjaResult
        return NinjaResult(
            success=True,
            summary=f"Multi-agent task executed with {len(agents)} agents",
            notes=f"Agents: {', '.join(agents)}",
            touched_paths=[],
            multi_agent_metadata={
                "agents": agents,
                "complexity": analysis.complexity.value,
            },
        )
```

---

### Phase 4: Comprehensive Logging System (Week 7)

#### 4.1 Structured Logger
```python
# src/ninja_common/structured_logger.py

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: str
    level: str
    logger_name: str
    message: str
    session_id: str | None = None
    task_id: str | None = None
    cli_name: str | None = None
    model: str | None = None
    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict, excluding None values."""
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


class StructuredLogger:
    """Logger with structured output for debugging and analysis."""

    def __init__(self, name: str, log_dir: Path):
        """Initialize structured logger.

        Args:
            name: Logger name.
            log_dir: Directory for log files.
        """
        self.name = name
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create daily log file
        today = datetime.utcnow().strftime("%Y%m%d")
        self.log_file = log_dir / f"ninja-{today}.jsonl"

        # Standard logger for console
        self.console_logger = logging.getLogger(name)

    def log(
        self,
        level: str,
        message: str,
        session_id: str | None = None,
        task_id: str | None = None,
        cli_name: str | None = None,
        model: str | None = None,
        **extra,
    ):
        """Log structured entry.

        Args:
            level: Log level (INFO, DEBUG, WARNING, ERROR).
            message: Log message.
            session_id: Optional session identifier.
            task_id: Optional task identifier.
            cli_name: Optional CLI name.
            model: Optional model name.
            **extra: Additional fields to log.
        """
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=level,
            logger_name=self.name,
            message=message,
            session_id=session_id,
            task_id=task_id,
            cli_name=cli_name,
            model=model,
            extra=extra if extra else None,
        )

        # Write to JSONL file
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

        # Also log to console
        console_level = getattr(logging, level, logging.INFO)
        self.console_logger.log(console_level, message)

    def info(self, message: str, **kwargs):
        """Log INFO level."""
        self.log("INFO", message, **kwargs)

    def debug(self, message: str, **kwargs):
        """Log DEBUG level."""
        self.log("DEBUG", message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log WARNING level."""
        self.log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log ERROR level."""
        self.log("ERROR", message, **kwargs)

    def log_command(
        self,
        command: list[str],
        session_id: str | None = None,
        task_id: str | None = None,
        **kwargs,
    ):
        """Log CLI command execution."""
        self.log(
            "INFO",
            f"Executing: {' '.join(command[:3])}...",
            session_id=session_id,
            task_id=task_id,
            command=command,
            **kwargs,
        )

    def log_result(
        self,
        success: bool,
        summary: str,
        session_id: str | None = None,
        task_id: str | None = None,
        **kwargs,
    ):
        """Log task result."""
        level = "INFO" if success else "ERROR"
        self.log(
            level,
            summary,
            session_id=session_id,
            task_id=task_id,
            success=success,
            **kwargs,
        )

    def query_logs(
        self,
        session_id: str | None = None,
        task_id: str | None = None,
        cli_name: str | None = None,
        level: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query logs with filters.

        Args:
            session_id: Filter by session ID.
            task_id: Filter by task ID.
            cli_name: Filter by CLI name.
            level: Filter by log level.
            limit: Maximum number of entries to return.

        Returns:
            List of log entries as dicts.
        """
        if not self.log_file.exists():
            return []

        results = []
        with open(self.log_file, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line)

                    # Apply filters
                    if session_id and entry.get("session_id") != session_id:
                        continue
                    if task_id and entry.get("task_id") != task_id:
                        continue
                    if cli_name and entry.get("cli_name") != cli_name:
                        continue
                    if level and entry.get("level") != level:
                        continue

                    results.append(entry)

                    if len(results) >= limit:
                        break
                except json.JSONDecodeError:
                    continue

        return results
```

#### 4.2 Driver Integration
```python
# src/ninja_coder/driver.py (logging additions)

from ninja_common.structured_logger import StructuredLogger

class NinjaDriver:
    """Main driver with comprehensive logging."""

    def __init__(self, config: NinjaConfig):
        # ... existing initialization ...
        self.structured_logger = StructuredLogger(
            name="ninja-coder",
            log_dir=self.cache_dir / "logs",
        )

    async def execute_with_logging(
        self,
        task: str,
        repo_root: str,
        task_id: str,
        session_id: str | None = None,
        **kwargs,
    ) -> NinjaResult:
        """Execute task with comprehensive logging.

        Args:
            task: Task description.
            repo_root: Repository root path.
            task_id: Unique task identifier.
            session_id: Optional session ID.
            **kwargs: Additional execution parameters.

        Returns:
            NinjaResult with execution metadata.
        """
        # Log task start
        self.structured_logger.info(
            f"Starting task: {task[:100]}...",
            task_id=task_id,
            session_id=session_id,
            repo_root=repo_root,
        )

        try:
            # Select strategy
            strategy, analysis = self.router.select_strategy(
                prompt=task,
                context_paths=kwargs.get("context_paths"),
                preferred_cli=self.config.code_bin,
            )

            # Log strategy selection
            self.structured_logger.info(
                f"Selected strategy: {strategy.name}",
                task_id=task_id,
                session_id=session_id,
                cli_name=strategy.name,
                complexity=analysis.complexity.value,
                task_type=analysis.task_type.value,
                requires_multi_agent=analysis.requires_multi_agent,
            )

            # Build command
            cmd_result = strategy.build_command(
                prompt=task,
                repo_root=repo_root,
                **kwargs,
            )

            # Log command
            self.structured_logger.log_command(
                command=cmd_result.command,
                task_id=task_id,
                session_id=session_id,
                cli_name=strategy.name,
                model=cmd_result.metadata.get("model"),
            )

            # Execute
            result = await self._execute_command(cmd_result, strategy)

            # Log result
            self.structured_logger.log_result(
                success=result.success,
                summary=result.summary,
                task_id=task_id,
                session_id=session_id,
                cli_name=strategy.name,
                touched_paths=result.touched_paths,
                execution_time=result.execution_time,
            )

            return result

        except Exception as e:
            # Log error
            self.structured_logger.error(
                f"Task failed: {str(e)}",
                task_id=task_id,
                session_id=session_id,
                error=str(e),
            )
            raise
```

---

### Phase 5: Container Support (Week 8)

#### 5.1 Docker Configuration
```dockerfile
# docker/Dockerfile.ninja-coder

FROM python:3.11-slim

# Install OpenCode CLI
RUN apt-get update && \
    apt-get install -y curl git && \
    curl -fsSL https://opencode.ai/install.sh | bash

# Install Aider (optional)
RUN pip install aider-chat

# Copy ninja-coder source
WORKDIR /app
COPY . /app

# Install dependencies
RUN pip install -e .

# Create cache directory
RUN mkdir -p /root/.cache/ninja-mcp

# Entry point
ENTRYPOINT ["python", "-m", "ninja_coder.server"]
```

```yaml
# docker-compose.yml

version: '3.8'

services:
  ninja-coder:
    build:
      context: .
      dockerfile: docker/Dockerfile.ninja-coder
    volumes:
      # Mount code repository
      - ${REPO_ROOT:-./}:/workspace
      # Mount cache for sessions
      - ninja-cache:/root/.cache/ninja-mcp
    environment:
      # Pass through API keys
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      # Configuration
      - NINJA_CODE_BIN=${NINJA_CODE_BIN:-opencode}
      - NINJA_MODEL=${NINJA_MODEL:-anthropic/claude-sonnet-4-5}
    working_dir: /workspace

volumes:
  ninja-cache:
```

#### 5.2 Container Execution
```python
# src/ninja_coder/container.py

import subprocess
from pathlib import Path
from typing import Any


class ContainerExecutor:
    """Executes CLI tools in containers."""

    def __init__(self, compose_file: Path):
        """Initialize container executor.

        Args:
            compose_file: Path to docker-compose.yml.
        """
        self.compose_file = compose_file

    def execute_in_container(
        self,
        command: list[str],
        env: dict[str, str],
        working_dir: Path,
        timeout: int = 600,
    ) -> tuple[str, str, int]:
        """Execute command in container.

        Args:
            command: Command to execute.
            env: Environment variables.
            working_dir: Working directory.
            timeout: Execution timeout in seconds.

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """
        # Build docker-compose exec command
        docker_cmd = [
            "docker-compose",
            "-f", str(self.compose_file),
            "exec",
            "-T",  # Non-interactive
            "-w", str(working_dir),
        ]

        # Add environment variables
        for key, value in env.items():
            docker_cmd.extend(["-e", f"{key}={value}"])

        docker_cmd.append("ninja-coder")
        docker_cmd.extend(command)

        # Execute
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return result.stdout, result.stderr, result.returncode
```

---

## 4. Feature Matrix

| Feature | Aider | OpenCode | Gemini | Copilot |
|---------|-------|----------|--------|---------|
| **Speed** | ⚡⚡⚡ | ⚡⚡ | ⚡⚡ | ⚡⚡ |
| **Sessions** | ❌ | ✅ | ❌ | ❌ |
| **Multi-Agent** | ❌ | ✅ (oh-my) | ❌ | ❌ |
| **Native MCP** | ❌ | ✅ | ❌ | ❌ |
| **Model Support** | 75+ | 75+ | Gemini | GPT-4 |
| **Best For** | Quick fixes | Complex tasks | Google users | GitHub users |
| **Container Ready** | ✅ | ✅ | ✅ | ⚠️ |
| **Structured Logs** | ✅ | ✅ | ✅ | ✅ |

---

## 5. Testing Strategy

### Unit Tests
```python
# tests/test_multi_agent.py

def test_agent_selection():
    """Test agent selection logic."""
    orchestrator = MultiAgentOrchestrator(mock_strategy)

    # Full-stack task
    analysis = TaskAnalysis(
        complexity=TaskComplexity.FULL_STACK,
        task_type=TaskType.FEATURE,
        estimated_files=15,
        requires_session=True,
        requires_multi_agent=True,
        keywords=["frontend", "backend", "api"],
        suggested_cli="opencode",
    )

    agents = orchestrator.select_agents(
        "Build e-commerce platform with React and FastAPI",
        analysis,
    )

    assert "Chief AI Architect" in agents
    assert "Frontend Engineer" in agents
    assert "Backend Engineer" in agents
    assert "Oracle" in agents
    assert "Librarian" in agents
```

### Integration Tests
```python
# tests/integration/test_opencode_session.py

async def test_opencode_with_session():
    """Test OpenCode execution with session persistence."""
    driver = NinjaDriver(config)

    # Create session
    result1 = await driver.execute_with_session(
        task="Create user.py with User class",
        repo_root="/tmp/test-repo",
        create_session=True,
    )
    assert result1.success
    assert result1.session_id is not None

    # Continue session
    result2 = await driver.execute_with_session(
        task="Add email validation to User class",
        repo_root="/tmp/test-repo",
        session_id=result1.session_id,
    )
    assert result2.success
    assert result2.session_id == result1.session_id

    # Verify session history
    session = driver.session_manager.load_session(result1.session_id)
    assert len(session.messages) >= 4  # system, user1, assistant1, user2, assistant2
```

### Multi-Agent Tests
```python
# tests/integration/test_multi_agent.py

async def test_ultrawork_activation():
    """Test oh-my-opencode multi-agent activation."""
    driver = NinjaDriver(config)

    result = await driver.execute_with_logging(
        task="Build full-stack todo app with React frontend and FastAPI backend ultrawork",
        repo_root="/tmp/test-repo",
        task_id="test-multiagent-001",
    )

    assert result.success
    assert result.multi_agent_metadata is not None
    assert len(result.multi_agent_metadata["agents"]) >= 4
    assert "Chief AI Architect" in result.multi_agent_metadata["agents"]
```

---

## 6. Timeline

### Phase 1: Enhanced Strategy System (Week 1-2)
- ✅ Base strategy class with capabilities
- ✅ Task analysis and routing
- ✅ OpenCode strategy enhancement

### Phase 2: Session Management (Week 3-4)
- ✅ Session manager implementation
- ✅ Driver integration
- ✅ Session persistence and loading

### Phase 3: Multi-Agent Orchestration (Week 5-6)
- ✅ oh-my-opencode integration
- ✅ Agent selection logic
- ✅ Ultrawork prompt builder

### Phase 4: Comprehensive Logging (Week 7)
- ✅ Structured logger
- ✅ JSONL log files
- ✅ Query interface

### Phase 5: Container Support (Week 8)
- ✅ Dockerfile for ninja-coder
- ✅ Docker Compose configuration
- ✅ Container executor

**Total: 8 weeks**

---

## 7. Success Metrics

- ✅ OpenCode integration: Working with anthropic/claude-sonnet-4-5
- ⏳ Session persistence: > 95% session recovery rate
- ⏳ Multi-agent tasks: Successfully complete full-stack tasks
- ⏳ Container execution: 100% parity with local execution
- ⏳ Log query performance: < 100ms for 10k entries

---

## 8. Documentation Plan

### User Guide
- **Quick Start**: Basic task execution
- **Session Management**: Creating and continuing sessions
- **Multi-Agent Mode**: When and how to use ultrawork
- **Container Deployment**: Docker setup guide
- **Logging & Debugging**: Querying logs, troubleshooting

### Developer Guide
- **Strategy Development**: Creating new CLI strategies
- **Agent Customization**: Adding oh-my-opencode agents
- **Extension Points**: Hooks and plugins

---

## 9. Open Questions

1. **oh-my-opencode Installation**: Package not on npm - need to investigate source/installation
2. **Container Networking**: How to expose MCP servers from containers?
3. **Session Limits**: When to auto-expire old sessions?
4. **Cost Tracking**: Should we track token usage per session/agent?

---

## 10. Next Steps

### Immediate (Current Sprint)
1. ✅ OpenCode configured and tested with Sonnet 4.5
2. ⏳ Implement session manager
3. ⏳ Test session persistence across tasks

### Short-term (Next 2 weeks)
1. ⏳ Multi-agent orchestrator implementation
2. ⏳ oh-my-opencode integration research
3. ⏳ Structured logging rollout

### Long-term (Next 2 months)
1. ⏳ Container deployment guides
2. ⏳ Additional CLI strategies (Gemini, Copilot)
3. ⏳ Performance optimization

---

## Summary

This plan focuses on **local/container execution** with powerful capabilities:
- ✅ **No remote dependencies** - everything runs locally or in containers
- ✅ **Multi-agent orchestration** - oh-my-opencode for complex tasks
- ✅ **Session management** - persistent conversations
- ✅ **Comprehensive logging** - structured JSONL logs with querying

**Status**: OpenCode integration complete (Phase 1), ready for Phase 2 (Sessions).
