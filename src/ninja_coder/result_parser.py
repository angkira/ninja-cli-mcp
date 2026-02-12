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

        Extracts JSON from output and converts to PlanExecutionResult.

        Expected JSON format:
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
        # Extract JSON from output
        json_data = self._extract_json_from_output(output)

        if not json_data:
            logger.error("Failed to extract JSON from output")
            raise ValueError("Could not extract valid JSON from CLI output")

        # Validate structure
        if not self._validate_plan_result(json_data):
            logger.error("Invalid plan result structure")
            raise ValueError("Invalid plan result structure")

        # Convert to PlanExecutionResult
        return self._convert_to_plan_result(json_data)

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
        """Extract JSON from CLI output using multiple strategies.

        Tries in order:
        1. JSON code blocks (```json...```)
        2. JSON objects in text ({...})
        3. Raw JSON parsing

        Args:
            output: Raw CLI output

        Returns:
            Parsed JSON dict or None if extraction fails
        """
        # Strategy 1: Extract from JSON code blocks
        json_block_pattern = r'```json\s*\n(.*?)\n```'
        matches = re.findall(json_block_pattern, output, re.DOTALL)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse JSON code block: {e}")
                continue

        # Strategy 2: Find JSON objects in text
        json_object_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_object_pattern, output, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, dict) and data:
                    return data
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse JSON object: {e}")
                continue

        # Strategy 3: Try parsing entire output as JSON
        try:
            data = json.loads(output.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse output as raw JSON: {e}")

        return None

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
        overall_status: Literal["success", "partial", "failed"] = data["overall_status"]

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
            f"Executed {total_count} step(s): "
            f"{completed_count} completed, {failed_count} failed. "
        )

        if data.get("notes"):
            overall_summary += f"\n\nNotes: {data['notes']}"

        return PlanExecutionResult(
            overall_status=data["overall_status"],
            steps=step_results,
            files_modified=data.get("files_modified", []),
            notes=overall_summary,
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
        path_pattern = r'(?:^|\s)([^\s]+\.[a-zA-Z]{1,4})(?:\s|$)'
        matches = re.findall(path_pattern, output, re.MULTILINE)

        for match in matches:
            # Filter out common non-file strings
            if '/' in match or '\\' in match:
                paths.append(match)

        # Remove duplicates while preserving order
        seen = set()
        unique_paths = []
        for path in paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        return unique_paths
