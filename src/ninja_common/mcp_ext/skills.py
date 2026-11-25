"""Skills over MCP: the ``io.modelcontextprotocol/skills`` extension (SEP-2640).

A skill is a directory of files — at minimum a ``SKILL.md`` with YAML
frontmatter — published over the base Resources primitive under ``skill://``
URIs. The extension adds three request methods:

* ``skills/list``  — every skill the server serves, as a full manifest;
* ``skills/get``   — one skill's manifest by the URI of its ``SKILL.md``;
* ``resources/directory/read`` — the direct children of a directory resource,
  only when the server advertises ``directoryRead``.

Skill *content* is read through the base ``resources/read`` method. On the
lowlevel server that means the caller registers those resources; this module
supplies the catalog side: :class:`SkillCatalog` scans a directory tree, and
:meth:`SkillCatalog.list_resources` yields the matching ``Resource`` entries.

Wire models are pydantic v2 with camelCase aliases and snake_case attributes,
matching the ``mcp_types`` convention. ``ttlMs``/``cacheScope``/``resultType``
are 2026-07-28 vocabulary, so they are dropped from results handed to a
pre-2026 connection (see :func:`_result_for_era`).
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, TypeVar
from urllib.parse import unquote

from mcp import types
from mcp.server.extension import Extension, MethodBinding
from mcp.server.mcpserver import require_client_extension
from mcp.shared.exceptions import MCPError
from mcp_types import RequestParams, Resource, Result
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ninja_common.mcp_ext.protocol import SKILLS_EXTENSION_ID


if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcp.server.context import HandlerResult, ServerRequestContext


#: File name every skill must contain at its root.
SKILL_MD: Final[str] = "SKILL.md"

#: MIME type a directory resource carries (spec: "Directory Resources").
DIRECTORY_MIME_TYPE: Final[str] = "inode/directory"

#: Per-skill limit on manifest entries, ``SKILL.md`` included.
MAX_RESOURCES_PER_SKILL: Final[int] = 512

#: Per-skill limit on the total size of the manifest's files, in bytes (16 MiB).
MAX_TOTAL_BYTES_PER_SKILL: Final[int] = 16 * 1024 * 1024

#: Scheme prefix for skill resource URIs.
SKILL_URI_PREFIX: Final[str] = "skill://"

#: Default ``skills/list`` page size.
DEFAULT_PAGE_SIZE: Final[int] = 50

_DIRECTORY_READ_METHOD: Final[str] = "resources/directory/read"
_LIST_METHOD: Final[str] = "skills/list"
_GET_METHOD: Final[str] = "skills/get"

#: Envelope fields that belong to the 2026-07-28 revisions only. A pre-2026
#: connection gets the payload without them; the SDK's own client strips the
#: same fields from a later revision's results for the same reason.
_LEGACY_OMITTED_FIELDS: Final[frozenset[str]] = frozenset({"result_type", "ttl_ms", "cache_scope"})

#: Capability setting a server that implements ``resources/directory/read`` declares.
_DIRECTORY_READ_SETTING: Final[str] = "directoryRead"

_CURSOR_PREFIX: Final[str] = "offset:"
_MAX_CURSOR_OFFSET: Final[int] = 1_000_000

_EXTRA_MIME_TYPES: Final[dict[str, str]] = {
    ".md": "text/markdown",
    ".mdx": "text/markdown",
    ".markdown": "text/markdown",
}

_TEXT_MIME_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/json",
        "application/ld+json",
        "application/toml",
        "application/x-yaml",
        "application/xml",
        "application/yaml",
        "image/svg+xml",
    }
)


# --------------------------------------------------------------------------- #
# Wire models
# --------------------------------------------------------------------------- #


class _WireModel(BaseModel):
    """camelCase-on-the-wire, snake_case-in-Python model base."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SkillResource(_WireModel):
    """A file belonging to a skill, with the digest and size of its content."""

    uri: str
    """Resource URI of the file."""

    digest: str
    """``sha256:{hex}`` digest of the file's raw bytes."""

    size: int
    """Length in bytes of the file's raw content (the bytes ``digest`` covers)."""


