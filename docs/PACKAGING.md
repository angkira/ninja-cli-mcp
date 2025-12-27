# Packaging Guide for Ninja MCP

This guide covers how to build and distribute Ninja MCP packages for various platforms.

## Overview

Ninja MCP supports multiple distribution methods:

1. **PyPI** - Python package (uv tool install)
2. **Homebrew** - macOS package manager
3. **Debian/Ubuntu** - .deb packages
4. **Arch Linux** - AUR packages (coming soon)
5. **Docker** - Containerized deployment (coming soon)

## Building Packages

### Prerequisites

Install `just` for task automation:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin
```

### PyPI Package

```bash
# Build package
just build

# This creates:
#   dist/ninja_mcp-0.2.0.tar.gz
#   dist/ninja_mcp-0.2.0-py3-none-any.whl

# Test publish to TestPyPI
just publish-test

# Publish to production PyPI
just publish
```

**Publishing to PyPI**:
1. Get API token from https://pypi.org/manage/account/token/
2. Configure: `uv publish --token YOUR_TOKEN`
3. Users install: `uv tool install ninja-mcp[all]`

### Homebrew Formula

```bash
# Generate formula
just build-homebrew

# This creates: packaging/homebrew/ninja-mcp.rb
```

**Publishing to Homebrew**:

1. **Create a tap** (one-time setup):
   ```bash
   brew tap-new angkira/ninja-mcp
   ```

2. **Copy formula to tap**:
   ```bash
   cp packaging/homebrew/ninja-mcp.rb $(brew --repo angkira/ninja-mcp)/Formula/
   ```

3. **Test locally**:
   ```bash
   brew install --build-from-source angkira/ninja-mcp/ninja-mcp
   brew test angkira/ninja-mcp/ninja-mcp
   ```

4. **Publish tap**:
   ```bash
   cd $(brew --repo angkira/ninja-mcp)
   git add Formula/ninja-mcp.rb
   git commit -m "Add ninja-mcp formula"
   git push
   ```

5. **Users install**:
   ```bash
   brew install angkira/ninja-mcp/ninja-mcp
   ```

**For official Homebrew core** (requires high standards):
- Submit PR to https://github.com/Homebrew/homebrew-core
- See: https://docs.brew.sh/Adding-Software-to-Homebrew

### Debian/Ubuntu Package

```bash
# Build .deb package
just build-deb

# This creates: packaging/debian/ninja-mcp_0.2.0_all.deb
```

**Installing locally**:
```bash
sudo dpkg -i packaging/debian/ninja-mcp_0.2.0_all.deb
sudo apt-get install -f  # Install dependencies
```

**Publishing to PPA** (Personal Package Archive):

1. **Setup PPA** (one-time):
   ```bash
   # Create account at https://launchpad.net
   # Import GPG key:
   gpg --gen-key
   gpg --send-keys YOUR_KEY_ID --keyserver keyserver.ubuntu.com
   ```

2. **Create PPA**:
   - Go to https://launchpad.net/~yourusername/+activate-ppa
   - Create PPA named "ninja-mcp"

3. **Build source package**:
   ```bash
   cd packaging/debian
   debuild -S -sa
   ```

4. **Upload to PPA**:
   ```bash
   dput ppa:yourusername/ninja-mcp ninja-mcp_0.2.0_source.changes
   ```

5. **Users install**:
   ```bash
   sudo add-apt-repository ppa:yourusername/ninja-mcp
   sudo apt update
   sudo apt install ninja-mcp
   ```

**Self-hosting repository**:

1. **Create repository**:
   ```bash
   mkdir -p /var/www/apt
   cp packaging/debian/*.deb /var/www/apt/
   cd /var/www/apt
   dpkg-scanpackages . /dev/null | gzip -9c > Packages.gz
   ```

2. **Serve via HTTP**:
   ```bash
   # Setup nginx/apache to serve /var/www/apt
   ```

3. **Users add repository**:
   ```bash
   echo "deb [trusted=yes] http://yourserver.com/apt ./" | \
     sudo tee /etc/apt/sources.list.d/ninja-mcp.list
   sudo apt update
   sudo apt install ninja-mcp
   ```

### Arch Linux (AUR)

Coming soon. Will use PKGBUILD.

**Resources**:
- https://wiki.archlinux.org/title/AUR_submission_guidelines
- https://wiki.archlinux.org/title/Python_package_guidelines

### Docker Image

Coming soon.

```dockerfile
FROM python:3.12-slim
RUN pip install uv
RUN uv tool install ninja-mcp[all]
CMD ["ninja-coder"]
```

## Release Checklist

When releasing a new version:

- [ ] Update version in `pyproject.toml`
- [ ] Update CHANGELOG.md
- [ ] Run all tests: `just test`
- [ ] Build all packages: `just build-all`
- [ ] Create git tag: `git tag v0.2.0`
- [ ] Push tag: `git push origin v0.2.0`
- [ ] Publish to PyPI: `just publish`
- [ ] Update Homebrew formula
- [ ] Build and upload .deb packages
- [ ] Create GitHub release with artifacts
- [ ] Announce on social media

## GitHub Release

1. **Create release on GitHub**:
   ```bash
   gh release create v0.2.0 \
     --title "Ninja MCP v0.2.0" \
     --notes "See CHANGELOG.md for details" \
     dist/*.whl \
     dist/*.tar.gz \
     packaging/debian/*.deb
   ```

2. **Users download**:
   ```bash
   wget https://github.com/angkira/ninja-mcp/releases/latest/download/ninja-mcp_0.2.0_all.deb
   ```

## Continuous Integration

Setup GitHub Actions for automatic building:

**.github/workflows/build.yml**:
```yaml
name: Build Packages

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - run: just build-all
      - uses: actions/upload-artifact@v4
        with:
          name: packages
          path: |
            dist/*
            packaging/debian/*.deb
            packaging/homebrew/*.rb
```

## Version Management

Use semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes
- **MINOR**: New features, backwards compatible
- **PATCH**: Bug fixes

Update version in one place:
```toml
# pyproject.toml
[project]
version = "0.2.0"
```

All scripts read from this file.

## Distribution Statistics

Track downloads:

- **PyPI**: https://pypistats.org/packages/ninja-mcp
- **Homebrew**: `brew info angkira/ninja-mcp/ninja-mcp --analytics`
- **GitHub**: Release download counts

## Support Matrix

| Platform | Status | Installation |
|----------|--------|--------------|
| macOS (Homebrew) | 🟢 Ready | `brew install angkira/ninja-mcp/ninja-mcp` |
| Ubuntu/Debian | 🟢 Ready | `sudo apt install ninja-mcp` |
| Arch Linux | 🟡 Planned | `yay -S ninja-mcp` |
| Windows | 🟡 Planned | `winget install ninja-mcp` |
| PyPI | 🟢 Ready | `uv tool install ninja-mcp[all]` |
| Docker | 🟡 Planned | `docker run ninja-mcp` |

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development setup.
