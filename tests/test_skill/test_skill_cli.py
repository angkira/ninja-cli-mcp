"""Tests for skill_cli module."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ninja_common.skill_cli import (
    cmd_info,
    cmd_list,
    cmd_package,
    cmd_validate,
    create_parser,
    format_skill_info,
    format_skill_list,
    format_validation_result,
    main,
)
from ninja_common.skill_packager import SkillInfo, SkillValidationResult


class TestFormatValidationResult:
    """Tests for format_validation_result function."""

    def test_format_valid_human_readable(self):
        """Test formatting valid result as human readable."""
        result = SkillValidationResult(valid=True)
        output = format_validation_result(result, json_output=False)

        assert "PASSED" in output

    def test_format_invalid_human_readable(self):
        """Test formatting invalid result as human readable."""
        result = SkillValidationResult(
            valid=False,
            errors=["Missing skill.md", "Missing config.json"],
        )
        output = format_validation_result(result, json_output=False)

        assert "FAILED" in output
        assert "Missing skill.md" in output
        assert "Missing config.json" in output

    def test_format_with_warnings_human_readable(self):
        """Test formatting result with warnings as human readable."""
        result = SkillValidationResult(
            valid=True,
            warnings=["README.md is missing"],
        )
        output = format_validation_result(result, json_output=False)

        assert "PASSED" in output
        assert "README.md is missing" in output

    def test_format_valid_json(self):
        """Test formatting valid result as JSON."""
        result = SkillValidationResult(valid=True)
        output = format_validation_result(result, json_output=True)

        parsed = json.loads(output)
        assert parsed["valid"] is True
        assert parsed["errors"] == []

    def test_format_invalid_json(self):
        """Test formatting invalid result as JSON."""
        result = SkillValidationResult(
            valid=False,
            errors=["error1"],
            warnings=["warning1"],
        )
        output = format_validation_result(result, json_output=True)

        parsed = json.loads(output)
        assert parsed["valid"] is False
        assert "error1" in parsed["errors"]
        assert "warning1" in parsed["warnings"]


class TestFormatSkillInfo:
    """Tests for format_skill_info function."""

    def test_format_minimal_human_readable(self):
        """Test formatting minimal skill info as human readable."""
        info = SkillInfo(
            name="test-skill",
            version="1.0.0",
            description="Test description",
        )
        output = format_skill_info(info, json_output=False)

        assert "test-skill" in output
        assert "1.0.0" in output
        assert "Test description" in output

    def test_format_full_human_readable(self):
        """Test formatting full skill info as human readable."""
        info = SkillInfo(
            name="ninja-code",
            version="1.0.0",
            description="Delegate code writing",
            author="Test Author",
            homepage="https://example.com",
            license="MIT",
            mcp_servers=["ninja-coder"],
            tools=["coder_quick_task"],
            permissions=["code_execution"],
            keywords=["coding", "ai"],
        )
        output = format_skill_info(info, json_output=False)

        assert "ninja-code" in output
        assert "Test Author" in output
        assert "https://example.com" in output
        assert "MIT" in output
        assert "ninja-coder" in output
        assert "coder_quick_task" in output
        assert "code_execution" in output
        assert "coding" in output

    def test_format_json(self):
        """Test formatting skill info as JSON."""
        info = SkillInfo(
            name="test",
            version="1.0.0",
            description="Test",
            mcp_servers=["server1"],
        )
        output = format_skill_info(info, json_output=True)

        parsed = json.loads(output)
        assert parsed["name"] == "test"
        assert parsed["mcp_servers"] == ["server1"]


class TestFormatSkillList:
    """Tests for format_skill_list function."""

    def test_format_empty_list_human_readable(self):
        """Test formatting empty list as human readable."""
        output = format_skill_list([], json_output=False)
        assert "No skills found" in output

    def test_format_list_human_readable(self):
        """Test formatting skill list as human readable."""
        skills = [
            SkillInfo(name="skill1", version="1.0.0", description="First skill"),
            SkillInfo(name="skill2", version="2.0.0", description="Second skill"),
        ]
        output = format_skill_list(skills, json_output=False)

        assert "skill1" in output
        assert "1.0.0" in output
        assert "First skill" in output
        assert "skill2" in output

    def test_format_empty_list_json(self):
        """Test formatting empty list as JSON."""
        output = format_skill_list([], json_output=True)
        parsed = json.loads(output)
        assert parsed == []

    def test_format_list_json(self):
        """Test formatting skill list as JSON."""
        skills = [
            SkillInfo(name="skill1", version="1.0.0", description="First"),
        ]
        output = format_skill_list(skills, json_output=True)

        parsed = json.loads(output)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "skill1"


class TestCmdPackage:
    """Tests for cmd_package command."""

    @pytest.fixture
    def valid_skill_dir(self, tmp_path):
        """Create a valid skill directory."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Test Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test-skill",
            "version": "1.0.0",
            "description": "A test skill",
        }))
        (skill_dir / "README.md").write_text("# README")
        return skill_dir

    def test_package_success(self, valid_skill_dir, tmp_path, capsys):
        """Test successful packaging."""
        output = tmp_path / "output.zip"
        args = Mock()
        args.skill_dir = str(valid_skill_dir)
        args.output = str(output)
        args.json = False

        result = cmd_package(args)

        assert result == 0
        assert output.exists()
        captured = capsys.readouterr()
        assert "Packaged" in captured.out

    def test_package_success_json(self, valid_skill_dir, tmp_path, capsys):
        """Test successful packaging with JSON output."""
        output = tmp_path / "output.zip"
        args = Mock()
        args.skill_dir = str(valid_skill_dir)
        args.output = str(output)
        args.json = True

        result = cmd_package(args)

        assert result == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["success"] is True

    def test_package_failure_invalid(self, tmp_path, capsys):
        """Test packaging failure for invalid skill."""
        invalid_dir = tmp_path / "invalid"
        invalid_dir.mkdir()

        args = Mock()
        args.skill_dir = str(invalid_dir)
        args.output = None
        args.json = False

        result = cmd_package(args)

        assert result == 1

    def test_package_failure_not_found(self, tmp_path, capsys):
        """Test packaging failure for non-existent directory."""
        args = Mock()
        args.skill_dir = str(tmp_path / "nonexistent")
        args.output = None
        args.json = False

        result = cmd_package(args)

        assert result == 1