class Skill(_WireModel):
    """One skill entry, identical in shape from ``skills/list`` and ``skills/get``."""

    uri: str
    """Resource URI of the skill's ``SKILL.md``."""

    frontmatter: dict[str, Any]
    """The ``SKILL.md`` YAML frontmatter, rendered verbatim as a JSON object."""

    resources: list[SkillResource] | Literal["dynamic"]
    """Complete file manifest, or ``"dynamic"`` for generated content."""

    meta: dict[str, Any] | None = Field(default=None, alias="_meta")
    """Optional ``_meta`` object, passed through unchanged."""


class DirectoryEntry(_WireModel):
    """One direct child of a directory resource."""

    uri: str
    """Resource URI of the child."""

    name: str
    """Display name of the child (its final path segment)."""

    mime_type: str
    """MIME type; subdirectories use :data:`DIRECTORY_MIME_TYPE`."""


class ListSkillsParams(RequestParams):
    """``skills/list`` parameters."""

    cursor: str | None = None
    """Opaque pagination cursor from a previous result's ``nextCursor``."""


class GetSkillParams(RequestParams):
    """``skills/get`` parameters."""

    uri: str
    """URI of the skill's ``SKILL.md``."""


class ReadDirectoryParams(RequestParams):
    """``resources/directory/read`` parameters."""

    uri: str
    """URI of the directory resource."""

    cursor: str | None = None
    """Opaque pagination cursor from a previous result's ``nextCursor``."""


class ListSkillsResult(Result):
    """``skills/list`` result."""

    result_type: Literal["complete"] = "complete"
    skills: list[Skill]
    next_cursor: str | None = None
    ttl_ms: int = 0
    cache_scope: Literal["public", "private"] = "private"


class GetSkillResult(Result):
    """``skills/get`` result."""

    result_type: Literal["complete"] = "complete"
    skill: Skill
    ttl_ms: int = 0
    cache_scope: Literal["public", "private"] = "private"


class ReadDirectoryResult(Result):
    """``resources/directory/read`` result."""

    result_type: Literal["complete"] = "complete"
    resources: list[DirectoryEntry]
    next_cursor: str | None = None
    ttl_ms: int = 0
    cache_scope: Literal["public", "private"] = "private"


# --------------------------------------------------------------------------- #
# Protocol-era helpers
# --------------------------------------------------------------------------- #


def _is_modern_era(ctx: ServerRequestContext[Any, Any]) -> bool:
    """Whether *ctx* speaks a modern (2026-07-28+) protocol revision."""
    return getattr(ctx, "protocol_version", None) in MODERN_PROTOCOL_VERSIONS


def _result_for_era(result: Result, ctx: ServerRequestContext[Any, Any]) -> HandlerResult:
    """Return *result*, or its pre-2026 payload when *ctx* is a legacy connection.

    ``ttlMs``, ``cacheScope`` and ``resultType`` were introduced by the
    2026-07-28 revision; a legacy peer must not see them, so on a legacy
    connection the result is dumped to a dict without those keys. The dict is
    what the server serializes verbatim (``mcp.server.runner._dump_result``).
    """
    if _is_modern_era(ctx):
        return result
    return result.model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
        exclude=set(_LEGACY_OMITTED_FIELDS),
    )


def _encode_cursor(offset: int) -> str:
    return f"{_CURSOR_PREFIX}{offset}"


def _decode_cursor(cursor: str | None) -> int:
    """Decode a pagination cursor, rejecting anything this server did not mint."""
    if cursor is None:
        return 0
    if not cursor.startswith(_CURSOR_PREFIX):
        raise MCPError(types.INVALID_PARAMS, f"invalid cursor: {cursor!r}")
    raw = cursor[len(_CURSOR_PREFIX) :]
    if not raw.isdigit() or int(raw) > _MAX_CURSOR_OFFSET:
        raise MCPError(types.INVALID_PARAMS, f"invalid cursor: {cursor!r}")
    return int(raw)


