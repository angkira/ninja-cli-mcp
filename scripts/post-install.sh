#!/usr/bin/env bash
# Post-install hook - automatically restart MCP servers after update

set -euo pipefail

echo "🔄 Post-install: Restarting MCP daemons with new code..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Stop all daemons properly (creates proper shutdown, removes PID files)
echo "Stopping all daemons..."
uv run ninja-daemon stop 2>/dev/null || true

sleep 2

# Start all daemons with proper PID file management
# This ensures Claude Code can connect via ninja-daemon connect
echo "Starting all daemons..."
uv run ninja-daemon start

sleep 3

# Verify daemons are running
echo ""
echo "Daemon status:"
uv run ninja-daemon status
