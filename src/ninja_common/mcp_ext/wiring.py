"""Wire the 2026-07-28 protocol extensions into the ninja MCP servers.

The four ninja servers are built directly on the lowlevel ``Server``, so
resources and ``tools/call`` interception are the caller's job
(:mod:`ninja_common.mcp_ext.apply` handles only ``methods()`` and settings).
This module owns the repeated half of that wiring so every entry point stays a
few lines:

* :func:`default_skill_root` / :func:`load_catalog` resolve the skills a module
  serves — ``NINJA_SKILLS_DIR`` when set, otherwise the packaged
  ``ninja_common/dist/skills/<module>`` — and degrade to an empty catalog
  instead of refusing to start when nothing was packaged;
* :func:`resource_handlers` serves a catalog through the base Resources
  primitive (``resources/list``, ``resources/read``);
* :func:`build_protocol_extensions` assembles the Skills and Tasks extensions
  for one server from a single durable task store.

Clients that did not declare an extension keep the plain synchronous surface:
Skills methods are 2026-07-28 only, and the Tasks interceptor passes calls
through untouched unless the client advertised
``io.modelcontextprotocol/tasks``.
"""

from __future__ import annotations

import base64
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from mcp import types
from mcp.shared.exceptions import MCPError

from ninja_common.mcp_ext.skills import SkillCatalog, SkillsExtension
from ninja_common.mcp_ext.tasks import TasksExtension


if TYPE_CHECKING:
    from collections.abc import Iterable

    from mcp.server.context import ServerRequestContext

    from ninja_common.mcp_ext.tasks_store import TaskStore


logger = logging.getLogger(__name__)

#: Environment override for the directory a server serves skills from.
SKILLS_DIR_ENV: Final[str] = "NINJA_SKILLS_DIR"

#: MIME type served for a file whose type could not be derived.
FALLBACK_MIME_TYPE: Final[str] = "application/octet-stream"

OnListResources = Callable[
    ["ServerRequestContext[Any, Any]", "types.PaginatedRequestParams | None"],
    Awaitable["types.ListResourcesResult"],
]
"""``resources/list`` handler signature on the lowlevel server."""

OnReadResource = Callable[
    ["ServerRequestContext[Any, Any]", "types.ReadResourceRequestParams"],
    Awaitable["types.ReadResourceResult"],
]
"""``resources/read`` handler signature on the lowlevel server."""


def default_skill_root(module: str) -> Path:
    """Return the directory *module* serves its skills from.

    ``NINJA_SKILLS_DIR`` wins when it is set (used by deployments that ship a
    skill bundle outside the wheel); otherwise the packaged
    ``ninja_common/dist/skills/<module>`` directory is used. The directory is
    not required to exist — see :func:`load_catalog`.

    Args:
        module: Server module name (``coder``, ``researcher``, ``secretary``,
            ``agent``).

    Returns:
        The skill catalog root for *module*.
    """
    override = os.environ.get(SKILLS_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[2] / "ninja_common" / "dist" / "skills" / module


def load_catalog(module: str) -> SkillCatalog:
    """Build the skill catalog *module* serves.

    A missing or empty skills directory is not an error: the server publishes
    an empty catalog and keeps serving, so a source checkout without packaged
    skills starts exactly like an installed wheel with them. A directory that
    *does* exist is validated strictly — a malformed ``SKILL.md`` is a
    correctness failure at the host and raises.

    Args:
        module: Server module name (see :func:`default_skill_root`).

    Returns:
        The populated catalog, or an empty one rooted at the expected path.
    """
    root = default_skill_root(module)
    if not root.is_dir():
        logger.info("No skills directory for %s at %s; serving an empty catalog", module, root)
        return SkillCatalog.empty(root)
    catalog = SkillCatalog(root)
    if not catalog.skills():
        logger.info("No skills found under %s; serving an empty catalog", root)
    return catalog


def resource_handlers(catalog: SkillCatalog) -> tuple[OnListResources, OnReadResource]:
    """Build the ``resources/list`` and ``resources/read`` handlers for *catalog*.

    ``skills/list`` describes a skill, but its content is read through the base
    Resources primitive: every served file is one resource, and ``SKILL.md`` is
    just the skill's entry point. An empty catalog still serves both handlers
    (an empty list, and an error for every read) so capabilities stay honest.

    Args:
        catalog: The skills this server publishes.

    Returns:
        ``(list_resources, read_resource)`` for ``Server(on_list_resources=...,
        on_read_resource=...)``.
    """

    async def list_resources(
        _ctx: ServerRequestContext[Any, Any],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListResourcesResult:
        """List every file of every skill."""
        return types.ListResourcesResult(resources=catalog.list_resources())

    async def read_resource(
        _ctx: ServerRequestContext[Any, Any],
        params: types.ReadResourceRequestParams,
    ) -> types.ReadResourceResult:
        """Serve one skill file, text or binary, by URI."""
        uri = params.uri
        try:
            body = catalog.read(uri)
        except (KeyError, ValueError):
            # 2026-07-28 reports a missing resource as invalid params.
            raise MCPError(types.INVALID_PARAMS, f"unknown resource: {uri}") from None
        mime_type = catalog.mime_type(uri) or FALLBACK_MIME_TYPE
        contents: types.TextResourceContents | types.BlobResourceContents
        if isinstance(body, str):
            contents = types.TextResourceContents(uri=uri, mime_type=mime_type, text=body)
        else:
            contents = types.BlobResourceContents(
                uri=uri,
                mime_type=mime_type,
                blob=base64.b64encode(body).decode("ascii"),
            )
        return types.ReadResourceResult(contents=[contents])

    return list_resources, read_resource


@dataclass(frozen=True, slots=True)
class ProtocolExtensions:
    """Everything one server needs to serve Skills and Tasks.

    Attributes:
        catalog: The skills the server publishes (also used for resource reads).
        skills_ext: The ``io.modelcontextprotocol/skills`` extension.
        tasks_ext: The ``io.modelcontextprotocol/tasks`` extension.
        on_list_resources: ``resources/list`` handler.
        on_read_resource: ``resources/read`` handler.
    """

    catalog: SkillCatalog
    skills_ext: SkillsExtension
    tasks_ext: TasksExtension
    on_list_resources: OnListResources
    on_read_resource: OnReadResource


def build_protocol_extensions(
    module: str,
    store: TaskStore,
    task_tools: Iterable[str],
    *,
    poll_interval_ms: int = 500,
) -> ProtocolExtensions:
    """Assemble the extensions served by *module*.

    Args:
        module: Server module name (see :func:`default_skill_root`).
        store: Durable task store; one instance per server, shared with the
            job manager where the server has one.
        task_tools: Tools that run as durable tasks for declaring clients.
        poll_interval_ms: ``pollIntervalMs`` advertised on task handles.

    Returns:
        The extensions plus the resource handlers to pass to ``Server(...)``.
    """
    catalog = load_catalog(module)
    list_resources, read_resource = resource_handlers(catalog)
    return ProtocolExtensions(
        catalog=catalog,
        skills_ext=SkillsExtension(catalog),
        tasks_ext=TasksExtension(store, task_tools=task_tools, poll_interval_ms=poll_interval_ms),
        on_list_resources=list_resources,
        on_read_resource=read_resource,
    )


__all__ = [
    "FALLBACK_MIME_TYPE",
    "SKILLS_DIR_ENV",
    "OnListResources",
    "OnReadResource",
    "ProtocolExtensions",
    "build_protocol_extensions",
    "default_skill_root",
    "load_catalog",
    "resource_handlers",
]
