"""Tests for the ``io.modelcontextprotocol/skills`` extension (SEP-2640).

Covers the catalog (frontmatter parsing, manifest digests, limits, path
safety), the extension's request handlers, registration on the lowlevel
``Server``, protocol-version gating, and the real wire shape on both the
2026-07-28 and the legacy (2025-11-25) eras.
"""

from __future__ import annotations

import hashlib
import re
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import anyio
import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.server.extension import Extension, MethodBinding
from mcp.server.lowlevel import Server
from mcp.server.models import InitializationOptions
from mcp.shared.exceptions import MCPError
from mcp.shared.memory import create_client_server_memory_streams
from pydantic import Field, TypeAdapter

from ninja_common.mcp_ext.apply import apply_extensions
from ninja_common.mcp_ext.skills import (
    DIRECTORY_MIME_TYPE,
    SKILLS_EXTENSION_ID,
    GetSkillParams,
    GetSkillResult,
    ListSkillsParams,
    ListSkillsResult,
    ReadDirectoryParams,
    SkillCatalog,
    SkillsExtension,
)


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


MODERN_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"

_DICT_ADAPTER: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])

ALPHA_MD = (
    "---\nname: alpha\ndescription: Alpha skill for the tests\nlicense: MIT\n---\n\n# Alpha\n"
)
BETA_MD = "---\nname: beta\ndescription: Beta skill\n---\n\n# Beta\n"
GAMMA_MD = "---\nname: gamma\ndescription: Gamma skill\n---\n\n# Gamma\n"

ALPHA_FILES = {
    "references/checklist.md": "# Checklist\n\n- one\n- two\n",
    "scripts/run.py": "print('hi')\n",
    "assets/logo.txt": "not a markdown file\n",
}
ALPHA_MANIFEST = {
    "SKILL.md": ALPHA_MD.encode(),
    **{path: body.encode() for path, body in ALPHA_FILES.items()},
}


# --------------------------------------------------------------------------- #
# Fixtures and helpers
# --------------------------------------------------------------------------- #


def _write_skill(root: Path, name: str, skill_md: str, files: dict[str, str] | None = None) -> Path:
    """Materialise one skill directory under *root*."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    for relpath, body in (files or {}).items():
        target = skill_dir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return skill_dir


@pytest.fixture
def catalog_root(tmp_path: Path) -> Path:
    """A catalog with three skills plus a directory that is not a skill."""
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "alpha", ALPHA_MD, ALPHA_FILES)
    _write_skill(root, "beta", BETA_MD)
    _write_skill(root, "gamma", GAMMA_MD)
    (root / "not-a-skill").mkdir()
    (root / "not-a-skill" / "README.md").write_text("no SKILL.md here\n", encoding="utf-8")
    return root


@pytest.fixture
def catalog(catalog_root: Path) -> SkillCatalog:
    return SkillCatalog.from_directory(catalog_root)


def _fake_ctx(protocol_version: str, *, declare_extension: bool = True) -> Any:
    """A ``ServerRequestContext`` stand-in exposing only what handlers read."""
    extensions = {SKILLS_EXTENSION_ID: {}} if declare_extension else None
    session = SimpleNamespace(client_capabilities=types.ClientCapabilities(extensions=extensions))
    return SimpleNamespace(protocol_version=protocol_version, session=session)


async def _invoke(binding: MethodBinding, ctx: Any, params: dict[str, Any]) -> Any:
    """Validate *params* and run *binding*'s raw handler (no version gate)."""
    validated = binding.params_type.model_validate(params)
    return await binding.handler(ctx, validated)


def _binding(extension: SkillsExtension, method: str) -> MethodBinding:
    for binding in extension.methods():
        if binding.method == method:
            return binding
    raise AssertionError(f"extension has no {method} binding")


class _RawRequest(types.Request[dict[str, Any], str]):
    """Requests a method the client SDK has no typed helper for."""

    params: dict[str, Any] = Field(default_factory=dict)


