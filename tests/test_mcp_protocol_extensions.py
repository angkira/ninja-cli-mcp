"""The 2026-07-28 Skills and Tasks extensions, wired into the four servers.

Each ninja server is built on the lowlevel ``Server``, so the extensions are
composed by hand (:mod:`ninja_common.mcp_ext.wiring`). These tests drive the
*real* server factories through an in-memory ``Client`` and assert the parts a
peer can observe:

* a modern client sees both extensions advertised, gets working
  ``resources/list`` / ``resources/read``, and reads a bogus skill URI as
  invalid params rather than a crash;
* a legacy client keeps the synchronous surface — tools list, a read-only tool
  call, and ``skills/list`` answering METHOD_NOT_FOUND;
* a task-enabled tool polled through ``TasksClient`` lands on the same result
  the synchronous call returns.

The read-only tools are stubbed or pointed at a temporary file so no model,
network call or subprocess is involved.
"""

from __future__ import annotations

import base64
import importlib
from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client, types
from mcp.client import advertise
from pydantic import Field, TypeAdapter

from ninja_agent.models import AgentExecPipelineResult
from ninja_coder.models import GetAgentsResult
from ninja_common.mcp_ext.files import FILES_ENABLE_ENV, FilesExtension, sha256_digest
from ninja_common.mcp_ext.protocol import (
    FILES_EXTENSION_ID,
    SKILLS_EXTENSION_ID,
    TASKS_EXTENSION_ID,
)
from ninja_common.mcp_ext.tasks_client import TasksClient
from ninja_researcher.models import QuickResearchResult


if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


MODULES = (
    "ninja_coder.server",
    "ninja_researcher.server",
    "ninja_secretary.server",
    "ninja_agent.server",
)

METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

_DICT_ADAPTER: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])


class _RawRequest(types.Request[dict[str, Any], str]):
    """A request for a method the client SDK has no typed helper for."""

    params: dict[str, Any] = Field(default_factory=dict)