_PageT = TypeVar("_PageT")


def _paginate(
    items: Sequence[_PageT], offset: int, page_size: int
) -> tuple[list[_PageT], str | None]:
    """Slice one page out of *items* and report the cursor for the next page."""
    page = list(items[offset : offset + page_size])
    consumed = offset + len(page)
    return page, (_encode_cursor(consumed) if consumed < len(items) else None)


# --------------------------------------------------------------------------- #
# Extension
# --------------------------------------------------------------------------- #

#: Protocol revisions the extension's methods are served at (SEP-2640 targets 2026-07-28+).
_MODERN_VERSIONS: Final[frozenset[str]] = frozenset(MODERN_PROTOCOL_VERSIONS)


class SkillsExtension(Extension):
    """The ``io.modelcontextprotocol/skills`` extension, served from a catalog.

    Args:
        catalog: The skills this server publishes.
        read_directory: Advertise and implement ``resources/directory/read``.
        page_size: Maximum entries per ``skills/list`` page.
        ttl_ms: Cache lifetime hint for results (``0`` = immediately stale).
        cache_scope: ``"private"`` (default) or ``"public"`` cache scope.

    Example:
        >>> catalog = SkillCatalog.from_directory(Path("skills"))  # doctest: +SKIP
        >>> extension = SkillsExtension(catalog, read_directory=True)  # doctest: +SKIP
    """

    identifier = SKILLS_EXTENSION_ID

    def __init__(
        self,
        catalog: SkillCatalog,
        *,
        read_directory: bool = False,
        page_size: int = DEFAULT_PAGE_SIZE,
        ttl_ms: int = 0,
        cache_scope: Literal["public", "private"] = "private",
    ) -> None:
        if page_size < 1:
            raise ValueError(f"page_size must be >= 1, got {page_size}")
        if ttl_ms < 0:
            raise ValueError(f"ttl_ms must be >= 0, got {ttl_ms}")
        self._catalog = catalog
        self._read_directory = read_directory
        self._page_size = page_size
        self._ttl_ms = ttl_ms
        self._cache_scope = cache_scope

    @property
    def catalog(self) -> SkillCatalog:
        """The catalog this extension serves (also used to register resources)."""
        return self._catalog

    def settings(self) -> dict[str, Any]:
        """Advertise ``directoryRead`` only when directory reads are enabled."""
        return {_DIRECTORY_READ_SETTING: True} if self._read_directory else {}

    def methods(self) -> Sequence[MethodBinding]:
        """The extension's request methods.

        All three are restricted to modern protocol revisions: SEP-2640 is
        specified against 2026-07-28+, and the extension is only advertised
        through ``server/discover``. A legacy request therefore fails with
        METHOD_NOT_FOUND rather than getting a half-shaped result.
        """
        bindings = [
            MethodBinding(
                _LIST_METHOD, ListSkillsParams, self._handle_list_skills, _MODERN_VERSIONS
            ),
            MethodBinding(_GET_METHOD, GetSkillParams, self._handle_get_skill, _MODERN_VERSIONS),
        ]
        if self._read_directory:
            bindings.append(
                MethodBinding(
                    _DIRECTORY_READ_METHOD,
                    ReadDirectoryParams,
                    self._handle_read_directory,
                    _MODERN_VERSIONS,
                )
            )
        return bindings

    async def _handle_list_skills(
        self, ctx: ServerRequestContext[Any, Any], params: ListSkillsParams
    ) -> HandlerResult:
        require_client_extension(ctx, self.identifier)
        page, next_cursor = _paginate(
            self._catalog.skills(), _decode_cursor(params.cursor), self._page_size
        )
        return _result_for_era(
            ListSkillsResult(
                skills=page,
                next_cursor=next_cursor,
                ttl_ms=self._ttl_ms,
                cache_scope=self._cache_scope,
            ),
            ctx,
        )

    async def _handle_get_skill(
        self, ctx: ServerRequestContext[Any, Any], params: GetSkillParams
    ) -> HandlerResult:
        require_client_extension(ctx, self.identifier)
        skill = self._catalog.get(params.uri)
        if skill is None:
            raise MCPError(types.INVALID_PARAMS, f"unknown skill: {params.uri}")
        return _result_for_era(
            GetSkillResult(skill=skill, ttl_ms=self._ttl_ms, cache_scope=self._cache_scope),
            ctx,
        )

    async def _handle_read_directory(
        self, ctx: ServerRequestContext[Any, Any], params: ReadDirectoryParams
    ) -> HandlerResult:
        require_client_extension(ctx, self.identifier)
        entries = self._catalog.list_directory(params.uri)
        if entries is None:
            raise MCPError(types.INVALID_PARAMS, f"not a directory resource: {params.uri}")
        page, next_cursor = _paginate(entries, _decode_cursor(params.cursor), self._page_size)
        return _result_for_era(
            ReadDirectoryResult(
                resources=page,
                next_cursor=next_cursor,
                ttl_ms=self._ttl_ms,
                cache_scope=self._cache_scope,
            ),
            ctx,
        )


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _FileEntry:
    """One served file: its raw bytes and the MIME type derived from its name."""

    data: bytes
    mime_type: str


