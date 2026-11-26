"""Tests for include/exclude glob filtering in ``secretary_codebase_report``.

Also covers the sibling schema drift: options the executors already implement
but the tool schemas did not advertise, plus the session_report guard for a
mutating action without a ``session_id``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ninja_common.path_utils import build_path_matcher
from ninja_secretary.models import CodebaseReportRequest, SessionReportRequest
from ninja_secretary.server import TOOLS as SECRETARY_TOOLS
from ninja_secretary.tools import SecretaryToolExecutor


if TYPE_CHECKING:
    from collections.abc import Generator


# Extension -> count on the unfiltered fixture tree. ``node_modules`` is in the
# executor's hardcoded skip set, so those files never appear in either column.
_BASELINE_EXTENSIONS = {"md": 1, "py": 5, "js": 1}


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def executor() -> SecretaryToolExecutor:
    """Create a SecretaryToolExecutor instance."""
    return SecretaryToolExecutor()


@pytest.fixture(autouse=True)
def _skip_operator_enrichment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep report tests hermetic: never spawn a real operator subprocess."""
    import ninja_coder.driver

    async def _unavailable(*args: object, **kwargs: object) -> tuple[bool, str]:
        return False, ""

    monkeypatch.setattr(ninja_coder.driver, "run_operator_text", _unavailable)


@pytest.fixture
def fixture_tree(temp_dir: Path) -> Path:
    """Build a small tree covering source, tests, deps and a skipped dir."""
    files = {
        "README.md": "# Fixture\n",
        "main.py": "print('main')\n",
        "src/util.py": "def helper():\n    return 1\n",
        "src/deep/mod.py": "VALUE = 1\nOTHER = 2\nTHIRD = 3\n",
        "tests/test_main.py": "def test_x():\n    assert True\n",
        "vendor/lib/dep.py": "DEP = 1\n",
        "web/app.js": "console.log('app');\n",
        "node_modules/pkg/index.js": "module.exports = {};\n",
        "node_modules/pkg/lib/extra.js": "export const x = 1;\n",
    }
    for rel_path, content in files.items():
        path = temp_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return temp_dir


def _total_bytes(fixture_root: Path, skip: set[str] | None = None) -> int:
    """Sum sizes of files outside *skip* components (matches the executor)."""
    skip = skip or {".git", "node_modules", "__pycache__", "venv"}
    total = 0
    for path in fixture_root.rglob("*"):
        if path.is_file() and not skip.intersection(path.relative_to(fixture_root).parts):
            total += path.stat().st_size
    return total


# --------------------------------------------------------------------------- #
# Matcher semantics
# --------------------------------------------------------------------------- #


def test_matcher_include_only_matches_basenames_at_any_depth() -> None:
    """``**/*.py`` matches top-level and nested files alike."""
    matches = build_path_matcher(["**/*.py"], [])

    assert matches("main.py")
    assert matches("src/deep/mod.py")
    assert not matches("README.md")
    assert not matches("web/app.js")


def test_matcher_empty_include_matches_everything_empty_exclude_excludes_nothing() -> None:
    """Empty lists degrade to "everything" / "nothing" respectively."""
    everything = build_path_matcher([], [])
    nothing = build_path_matcher([], ["**/*"])

    assert everything("src/deep/mod.py")
    assert not nothing("src/deep/mod.py")


def test_matcher_is_intersection_minus_exclusion() -> None:
    """A path needs an include hit and must not hit any exclude pattern."""
    matches = build_path_matcher(["**/*.py"], ["tests/**"])

    assert matches("src/util.py")
    assert not matches("tests/test_main.py")
    assert not matches("README.md")


def test_matcher_rejects_invalid_pattern() -> None:
    """Invalid gitwildmatch syntax surfaces as a ValueError, not a traceback."""
    with pytest.raises(ValueError, match="Invalid glob pattern"):
        build_path_matcher(["\\"], [])


# --------------------------------------------------------------------------- #
# codebase_report filtering
# --------------------------------------------------------------------------- #