class TestCmdValidate:
    """Tests for cmd_validate command."""

    def test_validate_success(self, tmp_path, capsys):
        """Test successful validation."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))
        (skill_dir / "README.md").write_text("# README")
        (skill_dir / "examples").mkdir()

        args = Mock()
        args.path = str(skill_dir)
        args.json = False

        result = cmd_validate(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "PASSED" in captured.out

    def test_validate_failure(self, tmp_path, capsys):
        """Test validation failure."""
        invalid_dir = tmp_path / "invalid"
        invalid_dir.mkdir()

        args = Mock()
        args.path = str(invalid_dir)
        args.json = False

        result = cmd_validate(args)

        assert result == 1
        captured = capsys.readouterr()
        assert "FAILED" in captured.out

    def test_validate_json(self, tmp_path, capsys):
        """Test validation with JSON output."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))

        args = Mock()
        args.path = str(skill_dir)
        args.json = True

        result = cmd_validate(args)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["valid"] is True


class TestCmdInfo:
    """Tests for cmd_info command."""

    def test_info_success(self, tmp_path, capsys):
        """Test successful info extraction."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test-skill",
            "version": "2.0.0",
            "description": "Test skill description",
        }))

        args = Mock()
        args.path = str(skill_dir)
        args.json = False

        result = cmd_info(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "test-skill" in captured.out
        assert "2.0.0" in captured.out

    def test_info_failure(self, tmp_path, capsys):
        """Test info failure for invalid path."""
        args = Mock()
        args.path = str(tmp_path / "nonexistent")
        args.json = False

        result = cmd_info(args)

        assert result == 1

    def test_info_json(self, tmp_path, capsys):
        """Test info with JSON output."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))

        args = Mock()
        args.path = str(skill_dir)
        args.json = True

        result = cmd_info(args)

        assert result == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["name"] == "test"


