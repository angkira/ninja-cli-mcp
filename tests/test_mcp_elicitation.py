"""Elicitation for ``coder_branch_discard`` on both protocol eras.

Deleting an isolation branch that still holds unmerged commits asks the user
first. A 2025-era connection answers that question with a push-style
``elicitation/create`` request sent mid-call; 2026-07-28 removed that
back-channel, so the server instead returns an ``input_required`` result
(SEP-2322 multi round-trip) and the client retries the same call with the
answer and the echoed ``request_state``.

These tests drive the real ``create_server()`` through an in-memory ``Client``
with a stubbed executor, so no git repository or subprocess is involved.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client, types

from ninja_coder.models import BranchDiscardResult
from ninja_coder.server import _verify_branch_discard_state


if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


TOOL = "coder_branch_discard"
BRANCH = "ninja/feature-x"
OTHER_BRANCH = "ninja/other"
REPO_ROOT = "/tmp/ninja-repo"
CONFIRM_KEY = "confirm_branch_delete"

UNMERGED_REFUSAL = f"error: The branch '{BRANCH}' is not fully merged."
DELETED = f"Deleted branch {BRANCH} (was 1a2b3c4)."

INVALID_PARAMS = -32602


@pytest.fixture(autouse=True)
def _isolated_task_store(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Keep the durable task store out of the developer's ``~/.ninja``."""
    monkeypatch.setenv("NINJA_TASKS_DB", str(tmp_path / "tasks.db"))


class DiscardRecorder:
    """Executor stand-in: an unforced discard is refused, a forced one deletes."""

    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def discard_branch(self, request: Any, client_id: str = "default") -> BranchDiscardResult:
        self.calls.append(request.force)
        if request.force:
            return BranchDiscardResult(status="ok", branch=request.branch, message=DELETED)
        return BranchDiscardResult(status="error", branch=request.branch, message=UNMERGED_REFUSAL)

    @property
    def forced(self) -> bool:
        return any(self.calls)


def install_executor(monkeypatch: MonkeyPatch) -> DiscardRecorder:
    """Replace the coder executor for the duration of one test."""
    recorder = DiscardRecorder()
    monkeypatch.setattr("ninja_coder.server.get_executor", lambda: recorder)
    return recorder


def create_server() -> Any:
    """Build the server the ``ninja_coder.server`` entry point would run."""
    from ninja_coder.server import create_server as factory

    return factory()


def arguments(branch: str = BRANCH) -> dict[str, str]:
    """Tool arguments for discarding *branch*."""
    return {"repo_root": REPO_ROOT, "branch": branch}


async def accept(_ctx: Any, _params: Any) -> types.ElicitResult:
    """Answer the confirmation with "yes"."""
    return types.ElicitResult(action="accept", content={"confirm": True})


async def decline(_ctx: Any, _params: Any) -> types.ElicitResult:
    """Answer the confirmation with "no"."""
    return types.ElicitResult(action="decline")


# --------------------------------------------------------------------------- #
# (a) 2026-07-28: the round trip
# --------------------------------------------------------------------------- #


async def test_modern_accept_forces_the_discard(monkeypatch: MonkeyPatch) -> None:
    """An accepting client ends up deleting the branch, after being asked once."""
    executor = install_executor(monkeypatch)
    asked: list[types.ElicitRequestParams] = []

    async def record(ctx: Any, params: types.ElicitRequestParams) -> types.ElicitResult:
        asked.append(params)
        return await accept(ctx, params)

    async with Client(create_server(), elicitation_callback=record) as client:
        result = await client.call_tool(TOOL, arguments())

    assert result.is_error is False
    assert result.structured_content == {
        "status": "ok",
        "branch": BRANCH,
        "message": f"{DELETED} (confirmed via elicitation)",
    }
    # Two rounds: the refusal, then the forced delete.
    assert executor.calls == [False, True]
    assert len(asked) == 1
    assert isinstance(asked[0], types.ElicitRequestFormParams)
    assert BRANCH in asked[0].message
    assert asked[0].requested_schema["required"] == ["confirm"]


async def test_modern_intermediate_result_is_sealed_and_singular(
    monkeypatch: MonkeyPatch,
) -> None:
    """The first round asks exactly one question and carries sealed state."""
    install_executor(monkeypatch)

    async with Client(create_server()) as client:
        first = await client.session.call_tool(TOOL, arguments(), allow_input_required=True)

        assert isinstance(first, types.InputRequiredResult)
        assert first.input_requests is not None
        assert list(first.input_requests) == [CONFIRM_KEY]

        request = first.input_requests[CONFIRM_KEY]
        assert isinstance(request, types.ElicitRequest)
        assert request.params.mode == "form"
        assert BRANCH in request.params.message
        assert request.params.requested_schema == {
            "type": "object",
            "properties": {
                "confirm": {
                    "type": "boolean",
                    "title": "Delete branch",
                    "description": f"Confirm: delete branch {BRANCH}",
                }
            },
            "required": ["confirm"],
        }

        # The boundary sealed the state: opaque on the wire, no branch in clear.
        assert first.request_state
        assert BRANCH not in first.request_state
        assert REPO_ROOT not in first.request_state


