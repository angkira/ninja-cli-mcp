# Releasing Ninja MCP

This document describes how to cut a release. Two channels are involved:

- **GitHub**: tag `vX.Y.Z` pushed to `main` triggers the `Release` workflow
  (builds wheel/sdist/deb/homebrew formula and creates the GitHub release).
- **PyPI**: publishing is done **locally** via `scripts/release.sh` because the
  `PYPI_API_TOKEN` secret used by the GitHub workflow is a project-scoped token
  that does not match the `ninja-mcp` project name. The local flow uses the
  all-projects token stored in `.env` (`PY_PI_TOKEN`).

## One command

```bash
./scripts/release.sh <version> [options]
```

Example:

```bash
./scripts/release.sh 1.0.5
```

This performs, in order:

1. **Preflight** — on `main`, clean tracked tree, tag free locally and on
   origin, and a `## <version>` section exists in `CHANGELOG.md`.
2. **Version bump** — updates every versioned file (`pyproject.toml`,
   `uv.lock` ninja-mcp entry, `src/ninja_agent/__init__.py`,
   `tests/test_container_config.py`, `Makefile`, `install.sh`,
   `docker-compose.yml`). `uv.lock` is edited directly (never `uv lock`) to
   avoid reformatting the lockfile.
3. **Quality gates** — `ruff format --check`, `ruff check`, `mypy`,
   `test_container_config` (the release-consistency test).
4. **Build** — `uv build`, verifying the artifacts carry the new version.
5. **Commit + push + tag** — commits the bump, pushes `main`, creates and
   pushes tag `v<version>` (triggers the GitHub Release workflow).
6. **Publish to PyPI (local)** — resolves the token
   (`UV_PUBLISH_TOKEN` / `PY_PI_TOKEN` / `TWINE_PASSWORD` env, else
   `PY_PI_TOKEN` from `.env`), runs `uv publish`, then polls PyPI's simple
   index until the version is visible.
7. **Summary** — prints the PyPI / GitHub release / Actions URLs.

## Options

| Option | Effect |
| --- | --- |
| `--dry-run` | Print the plan without mutating anything |
| `--skip-tests` | Skip lint/typecheck/consistency gates |
| `--skip-publish` | Bump, build, commit, tag — but do not publish to PyPI |
| `--yes` | Skip the interactive confirmation |

## Make / just wrappers

| Tool | Command | Notes |
| --- | --- | --- |
| make | `make release VERSION=1.0.6` | full flow |
| make | `make release-dry-run VERSION=1.0.6` | plan only |
| make | `make release-tag-only VERSION=1.0.6` | no PyPI publish |
| make | `make publish-local` | publish current version |
| just | `just release-local 1.0.6` | full flow |
| just | `just release-dry-run 1.0.6` | plan only |
| just | `just release-tag-only 1.0.6` | no PyPI publish |
| just | `just publish-local` | publish current version |

## Manual steps (what the script automates)

For reference / troubleshooting, the manual flow is:

```bash
# 1. Add a "## X.Y.Z - <date>" section to CHANGELOG.md
# 2. Bump version in: pyproject.toml, uv.lock (ninja-mcp entry),
#    src/ninja_agent/__init__.py, tests/test_container_config.py,
#    Makefile (VERSION + help), install.sh, docker-compose.yml
# 3. Verify
uv run pytest tests/test_container_config.py -q
uv run ruff format --check src/ && uv run ruff check src/ && uv run mypy src/
# 4. Build, commit, tag, push
uv build
git commit -am "chore(release): bump version to X.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main vX.Y.Z
# 5. Publish locally (all-projects token from .env)
TOKEN=$(grep '^PY_PI_TOKEN=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
UV_PUBLISH_TOKEN="$TOKEN" uv publish dist/ninja_mcp-X.Y.Z-py3-none-any.whl dist/ninja_mcp-X.Y.Z.tar.gz
```

## Notes

- The GitHub `Release` workflow's PyPI publish step will keep failing until the
  `PYPI_API_TOKEN` repository secret is replaced with the all-projects token.
  Until then, always publish locally (the script does this automatically).
- Version bump must be committed **before** the tag is pushed; the script does
  both in the right order.
- Untracked files (e.g. `docs/superpowers/`, `training/`) do not block the
  release — only tracked modifications do.