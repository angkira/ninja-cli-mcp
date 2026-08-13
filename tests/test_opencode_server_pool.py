"""Tests for OpenCode serve-pool event handling."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from ninja_coder.strategies.opencode_server_pool import (
    OpenCodeServerPool,
    ServerInstance,
    SSEListener,
)


class FakeResp:
    def __init__(self, status: int, json_payload: object) -> None:
        self.status = status
        self._json_payload = json_payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._json_payload

    async def text(self):
        return json.dumps(self._json_payload) if isinstance(self._json_payload, dict) else str(self._json_payload)

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


class FakeHttp:
    """aiohttp stand-in recording calls and replaying canned (status, payload) responses."""

    def __init__(self, responses: list[tuple[int, object]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url: str, json: object | None = None, timeout=None) -> FakeResp:
        self.calls.append({"method": "post", "url": url, "json": json})
        status, payload = self.responses.pop(0)
        return FakeResp(status, payload)

    def get(self, url: str, params=None, timeout=None) -> FakeResp:
        self.calls.append({"method": "get", "url": url, "params": params})
        status, payload = self.responses.pop(0)
        return FakeResp(status, payload)


@pytest.mark.asyncio
async def test_sse_listener_routes_top_level_session_id_events() -> None:
    """OpenCode emits sessionID at the top level in newer event schemas."""
    listener = SSEListener("http://127.0.0.1:1")
    queue = await listener.subscribe("ses_test")

    await listener._dispatch_event({"type": "step_finish", "sessionID": "ses_test"})

    assert await asyncio.wait_for(queue.get(), timeout=1) == {
        "type": "step_finish",
        "sessionID": "ses_test",
    }


@pytest.mark.asyncio
async def test_wait_for_idle_handles_tool_use_and_step_finish_events() -> None:
    """Newer OpenCode events report writes as tool_use and completion as step_finish."""
    pool = OpenCodeServerPool()
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(
        {
            "type": "tool_use",
            "sessionID": "ses_test",
            "part": {
                "type": "tool",
                "tool": "write",
                "state": {
                    "status": "completed",
                    "input": {
                        "filePath": "/tmp/repo/CREATED.txt",
                        "content": "created",
                    },
                },
            },
        }
    )
    await queue.put(
        {
            "type": "step_finish",
            "sessionID": "ses_test",
            "part": {"reason": "stop"},
        }
    )
    inst = ServerInstance(
        port=20000,
        process=SimpleNamespace(poll=lambda: None),
        repo_root="/tmp/repo",
    )

    result = await pool._wait_for_idle(queue, inst, "ses_test", timeout=1)

    assert result.success is True
    assert result.files_changed == ["CREATED.txt"]


def test_split_model_parses_provider_and_model_id() -> None:
    """Model strings are split as provider prefix + rest of the id."""
    assert OpenCodeServerPool._split_model("openrouter/deepseek/deepseek-v4-flash-0731") == (
        "openrouter",
        "deepseek/deepseek-v4-flash-0731",
    )
    assert OpenCodeServerPool._split_model("zai-coding-plan/glm-5.2") == (
        "zai-coding-plan",
        "glm-5.2",
    )
    assert OpenCodeServerPool._split_model("nonslash") is None
    assert OpenCodeServerPool._split_model(None) is None
    assert OpenCodeServerPool._split_model("") is None


def test_build_summary_formats_file_lists() -> None:
    """Summary truncates long file lists and handles empty input."""
    assert OpenCodeServerPool._build_summary([]) == (
        "Task completed (no file changes detected)"
    )
    assert OpenCodeServerPool._build_summary(["a.py"]) == "Modified 1 file(s): a.py"
    long = [f"f{i}.py" for i in range(7)]
    summary = OpenCodeServerPool._build_summary(long)
    assert "f5.py" not in summary or "and 2 more" in summary


@pytest.mark.asyncio
async def test_create_session_uses_v2_api_endpoint_when_available() -> None:
    """Newer opencode exposes /api/session which returns data.id."""
    http = FakeHttp(
        [
            (200, {"data": {"id": "ses_v2"}}),
        ]
    )
    inst = ServerInstance(
        port=20000,
        process=SimpleNamespace(poll=lambda: None),
        repo_root="/tmp/repo",
    )

    session_id = await OpenCodeServerPool()._create_session(http, inst, model="openrouter/deepseek/deepseek-v4-flash-0731")

    assert session_id == "ses_v2"
    assert http.calls[0]["method"] == "post"
    assert http.calls[0]["url"].endswith("/api/session")
    assert http.calls[0]["json"]["model"]["providerID"] == "openrouter"
    assert http.calls[0]["json"]["model"]["id"] == "deepseek/deepseek-v4-flash-0731"


@pytest.mark.asyncio
async def test_create_session_falls_back_to_legacy_endpoint() -> None:
    """When /api/session is missing, fall back to the legacy /session endpoint."""
    http = FakeHttp(
        [
            (404, {}),
            (200, {"id": "ses_legacy"}),
        ]
    )
    pool = OpenCodeServerPool()
    inst = ServerInstance(
        port=20000,
        process=SimpleNamespace(poll=lambda: None),
        repo_root="/tmp/repo",
    )

    session_id = await pool._create_session(http, inst)

    assert session_id == "ses_legacy"
    assert http.calls[0]["url"].endswith("/api/session")
    assert http.calls[1]["url"].endswith("/session")


@pytest.mark.asyncio
async def test_send_prompt_includes_model_ref() -> None:
    """prompt_async body must carry model when provided."""
    http = FakeHttp(
        [
            (200, {}),
        ]
    )
    pool = OpenCodeServerPool()
    inst = ServerInstance(
        port=20000,
        process=SimpleNamespace(poll=lambda: None),
        repo_root="/tmp/repo",
    )

    await pool._send_prompt(http, inst, "ses_test", "do it", model="openrouter/deepseek/deepseek-v4-flash-0731")

    assert http.calls[0]["json"]["model"]["providerID"] == "openrouter"
    assert http.calls[0]["json"]["model"]["modelID"] == "deepseek/deepseek-v4-flash-0731"


@pytest.mark.asyncio
async def test_fetch_vcs_diff_parses_files_and_returns_raw() -> None:
    """/vcs/diff returns authoritative files changed plus raw patches."""
    http = FakeHttp(
        [
            (
                200,
                [
                    {"file": "/tmp/repo/a.py", "patch": "---", "additions": 5, "deletions": 2, "status": "modified"},
                    {"file": "/tmp/repo/b.py", "patch": "+++", "additions": 1, "deletions": 0, "status": "added"},
                ],
            )
        ]
    )
    pool = OpenCodeServerPool()
    inst = ServerInstance(
        port=20000,
        process=SimpleNamespace(poll=lambda: None),
        repo_root="/tmp/repo",
    )

    files, raw = await pool._fetch_vcs_diff(http, inst)

    assert files == ["a.py", "b.py"]
    assert raw is not None and len(raw) == 2
    assert http.calls[0]["params"] == {"mode": "git"}


@pytest.mark.asyncio
async def test_fetch_vcs_diff_handles_api_error_gracefully() -> None:
    """A non-git repo or API error must degrade to empty, not raise."""
    http = FakeHttp(
        [
            (400, [None]),
        ]
    )
    pool = OpenCodeServerPool()
    inst = ServerInstance(
        port=20000,
        process=SimpleNamespace(poll=lambda: None),
        repo_root="/tmp/repo",
    )

    files, raw = await pool._fetch_vcs_diff(http, inst)

    assert files == []
    assert raw == []
