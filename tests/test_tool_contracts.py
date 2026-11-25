"""Contract tests: declared tool input schemas must match their request models.

These guard the class of drift found in battle testing: a tool whose JSON
schema advertises a field as optional while the pydantic request model requires
it (or vice versa). A conforming client trusts the schema, so any mismatch turns
a valid-looking call into a framework error.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client, types

from ninja_agent.models import (
    AgentAnalyzeRequest,
    AgentDistillLogsRequest,
    AgentExecCommandRequest,
    AgentExecPipelineRequest,
    AgentJobsOverviewRequest,
    AgentProcessesRequest,
    AgentReviewRequest,
    AgentRunAndDiagnoseRequest,
    AgentTailLogsRequest,
)
from ninja_coder.models import (
    BranchDiscardRequest,
    BranchListRequest,
    BranchMergeRequest,
    GetAgentsRequest,
    MultiAgentTaskRequest,
    ParallelPlanRequest,
    QueryLogsRequest,
    SequentialPlanRequest,
    SimpleTaskRequest,
)
from ninja_researcher.models import (
    ArxivSearchRequest,
    DeepResearchBatchRequest,
    DeepResearchRequest,
    FactCheckRequest,
    GenerateReportRequest,
    PaperFetchRequest,
    QuickResearchRequest,
    SummarizeSourcesRequest,
)
from ninja_secretary.models import (
    AnalyseFileRequest,
    CodebaseReportRequest,
    DocumentSummaryRequest,
    FileSearchRequest,
    SessionReportRequest,
    UpdateDocRequest,
)


if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import BaseModel
    from pytest import MonkeyPatch


SERVER_MODULES: tuple[str, ...] = (
    "ninja_coder.server",
    "ninja_researcher.server",
    "ninja_secretary.server",
    "ninja_agent.server",
)

#: tool name -> request model the dispatch path constructs from the arguments.
#: ``coder_submit_*`` reuse the synchronous tool's model.
REQUEST_MODELS: dict[str, dict[str, type[BaseModel]]] = {
    "ninja_coder.server": {
        "coder_simple_task": SimpleTaskRequest,
        "coder_execute_plan_sequential": SequentialPlanRequest,
        "coder_execute_plan_parallel": ParallelPlanRequest,
        "coder_get_agents": GetAgentsRequest,
        "coder_multi_agent_task": MultiAgentTaskRequest,
        "coder_query_logs": QueryLogsRequest,
        "coder_branches_list": BranchListRequest,
        "coder_branch_merge": BranchMergeRequest,
        "coder_branch_discard": BranchDiscardRequest,
        "coder_submit_simple": SimpleTaskRequest,
        "coder_submit_sequential": SequentialPlanRequest,
        "coder_submit_parallel": ParallelPlanRequest,
    },
    "ninja_researcher.server": {
        "researcher_quick_research": QuickResearchRequest,
        "researcher_deep_research": DeepResearchRequest,
        "researcher_generate_report": GenerateReportRequest,
        "researcher_fact_check": FactCheckRequest,
        "researcher_summarize_sources": SummarizeSourcesRequest,
        "researcher_arxiv_search": ArxivSearchRequest,
        "researcher_paper_fetch": PaperFetchRequest,
        "researcher_deep_research_batch": DeepResearchBatchRequest,
    },
    "ninja_secretary.server": {
        "secretary_analyse_file": AnalyseFileRequest,
        "secretary_file_search": FileSearchRequest,
        "secretary_codebase_report": CodebaseReportRequest,
        "secretary_document_summary": DocumentSummaryRequest,
        "secretary_update_documentation": UpdateDocRequest,
        "secretary_session_report": SessionReportRequest,
    },
    "ninja_agent.server": {
        "agent_exec_command": AgentExecCommandRequest,
        "agent_tail_logs": AgentTailLogsRequest,
        "agent_processes": AgentProcessesRequest,
        "agent_jobs_overview": AgentJobsOverviewRequest,
        "agent_analyze": AgentAnalyzeRequest,
        "agent_review": AgentReviewRequest,
        "agent_run_and_diagnose": AgentRunAndDiagnoseRequest,
        "agent_exec_pipeline": AgentExecPipelineRequest,
        "agent_distill_logs": AgentDistillLogsRequest,
    },
}

#: Tools whose arguments are read directly by the handler, with no request
#: model. Each is asserted explicitly instead of being skipped silently.
NO_REQUEST_MODEL: dict[str, frozenset[str]] = {
    "ninja_coder.server": frozenset(
        {
            # job_id is a required string, checked by hand in _handle_job_tool
            "coder_job_status",
            "coder_job_result",
            "coder_job_cancel",
            # cursor/limit are optional and passed straight to JobManager
            "coder_jobs_list",
        }
    ),
}


@pytest.fixture(autouse=True)
def _task_store_path(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Keep the durable task store and job rows out of the developer's HOME."""
    monkeypatch.setenv("NINJA_TASKS_DB", str(tmp_path / "tasks.db"))