class SkillCatalog:
    """A directory of skills, validated and manifested at construction time.

    Each direct child directory of *root* that contains a ``SKILL.md`` is a
    skill. Invalid skills raise :class:`ValueError` naming the offending path —
    a silently dropped skill would be a silent correctness failure at the host.

    Files are read once, so the manifest's digests describe exactly the bytes
    :meth:`read` serves afterward.
    """

    def __init__(self, root: Path) -> None:
        root = Path(root)
        if not root.is_dir():
            raise ValueError(f"skill catalog root is not a directory: {root}")
        self._root = root
        self._skills: dict[str, Skill] = {}
        self._files: dict[tuple[str, str], _FileEntry] = {}
        self._directories: dict[str, list[DirectoryEntry]] = {}

        for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            if not (skill_dir / SKILL_MD).is_file():
                continue
            self._load_skill(skill_dir)

    @classmethod
    def from_directory(cls, root: Path) -> SkillCatalog:
        """Build a catalog from *root* (alias for ``cls(root)``)."""
        return cls(root)

    @classmethod
    def empty(cls, root: Path) -> SkillCatalog:
        """Build an empty catalog rooted at *root*.

        Unlike ``cls(root)``, *root* need not exist: a server whose packaged
        skills directory was never populated still publishes a (empty) catalog
        instead of failing at startup.

        Args:
            root: The directory the catalog would have been built from.

        Returns:
            A catalog with no skills, no files and no directories.
        """
        catalog = cls.__new__(cls)
        catalog._root = Path(root)
        catalog._skills = {}
        catalog._files = {}
        catalog._directories = {}
        return catalog

    # -- public surface ---------------------------------------------------- #

    @property
    def root(self) -> Path:
        """The directory the catalog was built from."""
        return self._root

    def skills(self) -> list[Skill]:
        """Every skill, ordered by name (a stable ``skills/list`` order)."""
        return [self._skills[name].model_copy(deep=True) for name in sorted(self._skills)]

    def get(self, uri: str) -> Skill | None:
        """The skill whose ``SKILL.md`` is *uri*, or ``None`` when unknown."""
        try:
            name, relpath = _split_skill_uri(uri)
        except ValueError:
            return None
        if relpath != SKILL_MD:
            return None
        skill = self._skills.get(name)
        return skill.model_copy(deep=True) if skill is not None else None

    def list_resources(self) -> list[Resource]:
        """One ``Resource`` per served file, for the server's ``resources/list``."""
        resources: list[Resource] = []
        for name in sorted(self._skills):
            frontmatter = self._skills[name].frontmatter
            for relpath, entry in sorted(self._skill_files(name)):
                is_skill_md = relpath == SKILL_MD
                resources.append(
                    Resource(
                        uri=_file_uri(name, relpath),
                        name=(_frontmatter_str(frontmatter, "name") or name)
                        if is_skill_md
                        else relpath,
                        description=_frontmatter_str(frontmatter, "description")
                        if is_skill_md
                        else None,
                        mime_type=entry.mime_type,
                        size=len(entry.data),
                    )
                )
        return resources

    def mime_type(self, uri: str) -> str | None:
        """The MIME type of the file served at *uri*, or ``None`` when unknown.

        Mirrors :meth:`read`'s notion of a served file, so a successful lookup
        always pairs with a successful read.
        """
        try:
            name, relpath = _split_skill_uri(uri)
        except ValueError:
            return None
        entry = self._files.get((name, relpath))
        return entry.mime_type if entry is not None else None

    def list_directory(self, uri: str) -> list[DirectoryEntry] | None:
        """The direct children of the directory resource *uri*, or ``None``."""
        try:
            name, relpath = _split_skill_uri(uri)
        except ValueError:
            return None
        if name not in self._skills:
            return None
        entries = self._directories.get(_directory_uri(name, relpath))
        return list(entries) if entries is not None else None

    def read(self, uri: str) -> str | bytes:
        """Serve the file at *uri*.

        Returns ``str`` for text content and ``bytes`` otherwise.

        Raises:
            ValueError: *uri* is not a ``skill://`` URI, or it escapes the skill
                directory (``..``, an absolute path, a NUL byte, ...).
            KeyError: *uri* is well formed but the server serves no such file.
        """
        name, relpath = _split_skill_uri(uri)
        if not relpath:
            raise KeyError(f"not a file resource: {uri}")
        entry = self._files.get((name, relpath))
        if entry is None:
            raise KeyError(f"no such skill file: {uri}")
        if _is_text(entry.mime_type):
            return _decode_utf8(entry.data, uri)
        return entry.data

    # -- loading ----------------------------------------------------------- #

    def _load_skill(self, skill_dir: Path) -> None:
        skill_md_path = skill_dir / SKILL_MD
        skill_md_text = _read_text(skill_md_path)
        frontmatter = parse_frontmatter(skill_md_text, skill_md_path)

        name = frontmatter.get("name")
        description = frontmatter.get("description")
        if not isinstance(name, str) or not name:
            raise ValueError(
                f"{skill_md_path}: frontmatter field 'name' must be a non-empty string"
            )
        if not isinstance(description, str) or not description:
            raise ValueError(
                f"{skill_md_path}: frontmatter field 'description' must be a non-empty string"
            )
        _check_skill_name(name, skill_dir)
        if skill_dir.name != name:
            raise ValueError(
                f"{skill_dir}: skill directory name {skill_dir.name!r} does not match "
                f"frontmatter name {name!r}"
            )

        resolved_dir = skill_dir.resolve()
        files: dict[str, _FileEntry] = {}
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(resolved_dir):
                raise ValueError(f"{path}: resolves outside the skill directory {skill_dir}")
            relpath = path.relative_to(skill_dir).as_posix()
            _check_relative_path(relpath, path)
            data = path.read_bytes()
            files[relpath] = _FileEntry(data=data, mime_type=_guess_mime(relpath))

        if SKILL_MD not in files:
            raise ValueError(f"{skill_dir}: {SKILL_MD} could not be read")
        if len(files) > MAX_RESOURCES_PER_SKILL:
            raise ValueError(
                f"{skill_dir}: {len(files)} files exceeds the per-skill limit of {MAX_RESOURCES_PER_SKILL}"
            )
        total_bytes = sum(len(entry.data) for entry in files.values())
        if total_bytes > MAX_TOTAL_BYTES_PER_SKILL:
            raise ValueError(
                f"{skill_dir}: {total_bytes} bytes exceeds the per-skill limit of "
                f"{MAX_TOTAL_BYTES_PER_SKILL} bytes"
            )

        manifest = [
            SkillResource(
                uri=_file_uri(name, relpath),
                digest=f"sha256:{hashlib.sha256(entry.data).hexdigest()}",
                size=len(entry.data),
            )
            for relpath, entry in sorted(files.items())
        ]
        self._skills[name] = Skill(
            uri=_file_uri(name, SKILL_MD), frontmatter=frontmatter, resources=manifest
        )
        for relpath, entry in files.items():
            self._files[(name, relpath)] = entry
        self._index_skill_directories(name, files)

    def _index_skill_directories(self, name: str, files: dict[str, _FileEntry]) -> None:
        """Index every directory of the skill as a directory resource."""
        directories: set[str] = {""}
        for relpath in files:
            parts = relpath.split("/")
            for depth in range(1, len(parts)):
                directories.add("/".join(parts[:depth]))

        for relpath in directories:
            self._directories[_directory_uri(name, relpath)] = []

        for relpath, entry in files.items():
            parent, _, child = relpath.rpartition("/")
            self._directories[_directory_uri(name, parent)].append(
                DirectoryEntry(uri=_file_uri(name, relpath), name=child, mime_type=entry.mime_type)
            )
        for relpath in directories - {""}:
            parent, _, child = relpath.rpartition("/")
            self._directories[_directory_uri(name, parent)].append(
                DirectoryEntry(
                    uri=_directory_uri(name, relpath),
                    name=child,
                    mime_type=DIRECTORY_MIME_TYPE,
                )
            )
        for entries in self._directories.values():
            entries.sort(key=lambda entry: entry.name)

    def _skill_files(self, name: str) -> list[tuple[str, _FileEntry]]:
        return [
            (relpath, entry) for (skill, relpath), entry in self._files.items() if skill == name
        ]


