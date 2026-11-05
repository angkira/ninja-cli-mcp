"""Tests for the modern MCP surface: titles, annotations, outputSchema,
structuredContent, icons, server metadata, elicitation fallback.
"""

from __future__ import annotations

import asyncio
import json

import jsonschema

from ninja_common.mcp_meta import (
    dict_result,
    elicit_confirm,
    model_result,
    patch_resource_link,
    server_icon,
)


def _all_servers():
    from ninja_agent import server as agent_server
    from ninja_coder import server as coder_server
    from ninja_researcher import server as researcher_server
    from ninja_secretary import server as secretary_server

    return {
        "coder": coder_server,
        "researcher": researcher_server,
        "agent": agent_server,
        "secretary": secretary_server,
    }


def test_every_tool_has_title_annotations_schema_and_icon():
    """All tools advertise title, behavioral annotations, output schema, icon."""
    for name, mod in _all_servers().items():
        assert mod.TOOLS, f"{name} has no tools"
        for tool in mod.TOOLS:
            assert tool.title, f"{name}/{tool.name} missing title"
            assert tool.annotations is not None, f"{name}/{tool.name} missing annotations"
            assert tool.outputSchema is not None, f"{name}/{tool.name} missing outputSchema"
            assert tool.icons, f"{name}/{tool.name} missing icons"
            assert tool.icons[0].src.startswith("data:image/svg+xml,"), (
                f"{name}/{tool.name} icon is not an SVG data URI"
            )


def test_readonly_tools_marked():
    """Pure readers must carry readOnlyHint; writers must carry destructiveHint."""
    from ninja_coder import server as coder_server

    by_name = {t.name: t for t in coder_server.TOOLS}
    assert by_name["coder_branches_list"].annotations.readOnlyHint is True
    assert by_name["coder_branch_discard"].annotations.destructiveHint is True
    assert by_name["coder_branch_merge"].annotations.destructiveHint is True
    assert by_name["coder_simple_task"].annotations.destructiveHint is True


def test_structured_results_validate_against_tool_schemas():
    """Real model payloads validate against their tool's declared outputSchema."""
    from ninja_agent.models import AgentReviewResult
    from ninja_coder.models import SimpleTaskResult
    from ninja_researcher.models import FactCheckResult
    from ninja_secretary.models import AnalyseFileResult

    samples = {
        "coder_simple_task": SimpleTaskResult(status="ok", summary="s"),
        "researcher_fact_check": FactCheckResult(
            status="uncertain", claim="c", verdict="v", sources=[], confidence=0.0
        ),
        "agent_review": AgentReviewResult(success=True, findings=[], summary="x"),
        "secretary_analyse_file": AnalyseFileResult(status="ok", result={}),
    }
    for mod_name, mod in _all_servers().items():
        by_name = {t.name: t for t in mod.TOOLS}
        for tool_name, sample in samples.items():
            tool = by_name.get(tool_name)
            if tool is None:
                continue
            texts, structured = model_result(sample)
            assert texts and texts[0].type == "text"
            # Same JSON in text and structured form.
            assert json.loads(texts[0].text) == structured
            jsonschema.validate(structured, tool.outputSchema)


def test_dict_result_validates():
    """Dict payloads validate against the generic object schema."""
    texts, structured = dict_result({"job_id": "x", "status": "working"})
    assert texts[0].type == "text"
    jsonschema.validate(structured, {"type": "object"})


def test_patch_resource_link(tmp_path):
    """Patch artifacts produce file:// resource links; missing files do not."""
    assert patch_resource_link(None) is None
    assert patch_resource_link("/nonexistent/patch.diff") is None
    patch = tmp_path / "out.patch"
    patch.write_text("diff --git a b\n")
    link = patch_resource_link(str(patch))
    assert link is not None
    assert str(link.uri).startswith("file://")
    assert link.mimeType == "text/x-patch"
    assert link.size and link.size > 0


def test_server_icon_is_svg_data_uri():
    icon = server_icon("coder")
    assert icon.mimeType == "image/svg+xml"
    assert icon.src.startswith("data:image/svg+xml,")
    assert icon.sizes == ["64x64"]


def test_server_metadata_present():
    """Servers advertise website and brand icons."""
    from ninja_agent import server as agent_server
    from ninja_coder import server as coder_server
    from ninja_researcher import server as researcher_server
    from ninja_secretary import server as secretary_server

    for mod in (agent_server, coder_server, researcher_server, secretary_server):
        srv = mod.create_server()
        # Server carries website + icon via constructor kwargs.
        assert srv.website_url == "https://github.com/angkira/ninja-cli-mcp"
        assert srv.icons, f"{mod.__name__} server has no icons"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_elicit_confirm_no_session_capability():
    """Without elicit support the helper falls back to None (refuse path)."""

    class NoElicit:
        pass

    assert _run(elicit_confirm(NoElicit(), "Delete?")) is None
    assert _run(elicit_confirm(None, "Delete?")) is None


def test_elicit_confirm_accept_and_decline():
    """Accepted confirmations pass True; declines pass False."""

    class FakeResult:
        def __init__(self, action, content):
            self.action = action
            self.content = content

    class AcceptSession:
        async def elicit_form(self, message, schema, related_request_id=None):
            assert "confirm" in schema["required"]
            return FakeResult("accept", {"confirm": True})

    class DeclineSession:
        async def elicit_form(self, message, schema, related_request_id=None):
            return FakeResult("decline", {})

    class BoomSession:
        async def elicit_form(self, message, schema, related_request_id=None):
            raise RuntimeError("no client back-channel")

    assert _run(elicit_confirm(AcceptSession(), "Delete branch?")) is True
    assert _run(elicit_confirm(DeclineSession(), "Delete branch?")) is False
    assert _run(elicit_confirm(BoomSession(), "Delete branch?")) is None


def test_is_unmerged_refusal():
    """The discard elicitation trigger matches git's refusal wording."""
    from ninja_coder.server import _is_unmerged_refusal

    assert _is_unmerged_refusal("error: The branch 'x' is not fully merged.")
    assert _is_unmerged_refusal("refusing to delete unmerged work")
    assert not _is_unmerged_refusal("Deleted branch ninja/x")
    assert not _is_unmerged_refusal(None)
