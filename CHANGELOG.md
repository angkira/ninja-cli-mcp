# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Modern build system using `just`
- One-line installer script
- Homebrew formula for macOS
- Debian package for Ubuntu/Debian
- GitHub Actions workflows for CI/CD
- Automated release process
- Comprehensive installation documentation
- Multiple installation modes (global/local/development)

### Changed
- **BREAKING**: Removed hardcoded paths from all configurations
- Installation script now auto-detects installation mode
- Updated README with modern installation methods
- Improved MCP server configuration handling

### Fixed
- Hardcoded user-specific paths in `.mcp.json`
- Installation portability issues
- Configuration not working for other users

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

[Unreleased]: https://github.com/angkira/ninja-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/angkira/ninja-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/angkira/ninja-mcp/releases/tag/v0.1.0
