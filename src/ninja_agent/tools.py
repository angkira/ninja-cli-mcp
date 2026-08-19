"""
MCP tool implementations for the Agent module.

The agent is an orchestrator that plans, analyzes, delegates, and reviews —
but never writes code itself. Code-writing is delegated to the coder module.
Analysis is delegated to the secretary module, and web research to the
researcher module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ninja_agent.models import (
    AgentAnalyzeRequest,
    AgentAnalyzeResult,
    AgentDelegateRequest,
    AgentDelegateResult,
    AgentPlanRequest,
    AgentPlanResult,
    AgentPlanStep,
    AgentReviewFinding,
    AgentReviewRequest,
    AgentReviewResult,
)
from ninja_common.logging_utils import get_logger
from ninja_common.rate_balancer import rate_balanced
from ninja_common.security import monitored


logger = get_logger(__name__)


class AgentToolExecutor:
    """Executor for agent MCP tools (planning, analysis, delegation, review)."""

    def __init__(self):
        """Initialize the agent tool executor."""
        self._coder = None
        self._secretary = None
        self._researcher = None

    def _get_coder(self):
        """Lazily import and return the coder tool executor."""
        if self._coder is None:
            from ninja_coder.tools import ToolExecutor as CoderToolExecutor

            self._coder = CoderToolExecutor()
        return self._coder

    def _get_secretary(self):
        """Lazily import and return the secretary tool executor."""
        if self._secretary is None:
            from ninja_secretary.tools import SecretaryToolExecutor

            self._secretary = SecretaryToolExecutor()
        return self._secretary

    def _get_researcher(self):
        """Lazily import and return the researcher tool executor."""
        if self._researcher is None:
            from ninja_researcher.tools import ResearchToolExecutor

            self._researcher = ResearchToolExecutor()
        return self._researcher

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def analyze(
        self, request: AgentAnalyzeRequest, client_id: str = "default"
    ) -> AgentAnalyzeResult:
        """
        Analyze a codebase by delegating to the secretary module.

        Args:
            request: Analysis request.
            client_id: Client identifier for rate limiting.

        Returns:
            Aggregated analysis result.
        """
        logger.info(f"Analyzing codebase at {request.repo_root} (client: {client_id})")
        secretary = self._get_secretary()

        try:
            from ninja_secretary.models import CodebaseReportRequest, FileSearchRequest

            report_result = await secretary.codebase_report(
                CodebaseReportRequest(repo_root=request.repo_root), client_id
            )

            findings: list[str] = []
            touched: list[str] = []

            if getattr(report_result, "report", None):
                findings.append(report_result.report[:2000])
            if getattr(report_result, "file_count", 0):
                findings.append(f"Analyzed {report_result.file_count} files total.")

            # Optionally narrow into a focus area via file search
            if request.focus:
                pattern = f"**/*{request.focus}*"
                search = await secretary.file_search(
                    FileSearchRequest(pattern=pattern, repo_root=request.repo_root), client_id
                )
                for m in getattr(search, "matches", []):
                    fp = getattr(m, "path", None) or getattr(m, "file_path", None)
                    if fp:
                        touched.append(fp)

            summary = f"Codebase at {request.repo_root} analyzed."
            if request.focus:
                summary += f" Focus: {request.focus}."

            return AgentAnalyzeResult(
                success=True,
                summary=summary,
                findings=findings,
                touched_paths=touched[:50],
            )
        except Exception as e:
            logger.error(f"Agent analyze failed: {e}", exc_info=True)
            return AgentAnalyzeResult(
                success=False,
                summary=f"Analysis failed: {e}",
                findings=[],
                touched_paths=[],
            )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def plan(
        self, request: AgentPlanRequest, client_id: str = "default"
    ) -> AgentPlanResult:
        """
        Decompose a task into an execution plan.

        Deterministic heuristic decomposition — no LLM call. Routes each step
        to the appropriate sub-agent (coder for code, researcher for research,
        secretary for analysis, self for review).

        Args:
            request: Planning request.
            client_id: Client identifier for rate limiting.

        Returns:
            A plan with ordered steps.
        """
        logger.info(f"Planning task: {request.task[:100]} (client: {client_id})")
        task_lower = request.task.lower()

        research_keywords = [
            "research", "search", "investigate", "find", "look up", "explore",
            "learn about", "what is", "how does", "compare", "latest",
        ]
        analysis_keywords = [
            "analy", "understand the code", "explain", "review", "map",
            "architecture", "structure", "assess", "audit",
        ]

        is_research = any(k in task_lower for k in research_keywords)
        is_analysis = any(k in task_lower for k in analysis_keywords) and not is_research

        steps: list[AgentPlanStep] = []

        if is_analysis:
            steps.append(
                AgentPlanStep(
                    title="Analyze codebase",
                    description="Inspect the relevant files and structure to understand the current state.",
                    delegate_to="secretary",
                    dependencies=[],
                )
            )
        elif is_research:
            steps.append(
                AgentPlanStep(
                    title="Gather information",
                    description="Search the web for current, accurate information on the topic.",
                    delegate_to="researcher",
                    dependencies=[],
                )
            )
        else:
            # Default: understand, then implement
            steps.append(
                AgentPlanStep(
                    title="Analyze context",
                    description="Inspect relevant files to understand the code that will be changed.",
                    delegate_to="secretary",
                    dependencies=[],
                )
            )

        # Implementation step (unless it's purely analysis)
        if not is_analysis:
            steps.append(
                AgentPlanStep(
                    title="Implement changes",
                    description=(
                        "Write or modify code to accomplish the task. Delegated to the coder "
                        "sub-agent, which owns all code-writing."
                    ),
                    delegate_to="coder",
                    dependencies=[0] if steps else [],
                )
            )

        # Final verification step
        steps.append(
            AgentPlanStep(
                title="Review and verify",
                description="Review the produced changes for correctness, quality, and completeness.",
                delegate_to="self",
                dependencies=list(range(len(steps))) if steps else [],
            )
        )

        # Optional step-count hint: cap the plan
        if request.steps_requested and request.steps_requested < len(steps):
            steps = steps[: request.steps_requested]

        reasoning = (
            "Heuristic decomposition based on task keywords. Code changes are always "
            "delegated to the coder sub-agent; analysis goes to the secretary; research "
            "goes to the researcher; final verification stays with the agent itself."
        )

        return AgentPlanResult(success=True, plan=steps, reasoning=reasoning)

    @rate_balanced(
        max_calls=30, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=30.0
    )
    @monitored
    async def delegate(
        self, request: AgentDelegateRequest, client_id: str = "default"
    ) -> AgentDelegateResult:
        """
        Delegate a subtask to the appropriate sub-agent.

        - 'coder': writes code via the coder module.
        - 'secretary': analyzes the codebase.
        - 'researcher': performs a web search.

        Args:
            request: Delegation request.
            client_id: Client identifier for rate limiting.

        Returns:
            Result summarizing what the sub-agent did.
        """
        logger.info(
            f"Delegating to '{request.delegate_to}': {request.subtask[:80]} (client: {client_id})"
        )

        try:
            if request.delegate_to == "coder":
                return await self._delegate_coder(request, client_id)
            elif request.delegate_to == "secretary":
                return await self._delegate_secretary(request, client_id)
            elif request.delegate_to == "researcher":
                return await self._delegate_researcher(request, client_id)
            else:
                return AgentDelegateResult(
                    success=False,
                    summary=f"Unknown delegate target: {request.delegate_to}",
                    delegate_to=request.delegate_to,
                )
        except Exception as e:
            logger.error(f"Delegate to {request.delegate_to} failed: {e}", exc_info=True)
            return AgentDelegateResult(
                success=False,
                summary=f"Delegation to {request.delegate_to} failed: {e}",
                delegate_to=request.delegate_to,
                raw_output="",
            )

    async def _delegate_coder(
        self, request: AgentDelegateRequest, client_id: str
    ) -> AgentDelegateResult:
        from ninja_coder.models import SimpleTaskRequest

        coder = self._get_coder()
        model_class = request.model_class or "smart"
        coder_request = SimpleTaskRequest(
            task=request.subtask,
            repo_root=request.repo_root,
            context_paths=request.context_paths,
            model_class=model_class,  # type: ignore[arg-type]
        )
        result = await coder.simple_task(coder_request, client_id)
        return AgentDelegateResult(
            success=result.status == "ok",
            summary=result.summary,
            delegate_to="coder",
            raw_output=result.notes or "",
        )

    async def _delegate_secretary(
        self, request: AgentDelegateRequest, client_id: str
    ) -> AgentDelegateResult:
        from ninja_secretary.models import CodebaseReportRequest

        secretary = self._get_secretary()
        result = await secretary.codebase_report(
            CodebaseReportRequest(repo_root=request.repo_root), client_id
        )
        return AgentDelegateResult(
            success=True,
            summary=getattr(result, "report", "")[:2000] or "Codebase analyzed.",
            delegate_to="secretary",
            raw_output="",
        )

    async def _delegate_researcher(
        self, request: AgentDelegateRequest, client_id: str
    ) -> AgentDelegateResult:
        from ninja_researcher.models import WebSearchRequest

        researcher = self._get_researcher()
        result = await researcher.web_search(
            WebSearchRequest(query=request.subtask), client_id
        )
        sources = getattr(result, "results", []) or []
        summary_lines = []
        for s in sources[:5]:
            title = getattr(s, "title", "") or getattr(s, "url", "")
            url = getattr(s, "url", "")
            summary_lines.append(f"- {title}: {url}")
        return AgentDelegateResult(
            success=True,
            summary="\n".join(summary_lines) or "Search completed, no results.",
            delegate_to="researcher",
            raw_output="",
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def review(
        self, request: AgentReviewRequest, client_id: str = "default"
    ) -> AgentReviewResult:
        """
        Review files without modifying them.

        Heuristic static analysis: long functions, empty except blocks, missing
        top-level docstrings. Never writes to disk.

        Args:
            request: Review request.
            client_id: Client identifier for rate limiting.

        Returns:
            Review findings and a summary.
        """
        logger.info(f"Reviewing {len(request.file_paths)} files (client: {client_id})")
        findings: list[AgentReviewFinding] = []
        root = Path(request.repo_root)

        for rel in request.file_paths:
            path = root / rel
            if not path.exists() or not path.is_file():
                findings.append(
                    AgentReviewFinding(
                        severity="warning",
                        file_path=rel,
                        message="File not found.",
                    )
                )
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")

            # Basic line count
            lines = text.splitlines()
            findings.extend(self._check_long_lines(rel, lines))

            # Python-specific static checks
            if rel.endswith(".py"):
                findings.extend(self._check_python(rel, text))

        summary = (
            f"Reviewed {len(request.file_paths)} files, "
            f"found {len(findings)} finding(s). No files modified."
        )

        return AgentReviewResult(success=True, findings=findings, summary=summary)

    def _check_long_lines(self, rel: str, lines: list[str]) -> list[AgentReviewFinding]:
        """Flag functions that are too long (rough heuristic via line blocks)."""
        # Track blank-line-delimited function-ish blocks
        findings: list[AgentReviewFinding] = []
        block_start = 1
        for i, line in enumerate(lines, start=1):
            if not line.strip() or (i > block_start and line[:1].isalnum()):
                length = i - block_start
                if length > 80:
                    findings.append(
                        AgentReviewFinding(
                            severity="info",
                            file_path=rel,
                            line=block_start,
                            message=(
                                f"Long block of {length} lines (starting line {block_start}); "
                                "consider splitting for readability."
                            ),
                        )
                    )
                block_start = i + 1
        return findings

    def _check_python(self, rel: str, text: str) -> list[AgentReviewFinding]:
        """Run Python-specific heuristic checks."""
        findings: list[AgentReviewFinding] = []
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            findings.append(
                AgentReviewFinding(
                    severity="critical",
                    file_path=rel,
                    line=e.lineno,
                    message=f"Syntax error: {e.msg}",
                )
            )
            return findings

        for node in ast.walk(tree):
            # Empty except blocks
            if isinstance(node, ast.ExceptHandler):
                if not node.body:
                    findings.append(
                        AgentReviewFinding(
                            severity="warning",
                            file_path=rel,
                            line=getattr(node, "lineno", None),
                            message="Empty except block - hides errors silently.",
                        )
                    )
                elif isinstance(node.body[0], ast.Pass):
                    findings.append(
                        AgentReviewFinding(
                            severity="warning",
                            file_path=rel,
                            line=getattr(node, "lineno", None),
                            message="except block only contains 'pass' - consider logging.",
                        )
                    )

            # Top-level functions missing docstrings
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.body and not (
                    isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    if not any(
                        isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                        for parent in _parents_of(tree, node)
                    ):
                        findings.append(
                            AgentReviewFinding(
                                severity="info",
                                file_path=rel,
                                line=node.lineno,
                                message=f"Function '{node.name}' has no docstring.",
                            )
                        )

        return findings


def _parents_of(tree: ast.AST, target: ast.AST) -> list[ast.AST]:
    """Return the parent nodes of a target within the tree."""
    parents: list[ast.AST] = []
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            if child is target:
                parents.append(node)
    return parents
