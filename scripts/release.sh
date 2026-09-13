#!/usr/bin/env bash
#
# release.sh - Local release automation for ninja-mcp.
#
# Bumps the version across every versioned file, runs quality gates, builds
# distributions, commits and pushes, creates and pushes the git tag, publishes
# to PyPI, and verifies the release on PyPI.
#
# Usage:
#   ./scripts/release.sh <version> [options]
#
# Options:
#   --dry-run        Print the plan without mutating anything.
#   --skip-tests     Skip lint/typecheck/consistency checks.
#   --skip-publish   Skip the local PyPI publish (tag + GitHub release only).
#   --yes            Do not prompt for confirmation.
#   -h, --help       Show this help.
#
# PyPI token resolution order:
#   1. UV_PUBLISH_TOKEN / PY_PI_TOKEN / TWINE_PASSWORD environment variable
#   2. PY_PI_TOKEN in .env at the repository root

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { printf "${CYAN}%s${NC}\n" "$*"; }
ok() { printf "${GREEN}✓ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}⚠ %s${NC}\n" "$*"; }
die() {
    printf "${RED}✗ %s${NC}\n" "$*" >&2
    exit 1
}

usage() {
    sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

DRY_RUN=0
SKIP_TESTS=0
SKIP_PUBLISH=0
ASSUME_YES=0
VERSION=""

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --skip-tests) SKIP_TESTS=1 ;;
        --skip-publish) SKIP_PUBLISH=1 ;;
        --yes | -y) ASSUME_YES=1 ;;
        -h | --help) usage ;;
        -*)
            die "Unknown option: $1 (use --help)"
            ;;
        *)
            if [ -n "$VERSION" ]; then
                die "Version already provided: $VERSION (got '$1')"
            fi
            VERSION="$1"
            ;;
    esac
    shift
done

[ -n "$VERSION" ] || die "Usage: ./scripts/release.sh <version> [options]"
VERSION="${VERSION#v}"

if ! printf '%s' "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$'; then
    die "Invalid version '$VERSION'. Expected semver, e.g. 1.0.5"
fi

CURRENT_VERSION="$(grep '^version' pyproject.toml | head -1 | cut -d'"' -f2)"
[ "$CURRENT_VERSION" != "$VERSION" ] || die "Version is already $VERSION"

TAG="v$VERSION"

info "Release plan"
printf '  version : %s -> %s\n' "$CURRENT_VERSION" "$VERSION"
printf '  tag     : %s\n' "$TAG"
printf '  publish : %s\n' "$([ "$SKIP_PUBLISH" -eq 1 ] && echo 'no (tag only)' || echo 'yes (local PyPI)')"
printf '  dry-run : %s\n\n' "$([ "$DRY_RUN" -eq 1 ] && echo yes || echo no)"

run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '  [dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

confirm() {
    [ "$ASSUME_YES" -eq 1 ] && return 0
    [ "$DRY_RUN" -eq 1 ] && return 0
    printf "${YELLOW}%s [y/N] ${NC}" "$1"
    read -r reply
    case "$reply" in
        y | Y | yes | YES) return 0 ;;
        *) die "Aborted by user" ;;
    esac
}

# ── Preflight ────────────────────────────────────────────────────────────────

info "Preflight checks"

branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" = "main" ] || die "Releases must run from 'main' (currently on '$branch')"

if ! git diff --quiet || ! git diff --cached --quiet; then
    die "Working tree has uncommitted tracked changes. Commit or stash them first."
fi

git rev-parse "$TAG" >/dev/null 2>&1 && die "Tag $TAG already exists"
git ls-remote --tags origin "$TAG" 2>/dev/null | grep -q "$TAG" && die "Tag $TAG already exists on origin"

grep -q "^## $VERSION " CHANGELOG.md ||
    die "CHANGELOG.md is missing a '## $VERSION' section. Add release notes first."

ok "Preflight passed (branch=main, tag free, changelog present)"

# ── Version bump ─────────────────────────────────────────────────────────────

info "Bumping version to $VERSION"

if [ "$DRY_RUN" -eq 0 ]; then
    python3 - "$CURRENT_VERSION" "$VERSION" <<'PY'
import re
import sys
from pathlib import Path

old, new = sys.argv[1], sys.argv[2]
root = Path(".")


def replace(path: str, pattern: str, replacement: str, *, required: bool = True) -> None:
    p = Path(path)
    text = p.read_text()
    updated, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if required and count == 0:
        raise SystemExit(f"pattern not found in {path}: {pattern!r}")
    p.write_text(updated)
    print(f"  {path}: {count} replacement(s)")


replace("pyproject.toml", r'^version = ".*"$', f'version = "{new}"')
replace(
    "src/ninja_agent/__init__.py",
    r'^__version__ = ".*"$',
    f'__version__ = "{new}"',
)
replace(
    "tests/test_container_config.py",
    r'^CURRENT_VERSION = ".*"$',
    f'CURRENT_VERSION = "{new}"',
)
replace("Makefile", r'^VERSION \?= .*$', f"VERSION ?= {new}")
replace("Makefile", r"^(\t@printf '%s\\n' 'Ninja MCP ).*( make targets')$", rf"\g<1>{new}\g<2>")
replace(
    "Makefile",
    r"IMAGE=ninja-mcp:local-.*'$",
    f"IMAGE=ninja-mcp:local-{new}'",
)
replace("install.sh", r"^NINJA_DOCKER_IMAGE=ninja-mcp:local-.*$", f"NINJA_DOCKER_IMAGE=ninja-mcp:local-{new}")
replace(
    "docker-compose.yml",
    r"ninja-mcp:local-.*\}",
    f"ninja-mcp:local-{new}}}",
)