# --------------------------------------------------------------------------- #
# URIs
# --------------------------------------------------------------------------- #


def _file_uri(name: str, relpath: str) -> str:
    return f"{SKILL_URI_PREFIX}{name}/{relpath}"


def _directory_uri(name: str, relpath: str) -> str:
    return f"{SKILL_URI_PREFIX}{name}/{relpath}" if relpath else f"{SKILL_URI_PREFIX}{name}"


def _split_skill_uri(uri: str) -> tuple[str, str]:
    """Split ``skill://<name>/<relpath>`` into ``(name, relpath)``, validating it.

    Percent-escapes are decoded *before* validation, so ``%2e%2e`` cannot slip
    a traversal segment past the check.

    Raises:
        ValueError: *uri* is not a skill URI, or its path escapes the skill
            directory.
    """
    if not isinstance(uri, str):
        raise ValueError(f"skill URI must be a string, got {type(uri).__name__}")
    raw = uri.strip()
    if not raw.startswith(SKILL_URI_PREFIX):
        raise ValueError(f"not a skill URI: {uri!r}")
    remainder = unquote(raw[len(SKILL_URI_PREFIX) :])
    name, separator, relpath = remainder.partition("/")
    if not name:
        raise ValueError(f"skill URI has no skill name: {uri!r}")
    _check_skill_name(name, uri)
    if separator and relpath:
        _check_relative_path(relpath, uri)
    return name, relpath


