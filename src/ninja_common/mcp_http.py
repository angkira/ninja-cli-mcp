"""Shared ASGI wiring for the ninja MCP servers' HTTP transports.

A single listening port serves two transports:

- legacy HTTP+SSE at ``/sse`` with the client -> server back-channel at
  ``/messages`` (the pre-2026-07-28 transport, kept for existing hosts);
- modern streamable HTTP at ``/mcp`` (protocol ``2026-07-28``).

``build_asgi_app`` owns that wiring so the four servers do not copy the same
route block. It reuses ``Server.streamable_http_app`` (which supplies the
session-manager lifespan) and injects the SSE routes through its supported
``custom_starlette_routes`` hook, so no Starlette internals are patched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.sse import SseServerTransport
from starlette.responses import Response
from starlette.routing import Route


if TYPE_CHECKING:
    from mcp.server.lowlevel.server import Server
    from starlette.applications import Starlette
    from starlette.types import Receive, Scope, Send


class _SseEndpoint:
    """Raw ASGI endpoint streaming one legacy SSE session."""

    def __init__(self, server: Server[Any], sse: SseServerTransport) -> None:
        self._server = server
        self._sse = sse

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async with self._sse.connect_sse(scope, receive, send) as streams:
            await self._server.run(
                streams[0], streams[1], self._server.create_initialization_options()
            )
        await Response()(scope, receive, send)


class _MessageEndpoint:
    """Raw ASGI endpoint for the legacy SSE client -> server back-channel."""

    def __init__(self, sse: SseServerTransport) -> None:
        self._sse = sse

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["method"] != "POST":
            await Response("Not Found", status_code=404)(scope, receive, send)
            return
        await self._sse.handle_post_message(scope, receive, send)


def build_asgi_app(
    server: Server[Any],
    *,
    host: str,
    sse_path: str = "/sse",
    message_path: str = "/messages",
    streamable_path: str = "/mcp",
) -> Starlette:
    """Build the combined ASGI app for one server.

    Args:
        server: Low-level MCP server whose ``run`` loop serves SSE sessions.
        host: Bind host, forwarded to the streamable-HTTP transport so its
            localhost DNS-rebinding guard matches the listener.
        sse_path: Legacy SSE stream path.
        message_path: Legacy SSE back-channel path. Must match the path baked
            into the ``endpoint`` event sent to clients, hence no trailing
            slash.
        streamable_path: Modern streamable-HTTP path.

    Returns:
        Starlette app serving both transports over one port.
    """
    sse = SseServerTransport(message_path)
    return server.streamable_http_app(
        host=host,
        streamable_http_path=streamable_path,
        custom_starlette_routes=[
            Route(sse_path, endpoint=_SseEndpoint(server, sse)),
            Route(message_path, endpoint=_MessageEndpoint(sse)),
        ],
    )
