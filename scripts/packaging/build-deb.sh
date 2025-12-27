#!/usr/bin/env bash
#
# build-deb.sh - Build Debian/Ubuntu package for ninja-mcp
#
# This script creates a .deb package that can be installed on Debian/Ubuntu systems.
# Usage: ./scripts/packaging/build-deb.sh

set -euo pipefail

# Get project info
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

VERSION=$(grep '^version' pyproject.toml | head -1 | cut -d'"' -f2)
DESCRIPTION=$(grep '^description' pyproject.toml | head -1 | cut -d'"' -f2)

echo "Building Debian package for ninja-mcp v${VERSION}..."

# Create packaging directory
PKG_DIR="packaging/debian/ninja-mcp_${VERSION}"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/local/bin"
mkdir -p "$PKG_DIR/usr/local/lib/ninja-mcp"
mkdir -p "$PKG_DIR/usr/share/doc/ninja-mcp"
mkdir -p "$PKG_DIR/usr/share/man/man1"

# Create control file
cat > "$PKG_DIR/DEBIAN/control" <<CONTROL_EOF
Package: ninja-mcp
Version: ${VERSION}
Section: devel
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), python3-pip, python3-venv
Maintainer: Ninja MCP Contributors <noreply@github.com>
Description: ${DESCRIPTION}
 A multi-module MCP (Model Context Protocol) server system for AI-powered
 development workflows. Ninja MCP consists of three specialized modules:
 .
  - Coder: AI code execution and modification
  - Researcher: Web search and report generation
  - Secretary: Codebase exploration and documentation
 .
 Each module runs as an independent MCP server and can be used standalone
 or together with AI assistants like Claude Code, VS Code, Zed, etc.
Homepage: https://github.com/angkira/ninja-mcp
CONTROL_EOF

# Create postinst script (runs after installation)
cat > "$PKG_DIR/DEBIAN/postinst" <<'POSTINST_EOF'
#!/bin/bash
set -e

echo "Installing ninja-mcp with uv..."

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Install ninja-mcp globally
uv tool install --force ninja-mcp[all]

echo ""
echo "✓ Ninja MCP installed successfully!"
echo ""
echo "Next steps:"
echo "  1. Set your API key: export OPENROUTER_API_KEY='your-key'"
echo "  2. Run setup: ninja-config"
echo "  3. Check docs: /usr/share/doc/ninja-mcp/"
echo ""

exit 0
POSTINST_EOF

chmod 755 "$PKG_DIR/DEBIAN/postinst"

# Create prerm script (runs before removal)
cat > "$PKG_DIR/DEBIAN/prerm" <<'PRERM_EOF'
#!/bin/bash
set -e

echo "Uninstalling ninja-mcp..."
uv tool uninstall ninja-mcp || true

exit 0
PRERM_EOF

chmod 755 "$PKG_DIR/DEBIAN/prerm"

# Copy documentation
cp README.md "$PKG_DIR/usr/share/doc/ninja-mcp/"
cp LICENSE "$PKG_DIR/usr/share/doc/ninja-mcp/" 2>/dev/null || echo "No LICENSE file found"
cp -r docs/* "$PKG_DIR/usr/share/doc/ninja-mcp/" 2>/dev/null || echo "No docs directory found"

# Create man pages (basic)
cat > "$PKG_DIR/usr/share/man/man1/ninja-coder.1" <<'MAN_EOF'
.TH NINJA-CODER 1 "2025" "ninja-mcp" "Ninja MCP Manual"
.SH NAME
ninja-coder \- AI code execution and modification MCP server
.SH SYNOPSIS
.B ninja-coder
[\fIOPTIONS\fR]
.SH DESCRIPTION
Ninja Coder is an MCP server that provides AI-powered code execution
and modification capabilities. It delegates to external code assistants
like Aider, Claude, or Cursor.
.SH OPTIONS
.TP
.B \-\-help
Display help information
.TP
.B \-\-http
Run in HTTP mode (default: stdio)
.TP
.B \-\-port PORT
Specify HTTP port (default: 8100)
.SH ENVIRONMENT
.TP
.B OPENROUTER_API_KEY
OpenRouter API key (required)
.TP
.B NINJA_CODER_MODEL
Model to use (default: anthropic/claude-haiku-4.5-20250929)
.TP
.B NINJA_CODE_BIN
Code assistant binary (default: aider)
.SH SEE ALSO
ninja-researcher(1), ninja-secretary(1), ninja-daemon(1)
.SH BUGS
Report bugs at: https://github.com/angkira/ninja-mcp/issues
MAN_EOF

# Compress man pages
gzip -9 "$PKG_DIR/usr/share/man/man1/ninja-coder.1"

# Create changelog
cat > "$PKG_DIR/usr/share/doc/ninja-mcp/changelog.Debian" <<CHANGELOG_EOF
ninja-mcp (${VERSION}) unstable; urgency=medium

  * New upstream release ${VERSION}
  * See https://github.com/angkira/ninja-mcp/releases for details

 -- Ninja MCP Contributors <noreply@github.com>  $(date -R)
CHANGELOG_EOF

gzip -9 "$PKG_DIR/usr/share/doc/ninja-mcp/changelog.Debian"

# Build the package
dpkg-deb --build "$PKG_DIR"

# Move to packaging directory
mv "$PKG_DIR.deb" "packaging/debian/ninja-mcp_${VERSION}_all.deb"

# Clean up build directory
rm -rf "$PKG_DIR"

echo "✓ Debian package built: packaging/debian/ninja-mcp_${VERSION}_all.deb"
echo ""
echo "To install locally:"
echo "  sudo dpkg -i packaging/debian/ninja-mcp_${VERSION}_all.deb"
echo "  sudo apt-get install -f  # Install dependencies if needed"
echo ""
echo "To publish to a PPA:"
echo "  1. Sign the package: dpkg-sig --sign builder packaging/debian/*.deb"
echo "  2. Upload to PPA"
echo ""
echo "To create a repository:"
echo "  1. Create Packages file: dpkg-scanpackages . /dev/null | gzip -9c > Packages.gz"
echo "  2. Serve via HTTP/HTTPS"
echo "  3. Users add: echo 'deb [trusted=yes] http://yourrepo.com/ ./' | sudo tee /etc/apt/sources.list.d/ninja-mcp.list"
