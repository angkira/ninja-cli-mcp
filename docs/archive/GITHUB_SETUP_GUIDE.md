# GitHub Repository Setup Guide

This guide shows how to configure your GitHub repository to enable automated releases.

## 1. Configure GitHub Secrets

Go to: https://github.com/angkira/ninja-mcp/settings/secrets/actions

### Required Secrets

#### PYPI_API_TOKEN

For publishing to PyPI:

1. **Create PyPI account** (if you don't have one):
   - Go to https://pypi.org/account/register/

2. **Generate API token**:
   - Go to https://pypi.org/manage/account/token/
   - Click "Add API token"
   - Name: `ninja-mcp-github-actions`
   - Scope: Select "Project: ninja-mcp" (or "Entire account" for now)
   - Click "Create token"
   - **COPY THE TOKEN NOW** (you won't see it again!)

3. **Add to GitHub**:
   - Go to GitHub repo → Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `PYPI_API_TOKEN`
   - Value: Paste the token from PyPI
   - Click "Add secret"

#### TAP_GITHUB_TOKEN (Optional - for Homebrew)

For updating Homebrew tap automatically:

1. **Create Homebrew tap repository**:
   ```bash
   brew tap-new angkira/ninja-mcp
   cd $(brew --repo angkira/ninja-mcp)
   git remote add origin https://github.com/angkira/homebrew-ninja-mcp
   git push -u origin main
   ```

2. **Generate GitHub Personal Access Token**:
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Name: `homebrew-tap-update`
   - Scopes: Check `repo` (Full control of private repositories)
   - Click "Generate token"
   - **COPY THE TOKEN NOW**

3. **Add to GitHub**:
   - Go to GitHub repo → Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `TAP_GITHUB_TOKEN`
   - Value: Paste the token
   - Click "Add secret"

## 2. Create GitHub Environment (for PyPI)

This adds extra protection for production releases:

1. Go to: https://github.com/angkira/ninja-mcp/settings/environments
2. Click "New environment"
3. Name: `pypi`
4. Click "Configure environment"
5. **Add secret to environment**:
   - Under "Environment secrets"
   - Click "Add secret"
   - Name: `PYPI_API_TOKEN`
   - Value: Same token as above
   - Click "Add secret"

## 3. Enable GitHub Actions

1. Go to: https://github.com/angkira/ninja-mcp/settings/actions
2. Under "Actions permissions":
   - Select "Allow all actions and reusable workflows"
3. Under "Workflow permissions":
   - Select "Read and write permissions"
   - Check "Allow GitHub Actions to create and approve pull requests"
4. Click "Save"

## 4. Enable GitHub Releases

1. Go to: https://github.com/angkira/ninja-mcp/releases
2. Releases should be enabled by default
3. Check that "Automatically generated release notes" is enabled

## 5. Test the Setup

### Test 1: Push to Main (CI)

```bash
git add .
git commit -m "Add build system and release automation"
git push origin main
```

Go to: https://github.com/angkira/ninja-mcp/actions

You should see the CI workflow running.

### Test 2: Create a Test Release

```bash
# Create a test tag
git tag -a v0.2.0-test -m "Test release"
git push origin v0.2.0-test
```

This will trigger the release workflow.

Check:
- GitHub Actions: https://github.com/angkira/ninja-mcp/actions
- Releases: https://github.com/angkira/ninja-mcp/releases

### Test 3: Verify PyPI Publication

If the release workflow succeeded:

```bash
# Check PyPI
open https://pypi.org/project/ninja-mcp/

# Try installing
uv tool install ninja-mcp[all]
ninja-coder --help
```

### Test 4: Cleanup Test Release

```bash
# Delete test tag
git tag -d v0.2.0-test
git push origin :refs/tags/v0.2.0-test

# Delete test release on GitHub
gh release delete v0.2.0-test
```

## 6. Create Production Release

Once everything is tested:

```bash
# Interactive release
just release 0.2.1

# Or quick release (if changelog is ready)
just release-quick 0.2.1
```

This will:
1. ✅ Update version in pyproject.toml
2. ✅ Commit changes
3. ✅ Create and push tag
4. ✅ Trigger GitHub Actions
5. ✅ Build all packages
6. ✅ Create GitHub release
7. ✅ Publish to PyPI
8. ✅ Update Homebrew tap (if configured)

Monitor at: https://github.com/angkira/ninja-mcp/actions

## 7. Verify Everything Works

After release completes:

### Check GitHub Release

```bash
open https://github.com/angkira/ninja-mcp/releases/latest
```

Should contain:
- Release notes
- Python wheel (.whl)
- Python tarball (.tar.gz)
- Debian package (.deb)
- Homebrew formula (.rb)

### Check PyPI

```bash
open https://pypi.org/project/ninja-mcp/
```

Should show new version.

### Test Installation

```bash
# PyPI
uv tool install ninja-mcp[all]

# Homebrew (if tap is setup)
brew install angkira/ninja-mcp/ninja-mcp

# Debian
wget https://github.com/angkira/ninja-mcp/releases/download/v0.2.1/ninja-mcp_0.2.1_all.deb
sudo dpkg -i ninja-mcp_0.2.1_all.deb
```

## 8. Setup Badges (Optional)

Add these to your README.md:

```markdown
[![CI](https://github.com/angkira/ninja-mcp/workflows/CI/badge.svg)](https://github.com/angkira/ninja-mcp/actions)
[![PyPI version](https://badge.fury.io/py/ninja-mcp.svg)](https://pypi.org/project/ninja-mcp/)
[![Downloads](https://pepy.tech/badge/ninja-mcp)](https://pepy.tech/project/ninja-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
```

## Summary Checklist

Setup tasks:

- [ ] Create PyPI account
- [ ] Generate PyPI API token
- [ ] Add `PYPI_API_TOKEN` to GitHub secrets
- [ ] Create `pypi` environment in GitHub
- [ ] Enable GitHub Actions with write permissions
- [ ] (Optional) Create Homebrew tap repository
- [ ] (Optional) Add `TAP_GITHUB_TOKEN` secret
- [ ] Test CI workflow (push to main)
- [ ] Test release workflow (push test tag)
- [ ] Verify PyPI publication
- [ ] Create production release
- [ ] Verify all installation methods
- [ ] Add badges to README

## Troubleshooting

### "PyPI publish failed: 403 Forbidden"

- Check `PYPI_API_TOKEN` is set correctly
- Verify token has correct scope
- Make sure version doesn't already exist on PyPI

### "GitHub Actions not running"

- Check Actions are enabled in settings
- Verify workflow file syntax (must be valid YAML)
- Check workflow permissions are set

### "Can't create release: Permission denied"

- Go to Settings → Actions → Workflow permissions
- Enable "Read and write permissions"

### "Homebrew tap update failed"

- Check `TAP_GITHUB_TOKEN` is set
- Verify tap repository exists: https://github.com/angkira/homebrew-ninja-mcp
- Check token has `repo` scope

## Resources

- [GitHub Actions docs](https://docs.github.com/en/actions)
- [PyPI publishing guide](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [Homebrew tap guide](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
- [Semantic Versioning](https://semver.org/)

## Need Help?

Open an issue: https://github.com/angkira/ninja-mcp/issues
