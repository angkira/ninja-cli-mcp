"""Files over MCP: the ``io.modelcontextprotocol/files`` extension (draft).

The extension moves files between clients and tools without putting their
bytes in model context. This module implements the **inline-only** half of the
draft: a server advertises ``maxInlineBytes`` and never ``upload``, so every
file a client sends must carry its bytes in ``data``.

What a server using it does:

* mark a file argument with ``x-mcp-file`` on the argument's object schema
  (:func:`x_mcp_file_schema`),
* advertise the extension with ``{"maxInlineBytes": <n>}``
  (:class:`FilesExtension`),
* accept the call only after decoding and validating the argument
  (:func:`decode_files`).

Out-of-band uploads (``upload_required``, ``requestState``) are deliberately
not implemented: this server cannot mint an upload target. Downloads are not
served either — an :class:`mcp.server.extension.Extension` cannot contribute an
HTTP route, and the lowlevel server's ``custom_route`` is unauthenticated — so
file *output* travels as embedded resources instead. The ``_meta`` download
model and :func:`file_download_meta` exist for completeness and are currently
unused.

The draft lives at
https://github.com/modelcontextprotocol/experimental-ext-file-uploads; it is
experimental and may change without notice.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Final, Literal

from mcp.server.extension import Extension
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic.alias_generators import to_camel

from ninja_common.mcp_ext.protocol import FILES_EXTENSION_ID


if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcp.server.extension import MethodBinding, ToolBinding


#: Environment flag that turns the extension on. Default: off.
FILES_ENABLE_ENV: Final[str] = "NINJA_MCP_ENABLE_FILE_UPLOADS"

#: Default total decoded inline payload a server accepts per request (8 MiB).
DEFAULT_MAX_INLINE_BYTES: Final[int] = 8 * 1024 * 1024

#: Values :func:`is_enabled` treats as true.
_TRUE_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})

#: The only digest algorithm the draft defines.
SHA256_ALGORITHM: Final[Literal["sha-256"]] = "sha-256"

#: Attribute the draft adds to a file argument's object schema.
X_MCP_FILE: Final[str] = "x-mcp-file"


class _WireModel(BaseModel):
    """camelCase-on-the-wire, snake_case-in-Python model base."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FileDigest(_WireModel):
    """SHA-256 over a file's original bytes, base64url without padding."""

    algorithm: Literal["sha-256"] = SHA256_ALGORITHM
    value: str


class FileInput(_WireModel):
    """The ``FileInput`` shape a client binds to an ``x-mcp-file`` argument."""

    id: str = Field(min_length=1, max_length=128)
    """Client-assigned identifier, unique within the call."""

    name: str | None = None
    """Client-supplied display name (untrusted)."""

    mime_type: str
    """Media type; ``application/octet-stream`` when unknown."""

    size: int = Field(ge=0)
    """Decoded size in bytes, as declared by the client (untrusted)."""

    digest: FileDigest | None = None
    """Optional SHA-256 of the original bytes."""

    data: str | None = None
    """RFC 4648 base64 of the file bytes; absent for an out-of-band file."""


class DownloadTarget(_WireModel):
    """One file a tool result offers for download (draft ``DownloadTarget``)."""

    name: str | None = None
    mime_type: str
    size: int = Field(ge=0)
    digest: FileDigest | None = None
    url: str | None = None
    path: str | None = None
    headers: dict[str, str] | None = None
    credentials: Literal["omit", "include"]
    expires_at: str | None = None

    @model_validator(mode="after")
    def _exactly_one_address(self) -> DownloadTarget:
        """The draft requires exactly one of ``url`` and ``path``."""
        if (self.url is None) == (self.path is None):
            raise ValueError("exactly one of 'url' and 'path' must be set")
        return self


class FilesResultMeta(_WireModel):
    """The ``io.modelcontextprotocol/files`` entry of a result's ``_meta``."""

    downloads: list[DownloadTarget] = Field(default_factory=list)


