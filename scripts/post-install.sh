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
ninja-mcp daemon stop 2>/dev/null || true

sleep 2

# Start all daemons with proper PID file management
# This ensures MCP clients can connect via ninja-mcp daemon connect
echo "Starting all daemons..."
ninja-mcp daemon start

sleep 3

# Verify daemons are running
echo ""
echo "Daemon status:"
ninja-mcp daemon status
