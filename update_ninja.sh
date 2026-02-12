#!/usr/bin/env bash
#
# Automatic updater for ninja-mcp
# Handles everything: pull, backup, reinstall, migrate, restart, verify
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "======================================================================"
echo "  NINJA-MCP AUTO-UPDATER"
echo "======================================================================"
echo ""
echo "This will:"
echo "  1. Pull latest code"
echo "  2. Backup credentials"
echo "  3. Reinstall package"
echo "  4. Run migration"
echo "  5. Update MCP config"
echo "  6. Restart daemons"
echo "  7. Verify installation"
echo ""
read -p "Continue? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
    echo "Aborted."
    exit 1
fi

# Run the Python auto-updater
cd "$SCRIPT_DIR"
python3 -m ninja_config.auto_updater "$@"
