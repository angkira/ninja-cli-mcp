"""Guard the shipped skill bundles: each ninja server must serve real skills.

The four servers publish the skills packaged under
``src/ninja_common/dist/skills/<module>`` through
``ninja_common.mcp_ext.wiring.load_catalog``. A bundle that stops loading —
a frontmatter typo, a directory/``name`` mismatch, a missing ``SKILL.md`` — is a
silent correctness failure at the host, so it is asserted here rather than
discovered in a release.

What is checked per module:

* the catalog is non-empty and every entry is served under a ``skill://`` URI;
* each skill's manifest contains a ``SKILL.md`` entry whose digest and size
  match the bytes on disk, and the same for every other manifest entry;
* every resource reported by ``list_resources()`` can be read back through
  :meth:`SkillCatalog.read`, with a MIME type that agrees with the payload;
* the bundle stays inside the per-skill file-count and size limits.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from ninja_common.mcp_ext.skills import (
    MAX_RESOURCES_PER_SKILL,
    MAX_TOTAL_BYTES_PER_SKILL,
    SKILL_MD,
    SKILL_URI_PREFIX,
    SkillCatalog,
)
from ninja_common.mcp_ext.wiring import SKILLS_DIR_ENV, default_skill_root, load_catalog


if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


MODULES = ("coder", "researcher", "secretary", "agent")


@pytest.fixture(autouse=True)
def _no_skills_override(monkeypatch: MonkeyPatch) -> None:
    """Validate the packaged bundles, never a developer's ``NINJA_SKILLS_DIR``."""
    monkeypatch.delenv(SKILLS_DIR_ENV, raising=False)


def _skill_dir(module: str, uri: str) -> Path:
    """Map a ``skill://<name>/<relpath>`` URI to its file on disk."""
    name, _, relpath = uri[len(SKILL_URI_PREFIX) :].partition("/")
    return default_skill_root(module) / name / relpath


@pytest.mark.parametrize("module", MODULES)
def test_catalog_is_not_empty(module: str) -> None:
    """Every module ships at least one skill, each served as a SKILL.md."""
    catalog = load_catalog(module)

    skills = catalog.skills()
    assert skills, f"{module} ships no skills under {default_skill_root(module)}"

    for skill in skills:
        assert skill.uri.startswith(SKILL_URI_PREFIX)
        assert skill.uri.endswith(f"/{SKILL_MD}")
        assert isinstance(skill.resources, list)
        assert skill.frontmatter["name"]
        assert skill.frontmatter["description"]


@pytest.mark.parametrize("module", MODULES)
def test_directory_name_matches_frontmatter_name(module: str) -> None:
    """The catalog rejects a mismatch, but assert it independently of the loader."""
    catalog = load_catalog(module)

    for skill in catalog.skills():
        name = skill.frontmatter["name"]
        assert (default_skill_root(module) / name / SKILL_MD).is_file(), (
            f"{module}: frontmatter name {name!r} has no matching directory"
        )


@pytest.mark.parametrize("module", MODULES)
def test_manifest_has_skill_md_and_matches_disk(module: str) -> None:
    """Every manifest entry's digest and size equal the recomputed disk values."""
    catalog = load_catalog(module)

    for skill in catalog.skills():
        assert isinstance(skill.resources, list)
        relpaths = [entry.uri.rsplit("/", 1)[-1] for entry in skill.resources]
        assert SKILL_MD in relpaths, f"{skill.uri}: manifest has no {SKILL_MD} entry"

        for entry in skill.resources:
            path = _skill_dir(module, entry.uri)
            assert path.is_file(), f"{entry.uri} is in the manifest but not on disk"

            data = path.read_bytes()
            assert entry.size == len(data), f"{entry.uri}: size does not match disk"
            assert entry.digest == f"sha256:{hashlib.sha256(data).hexdigest()}", (
                f"{entry.uri}: digest does not match disk"
            )


@pytest.mark.parametrize("module", MODULES)
def test_every_listed_resource_reads_back(module: str) -> None:
    """``list_resources()`` and ``read()`` agree on the same set of URIs."""
    catalog = load_catalog(module)

    resources = catalog.list_resources()
    assert resources, f"{module} lists no resources"

    for resource in resources:
        assert resource.uri.startswith(SKILL_URI_PREFIX)
        body = catalog.read(resource.uri)
        encoded = body.encode() if isinstance(body, str) else body
        assert resource.size == len(encoded)

        mime_type = catalog.mime_type(resource.uri)
        assert mime_type is not None
        assert mime_type == resource.mime_type


@pytest.mark.parametrize("module", MODULES)
def test_bundles_stay_within_limits(module: str) -> None:
    """Each skill is inside the per-skill file-count and byte budget."""
    catalog = load_catalog(module)

    for skill in catalog.skills():
        assert isinstance(skill.resources, list)
        assert len(skill.resources) <= MAX_RESOURCES_PER_SKILL
        assert sum(entry.size for entry in skill.resources) <= MAX_TOTAL_BYTES_PER_SKILL


def test_bundle_layout_is_one_directory_per_skill() -> None:
    """A packaged root contains skills and nothing else at its top level."""
    for module in MODULES:
        root = default_skill_root(module)
        assert root.is_dir(), f"{module}: missing packaged skills root {root}"
        for child in root.iterdir():
            assert child.is_dir(), f"{module}: stray file {child} in the skills root"
            assert (child / SKILL_MD).is_file(), f"{module}: {child} has no {SKILL_MD}"


def test_load_catalog_returns_the_real_bundle() -> None:
    """The module name selects the bundle; it is not a shared global catalog."""
    first = load_catalog("coder")
    second = load_catalog("researcher")

    assert isinstance(first, SkillCatalog)
    names_first = {skill.frontmatter["name"] for skill in first.skills()}
    names_second = {skill.frontmatter["name"] for skill in second.skills()}
    assert names_first and names_second
    assert names_first != names_second
