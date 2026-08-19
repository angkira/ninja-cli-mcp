"""``ninja-mcp update`` — update ninja-mcp to the latest version.

Thin CLI wrapper over :class:`ninja_config.auto_updater.AutoUpdater`. Preserves
credentials, reinstalls the package (editable-aware), runs migrations, restarts
daemons and verifies the installation.

Usage::

    ninja-mcp update
    ninja-mcp update --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ninja_config.auto_updater import AutoUpdater, UpdateError


def main() -> int:
    """CLI entry point for ``ninja-mcp update``."""
    parser = argparse.ArgumentParser(
        prog="ninja-mcp update",
        description="Update ninja-mcp to the latest version (preserves config, restarts daemons)",
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=None,
        help="Path to the ninja-cli-mcp source checkout (auto-detected)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force update/reinstall even when already up to date",
    )
    args = parser.parse_args()

    try:
        updater = AutoUpdater(repo_path=args.repo_path)
        result = updater.update(force=args.force)

        if result["verified"]:
            print("\n✅ Update completed successfully!")
            print("\nYou can now use:")
            print("  - ninja-mcp config")
            print("  - ninja-mcp daemon status")
            print("  - ninja-coder (via MCP)")
            return 0
        print("\n⚠️  Update completed but verification failed")
        print("Please check the verification results above")
        return 1
    except UpdateError as e:
        print(f"\n❌ Update failed: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n\nUpdate cancelled by user")
        return 1


if __name__ == "__main__":
    sys.exit(main())
