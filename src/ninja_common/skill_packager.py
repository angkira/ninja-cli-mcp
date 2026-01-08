"""Skill packaging system for Claude Code skills.

This module provides functionality to create, validate, and distribute
Claude Code skills as ZIP packages.
"""

from __future__ import annotations

import json
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


@dataclass
class SkillValidationResult:
    """Result of skill validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class SkillInfo:
    """Information about a skill package."""

    name: str
    version: str
    description: str
    author: str = ""
    homepage: str = ""
    license: str = ""
    mcp_servers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "license": self.license,
            "mcp_servers": self.mcp_servers,
            "tools": self.tools,
            "permissions": self.permissions,
            "keywords": self.keywords,
        }


class SkillPackager:
    """Package, validate, and inspect Claude Code skills."""

    REQUIRED_FILES: ClassVar[list[str]] = ["skill.md", "config.json"]
    OPTIONAL_FILES: ClassVar[list[str]] = ["README.md", "examples/"]
    REQUIRED_CONFIG_FIELDS: ClassVar[list[str]] = ["name", "version", "description"]
    KNOWN_PERMISSIONS: ClassVar[list[str]] = [
        "code_execution",
        "file_write",
        "file_read",
        "network",
        "shell",
    ]
    SEMVER_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
        r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
        r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
    )
    MAX_FILE_SIZE: ClassVar[int] = 1024 * 1024  # 1MB

    def validate(self, path: Path | str) -> SkillValidationResult:
        """Validate a skill directory or ZIP file.

        Args:
            path: Path to skill directory or ZIP file

        Returns:
            SkillValidationResult with validation status, errors, and warnings
        """
        path = Path(path)
        errors: list[str] = []
        warnings: list[str] = []

        # Handle ZIP files
        if path.suffix == ".zip" and path.is_file():
            return self._validate_zip(path)

        # Handle directories
        if not path.is_dir():
            return SkillValidationResult(
                valid=False,
                errors=[f"Path does not exist or is not a directory: {path}"],
            )

        # Check required files
        for required_file in self.REQUIRED_FILES:
            file_path = path / required_file
            if not file_path.exists():
                errors.append(f"Missing required file: {required_file}")

        # Check optional files
        if not (path / "README.md").exists():
            warnings.append("README.md is missing")
        if not (path / "examples").is_dir():
            warnings.append("examples/ directory is missing")

        # Validate config.json if it exists
        config_path = path / "config.json"
        if config_path.exists():
            config_errors, config_warnings = self._validate_config(config_path)
            errors.extend(config_errors)
            warnings.extend(config_warnings)

        # Check for large files
        for file_path in path.rglob("*"):
            if file_path.is_file() and file_path.stat().st_size > self.MAX_FILE_SIZE:
                warnings.append(f"Large file (>1MB): {file_path.relative_to(path)}")

        return SkillValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _validate_zip(self, zip_path: Path) -> SkillValidationResult:
        """Validate a ZIP file containing a skill."""
        errors: list[str] = []
        warnings: list[str] = []

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()

                # Find the root directory in the ZIP
                root_dirs = {name.split("/")[0] for name in names if "/" in name}
                if len(root_dirs) == 1:
                    root = list(root_dirs)[0] + "/"
                else:
                    root = ""

                # Check required files
                for required_file in self.REQUIRED_FILES:
                    expected = root + required_file
                    if expected not in names:
                        errors.append(f"Missing required file: {required_file}")

                # Check optional files
                readme_found = any(name.endswith("README.md") for name in names)
                if not readme_found:
                    warnings.append("README.md is missing")

                examples_found = any("examples/" in name for name in names)
                if not examples_found:
                    warnings.append("examples/ directory is missing")

                # Validate config.json if present
                config_name = root + "config.json"
                if config_name in names:
                    with zf.open(config_name) as f:
                        config_errors, config_warnings = self._validate_config_content(
                            f.read().decode("utf-8")
                        )
                        errors.extend(config_errors)
                        warnings.extend(config_warnings)

                # Check file sizes
                for info in zf.infolist():
                    if info.file_size > self.MAX_FILE_SIZE:
                        warnings.append(f"Large file (>1MB): {info.filename}")

        except zipfile.BadZipFile:
            return SkillValidationResult(
                valid=False,
                errors=["Invalid ZIP file"],
            )

        return SkillValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _validate_config(self, config_path: Path) -> tuple[list[str], list[str]]:
        """Validate config.json file."""
        try:
            content = config_path.read_text(encoding="utf-8")
            return self._validate_config_content(content)
        except json.JSONDecodeError as e:
            return [f"Invalid JSON in config.json: {e}"], []

    def _validate_config_content(self, content: str) -> tuple[list[str], list[str]]:
        """Validate config.json content."""
        errors: list[str] = []
        warnings: list[str] = []

        try:
            config = json.loads(content)
        except json.JSONDecodeError as e:
            return [f"Invalid JSON in config.json: {e}"], []

        # Check required fields
        for field_name in self.REQUIRED_CONFIG_FIELDS:
            if field_name not in config:
                errors.append(f"Missing required field in config.json: {field_name}")
            elif not config[field_name]:
                errors.append(f"Empty required field in config.json: {field_name}")

        # Validate version format (semver)
        if config.get("version"):
            if not self.SEMVER_PATTERN.match(config["version"]):
                errors.append(f"Invalid version format (must be semver): {config['version']}")

        # Check for unknown permissions
        if "permissions" in config:
            for perm in config["permissions"]:
                if perm not in self.KNOWN_PERMISSIONS:
                    warnings.append(f"Unknown permission: {perm}")

        return errors, warnings

    def package(self, skill_dir: Path | str, output: Path | str | None = None) -> Path:
        """Package a skill directory into a ZIP file.

        Args:
            skill_dir: Path to skill directory
            output: Optional output path for ZIP file

        Returns:
            Path to the created ZIP file

        Raises:
            ValueError: If validation fails
            FileNotFoundError: If skill_dir doesn't exist
        """
        skill_dir = Path(skill_dir)

        if not skill_dir.is_dir():
            raise FileNotFoundError(f"Skill directory not found: {skill_dir}")

        # Validate first
        validation = self.validate(skill_dir)
        if not validation.valid:
            raise ValueError(f"Skill validation failed: {'; '.join(validation.errors)}")

        # Determine output path
        if output is None:
            info = self.extract_info(skill_dir)
            output = Path(f"{info.name}.zip")
        else:
            output = Path(output)

        # Create ZIP file
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in skill_dir.rglob("*"):
                if file_path.is_file():
                    arcname = str(skill_dir.name / file_path.relative_to(skill_dir))
                    zf.write(file_path, arcname)

        return output

    def extract_info(self, path: Path | str) -> SkillInfo:
        """Extract information from a skill package or directory.

        Args:
            path: Path to skill directory or ZIP file

        Returns:
            SkillInfo with skill metadata

        Raises:
            FileNotFoundError: If path doesn't exist
            ValueError: If config.json is missing or invalid
        """
        path = Path(path)

        if path.suffix == ".zip" and path.is_file():
            return self._extract_info_from_zip(path)

        if not path.is_dir():
            raise FileNotFoundError(f"Path not found: {path}")

        config_path = path / "config.json"
        if not config_path.exists():
            raise ValueError(f"config.json not found in {path}")

        config = json.loads(config_path.read_text(encoding="utf-8"))
        return self._config_to_info(config)

    def _extract_info_from_zip(self, zip_path: Path) -> SkillInfo:
        """Extract skill info from a ZIP file."""
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

            # Find config.json
            config_name = None
            for name in names:
                if name.endswith("config.json"):
                    config_name = name
                    break

            if config_name is None:
                raise ValueError(f"config.json not found in {zip_path}")

            with zf.open(config_name) as f:
                config = json.loads(f.read().decode("utf-8"))
                return self._config_to_info(config)

    def _config_to_info(self, config: dict[str, Any]) -> SkillInfo:
        """Convert config dictionary to SkillInfo."""
        return SkillInfo(
            name=config.get("name", ""),
            version=config.get("version", ""),
            description=config.get("description", ""),
            author=config.get("author", ""),
            homepage=config.get("homepage", ""),
            license=config.get("license", ""),
            mcp_servers=config.get("mcp_servers", []),
            tools=config.get("tools", []),
            permissions=config.get("permissions", []),
            keywords=config.get("keywords", []),
        )

    def unpack(self, zip_path: Path | str, dest_dir: Path | str | None = None) -> Path:
        """Unpack a skill ZIP file.

        Args:
            zip_path: Path to ZIP file
            dest_dir: Optional destination directory

        Returns:
            Path to the unpacked skill directory
        """
        zip_path = Path(zip_path)

        if dest_dir is None:
            dest_dir = Path(tempfile.mkdtemp())
        else:
            dest_dir = Path(dest_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)

        # Find the skill directory (should be the only top-level directory)
        extracted_dirs = [d for d in dest_dir.iterdir() if d.is_dir()]
        if len(extracted_dirs) == 1:
            return extracted_dirs[0]

        return dest_dir

    def list_installed(self, skills_dir: Path | str | None = None) -> list[SkillInfo]:
        """List installed skills.

        Args:
            skills_dir: Optional path to skills directory

        Returns:
            List of SkillInfo for installed skills
        """
        if skills_dir is None:
            # Default to ~/.config/claude-code/skills or similar
            skills_dir = Path.home() / ".config" / "claude-code" / "skills"

        skills_dir = Path(skills_dir)
        if not skills_dir.exists():
            return []

        skills = []
        for item in skills_dir.iterdir():
            if item.is_dir() or item.suffix == ".zip":
                try:
                    info = self.extract_info(item)
                    skills.append(info)
                except (ValueError, FileNotFoundError):
                    continue

        return skills
