class NinjaMcp < Formula
  include Language::Python::Virtualenv

  desc "Multi-module MCP server system for AI-powered development"
  homepage "https://github.com/angkira/ninja-mcp"
  url "https://github.com/angkira/ninja-mcp/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "82d2117ef4398b2b0eb594362290cce6b553d1c8cc490e3d105ee46a95233798"
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
```

The Homebrew formula file was already correctly referencing the new repository name (`angkira/ninja-mcp`), so no changes were needed. The Debian package file is a binary file that doesn't need text modifications. All other files we've already updated are correct.