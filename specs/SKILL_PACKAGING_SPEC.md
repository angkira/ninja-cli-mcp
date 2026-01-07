# Skill Packaging System - Architecture Specification

## Overview

The skill packaging system allows ninja-mcp to create, validate, and distribute Claude Code skills as ZIP packages that can be uploaded to Claude.ai or shared with other users.

## Components

### 1. Skill Structure

A valid skill package contains:

```
skill-name/
├── skill.md           # Main skill definition (required)
├── config.json        # Skill metadata (required)
├── examples/          # Usage examples (optional)
│   ├── basic.md
│   └── advanced.md
└── README.md          # Documentation (optional)
```

### 2. config.json Schema

```json
{
  "name": "skill-name",
  "version": "1.0.0",
  "description": "Short description of what the skill does",
  "author": "author name or organization",
  "homepage": "https://github.com/...",
  "license": "MIT",
  "requires": {
    "ninja-mcp": ">=0.2.0"
  },
  "mcp_servers": ["ninja-coder"],
  "permissions": ["code_execution", "file_write"],
  "environment": {
    "OPENROUTER_API_KEY": {
      "required": true,
      "description": "OpenRouter API key for model access"
    }
  },
  "tools": ["coder_quick_task", "coder_execute_plan_sequential"],
  "keywords": ["coding", "ai", "automation"]
}
```

### 3. CLI Commands

#### `ninja-skill package`
Package a skill directory into a ZIP file.

```bash
ninja-skill package <skill_dir> [--output <path>]
```

**Arguments:**
- `skill_dir`: Path to skill directory

**Options:**
- `--output`, `-o`: Output path for ZIP file (default: `<skill_name>.zip`)

**Example:**
```bash
ninja-skill package claude-integration/skills/ninja-code -o ninja-code-skill.zip
```

#### `ninja-skill validate`
Validate a skill package or directory.

```bash
ninja-skill validate <path>
```

**Arguments:**
- `path`: Path to skill directory or ZIP file

**Output:**
```json
{
  "valid": true,
  "errors": [],
  "warnings": ["README.md is missing"]
}
```

#### `ninja-skill info`
Show information about a skill.

```bash
ninja-skill info <path>
```

**Output:**
```
Skill: ninja-code
Version: 1.0.0
Description: Delegate code writing to Ninja Coder (Aider)
Author: ninja-mcp contributors
MCP Servers: ninja-coder
Tools: coder_quick_task, coder_execute_plan_sequential
```

#### `ninja-skill list`
List installed/available skills.

```bash
ninja-skill list [--installed] [--available]
```

### 4. File Structure

```
src/ninja_common/
├── skill_packager.py     # Core packaging logic
└── skill_cli.py          # CLI interface
```

### 5. Implementation

#### SkillPackager Class

```python
from dataclasses import dataclass
from pathlib import Path
import json
import zipfile

@dataclass
class SkillValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]

@dataclass
class SkillInfo:
    name: str
    version: str
    description: str
    author: str
    mcp_servers: list[str]
    tools: list[str]
    permissions: list[str]

class SkillPackager:
    REQUIRED_FILES = ["skill.md", "config.json"]
    OPTIONAL_FILES = ["README.md", "examples/"]

    def validate(self, path: Path) -> SkillValidationResult:
        """Validate a skill directory or ZIP file."""
        pass

    def package(self, skill_dir: Path, output: Path) -> Path:
        """Package a skill directory into a ZIP file."""
        pass

    def extract_info(self, path: Path) -> SkillInfo:
        """Extract information from a skill package."""
        pass
```

### 6. Validation Rules

**Errors (blocking):**
- Missing `skill.md`
- Missing `config.json`
- Invalid JSON in `config.json`
- Missing required fields in `config.json` (name, version, description)
- Invalid version format (must be semver)

**Warnings (non-blocking):**
- Missing `README.md`
- Missing `examples/` directory
- Unknown permissions in config
- Large file sizes (> 1MB)

### 7. pyproject.toml Addition

```toml
[project.scripts]
ninja-skill = "ninja_common.skill_cli:main"
```

## Testing Requirements

1. **Unit tests** for SkillPackager class
2. **CLI integration tests** for all commands
3. **Validation tests** for all error/warning cases
4. **Package/unpackage round-trip tests**

## Example Usage

```bash
# Package the ninja-code skill
ninja-skill package claude-integration/skills/ninja-code

# Validate before packaging
ninja-skill validate claude-integration/skills/ninja-code

# Show skill info
ninja-skill info ninja-code-skill.zip

# The output ZIP can be uploaded to Claude.ai settings
```
