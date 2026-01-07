"""CLI for skill packaging operations.

Usage:
    ninja-skill package <skill_dir> [-o <output>]
    ninja-skill validate <path>
    ninja-skill info <path>
    ninja-skill list [--installed] [--available]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from ninja_common.skill_packager import SkillPackager, SkillInfo, SkillValidationResult


def format_validation_result(result: SkillValidationResult, json_output: bool) -> str:
    """Format validation result for output."""
    if json_output:
        return json.dumps(result.to_dict(), indent=2)

    lines = []
    if result.valid:
        lines.append("Validation: PASSED")
    else:
        lines.append("Validation: FAILED")

    if result.errors:
        lines.append("\nErrors:")
        for error in result.errors:
            lines.append(f"  - {error}")

    if result.warnings:
        lines.append("\nWarnings:")
        for warning in result.warnings:
            lines.append(f"  - {warning}")

    return "\n".join(lines)


def format_skill_info(info: SkillInfo, json_output: bool) -> str:
    """Format skill info for output."""
    if json_output:
        return json.dumps(info.to_dict(), indent=2)

    lines = [
        f"Skill: {info.name}",
        f"Version: {info.version}",
        f"Description: {info.description}",
    ]

    if info.author:
        lines.append(f"Author: {info.author}")
    if info.homepage:
        lines.append(f"Homepage: {info.homepage}")
    if info.license:
        lines.append(f"License: {info.license}")
    if info.mcp_servers:
        lines.append(f"MCP Servers: {', '.join(info.mcp_servers)}")
    if info.tools:
        lines.append(f"Tools: {', '.join(info.tools)}")
    if info.permissions:
        lines.append(f"Permissions: {', '.join(info.permissions)}")
    if info.keywords:
        lines.append(f"Keywords: {', '.join(info.keywords)}")

    return "\n".join(lines)


def format_skill_list(skills: list[SkillInfo], json_output: bool) -> str:
    """Format skill list for output."""
    if json_output:
        return json.dumps([s.to_dict() for s in skills], indent=2)

    if not skills:
        return "No skills found."

    lines = []
    for skill in skills:
        lines.append(f"  {skill.name} ({skill.version})")
        lines.append(f"    {skill.description}")
        lines.append("")

    return "\n".join(lines)


def cmd_package(args: argparse.Namespace) -> int:
    """Handle package command."""
    packager = SkillPackager()
    skill_dir = Path(args.skill_dir)
    output = Path(args.output) if args.output else None

    try:
        # Validate first
        validation = packager.validate(skill_dir)
        if not validation.valid:
            print(format_validation_result(validation, args.json), file=sys.stderr)
            return 1

        # Show warnings if any
        if validation.warnings:
            if args.json:
                print(json.dumps({"warnings": validation.warnings}), file=sys.stderr)
            else:
                print("Warnings:")
                for warning in validation.warnings:
                    print(f"  - {warning}")

        # Package
        output_path = packager.package(skill_dir, output)

        if args.json:
            print(json.dumps({"success": True, "output": str(output_path)}))
        else:
            print(f"Packaged skill to: {output_path}")

        return 0

    except FileNotFoundError as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Handle validate command."""
    packager = SkillPackager()
    path = Path(args.path)

    result = packager.validate(path)
    print(format_validation_result(result, args.json))

    return 0 if result.valid else 1


def cmd_info(args: argparse.Namespace) -> int:
    """Handle info command."""
    packager = SkillPackager()
    path = Path(args.path)

    try:
        info = packager.extract_info(path)
        print(format_skill_info(info, args.json))
        return 0
    except FileNotFoundError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """Handle list command."""
    packager = SkillPackager()

    skills_dir = Path(args.skills_dir) if args.skills_dir else None
    skills = packager.list_installed(skills_dir)

    print(format_skill_list(skills, args.json))
    return 0


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="ninja-skill",
        description="Package and manage Claude Code skills",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Package command
    package_parser = subparsers.add_parser(
        "package",
        help="Package a skill directory into a ZIP file",
    )
    package_parser.add_argument(
        "skill_dir",
        help="Path to skill directory",
    )
    package_parser.add_argument(
        "-o", "--output",
        help="Output path for ZIP file",
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a skill package or directory",
    )
    validate_parser.add_argument(
        "path",
        help="Path to skill directory or ZIP file",
    )

    # Info command
    info_parser = subparsers.add_parser(
        "info",
        help="Show information about a skill",
    )
    info_parser.add_argument(
        "path",
        help="Path to skill directory or ZIP file",
    )

    # List command
    list_parser = subparsers.add_parser(
        "list",
        help="List installed skills",
    )
    list_parser.add_argument(
        "--skills-dir",
        help="Path to skills directory",
    )

    return parser


def main(argv: list[str] | None = None) -> NoReturn:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "package": cmd_package,
        "validate": cmd_validate,
        "info": cmd_info,
        "list": cmd_list,
    }

    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