#: JSON Schema fragment for a ``FileInput`` object, without ``x-mcp-file``.
#: Mirrors the draft's reference schema; use :func:`x_mcp_file_schema` rather
#: than attaching this dict directly, so the annotation travels with it.
FILE_INPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1, "maxLength": 128},
        "name": {"type": "string"},
        "mimeType": {"type": "string"},
        "size": {"type": "integer", "minimum": 0},
        "digest": {
            "type": "object",
            "properties": {
                "algorithm": {"const": SHA256_ALGORITHM},
                "value": {"type": "string"},
            },
            "required": ["algorithm", "value"],
        },
        "data": {"type": "string"},
    },
    "required": ["id", "mimeType", "size"],
}


class FileArgumentError(ValueError):
    """A file argument that cannot be accepted inline.

    The message is safe to show to the user and to log: it never contains the
    argument's ``data`` or any decoded bytes.
    """


def is_enabled() -> bool:
    """Whether this server should serve the Files extension.

    Reads ``NINJA_MCP_ENABLE_FILE_UPLOADS`` at call time (``1``, ``true``,
    ``yes`` or ``on``). Default is off, which keeps the advertised surface
    unchanged.
    """
    return os.environ.get(FILES_ENABLE_ENV, "").strip().lower() in _TRUE_VALUES


def sha256_digest(data: bytes) -> str:
    """Return the draft's digest form of *data*: base64url, no padding."""
    hashed = hashlib.sha256(data).digest()
    return base64.urlsafe_b64encode(hashed).rstrip(b"=").decode("ascii")


def x_mcp_file_schema(
    *,
    accept: list[str] | None = None,
    max_size: int | None = None,
) -> dict[str, Any]:
    """Return a ``FileInput`` object schema annotated with ``x-mcp-file``.

    The keyword is a JSON Schema annotation, so clients that do not implement
    the extension ignore it and see an ordinary object argument.

    Args:
        accept: Media types or dot-prefixed extensions for a file picker.
        max_size: Maximum decoded size of the file, in bytes.

    Returns:
        A fresh schema dict; mutating it does not affect ``FILE_INPUT_SCHEMA``.

    Raises:
        ValueError: *max_size* is negative.
    """
    if max_size is not None and max_size < 0:
        raise ValueError(f"max_size must be >= 0, got {max_size}")

    descriptor: dict[str, Any] = {}
    if accept is not None:
        descriptor["accept"] = list(accept)
    if max_size is not None:
        descriptor["maxSize"] = max_size

    schema = deepcopy(FILE_INPUT_SCHEMA)
    schema[X_MCP_FILE] = descriptor
    return schema


def _validation_summary(exc: ValidationError, field_name: str) -> str:
    """Render a pydantic error without echoing any input value."""
    details = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or field_name
        details.append(f"{location} ({error['type']})")
    return ", ".join(details)


