"""
Automatic updater for ninja-mcp.

Handles the complete update process:
1. Detects if update is needed
2. Backs up credentials
3. Reinstalls package
4. Runs migration
5. Updates MCP config
6. Restarts daemons
7. Verifies everything works

Usage:
    ninja-config update
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ninja_config.config_migrator import ConfigMigrator
from ninja_config.credentials import CredentialManager


class UpdateError(Exception):
    """Update failed."""

    pass


class AutoUpdater:
    """Automatic updater for ninja-mcp."""

    def __init__(self, repo_path: Path | None = None):
        """
        Initialize the auto-updater.

        Args:
            repo_path: Path to ninja-cli-mcp repository (auto-detected if not provided)
        """
        self.repo_path = repo_path or self._find_repo_path()

    def _find_repo_path(self) -> Path:
        """Find the ninja-cli-mcp repository path."""
        # Try common locations
        candidates = [
            Path.cwd(),
            Path(__file__).parent.parent.parent,  # From installed package
            Path.home() / "Project" / "ninja-coder" / "ninja-cli-mcp",
        ]

        for path in candidates:
            if (path / "pyproject.toml").exists():
                return path

        raise UpdateError(
            "Could not find ninja-cli-mcp repository. "
            "Please run from the repository directory or specify --repo-path"
        )

    def update(self, force: bool = False) -> dict[str, Any]:
        """
        Perform complete update process.

        Args:
            force: Force update even if no updates available

        Returns:
            Update result dictionary

        Raises:
            UpdateError: If update fails
        """
        print("\n" + "=" * 70)
        print("  NINJA-MCP AUTO-UPDATER")
        print("=" * 70)
        print()

        result = {
            "steps_completed": [],
            "credentials_backed_up": False,
            "package_updated": False,
            "migration_ran": False,
            "daemons_restarted": False,
            "verified": False,
        }

        try:
            # Step 1: Pull latest code
            print("📥 Step 1: Pulling latest code...")
            self._git_pull()
            result["steps_completed"].append("git_pull")
            print("   ✓ Code updated\n")

            # Step 2: Backup credentials
            print("💾 Step 2: Backing up credentials...")
            backup_path = self._backup_credentials()
            result["credentials_backed_up"] = True
            result["backup_path"] = str(backup_path)
            result["steps_completed"].append("backup")
            print(f"   ✓ Backed up to: {backup_path}\n")

            # Step 3: Reinstall package
            print("📦 Step 3: Reinstalling package...")
            self._reinstall_package()
            result["package_updated"] = True
            result["steps_completed"].append("reinstall")
            print("   ✓ Package updated\n")

            # Step 4: Run migration if needed
            print("🔄 Step 4: Checking for migration...")
            migration_result = self._run_migration_if_needed()
            if migration_result:
                result["migration_ran"] = True
                result["migration_result"] = migration_result
                result["steps_completed"].append("migration")
                print(f"   ✓ Migrated {migration_result['credentials_count']} credentials\n")
            else:
                print("   ℹ️  Migration not needed\n")

            # Step 5: Update MCP config
            print("⚙️  Step 5: Updating MCP configuration...")
            self._update_mcp_config()
            result["steps_completed"].append("mcp_config")
            print("   ✓ MCP config updated\n")

            # Step 6: Restart daemons
            print("🔄 Step 6: Restarting daemons...")
            self._restart_daemons()
            result["daemons_restarted"] = True
            result["steps_completed"].append("restart_daemons")
            print("   ✓ Daemons restarted\n")

            # Step 7: Verify
            print("✅ Step 7: Verifying installation...")
            verification = self._verify()
            result["verified"] = verification["success"]
            result["verification"] = verification
            result["steps_completed"].append("verify")
            print("   ✓ Verification complete\n")

            print("=" * 70)
            print("  UPDATE COMPLETED SUCCESSFULLY!")
            print("=" * 70)
            print()

            return result

        except Exception as e:
            print(f"\n✗ ERROR: {e}\n")
            print(f"Steps completed: {', '.join(result['steps_completed'])}")
            print("\nTo recover:")
            if result.get("backup_path"):
                print(f"  1. Your credentials backup: {result['backup_path']}")
            print("  2. Check logs in ~/.cache/ninja-mcp/logs/")
            print("  3. Run: ninja-daemon status")
            raise UpdateError(f"Update failed: {e}") from e

    def _git_pull(self) -> None:
        """Pull latest code from git."""
        # Check if this is a git repository
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            print("   ℹ️  Not a git repository, skipping pull")
            return

        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            if "Already up to date" in result.stdout:
                print("   ℹ️  Already up to date")
        except subprocess.CalledProcessError as e:
            raise UpdateError(f"git pull failed: {e.stderr}") from e

    def _backup_credentials(self) -> Path:
        """Backup credentials before update."""
        old_env = Path.home() / ".ninja-mcp.env"

        if old_env.exists():
            import time
            timestamp = int(time.time())
            backup_path = Path.home() / f".ninja-mcp.env.backup-{timestamp}"

            import shutil
            shutil.copy2(old_env, backup_path)
            backup_path.chmod(0o600)

            return backup_path

        # Also backup credentials database if it exists
        creds_db = Path.home() / ".ninja" / "credentials.db"
        if creds_db.exists():
            import time
            timestamp = int(time.time())
            backup_path = Path.home() / ".ninja" / f"credentials.db.backup-{timestamp}"

            import shutil
            shutil.copy2(creds_db, backup_path)
            backup_path.chmod(0o600)

            return backup_path

        # No credentials to backup
        return Path("/dev/null")

    def _reinstall_package(self) -> None:
        """Reinstall the package."""
        try:
            result = subprocess.run(
                ["uv", "tool", "install", "--reinstall", "--force", "."],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            # Check if version changed
            if "ninja-mcp==" in result.stdout:
                # Extract version
                for line in result.stdout.split("\n"):
                    if "ninja-mcp==" in line:
                        print(f"   ℹ️  {line.strip()}")
        except subprocess.CalledProcessError as e:
            raise UpdateError(f"Package reinstall failed: {e.stderr}") from e

    def _run_migration_if_needed(self) -> dict[str, Any] | None:
        """Run migration if needed."""
        migrator = ConfigMigrator()

        if migrator.needs_migration():
            try:
                return migrator.migrate()
            except Exception as e:
                raise UpdateError(f"Migration failed: {e}") from e

        return None

    def _update_mcp_config(self) -> None:
        """Update MCP configuration with credentials."""
        config_path = Path.home() / ".claude.json"

        if not config_path.exists():
            print("   ℹ️  No .claude.json found, skipping MCP config update")
            return

        # Backup MCP config
        backup_path = Path.home() / ".claude.json.backup-auto-update"
        import shutil
        shutil.copy2(config_path, backup_path)

        with open(config_path) as f:
            config = json.load(f)

        # Get credentials - try encrypted DB first, fallback to .env file
        openrouter_key = None
        try:
            manager = CredentialManager()
            openrouter_key = manager.get("OPENROUTER_API_KEY")
        except Exception as e:
            print(f"   ⚠️  Could not read from credentials DB: {e}")
            print("   ℹ️  Trying to read from .ninja-mcp.env file...")

            # Fallback: read from .env file
            env_file = Path.home() / ".ninja-mcp.env"
            if env_file.exists():
                import re
                with open(env_file) as f:
                    for line in f:
                        match = re.match(r'^OPENROUTER_API_KEY=(.+)$', line.strip())
                        if match:
                            openrouter_key = match.group(1).strip('"\'')
                            break

        if not openrouter_key:
            print("   ⚠️  No OPENROUTER_API_KEY found in credentials or .env file")
            return

        # Update all ninja servers
        mcpServers = config.get("mcpServers", {})
        updated = []

        for server_name in ["ninja-coder", "ninja-researcher", "ninja-secretary", "ninja-prompts"]:
            if server_name in mcpServers:
                if "env" not in mcpServers[server_name]:
                    mcpServers[server_name]["env"] = {}

                mcpServers[server_name]["env"]["OPENROUTER_API_KEY"] = openrouter_key
                mcpServers[server_name]["env"]["OPENAI_API_KEY"] = openrouter_key
                mcpServers[server_name]["env"]["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
                updated.append(server_name)

        # Save
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        if updated:
            print(f"   ℹ️  Updated: {', '.join(updated)}")

    def _restart_daemons(self) -> None:
        """Restart ninja daemons."""
        try:
            subprocess.run(
                ["ninja-daemon", "restart"],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise UpdateError(f"Daemon restart failed: {e.stderr}") from e

    def _verify(self) -> dict[str, Any]:
        """Verify installation."""
        verification = {
            "success": True,
            "checks": {},
        }

        # Check daemons
        try:
            result = subprocess.run(
                ["ninja-daemon", "status"],
                check=True,
                capture_output=True,
                text=True,
            )
            daemon_status = json.loads(result.stdout)

            running_daemons = []
            for name, status in daemon_status.items():
                if status.get("running"):
                    running_daemons.append(name)

            verification["checks"]["daemons"] = {
                "success": len(running_daemons) >= 3,
                "running": running_daemons,
            }

            if len(running_daemons) < 3:
                verification["success"] = False

        except Exception as e:
            verification["checks"]["daemons"] = {
                "success": False,
                "error": str(e),
            }
            verification["success"] = False

        # Check credentials
        try:
            manager = CredentialManager()
            has_key = bool(manager.get("OPENROUTER_API_KEY"))

            verification["checks"]["credentials"] = {
                "success": has_key,
                "has_openrouter_key": has_key,
            }

            if not has_key:
                verification["success"] = False

        except Exception as e:
            verification["checks"]["credentials"] = {
                "success": False,
                "error": str(e),
            }
            verification["success"] = False

        return verification


def main():
    """Main entry point for auto-updater."""
    import argparse

    parser = argparse.ArgumentParser(description="Auto-update ninja-mcp")
    parser.add_argument("--repo-path", type=Path, help="Path to ninja-cli-mcp repository")
    parser.add_argument("--force", action="store_true", help="Force update")

    args = parser.parse_args()

    try:
        updater = AutoUpdater(repo_path=args.repo_path)
        result = updater.update(force=args.force)

        if result["verified"]:
            print("\n✅ Update completed successfully!")
            print("\nYou can now use:")
            print("  - ninja-config configure")
            print("  - ninja-daemon status")
            print("  - ninja-coder (via MCP)")
            sys.exit(0)
        else:
            print("\n⚠️  Update completed but verification failed")
            print("Please check the verification results above")
            sys.exit(1)

    except UpdateError as e:
        print(f"\n❌ Update failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nUpdate cancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
