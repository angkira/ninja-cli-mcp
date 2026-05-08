"""
Tests for Bug 1 (ClosedResourceError crash) and Bug 2 (snippet/content/description key).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# Ensure src/ is on sys.path when run directly
_root = Path(__file__).parent.parent
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))

from ninja_researcher.models import GenerateReportRequest  # noqa: E402
from ninja_researcher.tools import ResearchToolExecutor, reset_executor  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_executor() -> ResearchToolExecutor:
    reset_executor()
    return ResearchToolExecutor()


async def _generate(sources: list[dict[str, Any]], report_type: str = "summary") -> str:
    executor = make_executor()
    request = GenerateReportRequest(topic="Test", sources=sources, report_type=report_type)
    result = await executor.generate_report(request)
    return result.report


# ---------------------------------------------------------------------------
# Bug 2 — content-key tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_report_accepts_content_key() -> None:
    """Bug 2: 'content' key should be used when 'snippet' is absent."""
    report = await _generate([{"url": "https://x.com", "title": "T", "content": "hello world"}])
    assert "hello world" in report
    assert "No description available" not in report


@pytest.mark.asyncio
async def test_generate_report_accepts_snippet_key() -> None:
    """Regression: existing 'snippet' key must keep working."""
    report = await _generate(
        [{"url": "https://x.com", "title": "T", "snippet": "hello from snippet"}]
    )
    assert "hello from snippet" in report
    assert "No description available" not in report


@pytest.mark.asyncio
async def test_generate_report_accepts_description_key() -> None:
    """Bug 2: 'description' key should be used when snippet/content are absent."""
    report = await _generate(
        [{"url": "https://x.com", "title": "T", "description": "hello from description"}]
    )
    assert "hello from description" in report
    assert "No description available" not in report


@pytest.mark.asyncio
async def test_generate_report_no_description_fallback() -> None:
    """Bug 2: missing body keys should fall back to 'No description available'."""
    report = await _generate([{"url": "https://x.com", "title": "T"}])
    assert "No description available" in report


# ---------------------------------------------------------------------------
# Bug 1 — ClosedResourceError does not crash the server
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_closed_resource_error_is_swallowed() -> None:
    """
    Simulate the crash path: anyio.ClosedResourceError raised during server.run()
    must be caught in main_stdio() and not propagate to the caller.
    """
    import anyio

    from ninja_researcher.server import create_server, main_stdio

    # Patch stdio_server so it yields mock streams, then patch server.run to raise
    # ClosedResourceError — the way it happens when stdin closes mid-flight.
    mock_read = MagicMock()
    mock_write = MagicMock()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_stdio():
        yield mock_read, mock_write

    server_instance = create_server()

    async def _raise_closed(*_args: Any, **_kwargs: Any) -> None:
        raise anyio.ClosedResourceError("stream closed")

    with (
        patch("ninja_researcher.server.stdio_server", _fake_stdio),
        patch("ninja_researcher.server.create_server", return_value=server_instance),
        patch.object(server_instance, "run", side_effect=_raise_closed),
    ):
        # Must NOT raise — the exception should be caught and logged.
        await main_stdio()


def test_server_subprocess_no_crash_on_stdin_close() -> None:
    """
    Integration: spawn ninja-researcher, send initialize + tool call, close stdin.
    Assert no ClosedResourceError traceback in stderr and non-crash exit.

    Uses researcher_summarize_sources with an unreachable URL so network I/O
    happens while stdin is already closed.
    """
    jsonrpc_input = textwrap.dedent(
        """\
        {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"qa","version":"0"}}}
        {"jsonrpc":"2.0","method":"notifications/initialized"}
        {"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"researcher_summarize_sources","arguments":{"urls":["http://127.0.0.1:1/"],"max_length":100}}}
        """
    )

    proc = subprocess.Popen(
        ["ninja-researcher"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = proc.communicate(
        input=jsonrpc_input.encode(),
        timeout=30,
    )

    stderr_text = stderr.decode(errors="replace")

    # The server must NOT emit a ClosedResourceError traceback.
    assert "ClosedResourceError" not in stderr_text, (
        f"Server crashed with ClosedResourceError:\n{stderr_text}"
    )
    assert "BrokenResourceError" not in stderr_text, (
        f"Server crashed with BrokenResourceError:\n{stderr_text}"
    )

    # The process must exit cleanly (0) or by natural EOF (also 0).
    # A crash typically exits with 1 via sys.exit(1) in the run() wrapper.
    assert proc.returncode == 0, (
        f"Server exited with code {proc.returncode}.\nstderr:\n{stderr_text}"
    )
