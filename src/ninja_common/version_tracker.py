"""Version tracking for Ninja MCP components."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VERSIONS_FILE = Path.home() / ".ninja-mcp-versions.json"


def get_component_versions() -> dict[str, str]:
    """
    Get current versions of all installed Ninja components.

    Returns:
        Dictionary mapping component name to version.
    """
    versions = {}

    # Try to import each component and get its version
    components = [
        ("ninja_coder", "coder"),
        ("ninja_researcher", "researcher"),
        ("ninja_secretary", "secretary"),
        ("ninja_prompts", "prompts"),
        ("ninja_common", "common"),
        ("ninja_config", "config"),
    ]

    for module_name, component_name in components:
        try:
            module = __import__(module_name)
            version = getattr(module, "__version__", "unknown")
            versions[component_name] = version
        except ImportError:
            versions[component_name] = "not installed"
        except Exception:
            versions[component_name] = "error"

    return versions


def load_previous_versions() -> dict[str, str]:
    """
    Load previously installed versions from file.

    Returns:
        Dictionary mapping component name to previous version.
    """
    if not VERSIONS_FILE.exists():
        return {}

    try:
        with VERSIONS_FILE.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_versions(versions: dict[str, str]) -> None:
    """
    Save current versions to file.

    Args:
        versions: Dictionary mapping component name to version.
    """
    try:
        VERSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with VERSIONS_FILE.open("w") as f:
            json.dump(versions, f, indent=2)
    except OSError:
        pass  # Silently fail if we can't write


def compare_versions(
    old: dict[str, str], new: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """
    Compare two version dictionaries and return changes.

    Args:
        old: Previous versions.
        new: Current versions.

    Returns:
        Dictionary mapping component name to change details.
        Each change has: status (new|updated|same|removed), old_version, new_version.
    """
    changes = {}
    all_components = set(old.keys()) | set(new.keys())

    for component in all_components:
        old_ver = old.get(component)
        new_ver = new.get(component)

        if old_ver is None and new_ver:
            # New component
            changes[component] = {
                "status": "new",
                "old_version": None,
                "new_version": new_ver,
            }
        elif old_ver and new_ver is None:
            # Removed component
            changes[component] = {
                "status": "removed",
                "old_version": old_ver,
                "new_version": None,
            }
        elif old_ver != new_ver:
            # Updated component
            changes[component] = {
                "status": "updated",
                "old_version": old_ver,
                "new_version": new_ver,
            }
        else:
            # Same version
            changes[component] = {
                "status": "same",
                "old_version": old_ver,
                "new_version": new_ver,
            }

    return changes


def format_version_changes(
    changes: dict[str, dict[str, Any]], show_unchanged: bool = False
) -> list[str]:
    """
    Format version changes as human-readable strings.

    Args:
        changes: Changes dictionary from compare_versions.
        show_unchanged: Whether to show components with same version.

    Returns:
        List of formatted strings describing changes.
    """
    lines = []

    for component, change in sorted(changes.items()):
        status = change["status"]
        old_ver = change["old_version"]
        new_ver = change["new_version"]

        if status == "new":
            lines.append(f"✨ {component}: NEW ({new_ver})")
        elif status == "updated":
            lines.append(f"⬆️  {component}: {old_ver} → {new_ver}")
        elif status == "removed":
            lines.append(f"❌ {component}: REMOVED (was {old_ver})")
        elif status == "same" and show_unchanged:
            lines.append(f"✓  {component}: {new_ver}")

    return lines


def track_update() -> tuple[dict[str, str], list[str]]:
    """
    Track version update: load previous, get current, save, and return changes.

    Returns:
        Tuple of (current_versions, formatted_change_lines).
    """
    previous = load_previous_versions()
    current = get_component_versions()
    changes = compare_versions(previous, current)
    change_lines = format_version_changes(changes, show_unchanged=False)

    # Save current versions for next time
    save_versions(current)

    return current, change_lines
