"""Wire models for the MCP Tasks extension (``io.modelcontextprotocol/tasks``).

The 2026-07-28 revision removed the core task shapes (``mcp_types.Task`` and
friends remain as legacy 2025-11-25 definitions that are no longer dispatched),
so ninja defines the extension contract here.

Field names are snake_case in Python; the wire form is camelCase, matching the
``mcp_types`` alias convention (``to_camel`` + ``populate_by_name``).
Request/result models subclass :class:`mcp_types.RequestParams` /
:class:`mcp_types.Result` so the SDK serializes them without extra adapters.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from mcp_types import RequestParams, Result
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


TaskStatus = Literal["working", "input_required", "completed", "failed", "cancelled"]

TASK_STATUS_WORKING: Final[TaskStatus] = "working"
TASK_STATUS_INPUT_REQUIRED: Final[TaskStatus] = "input_required"
TASK_STATUS_COMPLETED: Final[TaskStatus] = "completed"
TASK_STATUS_FAILED: Final[TaskStatus] = "failed"
TASK_STATUS_CANCELLED: Final[TaskStatus] = "cancelled"

#: Statuses after which a task record is immutable.
TERMINAL_TASK_STATUSES: Final[frozenset[str]] = frozenset(
    {TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, TASK_STATUS_CANCELLED}
)


def is_terminal(status: str) -> bool:
    """Whether *status* is a terminal task status.

    Terminal tasks are ``completed``, ``failed`` or ``cancelled``; everything
    else (``working``, ``input_required``) may still transition.
    """
    return status in TERMINAL_TASK_STATUSES


class TaskFields(BaseModel):
    """Fields shared by the task object and the task result envelopes."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    task_id: str
    """Server-assigned task identifier."""

    status: TaskStatus
    """Current task state."""

    status_message: str | None = None
    """Optional human-readable detail about *status*."""

    created_at: str
    """Creation timestamp (ISO 8601)."""

    last_updated_at: str
    """Timestamp of the last state change (ISO 8601)."""

    ttl_ms: int | None = None
    """Retention for the task record, in milliseconds, once terminal."""

    poll_interval_ms: int | None = None
    """Suggested client poll interval, in milliseconds."""


class Task(TaskFields):
    """A durable task record as stored and as returned to clients."""


class CreateTaskResult(Result, TaskFields):
    """``tasks/create`` result: the freshly created task."""

    result_type: Literal["task"] = "task"


class GetTaskResult(Result, TaskFields):
    """``tasks/get`` result.

    Carries the task state plus, depending on status, the completed payload
    (``result``), the failure (``error``, a JSON-RPC error object) or the
    outstanding elicitation requests (``input_requests``).
    """

    result_type: Literal["complete"] = "complete"

    result: dict[str, Any] | None = None
    """Completed task payload, present when ``status == "completed"``."""

    error: dict[str, Any] | None = None
    """JSON-RPC error object, present when ``status == "failed"``."""

    input_requests: dict[str, Any] | None = None
    """Outstanding input requests, present when ``status == "input_required"``."""


class GetTaskParams(RequestParams):
    """``tasks/get`` parameters."""

    task_id: str


class UpdateTaskParams(RequestParams):
    """``tasks/update`` parameters (client-supplied input responses)."""

    task_id: str
    input_responses: dict[str, Any]


class CancelTaskParams(RequestParams):
    """``tasks/cancel`` parameters."""

    task_id: str


class StoredResult(Result):
    """Permissive result envelope used to persist arbitrary tool payloads.

    The 2.x base :class:`mcp_types.Result` only declares ``_meta`` and silently
    drops unknown fields, while job payloads live in ``content`` /
    ``structuredContent``. Tasks store results through this subclass so the
    persisted payload survives a store/read round-trip.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")


__all__ = [
    "TASK_STATUS_CANCELLED",
    "TASK_STATUS_COMPLETED",
    "TASK_STATUS_FAILED",
    "TASK_STATUS_INPUT_REQUIRED",
    "TASK_STATUS_WORKING",
    "TERMINAL_TASK_STATUSES",
    "CancelTaskParams",
    "CreateTaskResult",
    "GetTaskParams",
    "GetTaskResult",
    "StoredResult",
    "Task",
    "TaskFields",
    "TaskStatus",
    "UpdateTaskParams",
    "is_terminal",
]