_SEGMENT_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _check_skill_name(name: str, source: object) -> None:
    """Reject a skill name that is not a single safe URI path segment."""
    if name in {".", ".."} or not _SEGMENT_RE.match(name):
        raise ValueError(f"{source}: invalid skill name {name!r}")


def _check_relative_path(relpath: str, source: object) -> None:
    """Reject an absolute, traversal or otherwise unsafe relative path."""
    if "\x00" in relpath:
        raise ValueError(f"{source}: path contains a NUL byte")
    if relpath.startswith("/") or relpath.startswith("\\"):
        raise ValueError(f"{source}: absolute paths are not allowed")
    if "\\" in relpath:
        raise ValueError(f"{source}: backslashes are not allowed in skill paths")
    if re.match(r"^[A-Za-z]:", relpath):
        raise ValueError(f"{source}: drive-qualified paths are not allowed")
    for part in relpath.split("/"):
        if part in {"", ".", ".."}:
            raise ValueError(f"{source}: unsafe path segment {part!r}")


# --------------------------------------------------------------------------- #
# File helpers
# --------------------------------------------------------------------------- #


def _guess_mime(relpath: str) -> str:
    suffix = Path(relpath).suffix.lower()
    if (mime := _EXTRA_MIME_TYPES.get(suffix)) is not None:
        return mime
    guessed, _ = mimetypes.guess_type(relpath)
    return guessed or "application/octet-stream"


