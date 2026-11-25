"""Shared MCP wire metadata: icons, tool annotations, structured results.

Implements the non-deprecated, currently-standard MCP surface on top of the
installed SDK:

- per-server SVG icons (tool-level and server-level ``icons``),
- ``title`` + ``annotations`` (readOnly/destructive/idempotent hints),
- ``outputSchema`` + ``structuredContent`` for machine-readable results,
- ``elicitation`` helper with graceful fallback when the client cannot ask,
- ``ResourceLink`` builders for file artifacts (e.g. patch files).

Deliberately NOT adopted (deprecated by SEP-2577, removal track): Roots,
Sampling, and the Logging protocol. We already follow the recommended
replacements (explicit ``repo_root`` params, own LLM engines, stderr logs).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from urllib.request import pathname2url

from mcp.types import (
    CallToolResult,
    Icon,
    ResourceLink,
    TextContent,
    Tool,
    ToolAnnotations,
)


if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic import BaseModel


WEBSITE_URL = "https://github.com/angkira/ninja-cli-mcp"

#: Server brand colors and glyphs for SVG icons.
SERVER_BRAND: dict[str, tuple[str, str]] = {
    "coder": ("#4F46E5", "C"),
    "researcher": ("#0D9488", "R"),
    "agent": ("#D97706", "A"),
    "secretary": ("#7C3AED", "S"),
}


def svg_icon(letter: str, bg: str) -> Icon:
    """Build a small SVG data-URI icon."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
        f'<rect width="64" height="64" rx="14" fill="{bg}"/>'
        f'<text x="32" y="44" font-family="sans-serif" font-size="36" '
        f'font-weight="bold" text-anchor="middle" fill="#ffffff">{letter}</text>'
        f"</svg>"
    )
    return Icon(
        src=f"data:image/svg+xml,{quote(svg, safe='')}",
        mime_type="image/svg+xml",
        sizes=["64x64"],
    )


def server_icon(kind: str) -> Icon:
    """Return the brand icon for a ninja server module."""
    bg, letter = SERVER_BRAND.get(kind, ("#475569", "N"))
    return svg_icon(letter, bg)


#: Loose error envelope accepted alongside every model schema so that
#: graceful error payloads never trip output validation.
ERROR_ENVELOPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "error": {"type": "string"},
        "error_type": {"type": "string"},
    },
    "required": ["status", "error"],
}

#: Minimal shape for payloads that only carry an error message.
BARE_ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["error"],
}


def output_schema_for(model: type[BaseModel] | None) -> dict[str, Any]:
    """Build an output schema for a tool.

    Model-backed tools accept the model shape or a graceful error envelope
    (so error payloads never trip output validation). Pydantic ``$defs``
    are hoisted to the wrapper root because inner ``$ref`` pointers are
    root-relative. Dict-payload tools (job handles, status views) accept
    any object.
    """
    if model is None:
        return {"type": "object"}
    schema = model.model_json_schema()
    defs = schema.pop("$defs", None)
    # ``type: object`` at the root is mandatory on the 2025-11-25 wire (its
    # ``OutputSchema`` model declares it as a required field) and is implied by
    # every branch of the ``anyOf`` below, so it narrows nothing.
    wrapped: dict[str, Any] = {
        "type": "object",
        "anyOf": [schema, ERROR_ENVELOPE_SCHEMA, BARE_ERROR_SCHEMA],
    }
    if defs:
        wrapped["$defs"] = defs
    return wrapped


@dataclass
class ToolMeta:
    """Wire metadata for a single tool."""

    title: str
    annotations: ToolAnnotations
    result_model: type[BaseModel] | None = None


def apply_tool_meta(
    tools: list[Tool],
    meta: dict[str, ToolMeta],
    icon: Icon,
) -> list[Tool]:
    """Return copies of *tools* with title/annotations/output_schema/icons set.

    Tools missing from *meta* keep their definition but still get the icon.
    """
    branded: list[Tool] = []
    for tool in tools:
        entry = meta.get(tool.name)
        update: dict[str, Any] = {"icons": [icon]}
        if entry is not None:
            update["title"] = entry.title
            update["annotations"] = entry.annotations
            update["output_schema"] = output_schema_for(entry.result_model)
        branded.append(tool.model_copy(update=update))
    return branded


