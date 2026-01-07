"""Tests for skill_packager module."""

import json
import zipfile
from pathlib import Path

import pytest

from ninja_common.skill_packager import (
    SkillInfo,
    SkillPackager,
    SkillValidationResult,
)


class TestSkillValidationResult:
    """Tests for SkillValidationResult dataclass."""

    def test_valid_result(self):
        """Test creating a valid result."""
        result = SkillValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_invalid_result_with_errors(self):
        """Test creating an invalid result with errors."""
        result = SkillValidationResult(
            valid=False,
            errors=["Missing skill.md", "Missing config.json"],
        )
        assert result.valid is False
        assert len(result.errors) == 2
        assert "Missing skill.md" in result.errors

    def test_valid_result_with_warnings(self):
        """Test creating a valid result with warnings."""
        result = SkillValidationResult(
            valid=True,
            warnings=["README.md is missing"],
        )
        assert result.valid is True
        assert len(result.warnings) == 1

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = SkillValidationResult(
            valid=True,
            errors=["error1"],
            warnings=["warning1"],
        )
        d = result.to_dict()
        assert d["valid"] is True
        assert d["errors"] == ["error1"]
        assert d["warnings"] == ["warning1"]


class TestSkillInfo:
    """Tests for SkillInfo dataclass."""

    def test_minimal_info(self):
        """Test creating minimal skill info."""
        info = SkillInfo(
            name="test-skill",
            version="1.0.0",
            description="A test skill",
        )
        assert info.name == "test-skill"
        assert info.version == "1.0.0"
        assert info.description == "A test skill"
        assert info.author == ""
        assert info.mcp_servers == []
        assert info.tools == []

    def test_full_info(self):
        """Test creating full skill info."""
        info = SkillInfo(
            name="ninja-code",
            version="1.0.0",
            description="Delegate code writing to Ninja Coder",
            author="ninja-mcp contributors",
            homepage="https://github.com/example/ninja-mcp",
            license="MIT",
            mcp_servers=["ninja-coder"],
            tools=["coder_quick_task"],
            permissions=["code_execution", "file_write"],
            keywords=["coding", "ai"],
        )
        assert info.name == "ninja-code"
        assert info.author == "ninja-mcp contributors"
        assert "ninja-coder" in info.mcp_servers
        assert "coder_quick_task" in info.tools

    def test_to_dict(self):
        """Test converting to dictionary."""
        info = SkillInfo(
            name="test",
            version="1.0.0",
            description="Test",
            mcp_servers=["server1"],
        )
        d = info.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "1.0.0"
        assert d["mcp_servers"] == ["server1"]


class TestSkillPackagerValidation:
    """Tests for SkillPackager.validate method."""

    @pytest.fixture
    def packager(self):
        """Create a packager instance."""
        return SkillPackager()

    @pytest.fixture
    def valid_skill_dir(self, tmp_path):
        """Create a valid skill directory."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()

        # Create required files
        (skill_dir / "skill.md").write_text("# Test Skill\n\nTest content")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test-skill",
            "version": "1.0.0",
            "description": "A test skill",
        }))

        # Create optional files
        (skill_dir / "README.md").write_text("# README")
        examples_dir = skill_dir / "examples"
        examples_dir.mkdir()
        (examples_dir / "basic.md").write_text("# Basic Example")

        return skill_dir

    def test_validate_valid_directory(self, packager, valid_skill_dir):
        """Test validating a valid skill directory."""
        result = packager.validate(valid_skill_dir)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_missing_skill_md(self, packager, tmp_path):
        """Test validation fails when skill.md is missing."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))

        result = packager.validate(skill_dir)
        assert result.valid is False
        assert any("skill.md" in err for err in result.errors)

    def test_validate_missing_config_json(self, packager, tmp_path):
        """Test validation fails when config.json is missing."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")

        result = packager.validate(skill_dir)
        assert result.valid is False
        assert any("config.json" in err for err in result.errors)

    def test_validate_invalid_json(self, packager, tmp_path):
        """Test validation fails with invalid JSON."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text("{ invalid json }")

        result = packager.validate(skill_dir)
        assert result.valid is False
        assert any("Invalid JSON" in err for err in result.errors)

    def test_validate_missing_required_fields(self, packager, tmp_path):
        """Test validation fails with missing required fields in config."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            # missing version and description
        }))

        result = packager.validate(skill_dir)
        assert result.valid is False
        assert any("version" in err for err in result.errors)
        assert any("description" in err for err in result.errors)

    def test_validate_invalid_version_format(self, packager, tmp_path):
        """Test validation fails with invalid semver version."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "not-a-version",
            "description": "Test",
        }))

        result = packager.validate(skill_dir)
        assert result.valid is False
        assert any("semver" in err.lower() for err in result.errors)

    def test_validate_valid_semver_versions(self, packager, tmp_path):
        """Test validation passes with valid semver versions."""
        valid_versions = ["1.0.0", "0.1.0", "10.20.30", "1.0.0-alpha", "1.0.0+build"]

        for version in valid_versions:
            skill_dir = tmp_path / f"skill-{version.replace('.', '_')}"
            skill_dir.mkdir()
            (skill_dir / "skill.md").write_text("# Skill")
            (skill_dir / "config.json").write_text(json.dumps({
                "name": "test",
                "version": version,
                "description": "Test",
            }))

            result = packager.validate(skill_dir)
            assert result.valid is True, f"Version {version} should be valid"

    def test_validate_warning_missing_readme(self, packager, tmp_path):
        """Test warning when README.md is missing."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))

        result = packager.validate(skill_dir)
        assert result.valid is True
        assert any("README.md" in warn for warn in result.warnings)

    def test_validate_warning_missing_examples(self, packager, tmp_path):
        """Test warning when examples/ directory is missing."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))

        result = packager.validate(skill_dir)
        assert result.valid is True
        assert any("examples" in warn for warn in result.warnings)

    def test_validate_warning_unknown_permission(self, packager, tmp_path):
        """Test warning for unknown permissions."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
            "permissions": ["unknown_permission"],
        }))

        result = packager.validate(skill_dir)
        assert result.valid is True
        assert any("unknown_permission" in warn for warn in result.warnings)

    def test_validate_warning_large_file(self, packager, tmp_path):
        """Test warning for large files."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test",
            "version": "1.0.0",
            "description": "Test",
        }))
        # Create a large file (>1MB)
        (skill_dir / "large_file.bin").write_bytes(b"x" * (1024 * 1024 + 1))

        result = packager.validate(skill_dir)
        assert result.valid is True
        assert any("Large file" in warn for warn in result.warnings)

    def test_validate_nonexistent_path(self, packager, tmp_path):
        """Test validation fails for nonexistent path."""
        result = packager.validate(tmp_path / "nonexistent")
        assert result.valid is False
        assert any("does not exist" in err for err in result.errors)


