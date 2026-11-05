"""
Result parser for extracting structured JSON output from CLI responses.

This module provides robust parsing of JSON results from AI code CLI tools,
with multiple extraction strategies and comprehensive error handling.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from .models import PlanExecutionResult, StepResult


logger = logging.getLogger(__name__)


class ResultParser:
    """Parser for extracting structured JSON results from CLI output.

    Handles multiple JSON extraction strategies:
    1. JSON code blocks (```json...```)
    2. JSON objects in text
    3. Raw JSON output

    Provides validation and error handling for malformed results.
    """

    def parse_plan_result(self, output: str) -> PlanExecutionResult:
        """Parse plan execution result from CLI output.

        Accepts two shapes (tried in order):

        1. Per-step objects (what the current prompts ask for) — one
           ````json` block per step, e.g.
           ``{"id": "s1", "status": "ok", "summary": "...",
           "suspected_touched_paths": [...]}``. All blocks are collected
           and merged; a ``{"strategy": ...}`` merge block is attached
           to notes instead of failing validation.
        2. Legacy aggregate object:
        {
            "overall_status": "success"|"partial"|"failed",
            "steps_completed": ["step1", "step2"],
            "steps_failed": ["step3"],
            "step_summaries": {"step1": "summary", ...},
            "files_modified": ["path1", "path2"],
            "notes": "optional"
        }

        Args:
            output: Raw CLI output containing JSON

        Returns:
            PlanExecutionResult with structured step results

        Raises:
            ValueError: If JSON cannot be extracted or parsed
            KeyError: If required fields are missing
        """
        # CLI envelopes (e.g. opencode --format json) wrap the model's answer
        # in per-line JSON objects with the real newlines escaped, so fenced
        # blocks are invisible until the envelope's text fields are decoded.
        decoded = self._decode_envelope_text(output)
        source = f"{decoded}\n{output}" if decoded else output

        blocks = self._extract_all_json_blocks(source)

        step_objs = self._collect_step_objects(blocks)
        if step_objs:
            merge = next(
                (b for b in blocks if isinstance(b, dict) and isinstance(b.get("strategy"), str)),
                None,
            )
            return self._convert_step_objects(step_objs, merge)

        for block in blocks:
            if isinstance(block, dict) and self._validate_plan_result(block):
                return self._convert_to_plan_result(block)

        if not blocks:
            logger.error("Failed to extract JSON from output")
            raise ValueError("Could not extract valid JSON from CLI output")
        logger.error("Invalid plan result structure")
        raise ValueError("Invalid plan result structure")

    def parse_simple_result(self, output: str) -> dict[str, Any]:
        """Parse simple task result from CLI output.

        Extracts summary and touched paths from output.
        Falls back to treating entire output as summary.

        Args:
            output: Raw CLI output

        Returns:
            Dict with 'summary' and 'touched_paths' keys
        """
        result: dict[str, Any] = {
            "summary": "",
            "touched_paths": [],
        }

        # Try to extract JSON first
        json_data = self._extract_json_from_output(output)

        if json_data:
            # Extract from structured JSON
            result["summary"] = json_data.get("summary", "")
            result["touched_paths"] = json_data.get("files_modified", [])
            if not result["summary"]:
                # Fallback: use overall notes or construct summary
                result["summary"] = json_data.get("notes", "Task completed")
        else:
            # Fallback: use entire output as summary
            result["summary"] = output.strip()

            # Try to extract file paths from text
            result["touched_paths"] = self._extract_file_paths(output)

        return result

    def _extract_json_from_output(self, output: str) -> dict[str, Any] | None:
        """Extract the first JSON object from CLI output (legacy single-block API).

        For multi-block plan outputs prefer :meth:`_extract_all_json_blocks`.

        Args:
            output: Raw CLI output

        Returns:
            Parsed JSON dict or None if extraction fails
        """
        for block in self._extract_all_json_blocks(output):
            if isinstance(block, dict) and block and not self._is_envelope_part(block):
                return block
        return None

    @staticmethod
    def _is_envelope_part(data: dict[str, Any]) -> bool:
        """Detect CLI-envelope internals (message/tool parts, metadata)."""
        envelope_keys = ("sessionID", "sessionId", "messageID", "messageId", "snapshot")
        return any(k in data for k in envelope_keys)

    def _extract_all_json_blocks(self, output: str) -> list[Any]:
        """Extract every JSON value from CLI output, in order.

        Strategies:
        1. Fenced code blocks (```json...``` or bare ```...```)
        2. Balanced-brace scan for bare objects/arrays in prose
        3. The whole output as raw JSON

        Args:
            output: Raw CLI output

        Returns:
            List of parsed JSON values (dicts, lists); unparseable
            candidates are skipped.
        """
        found: list[Any] = []

        # Strategy 1: fenced code blocks
        fence_pattern = r"```(?:json)?\s*\n(.*?)```"
        for match in re.finditer(fence_pattern, output, re.DOTALL):
            try:
                found.append(json.loads(match.group(1)))
            except json.JSONDecodeError:
                logger.debug("Failed to parse fenced JSON block")
                continue

        # Strategy 2: balanced scan for bare objects/arrays (string-aware)
        for candidate in self._scan_balanced_json(output, limit=50):
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, (dict, list)) and value:
                found.append(value)

        # Strategy 3: whole output as raw JSON
        stripped = output.strip()
        try:
            value = json.loads(stripped)
            if isinstance(value, (dict, list)) and value and value not in found:
                found.append(value)
        except json.JSONDecodeError:
            pass

        return found

    @staticmethod
    def _decode_envelope_text(output: str) -> str:
        """Decode a CLI JSON envelope into the model's plain text.

        CLIs like ``opencode run --format json`` emit one JSON object per
        line; the model's answer (including its ```json blocks) lives in
        ``text`` fields with newlines escaped, invisible to regexes run on
        the raw output. This collects those fields so downstream extraction
        sees the answer as the model wrote it.

        Args:
            output: Raw CLI stdout

        Returns:
            Joined text fields, or "" when the output is not an envelope.
        """
        texts: list[str] = []

        def _collect(node: Any) -> None:
            if isinstance(node, dict):
                text = node.get("text")
                if isinstance(text, str) and text.strip() and isinstance(node.get("type"), str):
                    texts.append(text)
                for value in node.values():
                    _collect(value)
            elif isinstance(node, list):
                for item in node:
                    _collect(item)

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line.startswith("{"):
                continue
            try:
                _collect(json.loads(line))
            except json.JSONDecodeError:
                continue
        return "\n".join(texts)

    @staticmethod
    def _scan_balanced_json(text: str, limit: int = 100) -> list[str]:
        """Return balanced {...}/[...] substrings, respecting string escapes.

        Uses a stack so nested objects yield both inner and outer
        candidates (inner first, by closing position). Unbalanced closers
        reset the stack.
        """
        candidates: list[str] = []
        pairs = {"{": "}", "[": "]"}
        stack: list[tuple[str, int]] = []
        in_string = False
        escape = False
        for i, ch in enumerate(text):
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in pairs:
                stack.append((ch, i))
            elif ch in "}]":
                if stack and pairs[stack[-1][0]] == ch:
                    _, start = stack.pop()
                    if len(candidates) < limit:
                        candidates.append(text[start : i + 1])
                else:
                    stack.clear()
        return candidates

    @staticmethod
    def _is_template_echo(data: dict[str, Any]) -> bool:
        """Detect the prompt's example JSON echoed back by the model."""
        if data.get("id") == "step_id":
            return True
        if "ok | fail" in str(data.get("status", "")):
            return True
        touched = data.get("suspected_touched_paths") or []
        return any("path/to/" in str(p) for p in touched)

    def _collect_step_objects(self, blocks: list[Any]) -> list[dict[str, Any]]:
        """Collect per-step result objects from parsed blocks, in order.

        A step object needs a string ``id``, a string ``status`` and at
        least one content field (summary/notes/touched paths). This keeps
        CLI-envelope internals (message/tool parts that happen to carry an
        ``id``) out of the results.
        """
        content_keys = (
            "summary",
            "notes",
            "suspected_touched_paths",
            "touched_paths",
            "files_touched",
            "files_modified",
        )
        steps: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _add(obj: dict[str, Any]) -> None:
            step_id = obj.get("id")
            status = obj.get("status")
            if not isinstance(step_id, str) or not step_id:
                return
            if not isinstance(status, str) or not status:
                return
            if not any(k in obj for k in content_keys):
                return
            if step_id in seen or self._is_template_echo(obj):
                return
            seen.add(step_id)
            steps.append(obj)

        for block in blocks:
            if isinstance(block, dict):
                if isinstance(block.get("id"), str):
                    _add(block)
                elif isinstance(block.get("steps"), list):
                    for item in block["steps"]:
                        if isinstance(item, dict):
                            _add(item)
            elif isinstance(block, list):
                for item in block:
                    if isinstance(item, dict) and isinstance(item.get("id"), str):
                        _add(item)
        return steps

    def _convert_step_objects(
        self,
        step_objs: list[dict[str, Any]],
        merge: dict[str, Any] | None,
    ) -> PlanExecutionResult:
        """Convert per-step objects to a PlanExecutionResult."""
        step_results: list[StepResult] = []
        files_modified: list[str] = []
        has_fail = False
        has_error = False

        for obj in step_objs:
            raw_status = str(obj.get("status", "ok")).lower()
            if raw_status in ("ok", "success", "done", "passed"):
                status: Literal["ok", "fail", "skipped"] = "ok"
            elif raw_status in ("skipped", "skip"):
                status = "skipped"
            else:
                status = "fail"
                if raw_status in ("error", "fatal"):
                    has_error = True
                else:
                    has_fail = True

            touched: list[str] = []
            for key in (
                "suspected_touched_paths",
                "touched_paths",
                "files_touched",
                "files_modified",
            ):
                value = obj.get(key)
                if isinstance(value, list):
                    touched.extend(str(p) for p in value if p)
            for path in touched:
                if path not in files_modified:
                    files_modified.append(path)

            summary = str(obj.get("summary", "") or "Completed")
            notes = obj.get("notes") or None
            step_results.append(
                StepResult(
                    id=str(obj["id"]),
                    status=status,
                    summary=summary,
                    files_touched=touched,
                    error_message=notes if status == "fail" else None,
                )
            )

        if has_error:
            overall: Literal["success", "partial", "failed"] = "failed"
        elif has_fail:
            overall = "partial"
        else:
            overall = "success"

        notes_parts = [f"Parsed {len(step_results)} step result(s) from model output."]
        if merge is not None:
            strategy = merge.get("strategy", "unknown")
            merge_notes = merge.get("notes", "")
            notes_parts.append(f"Merge: {strategy}. {merge_notes}".strip())

        return PlanExecutionResult(
            overall_status=overall,
            steps=step_results,
            files_modified=files_modified,
            patch_path=None,
            notes=" ".join(notes_parts),
            execution_time=0,
        )

    def _validate_plan_result(self, data: dict[str, Any]) -> bool:
        """Validate plan result structure.

        Checks for required fields and proper types.

        Args:
            data: Parsed JSON data

        Returns:
            True if structure is valid
        """
        # Check for required fields
        required_fields = ["overall_status", "steps_completed", "step_summaries"]

        for field in required_fields:
            if field not in data:
                logger.warning(f"Missing required field: {field}")
                return False

        # Validate status
        valid_statuses = ["success", "partial", "failed"]
        if data["overall_status"] not in valid_statuses:
            logger.warning(f"Invalid overall_status: {data['overall_status']}")
            return False

        # Validate steps_completed is a list
        if not isinstance(data["steps_completed"], list):
            logger.warning("steps_completed must be a list")
            return False

        # Validate step_summaries is a dict
        if not isinstance(data["step_summaries"], dict):
            logger.warning("step_summaries must be a dict")
            return False

        return True

    def _convert_to_plan_result(self, data: dict[str, Any]) -> PlanExecutionResult:
        """Convert raw JSON data to PlanExecutionResult.

        Args:
            data: Validated JSON data

        Returns:
            PlanExecutionResult with structured step results
        """
        # Get overall status from data (already in correct format)
        _ = data["overall_status"]

        # Build step results
        step_results: list[StepResult] = []

        steps_completed = set(data.get("steps_completed", []))
        steps_failed = set(data.get("steps_failed", []))
        step_summaries = data.get("step_summaries", {})

        # All steps mentioned in summaries
        all_steps = set(step_summaries.keys())

        for step_id in all_steps:
            # Determine step status
            if step_id in steps_completed:
                status: Literal["ok", "fail", "skipped"] = "ok"
            elif step_id in steps_failed:
                status = "fail"
            else:
                # Default to ok if in summaries but not marked as failed
                status = "ok"

            # Get summary
            summary = step_summaries.get(step_id, "No summary available")

            # Create step result
            step_result = StepResult(
                id=step_id,
                status=status,
                summary=summary,
                files_touched=data.get("files_modified", []),
                error_message=data.get("notes", "") if status == "fail" else None,
            )

            step_results.append(step_result)

        # Build overall summary
        completed_count = len(steps_completed)
        failed_count = len(steps_failed)
        total_count = len(all_steps)

        overall_summary = (
            f"Executed {total_count} step(s): {completed_count} completed, {failed_count} failed. "
        )

        if data.get("notes"):
            overall_summary += f"\n\nNotes: {data['notes']}"

        return PlanExecutionResult(
            overall_status=data["overall_status"],
            steps=step_results,
            files_modified=data.get("files_modified", []),
            patch_path=data.get("patch_path"),
            notes=overall_summary,
            execution_time=0,  # TODO: Add proper execution time tracking
        )

    def _extract_file_paths(self, output: str) -> list[str]:
        """Extract file paths from unstructured output.

        Uses heuristics to find file paths in text.

        Args:
            output: Raw CLI output

        Returns:
            List of extracted file paths
        """
        paths: list[str] = []

        # Pattern for common file path indicators
        # Looks for lines containing file extensions and path separators
        path_pattern = r"(?:^|\s)([^\s]+\.[a-zA-Z]{1,4})(?:\s|$)"
        matches = re.findall(path_pattern, output, re.MULTILINE)

        for match in matches:
            # Filter out common non-file strings
            if "/" in match or "\\" in match:
                paths.append(match)

        # Remove duplicates while preserving order
        seen = set()
        unique_paths = []
        for path in paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        return unique_paths
