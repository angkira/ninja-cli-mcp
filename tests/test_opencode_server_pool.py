"""Tests for OpenCode serve-pool event handling."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ninja_coder.strategies.opencode_server_pool import (
    OpenCodeServerPool,
    ServerInstance,
    SSEListener,
)


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
