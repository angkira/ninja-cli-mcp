# Release Process

This document describes how to create a new release of Ninja MCP.

## Overview

The release process is mostly automated via GitHub Actions. When you push a version tag, it will:

1. Build all packages (Python, Debian, Homebrew)
2. Run tests
3. Create a GitHub release
4. Upload all artifacts
5. Publish to PyPI (if configured)
6. Update Homebrew tap (if configured)

## Prerequisites

### One-Time Setup

1. **PyPI API Token** (for publishing to PyPI):
   - Go to https://pypi.org/manage/account/token/
   - Create a new API token with scope for this project
   - Add to GitHub secrets: `PYPI_API_TOKEN`

2. **Homebrew Tap Repository** (optional):
   - Create a tap: `brew tap-new angkira/ninja-mcp`
   - Push to GitHub: https://github.com/angkira/homebrew-ninja-mcp
   - Generate personal access token with `repo` scope
   - Add to GitHub secrets: `TAP_GITHUB_TOKEN`

3. **GitHub Environment** (for PyPI publishing):
   - Go to Settings → Environments
   - Create environment named `pypi`
   - Add secret `PYPI_API_TOKEN`

## Release Steps

### 1. Prepare the Release

```bash
# Make sure you're on main branch and up to date
git checkout main
git pull origin main

# Run all tests
just test

# Check everything builds
just build-all

# Review the built packages
ls -lh dist/ packaging/debian/ packaging/homebrew/
```

### 2. Update Version and Changelog

```bash
# Edit version in pyproject.toml
vim pyproject.toml  # Update version = "0.3.0"

# Update CHANGELOG.md
vim CHANGELOG.md    # Add release notes under [0.3.0] section

# Commit changes
git add pyproject.toml CHANGELOG.md
git commit -m "Bump version to 0.3.0"
git push origin main
```

### 3. Create and Push Tag

```bash
# Create annotated tag
git tag -a v0.3.0 -m "Release v0.3.0"

# Push tag to GitHub
git push origin v0.3.0
```

This triggers the release workflow automatically!

### 4. Monitor Release Process

Watch the GitHub Actions:
- https://github.com/angkira/ninja-mcp/actions

The workflow will:
1. ✅ Run CI tests
2. ✅ Build Python packages
3. ✅ Build Debian package
4. ✅ Generate Homebrew formula
5. ✅ Create GitHub release with all artifacts
6. ✅ Publish to PyPI
7. ✅ Update Homebrew tap

### 5. Verify Release

```bash
# Check GitHub release
open https://github.com/angkira/ninja-mcp/releases/latest

# Check PyPI
open https://pypi.org/project/ninja-mcp/

# Test installation
uv tool install ninja-mcp[all]
ninja-coder --help

# Test Homebrew (if tap is setup)
brew install angkira/ninja-mcp/ninja-mcp

# Test Debian package
wget https://github.com/angkira/ninja-mcp/releases/download/v0.3.0/ninja-mcp_0.3.0_all.deb
sudo dpkg -i ninja-mcp_0.3.0_all.deb
```

## Manual Release (if needed)

If automatic release fails, you can do it manually:

### Build Locally

```bash
# Build all packages
just build-all

# Verify
ls -lh dist/ packaging/debian/ packaging/homebrew/
```

### Create GitHub Release

```bash
# Install GitHub CLI
brew install gh  # or: sudo apt install gh

# Create release
gh release create v0.3.0 \
  --title "Ninja MCP v0.3.0" \
  --notes-file CHANGELOG.md \
  dist/* \
  packaging/debian/*.deb \
  packaging/homebrew/*.rb
```

### Publish to PyPI

```bash
# Using uv
just publish

# Or manually
uv publish --token $PYPI_API_TOKEN
```

### Update Homebrew Tap

```bash
# Clone tap repo
git clone https://github.com/angkira/homebrew-ninja-mcp
cd homebrew-ninja-mcp

# Copy new formula
cp ../ninja-mcp/packaging/homebrew/ninja-mcp.rb Formula/

# Commit and push
git add Formula/ninja-mcp.rb
git commit -m "Update ninja-mcp to v0.3.0"
git push
```

## Hotfix Release

For urgent bug fixes:

```bash
# Create hotfix branch
git checkout -b hotfix/v0.2.1 v0.2.0

# Fix the bug
vim src/...
git commit -am "Fix critical bug"

# Bump patch version
vim pyproject.toml  # version = "0.2.1"
vim CHANGELOG.md    # Add [0.2.1] section

git commit -am "Bump version to 0.2.1"

# Merge to main
git checkout main
git merge hotfix/v0.2.1

# Tag and release
git tag -a v0.2.1 -m "Hotfix v0.2.1"
git push origin main v0.2.1
```

## Pre-release / Beta

For testing before stable release:

```bash
# Tag as pre-release
git tag -a v0.3.0-beta.1 -m "Beta release v0.3.0-beta.1"
git push origin v0.3.0-beta.1

# GitHub Actions will mark it as pre-release
```

Install pre-release:
```bash
uv tool install ninja-mcp[all]==0.3.0b1
```

## Post-Release Tasks

After successful release:

1. **Announce** on social media, Discord, etc.
2. **Update documentation** if needed
3. **Close milestone** on GitHub
4. **Thank contributors** in release notes

## Rollback

If a release has critical issues:

```bash
# Delete tag locally and remotely
git tag -d v0.3.0
git push origin :refs/tags/v0.3.0

# Delete GitHub release
gh release delete v0.3.0

# Yank from PyPI (doesn't delete, but warns users)
uv publish --yank v0.3.0
```

## Versioning Guide

Use [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0): Breaking changes, incompatible API
- **MINOR** (0.1.0): New features, backwards compatible
- **PATCH** (0.0.1): Bug fixes, backwards compatible

Examples:
- `0.2.0` → `0.2.1`: Bug fix
- `0.2.0` → `0.3.0`: New feature
- `0.2.0` → `1.0.0`: Breaking change

## Checklist

Before releasing, verify:

- [ ] All tests pass: `just test`
- [ ] Linting passes: `just lint`
- [ ] Version bumped in `pyproject.toml`
- [ ] CHANGELOG.md updated
- [ ] Documentation updated
- [ ] Builds successfully: `just build-all`
- [ ] Tag follows format: `vX.Y.Z`
- [ ] GitHub Actions secrets configured
- [ ] Release notes prepared

## Troubleshooting

### "PyPI publish failed"

Check:
- Is `PYPI_API_TOKEN` secret set?
- Is the version already published?
- Try: `just publish-test` first

### "Homebrew tap update failed"

Check:
- Is `TAP_GITHUB_TOKEN` secret set?
- Does tap repository exist?
- Does token have `repo` scope?

### "Debian package build failed"

Check:
- Are all scripts executable?
- Is `dpkg-dev` installed?
- Check logs in GitHub Actions

### "Release tag already exists"

```bash
# Delete and recreate
git tag -d v0.3.0
git push origin :refs/tags/v0.3.0
git tag -a v0.3.0 -m "Release v0.3.0"
git push origin v0.3.0
```

## See Also

- [PACKAGING.md](../../docs/PACKAGING.md) - Detailed packaging guide
- [GitHub Actions docs](https://docs.github.com/en/actions)
- [PyPI publishing guide](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [Homebrew tap docs](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