async def test_modern_retry_with_accepted_response_forces_the_discard(
    monkeypatch: MonkeyPatch,
) -> None:
    """Replaying the same call with the answer and the echoed state completes it."""
    executor = install_executor(monkeypatch)

    async with Client(create_server()) as client:
        first = await client.session.call_tool(TOOL, arguments(), allow_input_required=True)
        assert isinstance(first, types.InputRequiredResult)

        result = await client.call_tool(
            TOOL,
            arguments(),
            input_responses={
                CONFIRM_KEY: types.ElicitResult(action="accept", content={"confirm": True})
            },
            request_state=first.request_state,
        )

    assert result.structured_content == {
        "status": "ok",
        "branch": BRANCH,
        "message": f"{DELETED} (confirmed via elicitation)",
    }
    assert executor.calls == [False, True]


async def test_modern_decline_keeps_the_refusal(monkeypatch: MonkeyPatch) -> None:
    """A declining client gets the untouched refusal and nothing is force-deleted."""
    executor = install_executor(monkeypatch)

    async with Client(create_server(), elicitation_callback=decline) as client:
        result = await client.call_tool(TOOL, arguments())

    assert result.structured_content == {
        "status": "error",
        "branch": BRANCH,
        "message": UNMERGED_REFUSAL,
    }
    assert executor.forced is False


async def test_modern_tampered_state_is_invalid_params(monkeypatch: MonkeyPatch) -> None:
    """A state minted for another call is refused, never resolved."""
    executor = install_executor(monkeypatch)

    async with Client(create_server()) as client:
        first = await client.session.call_tool(TOOL, arguments(), allow_input_required=True)
        assert isinstance(first, types.InputRequiredResult)

        with pytest.raises(Exception) as excinfo:
            await client.call_tool(
                TOOL,
                arguments(OTHER_BRANCH),
                input_responses={
                    CONFIRM_KEY: types.ElicitResult(action="accept", content={"confirm": True})
                },
                request_state=first.request_state,
            )

    assert getattr(excinfo.value, "code", None) == INVALID_PARAMS
    assert executor.forced is False


def test_plaintext_state_naming_another_branch_is_rejected() -> None:
    """The handler's own check refuses state that describes a different discard."""
    from ninja_coder.models import BranchDiscardRequest

    request = BranchDiscardRequest(repo_root=REPO_ROOT, branch=BRANCH)
    mismatched = json.dumps(
        {"op": "branch_discard", "branch": OTHER_BRANCH, "repo_root": REPO_ROOT},
        sort_keys=True,
    )

    with pytest.raises(Exception) as excinfo:
        _verify_branch_discard_state(request, mismatched)

    assert getattr(excinfo.value, "code", None) == INVALID_PARAMS


def test_plaintext_state_for_the_same_branch_is_accepted() -> None:
    """The happy path of the handler's own check."""
    from ninja_coder.models import BranchDiscardRequest
    from ninja_coder.server import _encode_branch_discard_state

    request = BranchDiscardRequest(repo_root=REPO_ROOT, branch=BRANCH)
    _verify_branch_discard_state(request, _encode_branch_discard_state(request))


# --------------------------------------------------------------------------- #
# (b) 2025-era: push elicitation keeps working
# --------------------------------------------------------------------------- #


async def test_legacy_push_elicitation_forces_the_discard(
    monkeypatch: MonkeyPatch,
) -> None:
    """A legacy connection still gets the mid-call request, and it still forces."""
    executor = install_executor(monkeypatch)
    asked: list[types.ElicitRequestParams] = []

    async def record(ctx: Any, params: types.ElicitRequestParams) -> types.ElicitResult:
        asked.append(params)
        return await accept(ctx, params)

    async with Client(create_server(), mode="legacy", elicitation_callback=record) as client:
        result = await client.call_tool(TOOL, arguments())

    assert result.structured_content == {
        "status": "ok",
        "branch": BRANCH,
        "message": f"{DELETED} (confirmed via elicitation)",
    }
    assert executor.calls == [False, True]
    assert len(asked) == 1
    assert BRANCH in asked[0].message


async def test_legacy_decline_keeps_the_refusal(monkeypatch: MonkeyPatch) -> None:
    """Declining on a legacy connection leaves the branch alone."""
    executor = install_executor(monkeypatch)

    async with Client(create_server(), mode="legacy", elicitation_callback=decline) as client:
        result = await client.call_tool(TOOL, arguments())

    assert result.structured_content == {
        "status": "error",
        "branch": BRANCH,
        "message": UNMERGED_REFUSAL,
    }
    assert executor.calls == [False]
