"""Ninja extensions built on top of the MCP 2026-07-28 protocol surface.

The MCP 2.x SDK removed the experimental task store/helpers that earlier
releases shipped, and moved Tasks to an opt-in extension
(``io.modelcontextprotocol/tasks``). This package owns the pieces ninja needs
to keep its durable, process-shared background job support:

* :mod:`ninja_common.mcp_ext.protocol` -- protocol revision and extension ids.
* :mod:`ninja_common.mcp_ext.models` -- Tasks wire models (camelCase aliases).
* :mod:`ninja_common.mcp_ext.tasks_store` -- SQLite-backed task store.
"""

from __future__ import annotations

from ninja_common.mcp_ext.protocol import (
    FILES_EXTENSION_ID,
    PROTOCOL_2026,
    SKILLS_EXTENSION_ID,
    TASKS_EXTENSION_ID,
    client_extensions,
    has_client_extension,
)


__all__ = [
    "FILES_EXTENSION_ID",
    "PROTOCOL_2026",
    "SKILLS_EXTENSION_ID",
    "TASKS_EXTENSION_ID",
    "client_extensions",
    "has_client_extension",
]