@pytest.fixture(autouse=True)
def _task_store_path(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Keep the durable task store out of the developer's ``~/.ninja``.

    The Files extension is experimental and off by default; clear any value a
    developer exported so the advertised surface is deterministic.
    """
    monkeypatch.setenv("NINJA_TASKS_DB", str(tmp_path / "tasks.db"))
    monkeypatch.delenv(FILES_ENABLE_ENV, raising=False)


def create_server(module: str) -> Any:
    """Build the server the *module* entry point would run."""
    return importlib.import_module(module).create_server()


# --------------------------------------------------------------------------- #
# Cheap read-only tools
# --------------------------------------------------------------------------- #


class _StubCoderExecutor:
    """``ToolExecutor`` stand-in: listing agents needs no model or subprocess."""

    async def get_agents(self, _request: Any, client_id: str = "default") -> GetAgentsResult:
        return GetAgentsResult(status="ok", total_agents=0, agents=[])


class _StubResearcherExecutor:
    """``ResearchToolExecutor`` stand-in: a quick answer without the network."""

    async def quick_research(self, request: Any, client_id: str = "default") -> QuickResearchResult:
        return QuickResearchResult(status="ok", query=request.query, answer="stubbed")


def stub_expensive_tools(module: str, monkeypatch: MonkeyPatch) -> None:
    """Replace network/model work for the modules whose read-only tool needs it."""
    if module == "ninja_coder.server":
        monkeypatch.setattr("ninja_coder.server.get_executor", _StubCoderExecutor)
    elif module == "ninja_researcher.server":
        monkeypatch.setattr("ninja_researcher.server.get_executor", _StubResearcherExecutor)


READ_ONLY_CALLS: dict[str, tuple[str, dict[str, Any]]] = {
    "ninja_coder.server": ("coder_get_agents", {}),
    "ninja_researcher.server": ("researcher_quick_research", {"query": "ping"}),
    "ninja_agent.server": ("agent_processes", {}),
}


# --------------------------------------------------------------------------- #
# (a) Capabilities
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("module", MODULES)
async def test_modern_client_sees_both_extensions(module: str) -> None:
    async with Client(create_server(module)) as client:
        advertised = client.server_capabilities.extensions or {}

    assert SKILLS_EXTENSION_ID in advertised
    assert TASKS_EXTENSION_ID in advertised


# --------------------------------------------------------------------------- #
# (b) Resources
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("module", MODULES)
async def test_modern_client_lists_and_reads_resources(module: str) -> None:
    async with Client(create_server(module)) as client:
        listed = await client.list_resources()
        # Every module ships a packaged skill bundle, so the handlers serve a
        # non-empty catalog of skill files.
        assert listed.resources
        assert all(resource.uri.startswith("skill://") for resource in listed.resources)
        assert any(resource.uri.endswith("/SKILL.md") for resource in listed.resources)

        with pytest.raises(Exception) as excinfo:
            await client.read_resource("skill://nope/SKILL.md")

    error = excinfo.value
    assert getattr(error, "code", None) == INVALID_PARAMS
    assert "unknown resource: skill://nope/SKILL.md" in str(error)


async def test_packaged_skill_is_served_through_resources(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """``NINJA_SKILLS_DIR`` bundles are published, readable and listable."""
    skills = tmp_path / "skills"
    (skills / "greeter").mkdir(parents=True)
    (skills / "greeter" / "SKILL.md").write_text(
        "---\nname: greeter\ndescription: Greets people\n---\n\n# Greeter\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NINJA_SKILLS_DIR", str(skills))

    async with Client(
        create_server("ninja_agent.server"),
        extensions=[advertise(SKILLS_EXTENSION_ID)],
    ) as client:
        listed = await client.list_resources()
        assert [resource.uri for resource in listed.resources] == ["skill://greeter/SKILL.md"]

        read = await client.read_resource("skill://greeter/SKILL.md")
        contents = read.contents[0]
        assert contents.mime_type == "text/markdown"
        assert contents.text is not None
        assert "# Greeter" in contents.text

        raw = await client.session.send_request(_RawRequest(method="skills/list"), _DICT_ADAPTER)
        assert [skill["uri"] for skill in raw["skills"]] == ["skill://greeter/SKILL.md"]


# --------------------------------------------------------------------------- #
# (c) Legacy clients keep the synchronous surface
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("module", MODULES)
async def test_legacy_client_keeps_synchronous_surface(
    module: str, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    stub_expensive_tools(module, monkeypatch)
    server = create_server(module)

    async with Client(server, mode="legacy") as client:
        tools = await client.list_tools()
        assert tools.tools, f"{module} exposed no tools"

        if module == "ninja_secretary.server":
            target = tmp_path / "sample.py"
            target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            name, arguments = "secretary_analyse_file", {"file_path": str(target)}
        else:
            name, arguments = READ_ONLY_CALLS[module]

        result = await client.call_tool(name, arguments)
        assert result.is_error is False
        assert result.content

        with pytest.raises(Exception) as excinfo:
            await client.session.send_request(_RawRequest(method="skills/list"), _DICT_ADAPTER)

    assert getattr(excinfo.value, "code", None) == METHOD_NOT_FOUND


# --------------------------------------------------------------------------- #
# (d) Tasks round-trip on the cheapest server
# --------------------------------------------------------------------------- #


async def _stub_pipeline(
    _self: Any, _request: Any, client_id: str = "default"
) -> AgentExecPipelineResult:
    """Instant pipeline result: no shell, no timeout, deterministic."""
    return AgentExecPipelineResult(success=True, summary="stubbed pipeline")


async def test_task_augmented_call_completes_with_the_synchronous_result(
    monkeypatch: MonkeyPatch,
) -> None:
    """A declaring client gets a task handle that resolves to the real result."""
    monkeypatch.setattr("ninja_agent.tools.AgentToolExecutor.exec_pipeline", _stub_pipeline)
    arguments = {"steps": [{"command": "true"}], "repo_root": "/tmp"}

    # Baseline: the synchronous surface a non-declaring client keeps.
    async with Client(create_server("ninja_agent.server")) as plain_client:
        sync_result = await plain_client.call_tool("agent_exec_pipeline", arguments)
    assert sync_result.is_error is False
    assert sync_result.structured_content == {
        "success": True,
        "summary": "stubbed pipeline",
        "total_duration_seconds": 0.0,
        "steps": [],
    }

    # Same tool, task-enabled client: the claim is created and polled to
    # ``completed`` by ``TasksClient`` before ``call_tool`` returns.
    tasks_client = TasksClient(poll_interval_ms=10, timeout_seconds=30)
    async with Client(
        create_server("ninja_agent.server"),
        extensions=[tasks_client],
    ) as client:
        assert TASKS_EXTENSION_ID in (client.server_capabilities.extensions or {})
        result = await client.call_tool("agent_exec_pipeline", arguments)

    assert result.is_error is False
    assert result.structured_content == sync_result.structured_content
    assert result.content[0].text == sync_result.content[0].text


async def test_task_handle_is_returned_before_the_work_finishes(
    monkeypatch: MonkeyPatch,
) -> None:
    """An in-flight task answers ``resultType: "task"`` and ``tasks/get`` sees it."""
    monkeypatch.setattr("ninja_agent.tools.AgentToolExecutor.exec_pipeline", _stub_pipeline)
    arguments = {"steps": [{"command": "true"}], "repo_root": "/tmp"}

    async with Client(
        create_server("ninja_agent.server"),
        extensions=[advertise(TASKS_EXTENSION_ID)],
    ) as client:
        # ``advertise`` declares the extension without claiming task results,
        # so the raw envelope reaches the caller instead of being polled.
        created = await client.session.send_request(
            _RawRequest(
                method="tools/call",
                params={"name": "agent_exec_pipeline", "arguments": arguments},
            ),
            _DICT_ADAPTER,
        )
        assert created["resultType"] == "task"
        task_id = created["taskId"]

        fetched = await client.session.send_request(
            _RawRequest(method="tasks/get", params={"taskId": task_id}),
            _DICT_ADAPTER,
        )

    assert fetched["taskId"] == task_id
    assert fetched["status"] in {"working", "completed"}


# --------------------------------------------------------------------------- #
# (e) Files extension (experimental, opt-in, secretary only)
# --------------------------------------------------------------------------- #

INGEST_FILE_TOOL = "secretary_ingest_file"
FILE_BYTES = b"hello, files extension\n"
FILE_B64 = base64.b64encode(FILE_BYTES).decode("ascii")


def file_argument(**overrides: Any) -> dict[str, Any]:
    """A well-formed inline file argument for the ingest tool."""
    argument: dict[str, Any] = {
        "id": "file-1",
        "name": "greeting.txt",
        "mimeType": "text/plain",
        "size": len(FILE_BYTES),
        "digest": {"algorithm": "sha-256", "value": sha256_digest(FILE_BYTES)},
        "data": FILE_B64,
    }
    argument.update(overrides)
    return argument


async def test_files_extension_is_off_by_default() -> None:
    """No flag: neither the capability nor the tool is advertised."""
    async with Client(create_server("ninja_secretary.server")) as client:
        advertised = client.server_capabilities.extensions or {}
        listed = await client.list_tools()

    assert FILES_EXTENSION_ID not in advertised
    assert INGEST_FILE_TOOL not in {tool.name for tool in listed.tools}


async def test_files_extension_is_advertised_and_ingests_inline_data(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(FILES_ENABLE_ENV, "1")

    async with Client(create_server("ninja_secretary.server")) as client:
        advertised = client.server_capabilities.extensions or {}
        listed = await client.list_tools()
        tools = {tool.name: tool for tool in listed.tools}

        assert advertised[FILES_EXTENSION_ID] == {
            "maxInlineBytes": FilesExtension().max_inline_bytes
        }
        assert INGEST_FILE_TOOL in tools

        schema = tools[INGEST_FILE_TOOL].input_schema
        file_schema = schema["properties"]["file"]
        assert schema["required"] == ["file"]
        assert file_schema["x-mcp-file"] == {
            "accept": ["application/pdf", "text/csv", "text/plain", "image/png", "image/jpeg"],
            "maxSize": FilesExtension().max_inline_bytes,
        }
        annotations = tools[INGEST_FILE_TOOL].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
        assert annotations.idempotent_hint is True
        assert annotations.open_world_hint is False

        result = await client.call_tool(INGEST_FILE_TOOL, {"file": file_argument()})

    assert result.is_error is False
    assert result.structured_content == {
        "name": "greeting.txt",
        "mime_type": "text/plain",
        "size": len(FILE_BYTES),
        "digest": sha256_digest(FILE_BYTES),
        "first_bytes_hex": FILE_BYTES[:32].hex(),
    }


async def test_files_ingest_rejects_a_bad_file_without_echoing_data(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(FILES_ENABLE_ENV, "1")

    async with Client(create_server("ninja_secretary.server")) as client:
        result = await client.call_tool(
            INGEST_FILE_TOOL,
            {"file": file_argument(digest={"algorithm": "sha-256", "value": sha256_digest(b"x")})},
        )

    assert result.is_error is True
    text = " ".join(block.text for block in result.content if isinstance(block, types.TextContent))
    assert "digest mismatch" in text
    assert FILE_B64 not in text
    assert result.structured_content is None
