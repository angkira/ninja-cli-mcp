# Python Version Setup Guide

ninja-cli-mcp requires **Python 3.11+**. We recommend Python 3.12 for the best experience.

## Quick Check

Check which Python versions you have installed:

```bash
python3 --version
python3.11 --version
python3.12 --version
```

## Installation Methods

### macOS (Homebrew) - Recommended

```bash
# Install Python 3.12
brew install python@3.12

# Verify installation
python3.12 --version

# Make it default (optional)
echo 'export PATH="/opt/homebrew/opt/python@3.12/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Ubuntu/Debian

```bash
# Update package list
sudo apt update

# Install Python 3.12
sudo apt install python3.12 python3.12-venv python3.12-dev

# Verify installation
python3.12 --version
```

### Fedora/RHEL/CentOS

```bash
# Install Python 3.12
sudo dnf install python3.12

# Verify installation
python3.12 --version
```

### Using pyenv (Cross-platform) - Recommended

pyenv allows you to manage multiple Python versions easily.

#### Install pyenv

**macOS:**
```bash
brew install pyenv

# Add to shell
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc
source ~/.zshrc
```

**Linux:**
```bash
curl https://pyenv.run | bash

# Add to shell (bash)
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
source ~/.bashrc
```

#### Install Python 3.12 with pyenv

```bash
# Install Python 3.12
pyenv install 3.12

# Set as global default
pyenv global 3.12

# Verify
python --version  # Should show 3.12.x
```

## Switching Between Python Versions

If you have multiple Python versions installed, here are ways to switch:

### Option 1: update-alternatives (Ubuntu/Debian)

```bash
# Register Python 3.12
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# If you have multiple versions, configure which to use
sudo update-alternatives --config python3

# Select Python 3.12 from the list
```

### Option 2: Shell Alias

Add to your `~/.bashrc`, `~/.zshrc`, or `~/.config/fish/config.fish`:

**Bash/Zsh:**
```bash
alias python3='python3.12'
alias python='python3.12'
```

**Fish:**
```fish
alias python3 'python3.12'
alias python 'python3.12'
```

Then reload:
```bash
source ~/.bashrc  # or ~/.zshrc
```

### Option 3: pyenv (Recommended)

```bash
# Set global default
pyenv global 3.12

# Set local default for a project
cd /path/to/project
pyenv local 3.12

# Verify
python --version
```

### Option 4: Specify Python in uv

If you want to keep your system Python but use 3.12 for this project:

```bash
# Install with specific Python
uv sync --python python3.12

# Or set UV_PYTHON environment variable
export UV_PYTHON=python3.12
uv sync
```

## Verification

After installation, verify everything works:

```bash
# Check Python version
python3.12 --version

# Check it can import basic modules
python3.12 -c "import sys; print(f'Python {sys.version}')"

# Check pip is available
python3.12 -m pip --version

# Check uv can use it
uv python list
```

## Troubleshooting

### "python3.12: command not found"

The Python executable might be in a location not in your PATH.

**Find Python 3.12:**
```bash
# On macOS with Homebrew
ls /opt/homebrew/bin/python3*
ls /usr/local/bin/python3*

# On Linux
ls /usr/bin/python3*
ls /usr/local/bin/python3*

# Find all Python installations
which -a python3
which -a python3.12
```

**Add to PATH:**
```bash
# If found at /usr/local/bin
export PATH="/usr/local/bin:$PATH"

# If found at /opt/homebrew/bin
export PATH="/opt/homebrew/bin:$PATH"
```

### "ModuleNotFoundError" or import errors

Make sure you're using the Python version uv installed dependencies for:

```bash
# Check which Python uv is using
uv run python --version

# Reinstall dependencies
uv sync --python python3.12
```

### uv can't find Python 3.12

```bash
# Tell uv explicitly where Python is
uv sync --python /usr/bin/python3.12

# Or with full path from which
uv sync --python $(which python3.12)
```

### Multiple Python versions causing conflicts

Use pyenv to manage versions cleanly:

```bash
# List installed versions
pyenv versions

# Set project-specific version
cd /path/to/ninja-cli-mcp
pyenv local 3.12

# This creates a .python-version file
cat .python-version
```

## Best Practices

1. **Use pyenv**: It's the cleanest way to manage multiple Python versions
2. **Don't modify system Python**: On macOS/Linux, leave the system Python alone
3. **Use virtual environments**: uv handles this automatically
4. **Check before installing**: Run `python3.12 --version` first to see if you already have it
5. **Keep it updated**: Run `brew upgrade python@3.12` or `pyenv install 3.12.latest` periodically

## For ninja-cli-mcp Developers

When running the interactive installer:

```bash
cd ninja-cli-mcp

# The installer will:
# 1. Detect available Python versions
# 2. Prefer python3.12 > python3.11 > python3
# 3. Show instructions if no compatible version found
# 4. Use the detected version for uv sync

./scripts/install_interactive.sh
```

The installer automatically:
- ✅ Detects Python 3.12 if available
- ✅ Falls back to Python 3.11+
- ✅ Shows installation instructions if needed
- ✅ Configures uv to use the correct Python version
- ✅ Offers to help you switch to Python 3.12 if detected but not default

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python3.12 --version` | Check Python 3.12 version |
| `which python3.12` | Find Python 3.12 location |
| `pyenv install 3.12` | Install Python 3.12 via pyenv |
| `pyenv global 3.12` | Set Python 3.12 as default |
| `uv sync --python python3.12` | Install deps with specific Python |
| `uv run python --version` | Check Python version uv is using |

## Need Help?

If you're still having issues:

1. Check the [uv documentation](https://docs.astral.sh/uv/)
2. Open an issue with your:
   - Operating system: `uname -a`
   - Python versions: `ls /usr/bin/python3*`
   - PATH: `echo $PATH`
   - Error message

---

**TL;DR**: Install with `brew install python@3.12` (macOS) or `sudo apt install python3.12` (Ubuntu) or use `pyenv install 3.12` (any OS), then run `./scripts/install_interactive.sh`