class TestCodebaseReportFilters:
    """End-to-end behaviour of include/exclude patterns."""

    @pytest.mark.asyncio
    async def test_include_only_reports_just_python(
        self, fixture_tree: Path, executor: SecretaryToolExecutor
    ) -> None:
        """Every reported extension is py and counts agree with file_count."""
        request = CodebaseReportRequest(
            repo_root=str(fixture_tree), include_patterns=["**/*.py"]
        )
        result = await executor.codebase_report(request, client_id="filters-include")

        assert result.status == "ok"
        assert result.metrics["extensions"] == {"py": 5}
        assert result.file_count == 5
        assert result.metrics["file_count"] == result.file_count
        assert result.file_count == sum(result.metrics["extensions"].values())

    @pytest.mark.asyncio
    async def test_exclude_drops_files_versus_no_filter(
        self, fixture_tree: Path, executor: SecretaryToolExecutor
    ) -> None:
        """Excluding vendored/node_modules trees drops files from the totals."""
        unfiltered = await executor.codebase_report(
            CodebaseReportRequest(repo_root=str(fixture_tree)), client_id="filters-exclude-all"
        )
        filtered = await executor.codebase_report(
            CodebaseReportRequest(
                repo_root=str(fixture_tree),
                exclude_patterns=["**/node_modules/**", "**/vendor/**"],
            ),
            client_id="filters-exclude",
        )

        assert unfiltered.status == filtered.status == "ok"
        assert unfiltered.file_count == 7
        assert filtered.file_count < unfiltered.file_count
        assert filtered.file_count == 6

        assert unfiltered.metrics["extensions"] == _BASELINE_EXTENSIONS
        # node_modules' two JS files and vendor's Python file are gone.
        assert filtered.metrics["extensions"] == {"md": 1, "py": 4, "js": 1}
        assert filtered.file_count == sum(filtered.metrics["extensions"].values())

    @pytest.mark.asyncio
    async def test_node_modules_already_skipped_matches_baseline(
        self, fixture_tree: Path, executor: SecretaryToolExecutor
    ) -> None:
        """The hardcoded skip set and an explicit node_modules glob agree."""
        unfiltered = await executor.codebase_report(
            CodebaseReportRequest(repo_root=str(fixture_tree)), client_id="filters-skip-all"
        )
        filtered = await executor.codebase_report(
            CodebaseReportRequest(
                repo_root=str(fixture_tree), exclude_patterns=["**/node_modules/**"]
            ),
            client_id="filters-skip-node",
        )

        assert filtered.file_count == unfiltered.file_count
        assert filtered.metrics["extensions"] == unfiltered.metrics["extensions"]

    @pytest.mark.asyncio
    async def test_include_and_exclude_compose(
        self, fixture_tree: Path, executor: SecretaryToolExecutor
    ) -> None:
        """Combined filters are the intersection minus the exclusions."""
        request = CodebaseReportRequest(
            repo_root=str(fixture_tree),
            include_patterns=["**/*.py", "**/*.js"],
            exclude_patterns=["tests/**", "**/vendor/**", "**/node_modules/**"],
        )
        result = await executor.codebase_report(request, client_id="filters-both")

        assert result.status == "ok"
        # main.py, src/util.py, src/deep/mod.py and web/app.js survive.
        assert result.file_count == 4
        assert result.metrics["extensions"] == {"py": 3, "js": 1}
        assert result.file_count == sum(result.metrics["extensions"].values())

    @pytest.mark.asyncio
    async def test_invalid_pattern_returns_error_envelope(
        self, fixture_tree: Path, executor: SecretaryToolExecutor
    ) -> None:
        """A malformed glob is a clean error result with a message."""
        request = CodebaseReportRequest(repo_root=str(fixture_tree), include_patterns=["\\"])
        result = await executor.codebase_report(request, client_id="filters-invalid")

        assert result.status == "error"
        assert "Invalid glob pattern" in result.message
        assert result.report == ""
        assert result.file_count == 0
        assert result.metrics == {}

    @pytest.mark.asyncio
    async def test_no_patterns_matches_pre_filter_aggregates(
        self, fixture_tree: Path, executor: SecretaryToolExecutor
    ) -> None:
        """Regression: an unfiltered report keeps the previous aggregate values."""
        request = CodebaseReportRequest(repo_root=str(fixture_tree))
        result = await executor.codebase_report(request, client_id="filters-regression")

        assert result.status == "ok"
        assert result.file_count == 7
        assert result.metrics["file_count"] == 7
        assert result.metrics["extensions"] == _BASELINE_EXTENSIONS
        # py: all five files; js: the one outside the skipped node_modules.
        assert result.metrics["total_lines"] == 10
        assert result.metrics["dir_count"] == 6
        assert result.metrics["total_size_mb"] == pytest.approx(
            _total_bytes(fixture_tree) / 1024 / 1024
        )
        # The markdown structure section reflects the same numbers.
        assert "- **Total Files:** 7" in result.report
        assert "- **Total Directories:** 6" in result.report

    @pytest.mark.asyncio
    async def test_file_count_truthful_without_structure_section(
        self, fixture_tree: Path, executor: SecretaryToolExecutor
    ) -> None:
        """include_structure=False no longer zeroes the authoritative count."""
        request = CodebaseReportRequest(
            repo_root=str(fixture_tree),
            include_structure=False,
            include_dependencies=False,
        )
        result = await executor.codebase_report(request, client_id="filters-nostructure")

        assert result.status == "ok"
        assert result.file_count > 0
        assert result.metrics["file_count"] == result.file_count
        assert "## Project Structure" not in result.report
        assert "## Code Metrics" in result.report