class TestCmdList:
    """Tests for cmd_list command."""

    def test_list_empty(self, tmp_path, capsys):
        """Test listing when no skills are installed."""
        args = Mock()
        args.skills_dir = str(tmp_path / "nonexistent")
        args.json = False

        result = cmd_list(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "No skills found" in captured.out

    def test_list_with_skills(self, tmp_path, capsys):
        """Test listing installed skills."""
        # Create a skill
        skill_dir = tmp_path / "skill1"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "skill1",
            "version": "1.0.0",
            "description": "First skill",
        }))

        args = Mock()
        args.skills_dir = str(tmp_path)
        args.json = False

        result = cmd_list(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "skill1" in captured.out

    def test_list_json(self, tmp_path, capsys):
        """Test listing with JSON output."""
        args = Mock()
        args.skills_dir = str(tmp_path)
        args.json = True

        result = cmd_list(args)

        assert result == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert isinstance(parsed, list)


class TestCreateParser:
    """Tests for create_parser function."""

    def test_parser_creation(self):
        """Test parser is created correctly."""
        parser = create_parser()
        assert parser.prog == "ninja-skill"

    def test_parser_package_command(self):
        """Test package command parsing."""
        parser = create_parser()
        args = parser.parse_args(["package", "skill_dir", "-o", "output.zip"])

        assert args.command == "package"
        assert args.skill_dir == "skill_dir"
        assert args.output == "output.zip"

    def test_parser_validate_command(self):
        """Test validate command parsing."""
        parser = create_parser()
        args = parser.parse_args(["validate", "path/to/skill"])

        assert args.command == "validate"
        assert args.path == "path/to/skill"

    def test_parser_info_command(self):
        """Test info command parsing."""
        parser = create_parser()
        args = parser.parse_args(["info", "skill.zip"])

        assert args.command == "info"
        assert args.path == "skill.zip"

    def test_parser_list_command(self):
        """Test list command parsing."""
        parser = create_parser()
        args = parser.parse_args(["list", "--skills-dir", "/custom/path"])

        assert args.command == "list"
        assert args.skills_dir == "/custom/path"

    def test_parser_json_flag(self):
        """Test --json flag parsing."""
        parser = create_parser()
        args = parser.parse_args(["--json", "validate", "path"])

        assert args.json is True
        assert args.command == "validate"


class TestMain:
    """Tests for main function."""

    def test_main_no_command(self, capsys):
        """Test main with no command shows help."""
        with pytest.raises(SystemExit) as exc_info:
            main([])

        assert exc_info.value.code == 0

    def test_main_package_command(self, tmp_path):
        """Test main with package command."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))

        output = tmp_path / "output.zip"

        with pytest.raises(SystemExit) as exc_info:
            main(["package", str(skill_dir), "-o", str(output)])

        assert exc_info.value.code == 0
        assert output.exists()

    def test_main_validate_command(self, tmp_path):
        """Test main with validate command."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))

        with pytest.raises(SystemExit) as exc_info:
            main(["validate", str(skill_dir)])

        assert exc_info.value.code == 0

    def test_main_info_command(self, tmp_path):
        """Test main with info command."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))

        with pytest.raises(SystemExit) as exc_info:
            main(["info", str(skill_dir)])

        assert exc_info.value.code == 0

    def test_main_list_command(self, tmp_path):
        """Test main with list command."""
        with pytest.raises(SystemExit) as exc_info:
            main(["list", "--skills-dir", str(tmp_path)])

        assert exc_info.value.code == 0