def decode_files(
    arguments: dict[str, Any],
    *,
    max_inline_bytes: int,
    field_name: str = "file",
) -> tuple[bytes | None, FileInput]:
    """Decode and validate the inline file in *arguments*.

    Validates the client-asserted metadata against the bytes: base64, declared
    size, per-file size and the digest when the client supplied one. The caller
    owns the per-request total: a tool with several file arguments must sum the
    decoded lengths against ``maxInlineBytes`` itself.

    Args:
        arguments: The ``tools/call`` arguments object.
        max_inline_bytes: The server's advertised ``maxInlineBytes``.
        field_name: Argument that carries the ``FileInput``.

    Returns:
        ``(payload, file)``. ``payload`` is ``None`` for a file with no bytes
        (``size`` 0), otherwise the decoded bytes.

    Raises:
        FileArgumentError: The file is missing, malformed, over the limit, not
            decodable, or does not match its declared size or digest. No
            message contains ``data`` or decoded bytes.
    """
    raw = arguments.get(field_name)
    if raw is None:
        raise FileArgumentError(f"missing required file argument: {field_name!r}")
    if not isinstance(raw, dict):
        raise FileArgumentError(f"file argument {field_name!r} must be an object")

    try:
        file = FileInput.model_validate(raw)
    except ValidationError as exc:
        raise FileArgumentError(
            f"invalid file argument {field_name!r}: {_validation_summary(exc, field_name)}"
        ) from None

    if file.size > max_inline_bytes:
        raise FileArgumentError(
            f"file {file.id!r} is too large: {file.size} declared bytes exceed the inline "
            f"limit of {max_inline_bytes} bytes"
        )

    if file.data is None:
        if file.size > 0:
            raise FileArgumentError(
                f"file {file.id!r} declares {file.size} bytes but has no inline data; "
                "this server does not accept out-of-band uploads"
            )
        payload = b""
    else:
        try:
            payload = base64.b64decode(file.data, validate=True)
        except (binascii.Error, ValueError):
            raise FileArgumentError(f"file {file.id!r} has invalid base64 inline data") from None

    if len(payload) > max_inline_bytes:
        raise FileArgumentError(
            f"file {file.id!r} is too large: decoded {len(payload)} bytes exceed the inline "
            f"limit of {max_inline_bytes} bytes"
        )
    if len(payload) != file.size:
        raise FileArgumentError(
            f"file {file.id!r} size mismatch: declared {file.size} bytes, "
            f"decoded {len(payload)} bytes"
        )

    if file.digest is not None and sha256_digest(payload) != file.digest.value:
        raise FileArgumentError(f"file {file.id!r} digest mismatch")

    return (None if file.size == 0 else payload), file


def file_download_meta(targets: Sequence[DownloadTarget]) -> dict[str, Any]:
    """Build the ``_meta`` envelope that offers *targets* for download.

    Currently unused: this project cannot serve HTTP file targets (an
    ``Extension`` cannot contribute a route, and ``custom_route`` is
    unauthenticated), so tools return file output as embedded resources. The
    helper exists so the download shape stays defined should a hosting layer
    appear; it emits no targets on its own.

    Args:
        targets: Fully-formed download targets.

    Returns:
        ``{"_meta": {"io.modelcontextprotocol/files": {"downloads": [...]}}}``.
    """
    downloads = [
        target.model_dump(mode="json", by_alias=True, exclude_none=True) for target in targets
    ]
    return {"_meta": {FILES_EXTENSION_ID: {"downloads": downloads}}}


class FilesExtension(Extension):
    """The ``io.modelcontextprotocol/files`` extension, inline-only.

    Advertises ``maxInlineBytes`` and nothing else: no ``upload`` (this server
    cannot issue a target) and no ``download`` (that setting is client-only).
    Contributes no request methods and no tools — the caller marks a file
    argument with :func:`x_mcp_file_schema` and validates it with
    :func:`decode_files`.

    Args:
        max_inline_bytes: Largest total decoded inline payload per request.
    """

    identifier = FILES_EXTENSION_ID

    def __init__(self, *, max_inline_bytes: int = DEFAULT_MAX_INLINE_BYTES) -> None:
        if max_inline_bytes < 0:
            raise ValueError(f"max_inline_bytes must be >= 0, got {max_inline_bytes}")
        self._max_inline_bytes = max_inline_bytes

    @property
    def max_inline_bytes(self) -> int:
        """The advertised per-request inline budget, in bytes."""
        return self._max_inline_bytes

    def settings(self) -> dict[str, Any]:
        """Advertise the inline budget under ``capabilities.extensions``."""
        return {"maxInlineBytes": self._max_inline_bytes}

    def methods(self) -> Sequence[MethodBinding]:
        """The extension adds no request methods."""
        return ()

    def tools(self) -> Sequence[ToolBinding]:
        """The extension adds no tools."""
        return ()


__all__ = [
    "DEFAULT_MAX_INLINE_BYTES",
    "FILES_ENABLE_ENV",
    "FILE_INPUT_SCHEMA",
    "SHA256_ALGORITHM",
    "X_MCP_FILE",
    "DownloadTarget",
    "FileArgumentError",
    "FileDigest",
    "FileInput",
    "FilesExtension",
    "FilesResultMeta",
    "decode_files",
    "file_download_meta",
    "is_enabled",
    "sha256_digest",
    "x_mcp_file_schema",
]