class TestSkillPackagerZipValidation:
    """Tests for SkillPackager ZIP file validation."""

    @pytest.fixture
    def packager(self):
        """Create a packager instance."""
        return SkillPackager()

    @pytest.fixture
    def valid_skill_zip(self, tmp_path):
        """Create a valid skill ZIP file."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Test Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test-skill",
            "version": "1.0.0",
            "description": "A test skill",
        }))
        (skill_dir / "README.md").write_text("# README")
        examples_dir = skill_dir / "examples"
        examples_dir.mkdir()
        (examples_dir / "basic.md").write_text("# Basic")

        zip_path = tmp_path / "test-skill.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for file in skill_dir.rglob("*"):
                if file.is_file():
                    arcname = f"test-skill/{file.relative_to(skill_dir)}"
                    zf.write(file, arcname)

        return zip_path

    def test_validate_valid_zip(self, packager, valid_skill_zip):
        """Test validating a valid ZIP file."""
        result = packager.validate(valid_skill_zip)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_zip_missing_skill_md(self, packager, tmp_path):
        """Test validation fails when skill.md is missing in ZIP."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test/config.json", json.dumps({
                "name": "test",
                "version": "1.0.0",
                "description": "Test",
            }))

        result = packager.validate(zip_path)
        assert result.valid is False
        assert any("skill.md" in err for err in result.errors)

    def test_validate_invalid_zip(self, packager, tmp_path):
        """Test validation fails for invalid ZIP file."""
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_text("not a zip file")

        result = packager.validate(bad_zip)
        assert result.valid is False
        assert any("Invalid ZIP" in err for err in result.errors)


class TestSkillPackagerPackage:
    """Tests for SkillPackager.package method."""

    @pytest.fixture
    def packager(self):
        """Create a packager instance."""
        return SkillPackager()

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

    def test_package_creates_zip(self, packager, valid_skill_dir, tmp_path):
        """Test that package creates a ZIP file."""
        output = tmp_path / "output.zip"
        result = packager.package(valid_skill_dir, output)

        assert result == output
        assert output.exists()
        assert zipfile.is_zipfile(output)

    def test_package_default_output_name(self, packager, valid_skill_dir, tmp_path, monkeypatch):
        """Test that package uses skill name for default output."""
        monkeypatch.chdir(tmp_path)
        result = packager.package(valid_skill_dir)

        assert result.name == "test-skill.zip"
        assert result.exists()

    def test_package_contains_all_files(self, packager, valid_skill_dir, tmp_path):
        """Test that ZIP contains all skill files."""
        output = tmp_path / "output.zip"
        packager.package(valid_skill_dir, output)

        with zipfile.ZipFile(output, "r") as zf:
            names = zf.namelist()
            assert any("skill.md" in name for name in names)
            assert any("config.json" in name for name in names)
            assert any("README.md" in name for name in names)

    def test_package_fails_for_invalid_skill(self, packager, tmp_path):
        """Test that package fails for invalid skill."""
        invalid_dir = tmp_path / "invalid"
        invalid_dir.mkdir()

        with pytest.raises(ValueError, match="validation failed"):
            packager.package(invalid_dir)

    def test_package_fails_for_nonexistent_dir(self, packager, tmp_path):
        """Test that package fails for nonexistent directory."""
        with pytest.raises(FileNotFoundError):
            packager.package(tmp_path / "nonexistent")

    def test_package_roundtrip(self, packager, valid_skill_dir, tmp_path):
        """Test packaging and unpacking produces same content."""
        output = tmp_path / "output.zip"
        packager.package(valid_skill_dir, output)

        # Validate the produced ZIP
        result = packager.validate(output)
        assert result.valid is True

        # Extract info should match
        info = packager.extract_info(output)
        assert info.name == "test-skill"
        assert info.version == "1.0.0"