def _is_text(mime_type: str) -> bool:
    return mime_type.startswith("text/") or mime_type in _TEXT_MIME_TYPES


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _frontmatter_str(frontmatter: dict[str, Any], key: str) -> str | None:
    return _str_or_none(frontmatter.get(key))


def _read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: SKILL.md must be UTF-8 text") from exc


def _decode_utf8(data: bytes, source: object) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{source}: content is not valid UTF-8") from exc


# --------------------------------------------------------------------------- #
# Frontmatter
# --------------------------------------------------------------------------- #

_DELIMITER: Final[str] = "---"
_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z0-9_.-]+):(?:[ \t]+(.*))?$")
_LIST_ITEM_RE: Final[re.Pattern[str]] = re.compile(r"^-(?:[ \t]+(.*))?$")
_INT_RE: Final[re.Pattern[str]] = re.compile(r"^[+-]?[0-9]+$")
_FLOAT_RE: Final[re.Pattern[str]] = re.compile(
    r"^[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)
_UNSUPPORTED_PREFIXES: Final[tuple[str, ...]] = ("&", "*", "!", "%", "@", "`", "|", ">", "{")
_NULL_TOKENS: Final[frozenset[str]] = frozenset({"~", "null", "Null", "NULL"})


def parse_frontmatter(text: str, source: object = "<frontmatter>") -> dict[str, Any]:
    """Parse the YAML frontmatter block at the top of *text*.

    Only the subset Agent Skills frontmatter uses is implemented, without a YAML
    dependency: ``key: value`` scalars (plain, single- or double-quoted), simple
    lists (block ``- item`` form and inline ``[a, b]``), and one level of nested
    mapping (as used by ``metadata:``). Anything else — block scalars, anchors,
    aliases, tags, flow mappings, deeper nesting, tab indentation — raises
    :class:`ValueError` instead of being guessed at.

    Args:
        text: Full text of a ``SKILL.md``.
        source: Path (or label) used in error messages.

    Returns:
        The frontmatter as a JSON-compatible dict.

    Raises:
        ValueError: The block is missing, unterminated, or outside the subset.
    """
    lines = text.splitlines()
    if not lines:
        raise ValueError(f"{source}: empty document, expected YAML frontmatter")
    if lines[0].lstrip("\ufeff").strip() != _DELIMITER:
        raise ValueError(f"{source}: SKILL.md must start with '{_DELIMITER}' YAML frontmatter")
    for end, line in enumerate(lines[1:], start=1):
        if line.strip() in {_DELIMITER, "..."}:
            return _parse_block(lines[1:end], source)
    raise ValueError(f"{source}: unterminated YAML frontmatter block")


def _parse_block(lines: Sequence[str], source: object) -> dict[str, Any]:
    """Parse top-level ``key: value`` pairs, descending one level for blocks."""
    result: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line[0] in {" ", "\t"}:
            raise ValueError(f"{source}: unexpected indentation in frontmatter: {line!r}")
        match = _KEY_RE.match(line.rstrip())
        if match is None:
            raise ValueError(f"{source}: cannot parse frontmatter line: {line!r}")
        key, raw_value = match.group(1), (match.group(2) or "").strip()
        index += 1
        if raw_value:
            result[key] = _parse_scalar(raw_value, source)
            continue

        block: list[str] = []
        while index < len(lines) and (not lines[index].strip() or lines[index][0] in {" ", "\t"}):
            block.append(lines[index])
            index += 1
        while block and not block[-1].strip():
            block.pop()
        result[key] = _parse_indented(block, source, key) if block else None
    return result


def _parse_indented(block: Sequence[str], source: object, key: str) -> Any:
    """Parse an indented block following ``key:`` as a list or a nested mapping."""
    indentation = [len(line) - len(line.lstrip()) for line in block]
    if any("\t" in line[:size] for line, size in zip(block, indentation)):
        raise ValueError(f"{source}: tab indentation is not supported (in {key!r})")

    content = [line for line in block if line.strip() and not line.lstrip().startswith("#")]
    if not content:
        return None

    indent = min(len(line) - len(line.lstrip()) for line in content)
    values = [line[indent:] for line in content]
    if all(_LIST_ITEM_RE.match(value) for value in values):
        items: list[Any] = []
        for value in values:
            item = _LIST_ITEM_RE.match(value)
            assert item is not None  # narrowed by the all() above
            raw_item = (item.group(1) or "").strip()
            items.append(_parse_scalar(raw_item, source) if raw_item else None)
        return items

    nested: dict[str, Any] = {}
    for value in values:
        match = _KEY_RE.match(value.rstrip())
        if match is None or not (match.group(2) or "").strip():
            raise ValueError(
                f"{source}: cannot parse nested frontmatter under {key!r}: {value!r} "
                "(only one level of 'key: value' mappings is supported)"
            )
        nested[match.group(1)] = _parse_scalar(match.group(2).strip(), source)
    return nested


def _parse_scalar(raw: str, source: object) -> Any:
    """Parse one scalar or inline list; raise on anything outside the subset."""
    value = _strip_trailing_comment(raw).strip()
    if not value:
        return None
    if value.startswith("{"):
        if value == "{}":
            return {}
        raise ValueError(f"{source}: flow mappings are not supported in frontmatter: {value!r}")
    if value[0] in _UNSUPPORTED_PREFIXES:
        raise ValueError(f"{source}: unsupported YAML construct in frontmatter: {value!r}")
    if value.startswith("["):
        if not value.endswith("]"):
            raise ValueError(f"{source}: unterminated inline list in frontmatter: {value!r}")
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip(), source) for item in _split_flow_items(inner, source)]
    if value.startswith('"'):
        if len(value) < 2 or not value.endswith('"'):
            raise ValueError(f"{source}: unterminated double-quoted value: {value!r}")
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}: invalid double-quoted value: {value!r}") from exc
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise ValueError(f"{source}: unterminated single-quoted value: {value!r}")
        return value[1:-1].replace("''", "'")
    if value in _NULL_TOKENS:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if _INT_RE.match(value):
        return int(value)
    if _FLOAT_RE.match(value):
        return float(value)
    return value


