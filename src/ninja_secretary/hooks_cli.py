"""
CLI for ninja-secretary hooks.

Provides commands for path validation, session reporting, and change analysis.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ninja_common.path_utils import PathTraversalError, is_path_within, safe_resolve


@dataclass
class HookResult:
    """Standard result format for hook commands."""
    
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None


class HookCommand:
    """Base class for hook commands."""
    
    def execute(self) -> HookResult:
        """Execute the hook command."""
        raise NotImplementedError


class ValidatePathCommand(HookCommand):
    """Validate a file path for security and policy compliance."""
    
    def __init__(self, file_path: str, repo_root: str):
        self.file_path = file_path
        self.repo_root = repo_root
    
    def execute(self) -> HookResult:
        """Execute path validation."""
        try:
            # Check for path traversal attempts
            if ".." in self.file_path or self.file_path.startswith(("/", "\\")):
                resolved_path = Path(self.file_path).resolve()
                root_path = Path(self.repo_root).resolve()
                try:
                    resolved_path.relative_to(root_path)
                except ValueError:
                    return HookResult(
                        success=False,
                        data={"status": "invalid", "reason": "path_traversal_detected"}
                    )
            
            # Resolve the path safely
            try:
                safe_path = safe_resolve(self.file_path, self.repo_root)
            except PathTraversalError:
                return HookResult(
                    success=False,
                    data={"status": "invalid", "reason": "path_traversal_detected"}
                )
            
            # Check deny patterns
            deny_patterns = {".git", "node_modules", "__pycache__", ".env"}
            path_parts = set(safe_path.relative_to(Path(self.repo_root).resolve()).parts)
            
            if path_parts & deny_patterns:
                return HookResult(
                    success=False,
                    data={"status": "invalid", "reason": "denied_path_pattern"}
                )
            
            # Check if path exists
            if not safe_path.exists():
                return HookResult(
                    success=False,
                    data={"status": "invalid", "reason": "path_not_found"}
                )
            
            return HookResult(
                success=True,
                data={"status": "valid", "path": str(safe_path)}
            )
            
        except Exception as e:
            return HookResult(
                success=False,
                error=str(e),
                data={"status": "invalid", "reason": "internal_error"}
            )


class SessionReportCommand(HookCommand):
    """Generate a session activity summary."""
    
    def __init__(self, repo_root: str, save: bool = False):
        self.repo_root = repo_root
        self.save = save
    
    def execute(self) -> HookResult:
        """Execute session report generation."""
        try:
            # Get basic repo info
            repo_path = Path(self.repo_root).resolve()
            
            # Count files in repo
            file_count = 0
            dir_count = 0
            for item in repo_path.rglob("*"):
                if item.is_file():
                    file_count += 1
                elif item.is_dir():
                    dir_count += 1
            
            # Get git info if available
            branch = "unknown"
            commit = "unknown"
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    check=True
                )
                branch = result.stdout.strip()
                
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    check=True
                )
                commit = result.stdout.strip()[:8]
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
            
            # Create report data
            report_data = {
                "repository": str(repo_path),
                "branch": branch,
                "commit": commit,
                "files": file_count,
                "directories": dir_count,
                "generated_at": datetime.now().isoformat()
            }
            
            # Save to file if requested
            if self.save:
                try:
                    from ninja_common.path_utils import get_internal_dir
                    internal_dir = get_internal_dir(self.repo_root)
                    sessions_dir = internal_dir / "sessions"
                    sessions_dir.mkdir(parents=True, exist_ok=True)
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    report_file = sessions_dir / f"session_report_{timestamp}.json"
                    
                    with open(report_file, "w") as f:
                        json.dump(report_data, f, indent=2)
                    
                    report_data["saved_to"] = str(report_file)
                except Exception as e:
                    report_data["save_error"] = str(e)
            
            return HookResult(success=True, data=report_data)
            
        except Exception as e:
            return HookResult(
                success=False,
                error=str(e)
            )


class AnalyzeChangesCommand(HookCommand):
    """Analyze changes using git diff."""
    
    def __init__(self, repo_root: str, since: str | None = None):
        self.repo_root = repo_root
        self.since = since
    
    def execute(self) -> HookResult:
        """Execute change analysis."""
        try:
            # Build git diff command
            cmd = ["git", "diff", "--numstat"]
            if self.since:
                cmd.extend([self.since, "HEAD"])
            
            # Execute git diff
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the output
            lines = result.stdout.strip().split("\n")
            if not lines or (len(lines) == 1 and not lines[0]):
                return HookResult(
                    success=True,
                    data={
                        "files_changed": 0,
                        "lines_added": 0,
                        "lines_removed": 0,
                        "changes": []
                    }
                )
            
            changes = []
            total_added = 0
            total_removed = 0
            
            for line in lines:
                if not line.strip():
                    continue
                    
                parts = line.split("\t")
                if len(parts) >= 3:
                    try:
                        added = int(parts[0]) if parts[0] != "-" else 0
                        removed = int(parts[1]) if parts[1] != "-" else 0
                        filename = parts[2]
                        
                        total_added += added
                        total_removed += removed
                        
                        changes.append({
                            "file": filename,
                            "lines_added": added,
                            "lines_removed": removed
                        })
                    except ValueError:
                        # Skip malformed lines
                        continue
            
            return HookResult(
                success=True,
                data={
                    "files_changed": len(changes),
                    "lines_added": total_added,
                    "lines_removed": total_removed,
                    "changes": changes
                }
            )
            
        except subprocess.CalledProcessError as e:
            return HookResult(
                success=False,
                error=f"Git command failed: {e.stderr}"
            )
        except FileNotFoundError:
            return HookResult(
                success=False,
                error="Git is not installed or not found in PATH"
            )
        except Exception as e:
            return HookResult(
                success=False,
                error=str(e)
            )


def main():
    """Main entry point for the hooks CLI."""
    parser = argparse.ArgumentParser(description="Ninja Secretary Hooks CLI")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")
    
    # Validate path command
    validate_parser = subparsers.add_parser("validate-path", help="Validate a file path")
    validate_parser.add_argument("file_path", help="Path to validate")
    validate_parser.add_argument("--repo-root", required=True, help="Repository root directory")
    
    # Session report command
    session_parser = subparsers.add_parser("session-report", help="Generate session report")
    session_parser.add_argument("--repo-root", required=True, help="Repository root directory")
    session_parser.add_argument("--save", action="store_true", help="Save report to cache")
    
    # Analyze changes command
    analyze_parser = subparsers.add_parser("analyze-changes", help="Analyze code changes")
    analyze_parser.add_argument("--repo-root", required=True, help="Repository root directory")
    analyze_parser.add_argument("--since", help="Analyze changes since this commit/ref")
    
    args = parser.parse_args()
    
    try:
        if args.command == "validate-path":
            command = ValidatePathCommand(args.file_path, args.repo_root)
        elif args.command == "session-report":
            command = SessionReportCommand(args.repo_root, args.save)
        elif args.command == "analyze-changes":
            command = AnalyzeChangesCommand(args.repo_root, args.since)
        else:
            raise ValueError(f"Unknown command: {args.command}")
        
        result = command.execute()
        
        if args.json:
            output = {
                "success": result.success,
                "data": result.data,
                "error": result.error
            }
            print(json.dumps(output, indent=2))
        else:
            if result.success:
                if result.data:
                    print(json.dumps(result.data, indent=2))
                else:
                    print("Command executed successfully")
            else:
                print(f"Error: {result.error or 'Command failed'}")
                if result.data:
                    print(json.dumps(result.data, indent=2))
        
        sys.exit(0 if result.success else 1)
        
    except Exception as e:
        if args.json:
            print(json.dumps({
                "success": False,
                "error": str(e)
            }, indent=2))
        else:
            print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
