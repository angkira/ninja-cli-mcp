"""
Automatic updater for ninja-mcp.

Handles the complete update process:
1. Detects if update is needed
2. Backs up credentials
3. Upgrades package through the resolved update channel (github, pypi, brew)
4. Runs migration
5. Updates MCP config
6. Restarts daemons
7. Verifies everything works

Usage:
    ninja-config update --channel pypi
"""

import json
import shutil
import subprocess
import sys
import urllib.request
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ninja_config.config_migrator import ConfigMigrator
from ninja_config.credentials import CredentialManager


PYPI_JSON_URL = "https://pypi.org/pypi/ninja-mcp/json"
GITHUB_RELEASES_URL = "https://api.github.com/repos/angkira/ninja-cli-mcp/releases/latest"
BREW_FORMULA = "ninja-mcp"
UPDATE_EXTRAS = "runtime"
CHANNELS = ("auto", "github", "pypi", "brew")


class UpdateError(Exception):
    """Update failed."""

    pass


class AutoUpdater:
    """Automatic updater for ninja-mcp."""

    def __init__(
        self,
        repo_path: Path | None = None,
        channel: str = "auto",
        console: Console | None = None,
    ):
        """
        Initialize the auto-updater.

        Args:
            repo_path: Path to ninja-cli-mcp repository (auto-detected if not provided)
            channel: Update channel (auto, github, pypi, brew)
            console: Rich console for output (created if not provided)
        """
        self.repo_path = repo_path or self._find_repo_path()
        self.channel = channel or "auto"
        self.console = console or Console()

    def _find_repo_path(self) -> Path | None:
        """Find the ninja-cli-mcp repository path if this is a source checkout."""
        # Try common locations
        candidates = [
            Path.cwd(),
            Path(__file__).parent.parent.parent,  # From installed package
            Path.home() / "Project" / "ninja-coder" / "ninja-cli-mcp",
        ]

        for path in candidates:
            if (path / "pyproject.toml").exists() and (path / ".git").exists():
                return path

        return None

    def _brew_has_formula(self) -> bool:
        """Check whether the ninja-mcp Homebrew formula is installed."""
        try:
            result = subprocess.run(
                ["brew", "list", "--formula", BREW_FORMULA],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def _detect_channel(self) -> str:
        """Detect the update channel for this installation."""
        if self._find_editable_repo() is not None or (
            self.repo_path is not None and (self.repo_path / ".git").exists()
        ):
            return "github"
        if shutil.which("brew") and self._brew_has_formula():
            return "brew"
        return "pypi"

    def resolve_channel(self) -> str:
        """Resolve the effective update channel."""
        if self.channel != "auto":
            if self.channel not in ("github", "pypi", "brew"):
                raise UpdateError(
                    f"Unknown channel '{self.channel}'. Choose from: github, pypi, brew"
                )
            return self.channel
        return self._detect_channel()

    def _installed_version(self) -> str:
        """Return the installed ninja-mcp version."""
        try:
            installed = pkg_version("ninja-mcp")
            if installed:
                return installed
        except PackageNotFoundError:
            pass
        try:
            from ninja_agent import __version__ as agent_version

            if agent_version:
                return agent_version
        except ImportError:
            pass
        return "0.0.0-dev"

    def _pypi_latest(self) -> str:
        """Fetch the latest ninja-mcp version from PyPI."""
        try:
            with urllib.request.urlopen(PYPI_JSON_URL, timeout=20) as response:
                data = json.load(response)
            return data["info"]["version"]
        except Exception as e:
            raise UpdateError(f"Could not fetch latest version from PyPI: {e}") from e

    def _github_latest(self) -> str:
        """Fetch the latest ninja-mcp version from GitHub releases."""
        try:
            request = urllib.request.Request(
                GITHUB_RELEASES_URL, headers={"User-Agent": "ninja-mcp-update"}
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.load(response)
            return data["tag_name"].lstrip("v")
        except Exception as e:
            raise UpdateError(f"Could not fetch latest version from GitHub: {e}") from e

    def _brew_latest(self) -> str:
        """Fetch the latest ninja-mcp version from Homebrew."""
        try:
            result = subprocess.run(
                ["brew", "info", "--json=v2", BREW_FORMULA],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                raise UpdateError(f"Could not fetch latest version from Homebrew: {result.stderr}")
            data = json.loads(result.stdout)
            return data["formulae"][0]["versions"]["stable"]
        except UpdateError:
            raise
        except Exception as e:
            raise UpdateError(f"Could not fetch latest version from Homebrew: {e}") from e

    def _latest_version(self, channel: str) -> str:
        """Fetch the latest version for the given channel."""
        if channel == "pypi":
            return self._pypi_latest()
        if channel == "github":
            return self._github_latest()
        if channel == "brew":
            return self._brew_latest()
        raise UpdateError(f"Unknown channel '{channel}'. Choose from: github, pypi, brew")

    def _needs_update(self, installed: str, latest: str) -> bool:
        """Compare installed and latest versions."""
        try:
            return Version(latest) > Version(installed)
        except InvalidVersion:
            return True

    def update(self, force: bool = False, channel: str | None = None) -> dict[str, Any]:
        """
        Perform complete update process.

        Args:
            force: Force update even if no updates available
            channel: Override the update channel for this run

        Returns:
            Update result dictionary

        Raises:
            UpdateError: If update fails
        """
        if channel:
            self.channel = channel
        ch = self.resolve_channel()

        self.console.print(Panel.fit("[bold]Ninja MCP Updater[/bold]", style="cyan"))

        with self.console.status("Checking versions..."):
            installed = self._installed_version()
            latest = self._latest_version(ch)

        self.console.print(f"Channel: {ch}")
        self.console.print(f"Installed: {installed}")
        self.console.print(f"Latest: {latest}")

        if not force and not self._needs_update(installed, latest):
            self.console.print(f"[bold green]Already up to date ({installed})[/bold green]")
            return {
                "verified": True,
                "up_to_date": True,
                "channel": ch,
                "installed": installed,
                "latest": latest,
                "steps_completed": [],
                "credentials_backed_up": False,
                "package_updated": False,
                "migration_ran": False,
                "daemons_restarted": False,
            }

        result: dict[str, Any] = {
            "steps_completed": [],
            "credentials_backed_up": False,
            "package_updated": False,
            "migration_ran": False,
            "daemons_restarted": False,
            "verified": False,
            "channel": ch,
            "installed": installed,
            "latest": latest,
        }

        try:
            with self.console.status("Backing up credentials..."):
                backup_path = self._backup_credentials()
            result["credentials_backed_up"] = True
            result["backup_path"] = str(backup_path)
            result["steps_completed"].append("backup")
            self.console.print(f"✓ Credentials backed up to {backup_path}")

            with self.console.status("Upgrading package..."):
                self._reinstall_package(ch)
            result["package_updated"] = True
            result["steps_completed"].append("upgrade")
            self.console.print("✓ Package updated")

            with self.console.status("Checking for migration..."):
                migration_result = self._run_migration_if_needed()
            if migration_result:
                result["migration_ran"] = True
                result["migration_result"] = migration_result
                result["steps_completed"].append("migration")
                self.console.print(
                    f"✓ Migrated {migration_result['credentials_count']} credentials"
                )
            else:
                self.console.print("✓ Migration not needed")

            with self.console.status("Updating MCP configuration..."):
                self._update_mcp_config()
            result["steps_completed"].append("mcp_config")
            self.console.print("✓ MCP config updated")

            with self.console.status("Restarting daemons..."):
                self._restart_daemons()
            result["daemons_restarted"] = True
            result["steps_completed"].append("restart_daemons")
            self.console.print("✓ Daemons restarted")

            with self.console.status("Verifying installation..."):
                verification = self._verify()
            result["verified"] = verification["success"]
            result["verification"] = verification
            result["steps_completed"].append("verify")
            self.console.print("✓ Verification complete")
        except Exception as e:
            recovery = [str(e), ""]
            if result.get("backup_path"):
                recovery.append(f"Credentials backup: {result['backup_path']}")
            recovery.append("Logs: ~/.cache/ninja-mcp/logs/")
            recovery.append("Run: ninja-mcp daemon status")
            self.console.print(Panel("\n".join(recovery), title="Update failed", style="red"))
            raise UpdateError(f"Update failed: {e}") from e

        table = Table(title="Update Summary")
        table.add_column("Step")
        table.add_column("Result")
        table.add_row("Backup", "OK")
        table.add_row("Package", "OK")
        table.add_row(
            "Migration",
            str(result["migration_result"]["credentials_count"])
            if result["migration_ran"]
            else "Skipped",
        )
        table.add_row("Daemons", "OK")
        table.add_row("Verification", "OK" if result["verified"] else "Failed")
        self.console.print(table)
        self.console.print("[bold green]Update completed successfully[/bold green]")

        return result

    def _git_pull(self) -> None:
        """Pull latest code from git."""
        if self.repo_path is None:
            print("   i No source checkout detected, using package channel")
            return

        # Check if this is a git repository
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            print("   i Not a git repository, skipping pull")
            return

        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            if "Already up to date" in result.stdout:
                print("   i Already up to date")
        except subprocess.CalledProcessError as e:
            raise UpdateError(f"git pull failed: {e.stderr}") from e
        except subprocess.TimeoutExpired:
            raise UpdateError("git pull timed out after 5 minutes") from None

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
            backup_path = Path.home() / f"credentials.db.backup-{timestamp}"

            import shutil

            shutil.copy2(creds_db, backup_path)
            backup_path.chmod(0o600)

            return backup_path

        # No credentials to backup
        return Path("/dev/null")

    def _reinstall_package(self, channel: str | None = None) -> None:
        """Reinstall/upgrade the package through the resolved update channel.

        ``github`` reinstalls from the source checkout (editable when one is
        detected), ``pypi`` installs from PyPI via uv or pip, and ``brew``
        upgrades the Homebrew formula.
        """
        ch = channel or self.resolve_channel()

        if ch == "github":
            editable_repo = self._find_editable_repo()
            if editable_repo is not None:
                self._reinstall_editable(editable_repo)
                return
            if self.repo_path is not None and (self.repo_path / ".git").exists():
                self._git_pull()
                self._reinstall_editable(self.repo_path)
                return
            self._run_install_command(
                ["uv", "tool", "install", "--force", f"ninja-mcp[{UPDATE_EXTRAS}]"]
            )
            return

        if ch == "pypi":
            self._pypi_reinstall()
            return

        if ch == "brew":
            self._run_install_command(["brew", "update"], timeout=300)
            self._run_install_command(["brew", "upgrade", BREW_FORMULA])
            return

        raise UpdateError(f"Unknown channel '{ch}'. Choose from: github, pypi, brew")

    def _install_method(self) -> str:
        """Detect how ninja-mcp was installed (uv-tool / pipx / pip / unknown)."""
        if (Path.home() / ".local" / "share" / "uv" / "tools" / "ninja-mcp").exists():
            return "uv-tool"
        if (Path.home() / ".local" / "pipx" / "venvs" / "ninja-mcp").exists():
            return "pipx"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", "ninja-mcp"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                return "pip"
        except (OSError, subprocess.TimeoutExpired):
            pass
        return "unknown"

    def _pypi_reinstall(self) -> None:
        """Reinstall from PyPI into the environment ninja-mcp was installed in.

        Updating the *wrong* environment (e.g. creating a uv tool when the user
        installed with pip) made `update` look like a no-op on some machines.
        """
        spec = f"ninja-mcp[{UPDATE_EXTRAS}]"
        method = self._install_method()
        if method == "uv-tool":
            self._run_install_command(["uv", "tool", "install", "--force", spec])
            return
        if method == "pipx":
            self._run_install_command(["pipx", "install", "--force", spec])
            return
        if method == "pip" or not shutil.which("uv"):
            self._pip_install(spec)
            return
        # No detectable install method but uv exists — use a uv tool.
        self._run_install_command(["uv", "tool", "install", "--force", spec])

    def _pip_install(self, spec: str) -> None:
        """``pip install --upgrade`` with a PEP 668 retry (externally-managed)."""
        base = [sys.executable, "-m", "pip", "install", "--user", "--upgrade", spec]
        try:
            self._run_install_command(base)
        except UpdateError as e:
            if "externally-managed" not in str(e):
                raise
            # Debian/Ubuntu (and Homebrew) mark the interpreter as externally
            # managed — fall back to the documented override.
            self._run_install_command([*base, "--break-system-packages"])

    def _run_install_command(self, command: list[str], timeout: int = 600) -> None:
        """Run a package install command and stream its output."""
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            for line in result.stdout.splitlines():
                if line.strip():
                    print(f"   i {line.strip()}")
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or e.stdout or "").strip() or f"exit {e.returncode}"
            raise UpdateError(f"Package upgrade failed: {detail}") from e
        except subprocess.TimeoutExpired:
            raise UpdateError(f"Package upgrade timed out after {timeout // 60} minutes") from None
        except FileNotFoundError as e:
            raise UpdateError(f"Installer not found: {command[0]}") from e

    def _find_editable_repo(self) -> Path | None:
        """Detect an editable (source) installation of ninja-mcp.

        Scans the active tool environment for the ``_editable_impl_ninja_mcp.pth``
        file that uv writes for ``uv tool install --editable``.

        Returns:
            Path to the editable source checkout, or None when not editable.
        """
        import site

        candidates: list[Path] = []
        try:
            candidates.extend(Path(p) for p in site.getsitepackages())
        except Exception:
            pass
        try:
            candidates.append(Path(site.getusersitepackages()))
        except Exception:
            pass

        # uv tool environments live under ~/.local/share/uv/tools/<name>.
        # The interpreter version inside the venv is not known here, so scan
        # every site-packages directory found under the tool root.
        tool_root = Path.home() / ".local" / "share" / "uv" / "tools" / "ninja-mcp"
        if tool_root.exists():
            for lib in (tool_root / "lib").glob("python*"):
                sp = lib / "site-packages"
                if sp.is_dir():
                    candidates.append(sp)

        seen: set[Path] = set()
        for sp in candidates:
            if sp in seen:
                continue
            seen.add(sp)
            pth = sp / "_editable_impl_ninja_mcp.pth"
            if not pth.exists():
                continue
            for raw_line in pth.read_text().splitlines():
                stripped = raw_line.strip()
                if not stripped:
                    continue
                # uv writes the src dir (or the repo root) — walk up looking
                # for pyproject.toml to find the actual source checkout.
                cursor = Path(stripped)
                while cursor != cursor.parent:
                    if (cursor / "pyproject.toml").exists():
                        return cursor
                    cursor = cursor.parent
        return None

    def _reinstall_editable(self, repo: Path) -> None:
        """Reinstall the editable package from its source checkout."""
        print(f"   i Detected editable install at {repo}")
        try:
            result = subprocess.run(
                ["uv", "tool", "install", "--force", "--editable", str(repo)],
                check=True,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )
            for line in result.stdout.splitlines():
                if line.strip():
                    print(f"   i {line.strip()}")
        except subprocess.CalledProcessError as e:
            raise UpdateError(f"Editable reinstall failed: {e.stderr}") from e
        except subprocess.TimeoutExpired:
            raise UpdateError("Editable reinstall timed out after 10 minutes") from None

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
            print("   i No .claude.json found, skipping MCP config update")
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
            print("   i Trying to read from .ninja-mcp.env file...")

            # Fallback: read from .env file
            env_file = Path.home() / ".ninja-mcp.env"
            if env_file.exists():
                import re

                with open(env_file) as f:
                    for line in f:
                        match = re.match(r"^OPENROUTER_API_KEY=(.+)$", line.strip())
                        if match:
                            openrouter_key = match.group(1).strip("\"'")
                            break

        if not openrouter_key:
            print("   ⚠️  No OPENROUTER_API_KEY found in credentials or .env file")
            return

        # Update all ninja servers
        mcpServers = config.get("mcpServers", {})
        updated = []

        for server_name in ["ninja-coder", "ninja-researcher", "ninja-secretary"]:
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
            print(f"   i Updated: {', '.join(updated)}")

    def _restart_daemons(self) -> None:
        """Restart ninja daemons."""
        try:
            subprocess.run(
                ["ninja-mcp", "daemon", "restart"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,  # 1 minute timeout
            )
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or e.stdout or "").strip() or f"exit {e.returncode}"
            raise UpdateError(f"Daemon restart failed: {detail}") from e
        except subprocess.TimeoutExpired:
            raise UpdateError("Daemon restart timed out after 1 minute") from None

    def _verify(self) -> dict[str, Any]:
        """Verify installation."""
        verification = {
            "success": True,
            "checks": {},
        }

        # Check daemons
        try:
            result = subprocess.run(
                ["ninja-mcp", "daemon", "status"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout
            )
            daemon_status = json.loads(result.stdout)

            running_daemons = []
            for name, status in daemon_status.items():
                if status.get("running"):
                    running_daemons.append(name)

            required_daemons = {"coder", "researcher"}
            running_required = required_daemons.issubset(set(running_daemons))

            verification["checks"]["daemons"] = {
                "success": running_required,
                "running": running_daemons,
                "required": sorted(required_daemons),
            }

            if not running_required:
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
    parser.add_argument(
        "--channel",
        choices=CHANNELS,
        default="auto",
        help="Update channel: auto (detect), github, pypi, brew",
    )

    args = parser.parse_args()

    try:
        updater = AutoUpdater(repo_path=args.repo_path, channel=args.channel)
        result = updater.update(force=args.force)

        if result["verified"]:
            print("\n✅ Update completed successfully!")
            print("\nYou can now use:")
            print("  - ninja-config configure")
            print("  - ninja-mcp daemon status")
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