def _strip_trailing_comment(raw: str) -> str:
    """Drop a YAML trailing ``# comment`` from a plain (unquoted) scalar."""
    if raw.startswith(('"', "'")):
        return raw
    for index, char in enumerate(raw):
        if char == "#" and index > 0 and raw[index - 1] in {" ", "\t"}:
            return raw[:index].rstrip()
    return raw


def _split_flow_items(inner: str, source: object) -> list[str]:
    """Split an inline list body on commas that are not inside quotes."""
    items: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    for char in inner:
        if quote is not None:
            buffer.append(char)
            if char == quote:
                quote = None
        elif char in {'"', "'"}:
            quote = char
            buffer.append(char)
        elif char == ",":
            items.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
    if quote is not None:
        raise ValueError(f"{source}: unterminated quoted item in inline list: {inner!r}")
    items.append("".join(buffer))
    return items


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "DIRECTORY_MIME_TYPE",
    "MAX_RESOURCES_PER_SKILL",
    "MAX_TOTAL_BYTES_PER_SKILL",
    "SKILLS_EXTENSION_ID",
    "SKILL_MD",
    "SKILL_URI_PREFIX",
    "DirectoryEntry",
    "GetSkillParams",
    "GetSkillResult",
    "ListSkillsParams",
    "ListSkillsResult",
    "ReadDirectoryParams",
    "ReadDirectoryResult",
    "Skill",
    "SkillCatalog",
    "SkillResource",
    "SkillsExtension",
    "parse_frontmatter",
]