def _tools(module_name: str) -> dict[str, types.Tool]:
    module = importlib.import_module(module_name)
    return {tool.name: tool for tool in module.TOOLS}


def _required(schema: dict[str, Any]) -> set[str]:
    return set(schema.get("required", []))


def _text(result: types.CallToolResult) -> str:
    return " ".join(block.text for block in result.content if isinstance(block, types.TextContent))


# --------------------------------------------------------------------------- #
# (1) Structural guard: schema required == model required
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("module_name", SERVER_MODULES)
def test_tool_schema_required_matches_request_model(module_name: str) -> None:
    """Every declared schema agrees with its request model on required fields."""
    tools = _tools(module_name)
    mapping = REQUEST_MODELS[module_name]
    exceptions = NO_REQUEST_MODEL.get(module_name, frozenset())

    # Completeness: a new tool must be mapped or explicitly excepted, so this
    # guard cannot silently stop covering it.
    assert set(tools) == set(mapping) | set(exceptions), (
        f"{module_name}: unmapped tools {sorted(set(tools) - set(mapping) - set(exceptions))}"
    )

    mismatches: list[str] = []
    for name, model in mapping.items():
        schema_required = _required(tools[name].input_schema)
        model_required = {
            field_name for field_name, field in model.model_fields.items() if field.is_required()
        }
        if schema_required != model_required:
            mismatches.append(
                f"{name}: schema required={sorted(schema_required)} "
                f"model required={sorted(model_required)}"
            )

    assert not mismatches, "\n".join(mismatches)


def test_tools_without_request_models_declare_their_arguments_honestly() -> None:
    """Hand-validated job tools advertise exactly what the handler enforces."""
    tools = _tools("ninja_coder.server")

    for name in ("coder_job_status", "coder_job_result", "coder_job_cancel"):
        schema = tools[name].input_schema
        assert _required(schema) == {"job_id"}
        assert schema["properties"]["job_id"]["type"] == "string"

    jobs_list = tools["coder_jobs_list"].input_schema
    assert _required(jobs_list) == set()
    assert set(jobs_list["properties"]) == {"cursor", "limit"}


# --------------------------------------------------------------------------- #
# (2) Framework failures are is_error=True
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("module_name", SERVER_MODULES)
async def test_unknown_tool_is_a_framework_error(module_name: str) -> None:
    module = importlib.import_module(module_name)
    async with Client(module.create_server()) as client:
        result = await client.call_tool("ninja_no_such_tool", {})

    assert result.is_error is True
    assert "ninja_no_such_tool" in _text(result)
    # The JSON body still carries the failure for payload parsers.
    assert result.structured_content is not None


MISSING_ARGUMENT_CALLS: dict[str, tuple[str, dict[str, Any]]] = {
    "ninja_coder.server": ("coder_simple_task", {}),
    "ninja_researcher.server": ("researcher_quick_research", {}),
    "ninja_secretary.server": ("secretary_file_search", {"pattern": "x"}),
    "ninja_agent.server": ("agent_exec_command", {}),
}


@pytest.mark.parametrize("module_name", SERVER_MODULES)
async def test_missing_required_argument_is_a_framework_error(module_name: str) -> None:
    module = importlib.import_module(module_name)
    name, arguments = MISSING_ARGUMENT_CALLS[module_name]
    async with Client(module.create_server()) as client:
        result = await client.call_tool(name, arguments)

    assert result.is_error is True
    assert result.structured_content is not None


# --------------------------------------------------------------------------- #
# (3) Business-logic envelopes stay is_error=False
# --------------------------------------------------------------------------- #


async def test_business_error_envelope_is_not_marked_as_tool_error() -> None:
    """An unknown job id is a normal tool answer, not a framework failure."""
    async with Client(importlib.import_module("ninja_coder.server").create_server()) as client:
        result = await client.call_tool("coder_job_status", {"job_id": "no-such-job"})

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["error_type"] == "UnknownJob"


# --------------------------------------------------------------------------- #
# (4) Wrong-typed job_id is rejected, not coerced
# --------------------------------------------------------------------------- #


async def test_job_id_must_be_a_string() -> None:
    async with Client(importlib.import_module("ninja_coder.server").create_server()) as client:
        result = await client.call_tool("coder_job_status", {"job_id": 12345})

    assert result.is_error is True
    assert "job_id must be a string" in _text(result)


# --------------------------------------------------------------------------- #
# (5) secretary_file_search: schema and runtime agree about repo_root
# --------------------------------------------------------------------------- #


async def test_file_search_requires_repo_root_at_the_framework_level() -> None:
    async with Client(importlib.import_module("ninja_secretary.server").create_server()) as client:
        missing = await client.call_tool("secretary_file_search", {"pattern": "x"})
        valid = await client.call_tool("secretary_file_search", {"pattern": "x", "repo_root": "."})

    assert missing.is_error is True
    assert "repo_root" in _text(missing)
    assert valid.is_error is False
