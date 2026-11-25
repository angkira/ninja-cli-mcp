"""Apply opt-in extensions to a lowlevel :class:`mcp.server.lowlevel.Server`.

The MCP 2.x SDK consumes :class:`mcp.server.extension.Extension` objects only in
``MCPServer`` (the composition tier). ninja's servers are built directly on the
lowlevel ``Server``, so this module performs the same three moves by hand:

* register every ``methods()`` binding as a request handler,
* advertise each extension's ``settings()`` under ``Server.extensions``,
* refuse to replace an existing handler (extension methods are additive).

What it deliberately does *not* do:

* ``tools()`` / ``resources()`` / ``intercept_tool_call()`` are ignored. The
  caller owns tool and resource registration: on the lowlevel server a resource
  is a ``resources/list`` entry plus a ``resources/read`` implementation, which
  a single generic helper cannot wire without knowing the server's routing.
  Compose ``tools/call`` yourself if an extension overrides
  ``intercept_tool_call`` (see ``mcp.server.extension.compose_tool_call_handler``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from mcp import types
from mcp.server.context import HandlerResult, ServerRequestContext
from mcp.shared.exceptions import MCPError
from mcp.shared.extension import validate_extension_identifier


if TYPE_CHECKING:
    from mcp.server.extension import Extension, MethodBinding
    from mcp.server.lowlevel import Server


RequestHandler = Callable[[ServerRequestContext[Any, Any], Any], Awaitable[HandlerResult]]


def apply_extensions(server: Server[Any], extensions: Sequence[Extension]) -> None:
    """Register *extensions*' methods and settings on a lowlevel *server*.

    Mirrors ``MCPServer._apply_extension`` for servers that are not built on
    ``MCPServer``. Tools and resources are **not** registered here — see the
    module docstring.

    Args:
        server: The lowlevel server to extend.
        extensions: Extensions to apply, in order.

    Raises:
        TypeError: An extension's ``identifier`` is not a ``vendor/name`` string.
        ValueError: An extension identifier is already applied, or a binding's
            method already has a handler (extension methods are additive).

    Example:
        >>> from mcp.server.lowlevel import Server
        >>> server: Server[Any] = Server("demo")  # doctest: +SKIP
        >>> apply_extensions(server, [SkillsExtension(catalog)])  # doctest: +SKIP
    """
    applied: set[str] = set()
    for extension in extensions:
        identifier = getattr(extension, "identifier", None)
        validate_extension_identifier(identifier, owner=type(extension).__name__)
        assert isinstance(identifier, str)  # narrowed by validate_extension_identifier
        if identifier in applied:
            raise ValueError(
                f"Extension {identifier!r} is already registered; extensions are additive "
                "and cannot replace another extension's handlers"
            )
        applied.add(identifier)

        for method in extension.methods():
            if server.get_request_handler(method.method) is not None:
                raise ValueError(
                    f"Extension {identifier!r} binds method {method.method!r}, which is already "
                    "registered; extension methods are additive and cannot replace another handler"
                )
            handler = (
                _version_gated(method) if method.protocol_versions is not None else method.handler
            )
            server.add_request_handler(method.method, method.params_type, handler)

        server.extensions[identifier] = extension.settings()


def _version_gated(method: MethodBinding) -> RequestHandler:
    """Wrap *method*'s handler so disallowed protocol versions see METHOD_NOT_FOUND.

    The lowlevel ``Server`` keys request handlers by method only, so
    per-protocol-version scoping has to happen inside the handler. This is a
    local copy of the SDK's private ``mcp.server.mcpserver.server._version_gated``
    (importing a private module is not acceptable across SDK minors).
    """
    versions = method.protocol_versions
    assert versions is not None

    async def gated(ctx: ServerRequestContext[Any, Any], params: Any) -> HandlerResult:
        if ctx.protocol_version not in versions:
            raise MCPError(
                code=types.METHOD_NOT_FOUND,
                message="Method not found",
                data=method.method,
            )
        return await method.handler(ctx, params)

    return gated


__all__ = ["apply_extensions"]