# uv.lock: only the ninja-mcp package entry, never a full re-resolve (which
# would reformat the whole lockfile depending on the local uv version).
lock = Path("uv.lock")
text = lock.read_text()
pattern = 'name = "ninja-mcp"\nversion = "' + old + '"\nsource = { editable = "." }'
replacement = 'name = "ninja-mcp"\nversion = "' + new + '"\nsource = { editable = "." }'
if pattern not in text:
    raise SystemExit("ninja-mcp entry not found in uv.lock")
lock.write_text(text.replace(pattern, replacement, 1))
print("  uv.lock: 1 replacement(s)")
PY
    ok "Version files updated"
else
    printf '  [dry-run] bump %s -> %s in pyproject.toml, uv.lock, ninja_agent, Makefile, docker-compose, install.sh, tests\n' "$CURRENT_VERSION" "$VERSION"
fi

# ── Quality gates ────────────────────────────────────────────────────────────

if [ "$SKIP_TESTS" -eq 0 ]; then
    info "Running quality gates"
    run uv run ruff format --check src/
    run uv run ruff check src/
    run uv run mypy src/ --ignore-missing-imports
    run uv run pytest tests/test_container_config.py -q
    ok "Quality gates passed"
else
    warn "Quality gates skipped (--skip-tests)"
fi

# ── Build ────────────────────────────────────────────────────────────────────

info "Building distributions"
run rm -rf dist
run uv build
if [ "$DRY_RUN" -eq 0 ]; then
    ls -1 dist/ | grep -q "ninja_mcp-${VERSION}" || die "Build did not produce $VERSION artifacts"
    ok "Built: $(ls dist/ | tr '\n' ' ')"
fi

# ── Commit, push, tag ────────────────────────────────────────────────────────

info "Committing and pushing"
confirm "Commit version bump, push main, and push tag $TAG?"

if [ "$DRY_RUN" -eq 0 ]; then
    git add pyproject.toml uv.lock src/ninja_agent/__init__.py tests/test_container_config.py \
        Makefile docker-compose.yml install.sh CHANGELOG.md
    git commit -m "chore(release): bump version to $VERSION"
    git push origin main
    git tag -a "$TAG" -m "Release $TAG"
    git push origin "$TAG"
    ok "Pushed main and tag $TAG"
else
    printf '  [dry-run] git add/commit/push + tag %s\n' "$TAG"
fi

# ── Publish to PyPI ──────────────────────────────────────────────────────────

if [ "$SKIP_PUBLISH" -eq 0 ]; then
    info "Publishing to PyPI (local)"

    TOKEN="${UV_PUBLISH_TOKEN:-${PY_PI_TOKEN:-${TWINE_PASSWORD:-}}}"
    if [ -z "$TOKEN" ] && [ -f .env ]; then
        TOKEN="$(grep -E '^(PY_PI_TOKEN|UV_PUBLISH_TOKEN)=' .env | head -1 | cut -d= -f2- | tr -d "\"'" || true)"
    fi
    [ -n "$TOKEN" ] || die "No PyPI token found. Set UV_PUBLISH_TOKEN or add PY_PI_TOKEN to .env"

    if [ "$DRY_RUN" -eq 0 ]; then
        UV_PUBLISH_TOKEN="$TOKEN" uv publish "dist/ninja_mcp-${VERSION}-py3-none-any.whl" "dist/ninja_mcp-${VERSION}.tar.gz"
        ok "Published to PyPI"
    else
        printf '  [dry-run] uv publish dist/ninja_mcp-%s-*.whl dist/ninja_mcp-%s.tar.gz\n' "$VERSION" "$VERSION"
    fi

    # Verify on PyPI (CDN may lag a few seconds).
    if [ "$DRY_RUN" -eq 0 ]; then
        info "Verifying on PyPI"
        found=0
        for _ in $(seq 1 12); do
            if curl -fsSL "https://pypi.org/simple/ninja-mcp/" 2>/dev/null | grep -q "ninja_mcp-${VERSION}"; then
                found=1
                break
            fi
            sleep 5
        done
        [ "$found" -eq 1 ] || die "Version $VERSION not visible on PyPI yet"
        ok "Verified on PyPI: https://pypi.org/project/ninja-mcp/$VERSION/"
    fi
fi

printf '\n'
ok "Release $TAG complete"
printf '  PyPI     : https://pypi.org/project/ninja-mcp/%s/\n' "$VERSION"
printf '  Releases : https://github.com/angkira/ninja-cli-mcp/releases/tag/%s\n' "$TAG"
printf '  Actions  : https://github.com/angkira/ninja-cli-mcp/actions\n'
