# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

(No unreleased changes)

## [0.3.1] - 2026-01-14

### Fixed
- **Daemon Support for All 5 Modules**
  - Add HTTP/SSE support to ninja-resources and ninja-prompts servers
  - Implement proper main_http() function for daemon mode
  - Fix missing asyncio import in ninja_prompts
  - Updated daemon manager to recognize all 5 modules
  - All modules now fully operational in daemon mode with HTTP/SSE

- **Configuration Updates**
  - Add port assignments for new modules (resources=8106, prompts=8107)
  - Update DEFAULT_PORTS in daemon configuration
  - Fix port configuration in ~/.ninja-mcp.env

- **Installation Scripts**
  - Update update.sh to register all 5 modules
  - Update config_cli.py with new module flags (--resources, --prompts)
  - All installation commands now support complete 5-module setup

### Status
- All 5 MCP modules now fully operational in daemon mode
- Tested and verified: ninja-daemon status shows all modules running
- Ready for production use

## [0.3.0] - 2026-01-14

### Added
- **Phase 1: Resources Module** - Load project context as queryable resources
  - `resource_codebase`: Analyze codebases with file structure, function/class extraction
  - `resource_config`: Load configs with automatic sensitive data redaction
  - `resource_docs`: Extract documentation with section parsing
  - Smart caching (1-hour TTL) for performance
  - Comprehensive API documentation

- **Phase 1: Prompts Module** - Reusable prompt templates and workflow composition
  - `prompt_registry`: CRUD operations for prompt templates
  - `prompt_suggest`: AI-powered prompt recommendations with relevance scoring
  - `prompt_chain`: Multi-step workflows with variable passing ({{prev.step}} syntax)
  - 4 built-in prompt templates (code-review, bug-debugging, feature-implementation, architecture-design)
  - YAML-based templates for easy customization

- Secretary module improvements
  - `secretary_analyse_file`: Unified file analysis with structure extraction
  - `secretary_git_*`: Git operations (status, diff, log, commit)
  - `secretary_codebase_report`: Project metrics and structure analysis
  - `secretary_document_summary`: Documentation indexing and summarization
  - Session tracking for work logs

- README redesign as "Swiss Knife" positioning
  - Quick look examples for all modules
  - Real-world use cases (web apps, debugging, learning, code review)
  - Module deep dives with feature details
  - Improved architecture visualization

### Changed
- Coder module tool rename: `coder_quick_task` → `coder_simple_task`
- Secretary API redesigned for better usability
- Test files renamed to avoid pytest collection conflicts
- Improved module error handling and validation

### Fixed
- Response model field mismatches in secretary tools
- File search pagination to count all matches
- Structure extraction for indented functions/methods
- Secretary tool import module parsing

### Security
- Automatic redaction of passwords, API keys, and tokens in config resources
- Rate limiting on all new tools (60 calls/minute)
- Input validation on all resource operations

## [0.2.0] - 2024-12-26

### Added
- Multi-module architecture (Coder, Researcher, Secretary)
- Daemon management system
- HTTP/SSE mode for persistent servers
- Comprehensive test suite (149+ tests)
- Security features (rate limiting, validation)
- Metrics tracking
- Interactive configuration wizard

### Changed
- Split into separate modules
- Improved error handling
- Better logging system

### Fixed
- Various bug fixes and improvements

## [0.1.0] - Initial Release

### Added
- Basic MCP server functionality
- Coder module with Aider integration
- Researcher module with web search
- Basic documentation

[Unreleased]: https://github.com/angkira/ninja-cli-mcp/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/angkira/ninja-cli-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/angkira/ninja-cli-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/angkira/ninja-cli-mcp/releases/tag/v0.1.0
