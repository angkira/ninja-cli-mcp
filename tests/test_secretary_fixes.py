"""
Tests for secretary bug fixes:
  - Bug 1: secretary_file_search ignores content_regex
  - Bug 2: secretary_session_report schema mismatch (session_id required)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


# Ensure src/ is importable.
_root = Path(__file__).parent.parent
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))

from ninja_secretary.models import FileSearchRequest, SessionReportRequest  # noqa: E402
from ninja_secretary.tools import SecretaryToolExecutor, reset_executor  # noqa: E402


REPO_ROOT = str(_root)


@pytest.fixture(autouse=True)
def clean_executor() -> None:
    """Reset the global executor singleton between tests."""
    reset_executor()
    yield
    reset_executor()


# ---------------------------------------------------------------------------
# Bug 1 — content_regex filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_search_content_regex_filters_correctly() -> None:
    """Files returned must actually contain the regex match; spurious files excluded."""
    executor = SecretaryToolExecutor()
    request = FileSearchRequest(
        pattern="**/*.py",
        repo_root=REPO_ROOT,
        max_results=500,
        content_regex="default_store",
    )
    result = await executor.file_search(request)

    assert result.status == "ok", f"Expected ok, got: {result}"
    assert result.matches, "Expected at least one match"

    # Every returned file must actually contain the string.
    for match in result.matches:
        content = (Path(REPO_ROOT) / match.path).read_text(encoding="utf-8", errors="replace")
        assert re.search("default_store", content), (
            f"{match.path} was returned but does not contain 'default_store'"
        )

    # The six known files must all be present.
    returned_paths = {m.path for m in result.matches}
    expected_paths = {
        "src/ninja_common/config_manager.py",
        "src/ninja_config/secrets_store.py",
        "src/ninja_config/modern_tui.py",
        "tests/test_config_manager_migration.py",
        "tests/test_secrets_panel.py",
        "tests/test_secrets_store.py",
    }
    missing = expected_paths - returned_paths
    assert not missing, f"Expected files not returned: {missing}"


@pytest.mark.asyncio
async def test_file_search_content_regex_empty_string_falls_back_to_glob(
    temp_repo: Path,
) -> None:
    """Empty content_regex should behave identically to no content_regex."""
    executor = SecretaryToolExecutor()

    request_no_regex = FileSearchRequest(
        pattern="**/*.py",
        repo_root=str(temp_repo),
        max_results=500,
        content_regex=None,
    )
    request_empty_regex = FileSearchRequest(
        pattern="**/*.py",
        repo_root=str(temp_repo),
        max_results=500,
        content_regex="",
    )

    result_no = await executor.file_search(request_no_regex)
    result_empty = await executor.file_search(request_empty_regex)

    assert result_no.status == "ok"
    assert result_empty.status == "ok"
    assert {m.path for m in result_no.matches} == {m.path for m in result_empty.matches}


@pytest.mark.asyncio
async def test_file_search_invalid_regex_returns_clean_error() -> None:
    """An invalid regex must return status='error' without crashing the server."""
    executor = SecretaryToolExecutor()
    request = FileSearchRequest(
        pattern="**/*.py",
        repo_root=REPO_ROOT,
        max_results=100,
        content_regex="[invalid(",
    )
    result = await executor.file_search(request)

    assert result.status == "error"
    assert result.matches == []
    assert "Invalid content_regex" in result.message


@pytest.mark.asyncio
async def test_file_search_skips_binary_or_unreadable(tmp_path: Path) -> None:
    """Binary files that cannot be decoded must be silently skipped."""
    # Write a .py file with null bytes that will look binary.
    binary_file = tmp_path / "binary_looking.py"
    binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe" * 100)

    # Write a normal file that matches.
    normal_file = tmp_path / "normal.py"
    normal_file.write_text("needle = True\n")

    executor = SecretaryToolExecutor()
    request = FileSearchRequest(
        pattern="**/*.py",
        repo_root=str(tmp_path),
        max_results=100,
        content_regex="needle",
    )
    # Must not raise.
    result = await executor.file_search(request)

    assert result.status == "ok"
    returned_paths = {m.path for m in result.matches}
    # The normal file must be returned.
    assert "normal.py" in returned_paths
    # The binary file must NOT be returned (it doesn't match "needle").
    assert "binary_looking.py" not in returned_paths


# ---------------------------------------------------------------------------
# Bug 2 — session_report with no session_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_report_no_session_id_lists_sessions() -> None:
    """Calling session_report with no session_id must succeed and return an index."""
    # Must not raise ValidationError.
    request = SessionReportRequest()  # session_id defaults to None

    executor = SecretaryToolExecutor()
    result = await executor.session_report(request)

    assert result.session_id == "__index__"
    assert "available_sessions" in result.metadata
    assert isinstance(result.metadata["available_sessions"], list)


@pytest.mark.asyncio
async def test_session_report_with_session_id_returns_report() -> None:
    """Calling session_report with a session_id must not raise and return a report."""
    request = SessionReportRequest(session_id="test-session-42")

    executor = SecretaryToolExecutor()
    result = await executor.session_report(request)

    # Either a real session or the "no session data" placeholder — both are valid.
    assert result.session_id == "test-session-42"
    assert result.started_at
