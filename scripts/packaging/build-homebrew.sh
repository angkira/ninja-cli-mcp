#!/usr/bin/env bash
#
# build-homebrew.sh - Generate Homebrew formula for ninja-mcp
#
# This script generates a Homebrew formula that can be published to a tap.
# Usage: ./scripts/packaging/build-homebrew.sh

set -euo pipefail

# Get project info
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

VERSION=$(grep '^version' pyproject.toml | head -1 | cut -d'"' -f2)
DESCRIPTION=$(grep '^description' pyproject.toml | head -1 | cut -d'"' -f2)

echo "Generating Homebrew formula for ninja-mcp v${VERSION}..."

# Create formula directory
mkdir -p packaging/homebrew

# Generate the formula
cat > packaging/homebrew/ninja-mcp.rb <<'FORMULA_EOF'
class NinjaMcp < Formula
  include Language::Python::Virtualenv

  desc "Multi-module MCP server system for AI-powered development"
  homepage "https://github.com/angkira/ninja-mcp"
  url "https://github.com/angkira/ninja-mcp/archive/refs/tags/v__VERSION__.tar.gz"
  sha256 "__SHA256__"
  license "MIT"

  depends_on "python@3.12"
  depends_on "uv"

  def install
    # Install using uv
    system "uv", "venv", libexec
    system libexec/"bin/pip", "install", "--no-deps", "."

    # Install all modules
    system libexec/"bin/pip", "install", ".[all]"

    # Create wrappers for executables
    bin.install_symlink libexec/"bin/ninja-coder"
    bin.install_symlink libexec/"bin/ninja-researcher"
    bin.install_symlink libexec/"bin/ninja-secretary"
    bin.install_symlink libexec/"bin/ninja-daemon"
    bin.install_symlink libexec/"bin/ninja-config"
  end

  def caveats
    <<~EOS
      🥷 Ninja MCP has been installed!

      Set up your API key:
        export OPENROUTER_API_KEY='your-key-here'

      Configure IDE integration:
        ninja-config

      Or use the interactive installer:
        #{libexec}/bin/ninja-config --interactive

      Available commands:
        ninja-coder       - Code assistant MCP server
        ninja-researcher  - Research MCP server
        ninja-secretary   - Secretary MCP server
        ninja-daemon      - Daemon manager
        ninja-config      - Configuration manager

      Documentation: https://github.com/angkira/ninja-mcp
    EOS
  end

  test do
    system "#{bin}/ninja-coder", "--help"
    system "#{bin}/ninja-researcher", "--help"
    system "#{bin}/ninja-secretary", "--help"
  end
end
FORMULA_EOF

# Replace placeholders
sed -i "s/__VERSION__/${VERSION}/g" packaging/homebrew/ninja-mcp.rb
sed -i "s/__DESCRIPTION__/${DESCRIPTION}/g" packaging/homebrew/ninja-mcp.rb

# Calculate SHA256 (if tarball exists)
if [[ -f "dist/ninja_mcp-${VERSION}.tar.gz" ]]; then
    SHA256=$(sha256sum "dist/ninja_mcp-${VERSION}.tar.gz" | cut -d' ' -f1)
    sed -i "s/__SHA256__/${SHA256}/g" packaging/homebrew/ninja-mcp.rb
    echo "✓ SHA256 calculated: ${SHA256}"
else
    echo "⚠ Tarball not found, SHA256 placeholder left in formula"
    echo "  Build with: uv build"
fi

echo "✓ Homebrew formula generated: packaging/homebrew/ninja-mcp.rb"
echo ""
echo "To test locally:"
echo "  brew install --build-from-source packaging/homebrew/ninja-mcp.rb"
echo ""
echo "To publish to a tap:"
echo "  1. Create a tap: brew tap yourusername/ninja-mcp"
echo "  2. Copy formula to tap: cp packaging/homebrew/ninja-mcp.rb \$(brew --repo yourusername/ninja-mcp)/Formula/"
echo "  3. Commit and push"
echo "  4. Users install with: brew install yourusername/ninja-mcp/ninja-mcp"