class _Tap:
    """Write-stream wrapper recording everything the server sends."""

    def __init__(self, inner: Any, sink: list[dict[str, Any]]) -> None:
        self._inner = inner
        self._sink = sink

    async def send(self, item: Any, /) -> None:
        message = item.message
        self._sink.append(message.model_dump(by_alias=True, mode="json", exclude_none=True))
        await self._inner.send(item)

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> _Tap:
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc_info: object) -> Any:
        return await self._inner.__aexit__(*exc_info)


@asynccontextmanager
async def _connected(
    extension: SkillsExtension,
    *,
    declare_extension: bool = True,
    wire: list[dict[str, Any]] | None = None,
) -> AsyncIterator[ClientSession]:
    """Serve *extension* over an in-memory stream pair and yield a client session."""
    server: Server[Any] = Server("skills-test")
    apply_extensions(server, [extension])
    init_options = InitializationOptions(
        server_name="skills-test",
        server_version="1.0.0",
        capabilities=types.ServerCapabilities(),
    )
    client_extensions = {extension.identifier: {}} if declare_extension else None
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        write_stream = _Tap(server_streams[1], wire) if wire is not None else server_streams[1]
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(server.run, server_streams[0], write_stream, init_options)
            async with ClientSession(
                client_streams[0], client_streams[1], extensions=client_extensions
            ) as session:
                try:
                    yield session
                finally:
                    task_group.cancel_scope.cancel()


