#!/bin/bash
# Ninja Recovery Tool - Recover from file overwrites

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Ninja Recovery Tool${NC}"
echo ""

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}❌ Not in a git repository!${NC}"
    exit 1
fi

# Function to show file diff
show_diff() {
    local file=$1
    echo -e "${YELLOW}Changes in $file:${NC}"
    git diff HEAD -- "$file" | head -50
    echo ""
    lines=$(git diff HEAD -- "$file" | wc -l)
    if [ "$lines" -gt 50 ]; then
        echo -e "${YELLOW}... and $((lines - 50)) more lines${NC}"
        echo ""
    fi
}

# Function to restore file
restore_file() {
    local file=$1
    echo -e "${GREEN}Restoring $file...${NC}"
    git checkout HEAD -- "$file"
    echo -e "${GREEN}✅ Restored${NC}"
}

# Main menu
echo "What would you like to do?"
echo ""
echo "1. Show all changed files"
echo "2. Show diff for specific file"
echo "3. Restore specific file"
echo "4. Restore all changed files (CAREFUL!)"
echo "5. List safety tags"
echo "6. Reset to safety tag"
echo "7. Show recovery options"
echo "q. Quit"
echo ""

read -p "Choice: " choice

case $choice in
    1)
        echo -e "${YELLOW}Changed files:${NC}"
        git status --short
        echo ""
        echo "Files with many changes (potential overwrites):"
        for file in $(git diff --name-only); do
            lines=$(git diff HEAD -- "$file" | wc -l)
            if [ "$lines" -gt 50 ]; then
                echo -e "  ${RED}$file${NC} ($lines lines changed)"
            fi
        done
        ;;

    2)
        read -p "File path: " file
        if [ -n "$file" ]; then
            show_diff "$file"
            read -p "Restore this file? (y/N): " restore
            if [ "$restore" = "y" ] || [ "$restore" = "Y" ]; then
                restore_file "$file"
            fi
        fi
        ;;

    3)
        read -p "File path: " file
        if [ -n "$file" ]; then
            restore_file "$file"
        fi
        ;;

    4)
        echo -e "${RED}WARNING: This will restore ALL changed files!${NC}"
        git status --short
        echo ""
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            git reset --hard HEAD
            echo -e "${GREEN}✅ All files restored${NC}"
        else
            echo "Cancelled"
        fi
        ;;

    5)
        echo -e "${YELLOW}Safety tags:${NC}"
        git tag | grep -E '(ninja-safety|pre-ninja-task)' | tail -10 || echo "No safety tags found"
        echo ""
        echo "Recent commits:"
        git log --oneline -5
        ;;

    6)
        echo -e "${YELLOW}Available safety tags:${NC}"
        tags=$(git tag | grep -E '(ninja-safety|pre-ninja-task)' | tail -10)
        if [ -z "$tags" ]; then
            echo "No safety tags found"
            exit 1
        fi
        echo "$tags"
        echo ""
        read -p "Tag name: " tag
        if [ -n "$tag" ]; then
            echo -e "${RED}WARNING: This will reset to tag $tag${NC}"
            git log --oneline "$tag"..HEAD
            echo ""
            read -p "Are you sure? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                git reset --hard "$tag"
                echo -e "${GREEN}✅ Reset to $tag${NC}"
            else
                echo "Cancelled"
            fi
        fi
        ;;

    7)
        echo -e "${BLUE}Recovery Options:${NC}"
        echo ""
        echo "1. ${YELLOW}Restore single file:${NC}"
        echo "   git checkout HEAD -- path/to/file"
        echo ""
        echo "2. ${YELLOW}Restore all files:${NC}"
        echo "   git reset --hard HEAD"
        echo ""
        echo "3. ${YELLOW}Reset to safety tag:${NC}"
        echo "   git reset --hard ninja-safety-TIMESTAMP"
        echo ""
        echo "4. ${YELLOW}View history:${NC}"
        echo "   git reflog"
        echo ""
        echo "5. ${YELLOW}Recover from reflog:${NC}"
        echo "   git reset --hard HEAD@{1}"
        echo ""
        echo "6. ${YELLOW}Find lost commits:${NC}"
        echo "   git fsck --lost-found"
        echo ""
        ;;

    q|Q)
        echo "Goodbye!"
        exit 0
        ;;

    *)
        echo "Invalid choice"
        exit 1
        ;;
esac
