# 🥷 Ninja MCP - Complete Installation Guide

> **TL;DR**: Run `curl -fsSL https://raw.githubusercontent.com/angkira/ninja-mcp/main/install.sh | bash`

## Table of Contents

- [Quick Install](#quick-install)
- [Platform-Specific Installation](#platform-specific-installation)
- [Development Setup](#development-setup)
- [Manual Installation](#manual-installation)
- [Verification](#verification)
- [IDE Integration](#ide-integration)
- [Troubleshooting](#troubleshooting)

## Quick Install

### One-Line Interactive Installer (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-mcp/main/install.sh | bash
```

**What it does**:
- ✅ Detects your OS and installs dependencies
- ✅ Offers 3 installation modes (interactive/quick/dev)
- ✅ Configures API keys securely
- ✅ Sets up IDE integrations automatically
- ✅ **No hardcoded paths** - works for everyone!

**Choose your mode**:
1. **Interactive** (recommended) - Full setup with wizard
2. **Quick** - Global tool installation only
3. **Development** - Clone repo for contributing

## Platform-Specific Installation

### macOS

#### Using Homebrew (Recommended)

```bash
# Once published to tap
brew install angkira/ninja-mcp/ninja-mcp

# Or build from source
brew install --build-from-source packaging/homebrew/ninja-mcp.rb
```

#### Using uv (alternative)

```bash
brew install uv
uv tool install ninja-mcp[all]
```

### Ubuntu/Debian

#### Using apt (Recommended)

```bash
# Once published to PPA
sudo add-apt-repository ppa:angkira/ninja-mcp
sudo apt update
sudo apt install ninja-mcp
```

#### Download .deb

```bash
wget https://github.com/angkira/ninja-mcp/releases/latest/download/ninja-mcp_0.2.0_all.deb
sudo dpkg -i ninja-mcp_0.2.0_all.deb
sudo apt-get install -f  # Install dependencies
```

#### Using uv (alternative)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install ninja-mcp[all]
```

### Arch Linux

```bash
# Coming soon
yay -S ninja-mcp
```

### Windows

```bash
# Coming soon
winget install ninja-mcp
```

Or use WSL2 with Ubuntu instructions above.

## Development Setup

For contributors or if you want to modify the code:

### 1. Clone Repository

```bash
git clone https://github.com/angkira/ninja-mcp.git
cd ninja-mcp
```

### 2. Install Dependencies

```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies
uv sync --all-extras
```

### 3. Install `just` (Modern Task Runner)

```bash
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | \
  bash -s -- --to /usr/local/bin
```

### 4. Run Development Commands

```bash
just --list              # Show all available commands
just install-dev         # Install in editable mode
just setup-ide           # Configure IDE integration
just test                # Run tests
just daemon-start        # Start all daemons
```

## Manual Installation

If you prefer complete control:

### 1. Install Prerequisites

```bash
# Python 3.11+
python3 --version  # Should be >= 3.11

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install Ninja MCP

```bash
# Install all modules
uv tool install ninja-mcp[all]

# Or install specific modules
uv tool install ninja-mcp[coder]
uv tool install ninja-mcp[researcher]
uv tool install ninja-mcp[secretary]
```

### 3. Configure Environment

```bash
# Set API key (required)
export OPENROUTER_API_KEY='sk-or-v1-...'

# Optional: Set model preferences
export NINJA_CODER_MODEL='anthropic/claude-haiku-4.5-20250929'
export NINJA_RESEARCHER_MODEL='anthropic/claude-sonnet-4'

# Optional: Set code assistant
export NINJA_CODE_BIN='aider'
```

Add to your shell profile (`~/.bashrc`, `~/.zshrc`):

```bash
echo 'export OPENROUTER_API_KEY="sk-or-v1-..."' >> ~/.bashrc
source ~/.bashrc
```

### 4. Configure IDE

Run the configuration wizard:

```bash
ninja-config
```

Or manually configure your IDE (see [IDE Integration](#ide-integration) below).

## Verification

### Check Installation

```bash
# Check commands are available
which ninja-coder
which ninja-researcher
which ninja-secretary

# Check versions
uv tool list | grep ninja-mcp

# Test a server
ninja-coder --help
```

### Test MCP Connection

```bash
# For Claude Code users
claude mcp list

# Should show:
#   ninja-coder      - ✓ Connected
#   ninja-researcher - ✓ Connected
#   ninja-secretary  - ✓ Connected
```

### Run Health Check

```bash
# Check system requirements
just check-requirements  # If using dev setup

# Or manually:
python3 --version  # >= 3.11
uv --version
echo $OPENROUTER_API_KEY  # Should be set
```

## IDE Integration

### Claude Code

**Automatic** (recommended):
```bash
./scripts/install_claude_code_mcp.sh --all
```

**Manual**:
Edit `~/.config/claude/mcp.json`:

```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "ninja-coder",
      "env": {
        "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}"
      }
    },
    "ninja-researcher": {
      "command": "ninja-researcher"
    },
    "ninja-secretary": {
      "command": "ninja-secretary"
    }
  }
}
```

Restart Claude Code and check: `claude mcp list`

### VS Code (Cline Extension)

**Automatic**:
```bash
./scripts/install_vscode_mcp.sh --all
```

**Manual**:
See `examples/vscode-cline-mcp.json`

### Zed Editor

**Automatic**:
```bash
./scripts/install_zed_mcp.sh --all
```

**Manual**:
See Zed's MCP documentation.

## Troubleshooting

### "Command not found: ninja-coder"

**Solution 1** - Check PATH:
```bash
echo $PATH | grep -o "$HOME/.local/bin"
# If empty, add to ~/.bashrc:
export PATH="$HOME/.local/bin:$PATH"
```

**Solution 2** - Reinstall:
```bash
uv tool uninstall ninja-mcp
uv tool install ninja-mcp[all]
```

### "OPENROUTER_API_KEY not set"

**Solution**:
```bash
# Add to shell profile
echo 'export OPENROUTER_API_KEY="your-key-here"' >> ~/.bashrc
source ~/.bashrc

# Verify
echo $OPENROUTER_API_KEY
```

### "MCP server failed to start"

**Check logs**:
```bash
# If using daemons
tail -f ~/.cache/ninja-mcp/logs/coder.log

# If using direct mode
ninja-coder 2>&1 | tee test.log
```

**Common issues**:
- Missing API key → Set `OPENROUTER_API_KEY`
- Wrong Python version → Need Python 3.11+
- Firewall blocking → Check network settings

### "Invalid MCP configuration"

**Validate JSON**:
```bash
python3 -m json.tool ~/.config/claude/mcp.json
```

**Reset configuration**:
```bash
# Backup old config
cp ~/.config/claude/mcp.json ~/.config/claude/mcp.json.bak

# Regenerate
./scripts/install_claude_code_mcp.sh --all
```

### "Hardcoded paths in config"

**This should never happen anymore!** If you see hardcoded paths:

1. **Delete old config**:
   ```bash
   rm ~/.config/claude/mcp.json
   ```

2. **Reinstall**:
   ```bash
   ./scripts/install_claude_code_mcp.sh --all
   ```

3. **Verify** - should use commands directly:
   ```bash
   cat ~/.config/claude/mcp.json
   # Should show: "command": "ninja-coder"
   # NOT: "command": "uv", "args": ["--directory", "/home/user/..."]
   ```

### Still Having Issues?

1. **Check system requirements**:
   ```bash
   just check-requirements
   ```

2. **Read the logs**:
   ```bash
   ls ~/.cache/ninja-mcp/logs/
   ```

3. **Ask for help**:
   - GitHub Issues: https://github.com/angkira/ninja-mcp/issues
   - Include: OS, Python version, error messages, logs

## Next Steps

After installation:

1. **Configure your API keys** - `ninja-config`
2. **Read module docs**:
   - [Coder Module](docs/CODER.md)
   - [Researcher Module](docs/RESEARCHER.md)
   - [Secretary Module](docs/SECRETARY.md)
3. **Try it out** - Ask Claude to use the tools!
4. **Join community** - Star the repo ⭐

## See Also

- [README.md](README.md) - Project overview
- [INSTALLATION_MODES.md](docs/INSTALLATION_MODES.md) - Detailed installation modes
- [PACKAGING.md](docs/PACKAGING.md) - Building packages
- [justfile](justfile) - All development commands