def _wire_result(wire: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """The single JSON-RPC response on *wire* whose result carries *key*."""
    matches = [message["result"] for message in wire if key in message.get("result", {})]
    assert len(matches) == 1, f"expected exactly one {key!r} response, got {len(matches)}"
    return matches[0]


def _wire_error(wire: list[dict[str, Any]]) -> dict[str, Any]:
    """The single JSON-RPC error on *wire*."""
    matches = [message["error"] for message in wire if "error" in message]
    assert len(matches) == 1, f"expected exactly one error response, got {len(matches)}"
    return matches[0]


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #


def test_manifest_matches_served_bytes(catalog: SkillCatalog) -> None:
    skill = catalog.get("skill://alpha/SKILL.md")
    assert skill is not None
    assert skill.uri == "skill://alpha/SKILL.md"
    assert skill.frontmatter == {
        "name": "alpha",
        "description": "Alpha skill for the tests",
        "license": "MIT",
    }
    assert isinstance(skill.resources, list)
    manifest = {resource.uri: (resource.digest, resource.size) for resource in skill.resources}
    assert set(manifest) == {f"skill://alpha/{relpath}" for relpath in ALPHA_MANIFEST}

    for relpath, raw in ALPHA_MANIFEST.items():
        expected_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        assert manifest[f"skill://alpha/{relpath}"] == (expected_digest, len(raw))
        assert catalog.read(f"skill://alpha/{relpath}") in (raw.decode(), raw)


def test_skills_are_sorted_and_directories_are_skipped(catalog: SkillCatalog) -> None:
    assert [skill.frontmatter["name"] for skill in catalog.skills()] == ["alpha", "beta", "gamma"]
    assert catalog.get("skill://not-a-skill/SKILL.md") is None


def test_list_resources_describes_every_file(catalog: SkillCatalog) -> None:
    resources = {resource.uri: resource for resource in catalog.list_resources()}
    assert len(resources) == 4 + 1 + 1  # alpha (SKILL.md + 3 files), beta, gamma

    skill_md = resources["skill://alpha/SKILL.md"]
    assert skill_md.name == "alpha"
    assert skill_md.description == "Alpha skill for the tests"
    assert skill_md.mime_type == "text/markdown"
    assert skill_md.size == len(ALPHA_MANIFEST["SKILL.md"])

    checklist = resources["skill://alpha/references/checklist.md"]
    assert checklist.mime_type == "text/markdown"
    assert checklist.size == len(ALPHA_MANIFEST["references/checklist.md"])


def test_directory_listing_includes_subdirectories(catalog: SkillCatalog) -> None:
    root_entries = catalog.list_directory("skill://alpha")
    assert root_entries is not None
    by_name = {entry.name: entry for entry in root_entries}
    assert by_name["SKILL.md"].mime_type == "text/markdown"
    assert by_name["references"].mime_type == DIRECTORY_MIME_TYPE
    assert by_name["references"].uri == "skill://alpha/references"

    nested = catalog.list_directory("skill://alpha/references")
    assert nested is not None
    assert [(entry.name, entry.mime_type) for entry in nested] == [
        ("checklist.md", "text/markdown")
    ]

    assert catalog.list_directory("skill://alpha/nope") is None
    assert catalog.list_directory("skill://alpha/SKILL.md") is None


@pytest.mark.parametrize(
    ("skill_md", "expected"),
    [
        pytest.param("# No frontmatter\n", "must start with", id="missing-frontmatter"),
        pytest.param("---\ndescription: no name here\n---\n", "field 'name'", id="missing-name"),
        pytest.param("---\nname: broken\n---\n", "field 'description'", id="missing-description"),
        pytest.param(
            "---\nname: other\ndescription: mismatched\n---\n",
            "does not match",
            id="dir-name-mismatch",
        ),
        pytest.param(
            "---\nname: broken\ndescription: >\n  folded\n---\n",
            "unsupported YAML",
            id="block-scalar",
        ),
    ],
)
def test_invalid_skills_raise_with_the_offending_path(
    tmp_path: Path, skill_md: str, expected: str
) -> None:
    skill_dir = tmp_path / "catalog" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    with pytest.raises(ValueError, match=re.escape(str(skill_dir))) as excinfo:
        SkillCatalog(tmp_path / "catalog")
    assert expected in str(excinfo.value)


def test_frontmatter_parses_lists_and_nested_metadata(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    _write_skill(
        root,
        "rich",
        "---\n"
        "name: rich\n"
        "description: 'Quoted: description'\n"
        "metadata:\n"
        "  author: acme\n"
        "  version: 1.5\n"
        "allowed-tools:\n"
        "  - read\n"
        "  - write\n"
        'tags: [docs, "two words"]\n'
        "---\n\n# Rich\n",
    )
    skill = SkillCatalog(root).get("skill://rich/SKILL.md")
    assert skill is not None
    assert skill.frontmatter == {
        "name": "rich",
        "description": "Quoted: description",
        "metadata": {"author": "acme", "version": 1.5},
        "allowed-tools": ["read", "write"],
        "tags": ["docs", "two words"],
    }


@pytest.mark.parametrize(
    "uri",
    [
        "skill://alpha/../../etc/passwd",
        "skill://alpha/%2e%2e/%2e%2e/etc/passwd",
        "skill://alpha//etc/passwd",
        "skill://alpha/references/../../../etc/passwd",
        "skill://../SKILL.md",
        "file:///etc/passwd",
    ],
)
def test_read_rejects_path_traversal(catalog: SkillCatalog, uri: str) -> None:
    with pytest.raises(ValueError):
        catalog.read(uri)


def test_read_rejects_unknown_but_well_formed_files(catalog: SkillCatalog) -> None:
    with pytest.raises(KeyError):
        catalog.read("skill://alpha/references/missing.md")


# --------------------------------------------------------------------------- #
# Extension handlers
# --------------------------------------------------------------------------- #


def test_directory_read_setting_and_method_surface(catalog: SkillCatalog) -> None:
    enabled = SkillsExtension(catalog, read_directory=True)
    disabled = SkillsExtension(catalog)

    assert enabled.settings() == {"directoryRead": True}
    assert disabled.settings() == {}
    assert {binding.method for binding in enabled.methods()} == {
        "skills/list",
        "skills/get",
        "resources/directory/read",
    }
    assert {binding.method for binding in disabled.methods()} == {"skills/list", "skills/get"}

    server: Server[Any] = Server("skills-no-directory")
    apply_extensions(server, [disabled])
    assert server.get_request_handler("resources/directory/read") is None
    assert server.extensions == {SKILLS_EXTENSION_ID: {}}


async def test_skills_get_unknown_uri_is_invalid_params(catalog: SkillCatalog) -> None:
    extension = SkillsExtension(catalog)
    binding = _binding(extension, "skills/get")

    found = await _invoke(binding, _fake_ctx(MODERN_VERSION), {"uri": "skill://alpha/SKILL.md"})
    assert isinstance(found, GetSkillResult)
    assert found.skill.frontmatter["name"] == "alpha"
    assert found.ttl_ms == 0
    assert found.cache_scope == "private"

    with pytest.raises(MCPError) as excinfo:
        await _invoke(binding, _fake_ctx(MODERN_VERSION), {"uri": "skill://missing/SKILL.md"})
    assert excinfo.value.code == types.INVALID_PARAMS
    assert excinfo.value.message == "unknown skill: skill://missing/SKILL.md"


async def test_skills_list_paginates_with_next_cursor(catalog: SkillCatalog) -> None:
    extension = SkillsExtension(catalog, page_size=2)
    binding = _binding(extension, "skills/list")
    ctx = _fake_ctx(MODERN_VERSION)

    first = await _invoke(binding, ctx, {})
    assert isinstance(first, ListSkillsResult)
    assert [skill.frontmatter["name"] for skill in first.skills] == ["alpha", "beta"]
    assert first.next_cursor is not None

    second = await _invoke(binding, ctx, {"cursor": first.next_cursor})
    assert isinstance(second, ListSkillsResult)
    assert [skill.frontmatter["name"] for skill in second.skills] == ["gamma"]
    assert second.next_cursor is None

    with pytest.raises(MCPError) as excinfo:
        await _invoke(binding, ctx, {"cursor": "not-a-cursor"})
    assert excinfo.value.code == types.INVALID_PARAMS


async def test_directory_read_lists_children(catalog: SkillCatalog) -> None:
    binding = _binding(SkillsExtension(catalog, read_directory=True), "resources/directory/read")
    result = await _invoke(binding, _fake_ctx(MODERN_VERSION), {"uri": "skill://alpha"})
    names = {entry.name for entry in result.resources}
    assert names == {"SKILL.md", "references", "scripts", "assets"}

    with pytest.raises(MCPError) as excinfo:
        await _invoke(binding, _fake_ctx(MODERN_VERSION), {"uri": "skill://alpha/SKILL.md"})
    assert excinfo.value.code == types.INVALID_PARAMS


async def test_results_drop_2026_envelope_fields_on_a_legacy_era(catalog: SkillCatalog) -> None:
    extension = SkillsExtension(catalog)
    payload = await _invoke(_binding(extension, "skills/list"), _fake_ctx(LEGACY_VERSION), {})
    assert isinstance(payload, dict)
    assert set(payload) == {"skills"}
    assert "ttlMs" not in payload
    assert "cacheScope" not in payload
    assert "resultType" not in payload
    assert payload["skills"][0]["uri"] == "skill://alpha/SKILL.md"

    modern = await _invoke(_binding(extension, "skills/list"), _fake_ctx(MODERN_VERSION), {})
    assert isinstance(modern, ListSkillsResult)
    assert modern.model_dump(by_alias=True, exclude_none=True)["resultType"] == "complete"


async def test_handlers_require_the_client_extension(catalog: SkillCatalog) -> None:
    extension = SkillsExtension(catalog)
    ctx = _fake_ctx(MODERN_VERSION, declare_extension=False)
    with pytest.raises(MCPError) as excinfo:
        await _invoke(_binding(extension, "skills/list"), ctx, {})
    assert excinfo.value.code == types.MISSING_REQUIRED_CLIENT_CAPABILITY


# --------------------------------------------------------------------------- #
# Registration and version gating
# --------------------------------------------------------------------------- #


class _DuplicateListMethod(Extension):
    identifier = "com.example/duplicate"

    def methods(self) -> list[MethodBinding]:
        return [MethodBinding("skills/list", ListSkillsParams, _noop_list)]


async def _noop_list(ctx: Any, params: Any) -> dict[str, Any]:
    return {}


def test_apply_extensions_registers_methods_and_settings(catalog: SkillCatalog) -> None:
    server: Server[Any] = Server("skills")
    apply_extensions(server, [SkillsExtension(catalog, read_directory=True)])

    assert server.extensions == {SKILLS_EXTENSION_ID: {"directoryRead": True}}
    list_entry = server.get_request_handler("skills/list")
    assert list_entry is not None
    assert list_entry.params_type is ListSkillsParams
    get_entry = server.get_request_handler("skills/get")
    assert get_entry is not None
    assert get_entry.params_type is GetSkillParams
    directory_entry = server.get_request_handler("resources/directory/read")
    assert directory_entry is not None
    assert directory_entry.params_type is ReadDirectoryParams


def test_apply_extensions_refuses_to_replace_an_existing_handler(catalog: SkillCatalog) -> None:
    server: Server[Any] = Server("skills")
    apply_extensions(server, [SkillsExtension(catalog)])

    with pytest.raises(ValueError, match="skills/list") as excinfo:
        apply_extensions(server, [_DuplicateListMethod()])
    assert "com.example/duplicate" in str(excinfo.value)


def test_apply_extensions_refuses_duplicate_identifiers(catalog: SkillCatalog) -> None:
    server: Server[Any] = Server("skills")
    apply_extensions(server, [SkillsExtension(catalog)])
    with pytest.raises(ValueError, match="already registered"):
        apply_extensions(server, [SkillsExtension(catalog)])


async def test_skills_list_is_gated_to_modern_protocol_versions(catalog: SkillCatalog) -> None:
    server: Server[Any] = Server("skills")
    apply_extensions(server, [SkillsExtension(catalog)])
    entry = server.get_request_handler("skills/list")
    assert entry is not None

    with pytest.raises(MCPError) as excinfo:
        await entry.handler(_fake_ctx(LEGACY_VERSION), ListSkillsParams())
    assert excinfo.value.code == types.METHOD_NOT_FOUND
    assert excinfo.value.data == "skills/list"

    served = await entry.handler(_fake_ctx(MODERN_VERSION), ListSkillsParams())
    assert isinstance(served, ListSkillsResult)


# --------------------------------------------------------------------------- #
# Wire-level behaviour
# --------------------------------------------------------------------------- #


async def test_wire_modern_skills_list(catalog: SkillCatalog) -> None:
    wire: list[dict[str, Any]] = []
    extension = SkillsExtension(catalog, ttl_ms=300_000, cache_scope="public")
    async with _connected(extension, wire=wire) as session:
        await session.discover()
        raw = await session.send_request(_RawRequest(method="skills/list"), _DICT_ADAPTER)

    assert raw == _wire_result(wire, "skills")
    assert raw["resultType"] == "complete"
    assert raw["ttlMs"] == 300_000
    assert raw["cacheScope"] == "public"
    assert "nextCursor" not in raw
    assert [skill["uri"] for skill in raw["skills"]] == [
        "skill://alpha/SKILL.md",
        "skill://beta/SKILL.md",
        "skill://gamma/SKILL.md",
    ]
    alpha = raw["skills"][0]
    assert alpha["frontmatter"] == {
        "name": "alpha",
        "description": "Alpha skill for the tests",
        "license": "MIT",
    }
    assert {resource["uri"] for resource in alpha["resources"]} == {
        f"skill://alpha/{relpath}" for relpath in ALPHA_MANIFEST
    }
    assert all(resource["digest"].startswith("sha256:") for resource in alpha["resources"])


async def test_wire_modern_skills_get_and_unknown_uri(catalog: SkillCatalog) -> None:
    wire: list[dict[str, Any]] = []
    async with _connected(SkillsExtension(catalog), wire=wire) as session:
        await session.discover()
        raw = await session.send_request(
            _RawRequest(method="skills/get", params={"uri": "skill://beta/SKILL.md"}),
            _DICT_ADAPTER,
        )
    assert raw["resultType"] == "complete"
    assert raw["skill"]["uri"] == "skill://beta/SKILL.md"
    assert raw["ttlMs"] == 0
    assert raw["cacheScope"] == "private"

    wire.clear()
    async with _connected(SkillsExtension(catalog), wire=wire) as session:
        await session.discover()
        with pytest.raises(MCPError) as excinfo:
            await session.send_request(
                _RawRequest(method="skills/get", params={"uri": "skill://missing/SKILL.md"}),
                _DICT_ADAPTER,
            )
    assert excinfo.value.code == types.INVALID_PARAMS
    assert _wire_error(wire)["message"] == "unknown skill: skill://missing/SKILL.md"


async def test_wire_modern_directory_read(catalog: SkillCatalog) -> None:
    wire: list[dict[str, Any]] = []
    async with _connected(SkillsExtension(catalog, read_directory=True), wire=wire) as session:
        discovered = await session.discover()
        capabilities = discovered.capabilities.model_dump(
            by_alias=True, mode="json", exclude_none=True
        )
        assert capabilities["extensions"][SKILLS_EXTENSION_ID] == {"directoryRead": True}

        raw = await session.send_request(
            _RawRequest(method="resources/directory/read", params={"uri": "skill://alpha"}),
            _DICT_ADAPTER,
        )

    assert raw == _wire_result(wire, "resources")
    entries = {entry["name"]: entry for entry in raw["resources"]}
    assert entries["SKILL.md"] == {
        "uri": "skill://alpha/SKILL.md",
        "name": "SKILL.md",
        "mimeType": "text/markdown",
    }
    assert entries["references"] == {
        "uri": "skill://alpha/references",
        "name": "references",
        "mimeType": DIRECTORY_MIME_TYPE,
    }
    assert raw["resultType"] == "complete"
    assert raw["ttlMs"] == 0
    assert raw["cacheScope"] == "private"


async def test_wire_directory_read_is_method_not_found_when_not_declared(
    catalog: SkillCatalog,
) -> None:
    wire: list[dict[str, Any]] = []
    async with _connected(SkillsExtension(catalog), wire=wire) as session:
        discovered = await session.discover()
        capabilities = discovered.capabilities.model_dump(
            by_alias=True, mode="json", exclude_none=True
        )
        assert capabilities["extensions"][SKILLS_EXTENSION_ID] == {}

        with pytest.raises(MCPError) as excinfo:
            await session.send_request(
                _RawRequest(method="resources/directory/read", params={"uri": "skill://alpha"}),
                _DICT_ADAPTER,
            )
    assert excinfo.value.code == types.METHOD_NOT_FOUND
    assert _wire_error(wire)["code"] == types.METHOD_NOT_FOUND


async def test_wire_legacy_era_rejects_skills_list(catalog: SkillCatalog) -> None:
    wire: list[dict[str, Any]] = []
    async with _connected(SkillsExtension(catalog, read_directory=True), wire=wire) as session:
        initialized = await session.initialize()
        assert initialized.protocol_version == LEGACY_VERSION

        with pytest.raises(MCPError) as excinfo:
            await session.send_request(_RawRequest(method="skills/list"), _DICT_ADAPTER)
    assert excinfo.value.code == types.METHOD_NOT_FOUND
    assert _wire_error(wire) == {
        "code": types.METHOD_NOT_FOUND,
        "message": "Method not found",
        "data": "skills/list",
    }


async def test_wire_modern_requires_the_client_extension(catalog: SkillCatalog) -> None:
    wire: list[dict[str, Any]] = []
    async with _connected(SkillsExtension(catalog), declare_extension=False, wire=wire) as session:
        await session.discover()
        with pytest.raises(MCPError) as excinfo:
            await session.send_request(_RawRequest(method="skills/list"), _DICT_ADAPTER)
    assert excinfo.value.code == types.MISSING_REQUIRED_CLIENT_CAPABILITY
    assert _wire_error(wire)["data"]["requiredCapabilities"]["extensions"] == {
        SKILLS_EXTENSION_ID: {}
    }
