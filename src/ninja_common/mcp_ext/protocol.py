"""Protocol revision constants and client-extension helpers.

MCP 2026-07-28 keeps the base protocol small and moves optional behaviour into
client-declared extensions advertised in ``ClientCapabilities.extensions``.
Servers gate extension-specific tools and result shapes on those declarations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from mcp.server import ServerRequestContext


#: The protocol revision this package targets.
PROTOCOL_2026 = "2026-07-28"

#: Tasks extension (durable background work with ``tasks/get`` polling).
TASKS_EXTENSION_ID = "io.modelcontextprotocol/tasks"

#: Skills extension (server-packaged skill bundles).
SKILLS_EXTENSION_ID = "io.modelcontextprotocol/skills"

#: Files extension (server-exposed filesystem resources).
FILES_EXTENSION_ID = "io.modelcontextprotocol/files"


def client_extensions(ctx: ServerRequestContext[Any, Any]) -> dict[str, dict[str, Any]]:
    """Return the extensions the peer client advertised for this session.

    Args:
        ctx: Request context carrying the connection-scoped server session.

    Returns:
        Extension identifier -> extension settings. Empty when the client is
        not available (e.g. no session capabilities) or declared none.
    """
    session = getattr(ctx, "session", None)
    capabilities = getattr(session, "client_capabilities", None)
    if capabilities is None:
        return {}
    extensions = getattr(capabilities, "extensions", None)
    if not extensions:
        return {}
    return dict(extensions)


def has_client_extension(ctx: ServerRequestContext[Any, Any], identifier: str) -> bool:
    """Whether the peer client declared *identifier* for this session."""
    return identifier in client_extensions(ctx)


__all__ = [
    "FILES_EXTENSION_ID",
    "PROTOCOL_2026",
    "SKILLS_EXTENSION_ID",
    "TASKS_EXTENSION_ID",
    "client_extensions",
    "has_client_extension",
]
