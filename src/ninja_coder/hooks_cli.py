"""
CLI for ninja-coder hooks.

Provides commands for file formatting, linting, and pre-commit checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ninja_common.hooks_base import (
    HookCommand,
    HookResult,
    detect_file_type,
    get_repo_root,
    get_staged_files,
    run_subprocess,
)


class FormatFileCommand(HookCommand):
    """Format a file using appropriate formatter."""
    
    def __init__(self, file_path: str, check_only: bool = False, json_output: bool = False):
        super().__init__(json_output)
        self.file_path = file_path
        self.check_only = check_only
    
    def execute(self) -> HookResult:
        """Execute file formatting."""
        path = Path(self.file_path)
        
        if not path.exists():
            return HookResult(
                status="error",
                message=f"File not found: {self.file_path}"
            )
        
        file_type = detect_file_type(self.file_path)
        
        if file_type == "python":
            return self._format_python()
        elif file_type in ("javascript", "typescript"):
            return self._format_js_ts()
        else:
            return HookResult(
                status="unchanged",
                message=f"No formatter configured for file type: {file_type}",
                data={"file": self.file_path, "file_type": file_type}
            )
    
    def _format_python(self) -> HookResult:
        """Format Python file using ruff."""
        cmd = ["ruff", "format"]
        if self.check_only:
            cmd.append("--check")
        cmd.append(self.file_path)
        
        exit_code, stdout, stderr = run_subprocess(cmd, timeout=30.0)
        
        if exit_code == 0:
            status = "unchanged" if self.check_only else "formatted"
            return HookResult(
                status=status,
                data={"file": self.file_path, "formatter": "ruff", "changes": not self.check_only}
            )
        elif exit_code == 1 and self.check_only:
            return HookResult(
                status="fail",
                message="File needs formatting",
                data={"file": self.file_path, "formatter": "ruff", "needs_formatting": True}
            )
        else:
            return HookResult(
                status="error",
                message=stderr or "Formatting failed",
                data={"file": self.file_path, "formatter": "ruff"}
            )
    
    def _format_js_ts(self) -> HookResult:
        """Format JS/TS file using prettier if available."""
        cmd = ["npx", "prettier"]
        if self.check_only:
            cmd.append("--check")
        else:
            cmd.append("--write")
        cmd.append(self.file_path)
        
        exit_code, stdout, stderr = run_subprocess(cmd, timeout=30.0)
        
        if exit_code == 0:
            status = "unchanged" if self.check_only else "formatted"
            return HookResult(
                status=status,
                data={"file": self.file_path, "formatter": "prettier", "changes": not self.check_only}
            )
        elif exit_code == 1 and self.check_only:
            return HookResult(
                status="fail",
                message="File needs formatting",
                data={"file": self.file_path, "formatter": "prettier", "needs_formatting": True}
            )
        else:
            # Prettier might not be installed
            return HookResult(
                status="unchanged",
                message="Prettier not available",
                data={"file": self.file_path, "formatter": "prettier"}
            )


class LintCheckCommand(HookCommand):
    """Check files for linting issues."""
    
    def __init__(
        self,
        staged: bool = False,
        fix: bool = False,
        repo_root: str | None = None,
        json_output: bool = False
    ):
        super().__init__(json_output)
        self.staged = staged
        self.fix = fix
        self.repo_root = repo_root or str(get_repo_root() or Path.cwd())
    
    def execute(self) -> HookResult:
        """Execute lint check."""
        files_to_check: list[str] = []
        
        if self.staged:
            staged_files = get_staged_files(self.repo_root)
            files_to_check = [f for f in staged_files if f.endswith(".py")]
        
        if not files_to_check:
            # Check all Python files in src/
            files_to_check = ["src/"]
        
        cmd = ["ruff", "check"]
        if self.fix:
            cmd.append("--fix")
        cmd.append("--output-format=json")
        cmd.extend(files_to_check)
        
        exit_code, stdout, stderr = run_subprocess(cmd, cwd=self.repo_root, timeout=60.0)
        
        issues = []
        try:
            if stdout.strip():
                issues = json.loads(stdout)
        except json.JSONDecodeError:
            pass
        
        if exit_code == 0:
            return HookResult(
                status="pass",
                data={"issues": [], "total_issues": 0, "fixed": 0}
            )
        else:
            formatted_issues = [
                {
                    "file": issue.get("filename", ""),
                    "line": issue.get("location", {}).get("row", 0),
                    "code": issue.get("code", ""),
                    "message": issue.get("message", "")
                }
                for issue in issues
            ]
            
            status = "fixed" if self.fix and exit_code == 0 else "fail"
            return HookResult(
                status=status,
                data={
                    "issues": formatted_issues[:10],  # Limit to first 10
                    "total_issues": len(issues),
                    "fixed": len(issues) if self.fix else 0
                }
            )


class PreCommitCommand(HookCommand):
    """Run pre-commit checks (lint + format check)."""
    
    def __init__(self, repo_root: str | None = None, json_output: bool = False):
        super().__init__(json_output)
        self.repo_root = repo_root or str(get_repo_root() or Path.cwd())
    
    def execute(self) -> HookResult:
        """Execute pre-commit checks."""
        checks = {}
        all_passed = True
        
        # Lint check
        lint_cmd = LintCheckCommand(staged=True, repo_root=self.repo_root)
        lint_result = lint_cmd.execute()
        checks["lint"] = {
            "status": lint_result.status,
            "issues": lint_result.data.get("total_issues", 0)
        }
        if not lint_result.success:
            all_passed = False
        
        # Format check on staged Python files
        staged_files = get_staged_files(self.repo_root)
        format_issues = 0
        for f in staged_files:
            if f.endswith(".py"):
                format_cmd = FormatFileCommand(
                    str(Path(self.repo_root) / f),
                    check_only=True
                )
                format_result = format_cmd.execute()
                if not format_result.success:
                    format_issues += 1
        
        checks["format"] = {
            "status": "pass" if format_issues == 0 else "fail",
            "issues": format_issues
        }
        if format_issues > 0:
            all_passed = False
        
        return HookResult(
            status="pass" if all_passed else "fail",
            data={"checks": checks}
        )


def main() -> int:
    """Main entry point for hooks CLI."""
    parser = argparse.ArgumentParser(
        description="Ninja Coder Hooks CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # format-file command
    format_parser = subparsers.add_parser("format-file", help="Format a file")
    format_parser.add_argument("file_path", help="Path to file to format")
    format_parser.add_argument("--check", action="store_true", help="Only check, don't modify")
    
    # lint-check command
    lint_parser = subparsers.add_parser("lint-check", help="Check for linting issues")
    lint_parser.add_argument("--staged", action="store_true", help="Only check staged files")
    lint_parser.add_argument("--fix", action="store_true", help="Auto-fix issues")
    lint_parser.add_argument("--repo-root", help="Repository root")
    
    # pre-commit command
    precommit_parser = subparsers.add_parser("pre-commit", help="Run pre-commit checks")
    precommit_parser.add_argument("--repo-root", help="Repository root")
    
    args = parser.parse_args()
    
    if args.command == "format-file":
        cmd = FormatFileCommand(args.file_path, args.check, args.json)
    elif args.command == "lint-check":
        cmd = LintCheckCommand(args.staged, args.fix, args.repo_root, args.json)
    elif args.command == "pre-commit":
        cmd = PreCommitCommand(args.repo_root, args.json)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1
    
    return cmd.run()


if __name__ == "__main__":
    sys.exit(main())