def pretty_json_text(payload: dict[str, Any]) -> TextContent:
    """Render a dict payload as a pretty-printed JSON text block."""
    return TextContent(type="text", text=json.dumps(payload, indent=2))


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Round-trip a payload through JSON so structured content is serializable."""
    decoded: Any = json.loads(json.dumps(payload, default=str))
    if not isinstance(decoded, dict):
        return {"value": decoded}
    return decoded


def model_result(
    result: BaseModel,
    extra_blocks: list[TextContent | ResourceLink] | None = None,
) -> tuple[list[TextContent | ResourceLink], dict[str, Any]]:
    """Build (content, structured) for a pydantic result model.

    The text block keeps the historical pretty-JSON format so existing
    text-parsing clients keep working; ``structuredContent`` carries the
    same payload for schema-aware clients.
    """
    structured = _json_safe(result.model_dump(mode="json"))
    blocks: list[TextContent | ResourceLink] = [pretty_json_text(structured)]
    if extra_blocks:
        blocks.extend(extra_blocks)
    return blocks, structured


def dict_result(
    payload: dict[str, Any],
    extra_blocks: list[TextContent | ResourceLink] | None = None,
) -> tuple[list[TextContent | ResourceLink], dict[str, Any]]:
    """Build (content, structured) for a plain-dict payload."""
    structured = _json_safe(payload)
    blocks: list[TextContent | ResourceLink] = [pretty_json_text(structured)]
    if extra_blocks:
        blocks.extend(extra_blocks)
    return blocks, structured


def file_resource_link(
    path: str | None,
    *,
    name: str,
    title: str | None = None,
    mime_type: str = "text/plain",
) -> ResourceLink | None:
    """Build a ``file://`` resource link when *path* points at a real file."""
    if not path:
        return None
    try:
        resolved = Path(path)
        if not resolved.is_file():
            return None
        uri = f"file://{pathname2url(str(resolved.resolve()))}"
        return ResourceLink(
            uri=uri,
            name=name,
            title=title or name,
            mime_type=mime_type,
            size=resolved.stat().st_size,
            type="resource_link",
        )
    except OSError:
        return None


def patch_resource_link(patch_path: str | None) -> ResourceLink | None:
    """Build a resource link for a unified-diff patch artifact, if present."""
    return file_resource_link(
        patch_path,
        name="agent-output.patch",
        title="Agent output patch (unified diff)",
        mime_type="text/x-patch",
    )


async def elicit_confirm(
    session: Any,
    message: str,
    *,
    item_label: str = "proceed",
) -> bool | None:
    """Ask the user for confirmation via elicitation.

    Push-style elicitation (a server-initiated request mid-call) is only
    available on legacy connections; 2026-07-28 replaces it with the
    ``resolve`` flow, where the server returns an ``input_required`` result and
    the client answers on a later request. Until the call sites migrate, this
    keeps the legacy shape. A later stage replaces it with ``Resolve``.

    Args:
        session: MCP server session (must expose ``elicit``).
        message: Human-readable confirmation prompt.
        item_label: Label interpolated into the confirm field description.

    Returns:
        True when the user confirmed, False when they declined, None when
        elicitation is unsupported or failed (caller must fall back).
    """
    elicit = getattr(session, "elicit", None)
    if not callable(elicit):
        return None
    try:
        result = await elicit(
            message=message,
            requested_schema={
                "type": "object",
                "properties": {
                    "confirm": {
                        "type": "boolean",
                        "description": f"Confirm: {item_label}",
                    }
                },
                "required": ["confirm"],
            },
        )
    except Exception:
        return None
    try:
        action = getattr(result, "action", "")
        if action != "accept":
            return False
        content = getattr(result, "content", None) or {}
        return bool(content.get("confirm"))
    except Exception:
        return None


def tool_call_result(
    built: tuple[Sequence[TextContent | ResourceLink], dict[str, Any] | None],
    *,
    is_error: bool = False,
) -> CallToolResult:
    """Wrap a ``model_result``/``dict_result`` tuple in a ``CallToolResult``.

    ``is_error`` marks *framework* failures only: an unknown tool name, a
    request-model validation failure, or an unhandled exception escaping a
    handler. The content block and ``structured_content`` stay identical to the
    success shape so payload-parsing clients are unaffected. A tool that ran
    and reports a business error inside its own envelope keeps
    ``is_error=False``.
    """
    texts, structured = built
    return CallToolResult(
        content=list(texts),
        structured_content=structured,
        is_error=is_error,
    )


def error_text_payload(
    error: str,
    error_type: str = "UpstreamError",
    *,
    is_error: bool = True,
) -> CallToolResult:
    """Minimal error payload (no outputSchema validation involved).

    ``is_error`` defaults to True because this shape is only used for failures;
    pass False for a business-logic envelope that must stay a successful call.
    """
    return CallToolResult(
        content=[pretty_json_text({"status": "error", "error": error, "error_type": error_type})],
        is_error=is_error,
    )


@dataclass
class ServerMeta:
    """Identity block applied to ``Server(...)`` constructors."""

    instructions: str
    kind: str


def server_kwargs(meta: ServerMeta) -> dict[str, Any]:
    """Build ``Server()`` kwargs: instructions, website and brand icon."""
    return {
        "instructions": meta.instructions,
        "website_url": WEBSITE_URL,
        "icons": [server_icon(meta.kind)],
    }