# --------------------------------------------------------------------------- #
# session_report guard
# --------------------------------------------------------------------------- #


class TestSessionReportGuard:
    """Mutating actions require a target session."""

    @pytest.mark.asyncio
    async def test_update_without_session_id_is_an_error(
        self, executor: SecretaryToolExecutor
    ) -> None:
        """action=update with no session_id returns an error envelope."""
        result = await executor.session_report(
            SessionReportRequest(action="update", updates={"summary": "ignored"}),
            client_id="session-update",
        )

        assert result.status == "error"
        assert "session_id" in result.message

    @pytest.mark.asyncio
    async def test_create_without_session_id_is_an_error(
        self, executor: SecretaryToolExecutor
    ) -> None:
        """action=create with no session_id returns an error envelope."""
        result = await executor.session_report(
            SessionReportRequest(action="create"), client_id="session-create"
        )

        assert result.status == "error"
        assert "session_id" in result.message

    @pytest.mark.asyncio
    async def test_get_without_session_id_still_lists_sessions(
        self, executor: SecretaryToolExecutor
    ) -> None:
        """The index short-circuit is unchanged for action=get."""
        result = await executor.session_report(
            SessionReportRequest(action="get"), client_id="session-get"
        )

        assert result.status == "ok"
        assert result.session_id == "__index__"
        assert "available_sessions" in result.metadata


# --------------------------------------------------------------------------- #
# Schema drift guards
# --------------------------------------------------------------------------- #


def _schema(tools: list, name: str) -> dict:
    return next(tool.input_schema for tool in tools if tool.name == name)


def test_codebase_report_schema_advertises_all_implemented_options() -> None:
    """The report schema matches CodebaseReportRequest, defaults included."""
    schema = _schema(SECRETARY_TOOLS, "secretary_codebase_report")
    properties = schema["properties"]

    for field_name in ("include_patterns", "exclude_patterns"):
        assert properties[field_name]["type"] == "array"
        assert properties[field_name]["items"] == {"type": "string"}
        assert properties[field_name]["default"] == []

    for field_name in ("include_metrics", "include_dependencies", "include_structure"):
        assert properties[field_name]["type"] == "boolean"
        assert properties[field_name]["default"] is True

    assert schema["required"] == ["repo_root"]


def test_analyse_file_schema_advertises_implemented_options() -> None:
    """secretary_analyse_file advertises its executor-side options."""
    properties = _schema(SECRETARY_TOOLS, "secretary_analyse_file")["properties"]

    assert properties["search_pattern"]["type"] == "string"
    assert properties["include_structure"]["type"] == "boolean"
    assert properties["include_structure"]["default"] is True
    assert properties["include_preview"]["type"] == "boolean"
    assert properties["include_preview"]["default"] is True


def test_file_search_schema_advertises_max_results() -> None:
    """secretary_file_search advertises the limits its model enforces."""
    properties = _schema(SECRETARY_TOOLS, "secretary_file_search")["properties"]

    max_results = properties["max_results"]
    assert max_results["type"] == "integer"
    assert max_results["default"] == 100
    assert max_results["minimum"] == 1
    assert max_results["maximum"] == 1000


def test_session_report_schema_advertises_updates_and_action() -> None:
    """secretary_session_report advertises the fields it interprets."""
    properties = _schema(SECRETARY_TOOLS, "secretary_session_report")["properties"]

    assert properties["updates"]["type"] == "object"
    assert properties["action"]["enum"] == ["get", "update", "create"]
    assert properties["action"]["default"] == "get"


def test_multi_agent_task_schema_advertises_globs_as_guidance() -> None:
    """coder_multi_agent_task advertises the globs its request model accepts."""
    from ninja_coder.server import TOOLS as CODER_TOOLS

    properties = _schema(CODER_TOOLS, "coder_multi_agent_task")["properties"]

    assert properties["allowed_globs"]["type"] == "array"
    assert properties["allowed_globs"]["items"] == {"type": "string"}
    assert properties["allowed_globs"]["default"] == ["**/*"]
    assert properties["deny_globs"]["type"] == "array"
    assert properties["deny_globs"]["items"] == {"type": "string"}
    assert properties["deny_globs"]["default"] == []
    assert "NOT an enforced sandbox" in properties["allowed_globs"]["description"]
    assert "NOT an enforced sandbox" in properties["deny_globs"]["description"]
