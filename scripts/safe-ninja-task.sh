#!/bin/bash
# Safe wrapper for ninja-coder tasks that ensures git safety

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🛡️  Safe Ninja Task Wrapper${NC}"
echo ""

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}❌ Not in a git repository!${NC}"
    echo "Initialize git first: git init"
    exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    echo -e "${RED}❌ You have uncommitted changes!${NC}"
    echo ""
    echo "Uncommitted files:"
    git status --short
    echo ""
    echo "Options:"
    echo "  1. Commit your changes: git add . && git commit -m 'your message'"
    echo "  2. Stash them: git stash"
    echo "  3. Force run anyway: use --force flag"
    echo ""

    if [[ "$1" != "--force" ]]; then
        exit 1
    else
        echo -e "${YELLOW}⚠️  Running with --force (DANGEROUS!)${NC}"
    fi
fi

# Check for untracked files that might be overwritten
untracked=$(git ls-files --others --exclude-standard)
if [ -n "$untracked" ]; then
    echo -e "${YELLOW}⚠️  Warning: You have untracked files${NC}"
    echo "$untracked"
    echo ""
    echo "These files might be overwritten. Consider:"
    echo "  git add <files> to track them"
    echo ""
fi

# Create a safety commit point
current_branch=$(git branch --show-current)
commit_hash=$(git rev-parse HEAD)

echo -e "${GREEN}✅ Safe to proceed${NC}"
echo "Branch: $current_branch"
echo "Commit: $commit_hash"
echo ""
echo "If ninja-coder overwrites files, you can recover with:"
echo "  git diff              # See changes"
echo "  git checkout <file>   # Restore single file"
echo "  git reset --hard HEAD # Restore everything (DANGER!)"
echo ""

# Tag this commit for easy recovery
git tag -f "pre-ninja-task-$(date +%Y%m%d-%H%M%S)" HEAD 2>/dev/null || true

echo -e "${GREEN}✅ Safety tag created${NC}"
echo ""