class TestSkillPackagerExtractInfo:
    """Tests for SkillPackager.extract_info method."""

    @pytest.fixture
    def packager(self):
        """Create a packager instance."""
        return SkillPackager()

    def test_extract_info_from_directory(self, packager, tmp_path):
        """Test extracting info from directory."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")
        (skill_dir / "config.json").write_text(json.dumps({
            "name": "test-skill",
            "version": "2.0.0",
            "description": "Test description",
            "author": "Test Author",
            "mcp_servers": ["server1", "server2"],
            "tools": ["tool1"],
            "permissions": ["code_execution"],
        }))

        info = packager.extract_info(skill_dir)

        assert info.name == "test-skill"
        assert info.version == "2.0.0"
        assert info.description == "Test description"
        assert info.author == "Test Author"
        assert info.mcp_servers == ["server1", "server2"]
        assert info.tools == ["tool1"]
        assert info.permissions == ["code_execution"]

    def test_extract_info_from_zip(self, packager, tmp_path):
        """Test extracting info from ZIP file."""
        zip_path = tmp_path / "skill.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("skill/skill.md", "# Skill")
            zf.writestr("skill/config.json", json.dumps({
                "name": "zip-skill",
                "version": "1.0.0",
                "description": "From ZIP",
            }))

        info = packager.extract_info(zip_path)

        assert info.name == "zip-skill"
        assert info.version == "1.0.0"
        assert info.description == "From ZIP"

    def test_extract_info_missing_config(self, packager, tmp_path):
        """Test extracting info fails without config.json."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("# Skill")

        with pytest.raises(ValueError, match="config.json not found"):
            packager.extract_info(skill_dir)

    def test_extract_info_nonexistent(self, packager, tmp_path):
        """Test extracting info from nonexistent path fails."""
        with pytest.raises(FileNotFoundError):
            packager.extract_info(tmp_path / "nonexistent")


class TestSkillPackagerUnpack:
    """Tests for SkillPackager.unpack method."""

    @pytest.fixture
    def packager(self):
        """Create a packager instance."""
        return SkillPackager()

    def test_unpack_creates_directory(self, packager, tmp_path):
        """Test that unpack creates a directory."""
        # Create a ZIP
        zip_path = tmp_path / "skill.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test-skill/skill.md", "# Skill")
            zf.writestr("test-skill/config.json", json.dumps({
                "name": "test",
                "version": "1.0.0",
                "description": "Test",
            }))

        dest = tmp_path / "extracted"
        result = packager.unpack(zip_path, dest)

        assert result.exists()
        assert (result / "skill.md").exists() or (dest / "test-skill" / "skill.md").exists()

    def test_unpack_default_destination(self, packager, tmp_path):
        """Test unpacking to default temp directory."""
        zip_path = tmp_path / "skill.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("skill/skill.md", "# Skill")
            zf.writestr("skill/config.json", json.dumps({
                "name": "test",
                "version": "1.0.0",
                "description": "Test",
            }))

        result = packager.unpack(zip_path)

        assert result.exists()


class TestSkillPackagerListInstalled:
    """Tests for SkillPackager.list_installed method."""

    @pytest.fixture
    def packager(self):
        """Create a packager instance."""
        return SkillPackager()

    def test_list_installed_empty(self, packager, tmp_path):
        """Test listing when no skills are installed."""
        skills = packager.list_installed(tmp_path / "nonexistent")
        assert skills == []

    def test_list_installed_directories(self, packager, tmp_path):
        """Test listing installed skill directories."""
        # Create skill directories
        for i in range(3):
            skill_dir = tmp_path / f"skill-{i}"
            skill_dir.mkdir()
            (skill_dir / "skill.md").write_text("# Skill")
            (skill_dir / "config.json").write_text(json.dumps({
                "name": f"skill-{i}",
                "version": "1.0.0",
                "description": f"Skill {i}",
            }))

        skills = packager.list_installed(tmp_path)

        assert len(skills) == 3
        names = [s.name for s in skills]
        assert "skill-0" in names
        assert "skill-1" in names
        assert "skill-2" in names

    def test_list_installed_ignores_invalid(self, packager, tmp_path):
        """Test that invalid directories are ignored."""
        # Create one valid skill
        valid = tmp_path / "valid-skill"
        valid.mkdir()
        (valid / "skill.md").write_text("# Skill")
        (valid / "config.json").write_text(json.dumps({
            "name": "valid",
            "version": "1.0.0",
            "description": "Valid",
        }))

        # Create an invalid directory (no config.json)
        invalid = tmp_path / "invalid"
        invalid.mkdir()

        skills = packager.list_installed(tmp_path)

        assert len(skills) == 1
        assert skills[0].name == "valid"
